"""Variant B agent: deterministic cosine-gated clarification + ReAct answer.

Flow (single-shot, no clarification loop):
  1. gate retrieval (same primitive as A): compute max_cosine.
  2. if max_cosine < tau  -> return ONE clarification question, stop.
  3. else -> run LangGraph ReAct agent (model + search tool) -> grounded answer.

Returns a dict with the answer and a trace (gate result + tool calls) for the
trace-completeness / clarification_rate measurements (M2-7R).
"""

from typing import Any, Dict, List

from langgraph.prebuilt import create_react_agent

from .model import get_chat_model
from .tools import search, search_consumer_disputes

SYSTEM_PROMPT = (
    "당신은 한국 소비자분쟁 상담 도우미입니다. "
    "반드시 search_consumer_disputes 도구로 근거를 먼저 검색한 뒤, "
    "검색된 근거에 기반해 한국어로 간결하고 정확하게 답하세요. "
    "근거가 부족하면 모른다고 답하고 추측하지 마세요."
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

    # 1. Deterministic gate retrieval
    docs, max_cosine = search(query, top_k=top_k)
    trace.append({"step": "gate_retrieval", "max_cosine": round(max_cosine, 4), "n_docs": len(docs)})

    # 2. Gate: single-shot clarification (no loop)
    if max_cosine < tau:
        trace.append({"step": "clarify", "reason": f"max_cosine {max_cosine:.3f} < tau {tau}"})
        return {
            "clarified": True,
            "answer": CLARIFY_MESSAGE,
            "max_cosine": max_cosine,
            "tool_calls": [],
            "trace": trace,
        }

    # 3. ReAct answer
    agent = create_react_agent(get_chat_model(model_spec), [search_consumer_disputes], prompt=SYSTEM_PROMPT)
    result = agent.invoke({"messages": [("user", query)]})
    messages = result["messages"]

    tool_calls: List[Dict[str, Any]] = []
    for m in messages:
        for tc in (getattr(m, "tool_calls", None) or []):
            tool_calls.append({"name": tc.get("name"), "args": tc.get("args")})

    answer = messages[-1].content if messages else ""
    trace.append({"step": "react", "n_tool_calls": len(tool_calls), "tool_calls": tool_calls})

    return {
        "clarified": False,
        "answer": answer,
        "max_cosine": max_cosine,
        "tool_calls": tool_calls,
        "trace": trace,
    }
