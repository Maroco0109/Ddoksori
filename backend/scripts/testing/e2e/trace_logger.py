"""
E2E Trace Logger — 에이전트별 I/O 추적 + 프로토콜 준수 검증

에이전트 간 데이터 전달 과정을 JSON 로그로 저장하고,
agent-protocols.md의 TypedDict 스펙 대비 실제 데이터 일치 여부를 검증합니다.

사용법:
    from trace_logger import E2ETraceLogger

    logger = E2ETraceLogger(test_name="dispute_full_pipeline")
    logger.capture_from_state(final_state)
    logger.save()
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# 프로토콜 필수 키 정의 (protocols.py 기반)
# ============================================================

PROTOCOL_REQUIRED_KEYS = {
    "query_analysis": {
        "intent", "original_query", "expanded_queries",
        "keywords", "retriever_types", "needs_clarification", "missing_fields",
    },
    "retrieval": {
        "source", "documents", "max_similarity",
        "avg_similarity", "search_time_ms",
    },
    "generation": {
        "draft_answer", "claim_evidence_map", "cited_cases",
        "has_sufficient_evidence", "generation_time_ms",
    },
    "review": {
        "passed", "violations", "final_answer", "review_time_ms",
    },
}


# ============================================================
# Trace 데이터 클래스
# ============================================================

@dataclass
class AgentTraceEntry:
    """개별 에이전트 실행 추적."""
    agent_name: str
    phase: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    duration_ms: float
    protocol_expected_keys: List[str]
    protocol_actual_keys: List[str]
    protocol_compliant: bool
    protocol_gaps: List[str]


@dataclass
class E2ETraceLog:
    """전체 E2E 실행 추적."""
    trace_id: str
    test_name: str
    query: str
    chat_type: str
    timestamp: str
    agent_traces: List[AgentTraceEntry] = field(default_factory=list)
    supervisor_decisions: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: Optional[str] = None
    total_time_ms: float = 0.0
    protocol_summary: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Trace Logger
# ============================================================

class E2ETraceLogger:
    """
    E2E 파이프라인 실행 추적 로거.

    최종 state에서 _node_timings, individual_retrieval_results, supervisor 등을
    추출하여 에이전트별 추적 정보를 구성합니다.
    """

    def __init__(self, test_name: str, query: str = "", chat_type: str = "dispute"):
        self.trace = E2ETraceLog(
            trace_id=uuid.uuid4().hex[:12],
            test_name=test_name,
            query=query,
            chat_type=chat_type,
            timestamp=datetime.now().isoformat(),
        )

    def capture_from_state(self, final_state: Dict[str, Any]) -> E2ETraceLog:
        """
        LangGraph 최종 state에서 추적 데이터를 추출합니다.

        추출 소스:
        1. _node_timings → query_analysis, generation, review, guardrails
        2. individual_retrieval_results → retrieval_law, retrieval_criteria, retrieval_case
        3. supervisor → Supervisor 결정 내역
        """
        import time
        start = time.time()

        self._capture_node_timings(final_state)
        self._capture_retrieval_results(final_state)
        self._capture_supervisor_decisions(final_state)
        self._capture_final_answer(final_state)

        self.trace.total_time_ms = self._compute_total_time(final_state)
        self.trace.protocol_summary = self._compute_protocol_summary()

        return self.trace

    def save(self, base_dir: str = None) -> str:
        """
        추적 로그를 JSON 파일로 저장합니다.

        Returns:
            저장된 파일 경로
        """
        if base_dir is None:
            base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "logs", "e2e_trace",
            )

        date_dir = os.path.join(base_dir, datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(date_dir, exist_ok=True)

        filename = f"{self.trace.test_name}_{self.trace.trace_id}.json"
        filepath = os.path.join(date_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                asdict(self.trace),
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        return filepath

    # -------------------------------------------------------
    # 내부 추출 메서드
    # -------------------------------------------------------

    def _capture_node_timings(self, state: Dict[str, Any]) -> None:
        """_node_timings에서 query_analysis, generation, review 추출."""
        timings = state.get("_node_timings", {})

        phase_map = {
            "input_guardrail": "guardrail",
            "query_analysis": "analyzing",
            "generation": "drafting",
            "review": "reviewing",
            "output_guardrail": "guardrail",
        }

        for node_name, timing_data in timings.items():
            if node_name not in phase_map:
                continue

            protocol_key = self._get_protocol_key(node_name)
            expected_keys = sorted(PROTOCOL_REQUIRED_KEYS.get(protocol_key, set()))

            output_snapshot = timing_data.get("output_snapshot", {})
            # For query_analysis, the actual data is nested under the key
            actual_output = self._extract_agent_output(node_name, output_snapshot, state)
            actual_keys = sorted(actual_output.keys()) if isinstance(actual_output, dict) else []

            expected_set = set(expected_keys)
            actual_set = set(actual_keys)
            missing = sorted(expected_set - actual_set)
            extra = sorted(actual_set - expected_set)
            gaps = [f"-{k}" for k in missing] + [f"+{k}" for k in extra]

            entry = AgentTraceEntry(
                agent_name=node_name,
                phase=phase_map[node_name],
                input_data=timing_data.get("input_snapshot", {}),
                output_data=_safe_serialize(actual_output),
                duration_ms=timing_data.get("duration_ms", 0.0),
                protocol_expected_keys=expected_keys,
                protocol_actual_keys=actual_keys,
                protocol_compliant=len(missing) == 0,
                protocol_gaps=gaps,
            )
            self.trace.agent_traces.append(entry)

    def _capture_retrieval_results(self, state: Dict[str, Any]) -> None:
        """individual_retrieval_results에서 retrieval agent 결과 추출."""
        results = state.get("individual_retrieval_results", [])

        expected_keys = sorted(PROTOCOL_REQUIRED_KEYS.get("retrieval", set()))
        expected_set = set(expected_keys)

        for result in results:
            source = result.get("source", "unknown")
            agent_name = f"retrieval_{source}"
            actual_keys = sorted(result.keys())
            actual_set = set(actual_keys)

            missing = sorted(expected_set - actual_set)
            extra = sorted(actual_set - expected_set)
            gaps = [f"-{k}" for k in missing] + [f"+{k}" for k in extra]

            entry = AgentTraceEntry(
                agent_name=agent_name,
                phase="retrieving",
                input_data={
                    "expanded_queries": state.get("query_analysis", {}).get("expanded_queries", []),
                    "top_k": 5,  # Supervisor 하드코딩 값
                },
                output_data=_safe_serialize(result),
                duration_ms=result.get("search_time_ms", 0.0),
                protocol_expected_keys=expected_keys,
                protocol_actual_keys=actual_keys,
                protocol_compliant=len(missing) == 0,
                protocol_gaps=gaps,
            )
            self.trace.agent_traces.append(entry)

    def _capture_supervisor_decisions(self, state: Dict[str, Any]) -> None:
        """Supervisor 상태에서 결정 내역 추출."""
        supervisor_state = state.get("supervisor", {})
        if not supervisor_state:
            return

        decisions = []

        # agent_messages에서 결정 내역 추출
        agent_messages = supervisor_state.get("agent_messages", [])
        for msg in agent_messages:
            if isinstance(msg, dict):
                decisions.append(msg)
            elif hasattr(msg, "__dict__"):
                decisions.append({
                    "agent": getattr(msg, "agent", "unknown"),
                    "status": getattr(msg, "status", "unknown"),
                    "summary": getattr(msg, "summary", ""),
                })

        # 기본 supervisor 메타데이터
        decisions.append({
            "_meta": {
                "current_phase": supervisor_state.get("current_phase", "unknown"),
                "iteration_count": supervisor_state.get("iteration_count", 0),
                "next_agent": supervisor_state.get("next_agent", None),
                "reasoning": supervisor_state.get("reasoning", ""),
            }
        })

        self.trace.supervisor_decisions = decisions

    def _capture_final_answer(self, state: Dict[str, Any]) -> None:
        """최종 답변 추출."""
        self.trace.final_answer = state.get("final_answer") or state.get("draft_answer")

    def _compute_total_time(self, state: Dict[str, Any]) -> float:
        """전체 소요 시간 계산."""
        timings = state.get("_node_timings", {})
        if not timings:
            return sum(t.duration_ms for t in self.trace.agent_traces)

        starts = [t.get("start", float("inf")) for t in timings.values()]
        ends = [t.get("end", 0) for t in timings.values()]

        if starts and ends:
            return round((max(ends) - min(starts)) * 1000, 2)
        return 0.0

    def _compute_protocol_summary(self) -> Dict[str, Any]:
        """프로토콜 준수율 요약."""
        total = len(self.trace.agent_traces)
        compliant = sum(1 for t in self.trace.agent_traces if t.protocol_compliant)

        per_agent = {}
        for t in self.trace.agent_traces:
            per_agent[t.agent_name] = {
                "compliant": t.protocol_compliant,
                "gaps": t.protocol_gaps,
            }

        return {
            "total_agents": total,
            "compliant_agents": compliant,
            "compliance_rate": f"{compliant}/{total}" if total else "N/A",
            "per_agent": per_agent,
        }

    def _get_protocol_key(self, node_name: str) -> str:
        """노드 이름 → 프로토콜 키 매핑."""
        mapping = {
            "query_analysis": "query_analysis",
            "generation": "generation",
            "review": "review",
        }
        return mapping.get(node_name, node_name)

    def _extract_agent_output(
        self, node_name: str, output_snapshot: Dict, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """노드별 실제 출력 데이터 추출."""
        if node_name == "query_analysis":
            # query_analysis 출력은 state['query_analysis'] dict에 저장됨
            return state.get("query_analysis", output_snapshot)
        elif node_name == "generation":
            return {
                "draft_answer": state.get("draft_answer", ""),
                "claim_evidence_map": state.get("claim_evidence_map", []),
                "cited_cases": state.get("cited_cases", []),
                "has_sufficient_evidence": state.get("has_sufficient_evidence", False),
                "generation_time_ms": state.get("_node_timings", {}).get("generation", {}).get("duration_ms", 0),
            }
        elif node_name == "review":
            review_data = state.get("review", {})
            if isinstance(review_data, dict):
                return review_data
            return {
                "passed": state.get("review_passed", None),
                "violations": state.get("violations", []),
                "final_answer": state.get("final_answer", ""),
                "review_time_ms": state.get("_node_timings", {}).get("review", {}).get("duration_ms", 0),
            }
        return output_snapshot


# ============================================================
# 유틸리티
# ============================================================

def _safe_serialize(data: Any, max_str_len: int = 2000) -> Any:
    """JSON 직렬화 안전 변환."""
    if isinstance(data, dict):
        return {k: _safe_serialize(v, max_str_len) for k, v in data.items()}
    elif isinstance(data, list):
        return [_safe_serialize(item, max_str_len) for item in data[:50]]  # 최대 50 항목
    elif isinstance(data, str):
        return data[:max_str_len]
    elif isinstance(data, (int, float, bool, type(None))):
        return data
    else:
        return str(data)[:max_str_len]
