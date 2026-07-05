"""Variant B agent: deterministic cosine-gated clarification + ReAct answer.

Flow (single-shot, no clarification loop):
  0. input guardrail (reuse A's moderation): block disallowed input.
  1. gate retrieval (same primitive as A): compute max_cosine.
  2. if max_cosine < tau  -> return ONE clarification question, stop.
  3. else -> run LangGraph ReAct agent (model + tools) -> grounded answer.
  4. output guardrail: block/replace disallowed answer.

Returns a dict with the answer and a trace (guardrail + gate + tool calls) for
the trace-completeness / clarification_rate / guardrail measurements (M2-7R).
"""

import time
from typing import Any, Dict, List

from langgraph.prebuilt import create_react_agent

from ..guardrail.moderation import check_input, check_output
from .model import get_chat_model
from .tools import (
    B_TOOLS,
    get_recorded_retrievals,
    get_recorded_search_events,
    search,
    start_retrieval_recording,
)

SYSTEM_PROMPT = (
    "당신은 한국 소비자분쟁 상담 도우미입니다. "
    "반드시 search_consumer_disputes 도구로 근거를 먼저 검색하세요. "
    "필요하면 domain(law/criteria/case)으로 검색 대상을 좁히고, "
    "조문 원문이 필요하면 get_law_article, 사례 상세는 get_case_detail을 사용하세요. "
    "특정 법령·조문이나 사례를 인용할 때는 verify_citation으로 실제 존재를 확인하고, "
    "확인되지 않은 인용은 답변에 넣지 마세요. "
    "검색된 근거에 기반해 한국어로 간결·정확하게 답하고, 근거가 부족하면 모른다고 하세요."
)

CLARIFY_MESSAGE = (
    "질문이 다소 모호합니다. 어떤 제품/서비스이고 어떤 문제"
    "(환불·교환·배송·계약 등)인지 조금만 더 구체적으로 알려주시겠어요?"
)


