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

from typing import Any, Dict, List

from langgraph.prebuilt import create_react_agent

from ..guardrail.moderation import check_input, check_output
from .model import get_chat_model
from .tools import B_TOOLS, search

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

    # 0. Input guardrail (reuse A's moderation, read-only)
    gr_in = check_input(query)
    trace.append({"step": "guardrail_input", "blocked": gr_in["blocked"], "flagged": gr_in["flagged"]})
    if gr_in["blocked"]:
        return {
            "clarified": False,
            "blocked": True,
            "answer": gr_in["fallback_message"],
            "max_cosine": 0.0,
            "tool_calls": [],
            "trace": trace,
        }

    # 1. Deterministic gate retrieval
    docs, max_cosine = search(query, top_k=top_k)
    trace.append({"step": "gate_retrieval", "max_cosine": round(max_cosine, 4), "n_docs": len(docs)})

    # 2. Gate: single-shot clarification (no loop)
    if max_cosine < tau:
        trace.append({"step": "clarify", "reason": f"max_cosine {max_cosine:.3f} < tau {tau}"})
        return {
            "clarified": True,
            "blocked": False,
            "answer": CLARIFY_MESSAGE,
            "max_cosine": max_cosine,
            "tool_calls": [],
            "trace": trace,
        }

    # 3. ReAct answer
    agent = create_react_agent(get_chat_model(model_spec), B_TOOLS, prompt=SYSTEM_PROMPT)
    result = agent.invoke({"messages": [("user", query)]})
    messages = result["messages"]

    tool_calls: List[Dict[str, Any]] = []
    for m in messages:
        for tc in (getattr(m, "tool_calls", None) or []):
            tool_calls.append({"name": tc.get("name"), "args": tc.get("args")})

    answer = messages[-1].content if messages else ""
    trace.append({"step": "react", "n_tool_calls": len(tool_calls), "tool_calls": tool_calls})

    # 4. Output guardrail (reuse A's moderation, read-only)
    gr_out = check_output(answer)
    trace.append({"step": "guardrail_output", "blocked": gr_out["blocked"], "flagged": gr_out["flagged"]})
    blocked = gr_out["blocked"]
    if blocked:
        answer = gr_out["fallback_message"]

    return {
        "clarified": False,
        "blocked": blocked,
        "answer": answer,
        "max_cosine": max_cosine,
        "tool_calls": tool_calls,
        "trace": trace,
    }
