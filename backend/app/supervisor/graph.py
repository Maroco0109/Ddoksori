"""
똑소리 프로젝트 - LangGraph 그래프 엔트리포인트

작성일: 2026-01-14
최종 수정: 2026-01-27 (Phase 7: supervisor 모듈로 이름 변경, Legacy 제거)

[역할]
MAS Supervisor 그래프 엔트리포인트 및 공통 유틸리티를 제공합니다.

[그래프 파일 구조]
- graph.py (이 파일): 엔트리포인트 및 공통 유틸리티
- graph_mas.py: MAS Supervisor 그래프 (현재 운영)
- (archived) graph_legacy.py: Legacy/Unified 그래프 → _archive/orchestrator/로 이동됨

[주요 함수]
- get_graph_for_chat_type(): MAS Supervisor 그래프 반환
- _create_timed_node(): 노드 타이밍 래퍼
"""

import inspect
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from langchain_core.runnables import RunnableConfig

from .state import ChatState, TraceEntry

logger = logging.getLogger(__name__)

# ============================================================================
# 공통 상수 및 유틸리티
# ============================================================================

NODE_TIMINGS_KEY = "_node_timings"
SIMILARITY_THRESHOLD_HIGH = 0.55

# 노드별 스냅샷 대상 필드 정의
NODE_SNAPSHOT_FIELDS = {
    "query_analysis": {
        "input": ["user_query", "onboarding", "chat_type"],
        "output": ["query_analysis", "mode"],
    },
    "retrieval": {
        "input": ["user_query", "query_analysis", "onboarding"],
        "output": ["retrieval", "sources"],
    },
    "react_think": {
        "input": ["user_query", "retrieval", "react_steps", "iteration_count"],
        "output": ["last_thought", "last_action", "should_continue", "iteration_count"],
    },
    "react_act": {
        "input": ["last_action", "last_thought"],
        "output": ["retrieval", "tool_result"],
    },
    "generation": {
        "input": ["user_query", "retrieval", "query_analysis", "react_steps"],
        "output": ["final_answer", "draft_answer"],
    },
    "review": {
        "input": ["final_answer", "draft_answer", "retrieval"],
        "output": ["review", "retry_count"],
    },
    "input_guardrail": {
        "input": ["user_query"],
        "output": ["guardrail_blocked", "guardrail_type"],
    },
    "output_guardrail": {
        "input": ["final_answer"],
        "output": ["guardrail_blocked", "final_answer"],
    },
}


def _snapshot_state(state: Dict[str, Any], fields: list) -> Dict[str, Any]:
    """상태에서 지정된 필드만 추출하여 스냅샷 생성"""
    snapshot = {}
    for field in fields:
        if field in state:
            value = state[field]
            # 직렬화 가능하도록 처리
            if hasattr(value, "__dict__"):
                snapshot[field] = str(value)[:500]  # 객체는 문자열로 변환 (500자 제한)
            elif isinstance(value, (list, dict)):
                try:
                    import json

                    serialized = json.dumps(value, ensure_ascii=False, default=str)
                    snapshot[field] = json.loads(serialized[:2000])  # 2KB 제한
                except Exception as e:
                    logger.debug(
                        f"[StateSnapshot] Serialization fallback for {field}: {e}"
                    )
                    snapshot[field] = str(value)[:500]
            else:
                snapshot[field] = value
    return snapshot


def _detect_state_changes(input_state: Dict[str, Any], output: Dict[str, Any]) -> list:
    """출력에서 변경/추가된 필드 목록 반환"""
    changes = []
    for key in output.keys():
        if key.startswith("_"):
            continue  # 내부 필드 제외
        if key not in input_state:
            changes.append(f"+{key}")  # 새로 추가된 필드
        elif input_state.get(key) != output.get(key):
            changes.append(f"~{key}")  # 변경된 필드
    return changes


AGENT_TRACE_KEY = "_agent_trace_entries"