def run_b(
    query: str,
    model_spec: str = "frontier",
    tau: float = 0.45,
    top_k: int = 5,
) -> Dict[str, Any]:
    trace: List[Dict[str, Any]] = []
    # M3-5: per-search retrieval events (gate + tool). instrumentation only.
    retrieval_records: List[Dict[str, Any]] = []

    # 0. Input guardrail (reuse A's moderation, read-only)
    _t = time.perf_counter()
    gr_in = check_input(query)
    trace.append({"step": "guardrail_input", "blocked": gr_in["blocked"], "flagged": gr_in["flagged"], "categories": [c for c, v in (gr_in.get("categories") or {}).items() if v], "duration_ms": (time.perf_counter() - _t) * 1000})
    if gr_in["blocked"]:
        return {
            "clarified": False,
            "blocked": True,
            "answer": gr_in["fallback_message"],
            "max_cosine": 0.0,
            "tool_calls": [],
            "retrieved_chunk_ids": [],
            "trace": trace,
            "retrieval_records": retrieval_records,
        }

    # 1. Deterministic gate retrieval
    _t = time.perf_counter()
    docs, max_cosine = search(query, top_k=top_k)
    trace.append({"step": "gate_retrieval", "max_cosine": round(max_cosine, 4), "n_docs": len(docs), "duration_ms": (time.perf_counter() - _t) * 1000})
    retrieval_records.append({
        "source": "gate",
        "query": query,
        "domain": None,
        "top_k": top_k,
        "docs": [{"chunk_id": d["chunk_id"], "cosine": d["cosine"]} for d in docs],
    })

    # 2. Gate: single-shot clarification (no loop)
    if max_cosine < tau:
        trace.append({"step": "clarify", "reason": f"max_cosine {max_cosine:.3f} < tau {tau}", "duration_ms": 0.0})
        return {
            "clarified": True,
            "blocked": False,
            "answer": CLARIFY_MESSAGE,
            "max_cosine": max_cosine,
            "tool_calls": [],
            "retrieved_chunk_ids": [],
            "trace": trace,
            "retrieval_records": retrieval_records,
        }

    # 3. ReAct answer (record only the agent's tool retrievals, not the gate)
    _t = time.perf_counter()
    start_retrieval_recording()
    chat_model = get_chat_model(model_spec)
    agent = create_react_agent(chat_model, B_TOOLS, prompt=SYSTEM_PROMPT)
    try:
        result = agent.invoke({"messages": [("user", query)]})
        messages = result["messages"]
    except Exception as react_err:
        # #68: ReAct can overflow max_model_len(8192) as accumulated tool context
        # grows -> the model call 400s (prompt too long) before any answer, which
        # otherwise 500s the request. Degrade to the empty-answer fallback below
        # (synthesize from the gate-retrieved docs) instead of a hard failure.
        messages = []
        trace.append({"step": "react_error", "error": str(react_err)[:300]})

    tool_calls: List[Dict[str, Any]] = []
    for m in messages:
        for tc in (getattr(m, "tool_calls", None) or []):
            tool_calls.append({"name": tc.get("name"), "args": tc.get("args")})

    # Dedupe recorded retrievals (rank order, first occurrence)
    retrieved_chunk_ids: List[str] = []
    seen = set()
    for cid in get_recorded_retrievals():
        if cid not in seen:
            seen.add(cid)
            retrieved_chunk_ids.append(cid)

    # M3-5: per-search tool events (each search_consumer_disputes call)
    for ev in get_recorded_search_events():
        retrieval_records.append({"source": "tool", **ev})

    # M3-6: aggregate react LLM usage (model + summed tokens + n_calls)
    prompt_t = completion_t = total_t = n_llm = 0
    for m in messages:
        um = getattr(m, "usage_metadata", None)
        if um:
            prompt_t += um.get("input_tokens", 0) or 0
            completion_t += um.get("output_tokens", 0) or 0
            total_t += um.get("total_tokens", 0) or 0
            n_llm += 1
    llm_summary = {
        "model": getattr(chat_model, "model_name", None) or getattr(chat_model, "model", None),
        "prompt_tokens": prompt_t,
        "completion_tokens": completion_t,
        "total_tokens": total_t,
        "n_calls": n_llm,
        "status": "ok",
    }

    # M3-9: distill ReAct trajectory (AIMessage reasoning+tool_calls, ToolMessage 관찰).
    # human(query) 제외. content는 절단(용량). answer/검색 무변경(읽기만).
    _PREVIEW = 500
    protocol_messages: List[Dict[str, Any]] = []
    for m in messages:
        mtype = getattr(m, "type", None)
        if mtype == "ai":
            tcs = [
                {"name": tc.get("name"), "args": tc.get("args")}
                for tc in (getattr(m, "tool_calls", None) or [])
            ]
            content = m.content if isinstance(m.content, str) else str(m.content)
            protocol_messages.append(
                {"kind": "ai", "tool_calls": tcs, "content": content[:_PREVIEW]}
            )
        elif mtype == "tool":
            protocol_messages.append(
                {
                    "kind": "tool",
                    "name": getattr(m, "name", None),
                    "content": str(m.content)[:_PREVIEW],
                }
            )

    answer = messages[-1].content if messages else ""
    trace.append({
        "step": "react",
        "n_tool_calls": len(tool_calls),
        "tool_calls": tool_calls,
        "n_retrieved": len(retrieved_chunk_ids),
        "duration_ms": (time.perf_counter() - _t) * 1000,
    })

    # #68: EXAONE(추론 모델)+ReAct 다단계로 누적 컨텍스트가 max_model_len(8192)을 채우면
    # 최종 답변 단계가 잘려 content가 빈 채로 온다(단일 호출은 정상 — probe 확인). 빈 답변이면
    # 수집한 tool 검색 근거만으로 '짧은' 프롬프트로 1회 재합성해 컨텍스트를 리셋하고 답을 확보한다.
    if not (answer or "").strip():
        _t = time.perf_counter()
        tool_context = "\n\n".join(
            str(m.content)[:1200] for m in messages if getattr(m, "type", None) == "tool"
        )[:6000]
        if not tool_context.strip():
            # No tool observations (e.g. ReAct invoke overflowed) -> use gate docs.
            tool_context = "\n\n".join((d.get("text") or "")[:1200] for d in docs)[:6000]
        synth_answer = ""
        try:
            synth = chat_model.invoke([
                ("system", SYSTEM_PROMPT),
                ("user",
                 "아래 검색 근거만 사용해 질문에 한국어로 간결·정확하게 답하세요. "
                 "도구를 더 호출하지 말고 최종 답변만 작성하세요. 근거가 부족하면 모른다고 하세요.\n\n"
                 f"[검색 근거]\n{tool_context}\n\n[질문]\n{query}"),
            ])
            synth_answer = synth.content if isinstance(synth.content, str) else str(synth.content)
            um = getattr(synth, "usage_metadata", None)
            if um:
                llm_summary["prompt_tokens"] += um.get("input_tokens", 0) or 0
                llm_summary["completion_tokens"] += um.get("output_tokens", 0) or 0
                llm_summary["total_tokens"] += um.get("total_tokens", 0) or 0
                llm_summary["n_calls"] += 1
        except Exception as e:
            trace.append({"step": "fallback_synthesis_error", "error": str(e)})
        if (synth_answer or "").strip():
            answer = synth_answer
        trace.append({
            "step": "fallback_synthesis",
            "reason": "empty ReAct answer (context exhaustion)",
            "recovered": bool((synth_answer or "").strip()),
            "answer_len": len(answer or ""),
            "duration_ms": (time.perf_counter() - _t) * 1000,
        })

    # 4. Output guardrail (reuse A's moderation, read-only)
    _t = time.perf_counter()
    gr_out = check_output(answer)
    trace.append({"step": "guardrail_output", "blocked": gr_out["blocked"], "flagged": gr_out["flagged"], "categories": [c for c, v in (gr_out.get("categories") or {}).items() if v], "duration_ms": (time.perf_counter() - _t) * 1000})
    blocked = gr_out["blocked"]
    if blocked:
        answer = gr_out["fallback_message"]

    return {
        "clarified": False,
        "blocked": blocked,
        "answer": answer,
        "max_cosine": max_cosine,
        "tool_calls": tool_calls,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "trace": trace,
        "retrieval_records": retrieval_records,
        "llm_summary": llm_summary,
        "protocol_messages": protocol_messages,
    }
