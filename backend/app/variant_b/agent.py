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
    trace.append({"step": "guardrail_input", "blocked": gr_in["blocked"], "flagged": gr_in["flagged"], "duration_ms": (time.perf_counter() - _t) * 1000})
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
    result = agent.invoke({"messages": [("user", query)]})
    messages = result["messages"]

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

    answer = messages[-1].content if messages else ""
    trace.append({
        "step": "react",
        "n_tool_calls": len(tool_calls),
        "tool_calls": tool_calls,
        "n_retrieved": len(retrieved_chunk_ids),
        "duration_ms": (time.perf_counter() - _t) * 1000,
    })

    # 4. Output guardrail (reuse A's moderation, read-only)
    _t = time.perf_counter()
    gr_out = check_output(answer)
    trace.append({"step": "guardrail_output", "blocked": gr_out["blocked"], "flagged": gr_out["flagged"], "duration_ms": (time.perf_counter() - _t) * 1000})
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
    }