def summarize_node_output(
    node_name: str, result: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """노드 출력을 트레이스 로깅용 축약 프로토콜 요약으로 변환.

    각 노드 타입별로 핵심 메트릭만 추출합니다.
    원본 텍스트는 포함하지 않습니다 (PII 방지).
    """
    if node_name == "cache_check":
        return {"cache_hit": bool(result.get("_cache_hit"))}

    if node_name == "cache_response":
        answer = result.get("final_answer", "")
        return {
            "final_answer_preview": (
                (answer[:100] + "...") if len(answer or "") > 100 else answer
            )
        }

    if node_name in ("input_guardrail", "output_guardrail"):
        return {
            "guardrail_blocked": result.get("guardrail_blocked", False),
            "guardrail_type": result.get("guardrail_type"),
        }

    if node_name == "supervisor":
        sup = result.get("supervisor") or {}
        reasoning = sup.get("reasoning", "")
        summary = {
            "current_phase": sup.get("current_phase"),
            "next_agent": sup.get("next_agent"),
            "iteration_count": sup.get("iteration_count", 0),
            "reasoning_preview": (
                (reasoning[:200] + "...") if len(reasoning or "") > 200 else reasoning
            ),
        }
        # M8(A-hub): LLM 라우팅 계측을 요약에 노출 (A에는 routing_meta 없음).
        routing_meta = sup.get("routing_meta")
        if routing_meta:
            summary["routing_meta"] = routing_meta
        return summary

    if node_name == "query_analysis":
        qa = result.get("query_analysis") or {}
        return {
            "intent": qa.get("intent"),
            "retriever_types": qa.get("retriever_types", []),
            "keyword_count": len(qa.get("keywords", [])),
            "expanded_query_count": len(result.get("expanded_queries", [])),
        }

    if node_name.startswith("retrieval_") and node_name != "retrieval_merge":
        # 개별 retrieval agent: result는 {'individual_retrieval_results': [individual_result]}
        results_list = result.get("individual_retrieval_results", [])
        if results_list:
            ir = results_list[0]
            return {
                "source": ir.get("source"),
                "document_count": len(ir.get("documents", [])),
                "max_similarity": ir.get("max_similarity", 0.0),
                "search_time_ms": round(ir.get("search_time_ms", 0), 1),
                "has_error": bool(ir.get("error")),
            }
        return {"source": node_name.replace("retrieval_", ""), "document_count": 0}

    if node_name == "retrieval_merge":
        retrieval = result.get("retrieval") or {}
        sections = {}
        for section_key in (
            "law_results",
            "criteria_results",
            "dispute_results",
            "counsel_results",
        ):
            items = retrieval.get(section_key, [])
            sections[section_key] = len(items) if isinstance(items, list) else 0
        return {
            "total_documents": sum(sections.values()),
            "sections": sections,
        }

    if node_name == "generation":
        answer = result.get("draft_answer") or result.get("final_answer") or ""
        return {
            "has_sufficient_evidence": result.get("has_sufficient_evidence", True),
            "answer_length": len(answer),
            "cited_case_count": len(result.get("cited_cases", [])),
        }

    if node_name == "review":
        review = result.get("review") or {}
        return {
            "passed": review.get("passed", True),
            "violation_count": len(review.get("violations", [])),
        }

    if node_name == "ask_clarification":
        return {
            "clarifying_question_count": len(result.get("clarifying_questions", [])),
        }

    return None


def build_pipeline_summary(
    trace_entries: List[TraceEntry],
    total_duration_ms: float,
) -> Dict[str, Any]:
    """트레이스 엔트리로부터 구조화된 파이프라인 실행 요약을 빌드.

    엔트리는 timestamp 기준으로 정렬하여 실행 순서를 재구성합니다.
    병렬 브랜치(retrieval agent)는 timestamp 순서로 나타납니다.
    """
    sorted_entries = sorted(trace_entries, key=lambda e: e["timestamp"])
    return {
        "total_duration_ms": round(total_duration_ms, 2),
        "node_count": len(sorted_entries),
        "node_sequence": [e["node_name"] for e in sorted_entries],
        "per_node": [
            {
                "seq": idx,
                "node": e["node_name"],
                "duration_ms": round(e["duration_ms"], 2),
                "summary": e.get("protocol_summary"),
            }
            for idx, e in enumerate(sorted_entries)
        ],
    }


def _create_timed_node(node_fn: Callable, node_name: str) -> Callable:
    """노드 함수를 감싸서 실행 시간과 I/O 스냅샷을 기록하는 래퍼 생성

    async 노드와 sync 노드 모두 지원합니다.
    async 노드는 RunnableConfig 파라미터를 받아 스트리밍 모드를 감지할 수 있습니다.
    """
    if inspect.iscoroutinefunction(node_fn):
        # 노드 함수가 config 파라미터를 받는지 래핑 시점에 한번만 확인
        _sig = inspect.signature(node_fn)
        _accepts_config = len(_sig.parameters) >= 2

        # Async node wrapper
        async def async_timed_wrapper(
            state: ChatState, config: RunnableConfig = None
        ) -> Dict[str, Any]:
            start_time = time.time()
            logger.info(f"[NODE START] {node_name}")

            # 입력 스냅샷 수집
            snapshot_config = NODE_SNAPSHOT_FIELDS.get(
                node_name, {"input": [], "output": []}
            )
            input_snapshot = _snapshot_state(dict(state), snapshot_config["input"])

            result = await (
                node_fn(state, config) if _accepts_config else node_fn(state)
            )

            end_time = time.time()
            duration_ms = round((end_time - start_time) * 1000, 2)
            logger.info(f"[NODE END] {node_name} - {duration_ms}ms")

            # 출력 스냅샷 수집
            output_snapshot = _snapshot_state(result, snapshot_config["output"])

            # 상태 변경 감지
            state_changes = _detect_state_changes(dict(state), result)

            existing_timings = state.get(NODE_TIMINGS_KEY)
            timings = dict(existing_timings) if existing_timings else {}
            timings[node_name] = {
                "start": start_time,
                "end": end_time,
                "duration_ms": duration_ms,
                "input_snapshot": input_snapshot,
                "output_snapshot": output_snapshot,
                "state_changes": state_changes,
            }
            result[NODE_TIMINGS_KEY] = timings

            # 트레이스 엔트리 추가 (operator.add용 단일 요소 리스트)
            trace_entry: TraceEntry = {
                "node_name": node_name,
                "timestamp": start_time,
                "duration_ms": duration_ms,
                "protocol_summary": summarize_node_output(node_name, result),
                "metadata": None,
            }
            result[AGENT_TRACE_KEY] = [trace_entry]

            return result

        return async_timed_wrapper
    else:
        # Sync node wrapper (unchanged)
        def timed_wrapper(state: ChatState) -> Dict[str, Any]:
            start_time = time.time()
            logger.info(f"[NODE START] {node_name}")

            # 입력 스냅샷 수집
            snapshot_config = NODE_SNAPSHOT_FIELDS.get(
                node_name, {"input": [], "output": []}
            )
            input_snapshot = _snapshot_state(dict(state), snapshot_config["input"])

            result = node_fn(state)

            end_time = time.time()
            duration_ms = round((end_time - start_time) * 1000, 2)
            logger.info(f"[NODE END] {node_name} - {duration_ms}ms")

            # 출력 스냅샷 수집
            output_snapshot = _snapshot_state(result, snapshot_config["output"])

            # 상태 변경 감지
            state_changes = _detect_state_changes(dict(state), result)

            existing_timings = state.get(NODE_TIMINGS_KEY)
            timings = dict(existing_timings) if existing_timings else {}
            timings[node_name] = {
                "start": start_time,
                "end": end_time,
                "duration_ms": duration_ms,
                "input_snapshot": input_snapshot,
                "output_snapshot": output_snapshot,
                "state_changes": state_changes,
            }
            result[NODE_TIMINGS_KEY] = timings

            # 트레이스 엔트리 추가 (operator.add용 단일 요소 리스트)
            trace_entry: TraceEntry = {
                "node_name": node_name,
                "timestamp": start_time,
                "duration_ms": duration_ms,
                "protocol_summary": summarize_node_output(node_name, result),
                "metadata": None,
            }
            result[AGENT_TRACE_KEY] = [trace_entry]

            return result

        return timed_wrapper


# ============================================================================
# 그래프 선택
# ============================================================================


def get_graph_for_chat_type(chat_type: str, session_id: str = None):
    """
    MAS Supervisor 그래프 반환

    chat_type별 동작 차이는 state 초기화 시 설정:
    - general: max_iterations=1, review 자동 통과
    - dispute: max_iterations=2, 전체 review 수행

    Args:
        chat_type: 'dispute' 또는 'general'
        session_id: (사용되지 않음, 하위 호환성 유지용)

    Returns:
        컴파일된 MAS Supervisor LangGraph 그래프
    """
    from .graph_mas import get_mas_supervisor_graph

    logger.info(f"[GraphSelect] Using MAS Supervisor graph (chat_type={chat_type})")
    return get_mas_supervisor_graph()


# ============================================================================
# 그래프 리셋 (테스트용)
# ============================================================================


def reset_graph():
    """MAS 그래프 싱글톤 리셋"""
    from .graph_mas import reset_mas_graph

    reset_mas_graph()
