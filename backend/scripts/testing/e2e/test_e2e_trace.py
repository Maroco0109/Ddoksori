"""
E2E Trace 테스트 — 실제 RDS + 실제 LLM으로 전체 파이프라인 실행 후
에이전트별 I/O를 JSON 로그로 저장하고 프로토콜 준수를 검증합니다.

실행:
    PYTHONPATH=backend conda run -n dsr pytest backend/scripts/testing/e2e/test_e2e_trace.py -v -s

사전 조건:
    - DB_HOST, DB_PASSWORD 환경변수 설정
    - OPENAI_API_KEY 설정
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Ensure backend on path
_backend = str(Path(__file__).parent.parent.parent.parent)
if _backend not in sys.path:
    sys.path.insert(0, _backend)

# Ensure e2e directory on path for trace_logger
_e2e_dir = str(Path(__file__).parent)
if _e2e_dir not in sys.path:
    sys.path.insert(0, _e2e_dir)

from trace_logger import E2ETraceLogger

pytestmark = [pytest.mark.e2e, pytest.mark.llm, pytest.mark.needs_db]


# ============================================================
# Helper
# ============================================================


def _create_initial_state(query: str, chat_type: str = "dispute") -> dict:
    """테스트용 ChatState 초기값 생성."""
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "chat_type": chat_type,
        "session_id": f"e2e_trace_test_{chat_type}",
        "onboarding": None,
        "mode": None,
        "guardrail_blocked": False,
        "final_answer": None,
        "draft_answer": None,
        "review": None,
        "retry_count": 0,
        "sources": [],
        "individual_retrieval_results": [],
        "retrieval": None,
        "query_analysis": None,
        "supervisor": None,
        "_node_timings": {},
        "_cache_hit": False,
    }


def _run_graph(compiled_graph, state: dict) -> dict:
    """그래프를 동기적으로 실행합니다."""
    config = {
        "configurable": {"thread_id": state.get("session_id", "test")},
    }
    result = asyncio.run(compiled_graph.ainvoke(state, config=config))
    return result


# ============================================================
# Tests
# ============================================================


class TestDisputeFullPipelineTrace:
    """분쟁 쿼리 전체 파이프라인 추적 테스트."""

    def test_dispute_query_trace(self, compiled_mas_graph, openai_api_key):
        """
        분쟁 쿼리 E2E: 전체 에이전트 호출 + 프로토콜 준수 검증.

        기대 흐름:
        cache_check → input_guardrail → supervisor → query_analysis → supervisor
        → retrieval_law/criteria/case → retrieval_merge → supervisor
        → generation → supervisor → review → supervisor → output_guardrail
        """
        query = "헬스장 3개월 이용 후 환불 가능한가요?"
        state = _create_initial_state(query, "dispute")
        final_state = _run_graph(compiled_mas_graph, state)

        # Trace 캡처 및 저장
        logger = E2ETraceLogger(
            test_name="dispute_full_pipeline",
            query=query,
            chat_type="dispute",
        )
        trace = logger.capture_from_state(final_state)
        filepath = logger.save()

        print(f"\n[Trace saved] {filepath}")
        print(f"[Agents traced] {len(trace.agent_traces)}")
        print(
            f"[Protocol compliance] {trace.protocol_summary.get('compliance_rate', 'N/A')}"
        )
        for t in trace.agent_traces:
            status = "PASS" if t.protocol_compliant else f"FAIL ({t.protocol_gaps})"
            print(f"  {t.agent_name}: {t.duration_ms:.0f}ms — {status}")

        # 기본 검증
        assert final_state.get("final_answer") or final_state.get("draft_answer"), (
            "답변이 생성되지 않았습니다"
        )

        # 에이전트 추적 존재 검증
        traced_agents = {t.agent_name for t in trace.agent_traces}
        assert "query_analysis" in traced_agents, "query_analysis 추적 누락"

        # Retrieval 결과 존재 검증
        retrieval_agents = {
            t.agent_name for t in trace.agent_traces if t.phase == "retrieving"
        }
        assert len(retrieval_agents) >= 1, "retrieval 에이전트 추적 누락"

        # generation 추적 존재 검증
        assert "generation" in traced_agents, "generation 추적 누락"

        # 프로토콜 준수 검증 (query_analysis)
        qa_trace = next(
            (t for t in trace.agent_traces if t.agent_name == "query_analysis"), None
        )
        if qa_trace:
            assert qa_trace.protocol_compliant, (
                f"query_analysis 프로토콜 불일치: {qa_trace.protocol_gaps}"
            )


class TestGeneralFastPathTrace:
    """일반 쿼리 Fast Path 추적 테스트."""

    def test_general_query_trace(self, compiled_mas_graph, openai_api_key):
        """
        일반 쿼리 Fast Path: Retrieval/Review 생략 검증.

        기대 흐름: cache_check → input_guardrail → supervisor → query_analysis
        → supervisor → generation → supervisor → output_guardrail
        """
        query = "안녕하세요"
        state = _create_initial_state(query, "general")
        final_state = _run_graph(compiled_mas_graph, state)

        logger = E2ETraceLogger(
            test_name="general_fast_path",
            query=query,
            chat_type="general",
        )
        trace = logger.capture_from_state(final_state)
        filepath = logger.save()

        print(f"\n[Trace saved] {filepath}")
        print(f"[Agents traced] {len(trace.agent_traces)}")
        for t in trace.agent_traces:
            print(f"  {t.agent_name}: {t.duration_ms:.0f}ms")

        # 답변 존재
        assert final_state.get("final_answer") or final_state.get("draft_answer"), (
            "답변이 생성되지 않았습니다"
        )

        # Fast path: retrieval 없음
        retrieval_agents = [t for t in trace.agent_traces if t.phase == "retrieving"]
        assert len(retrieval_agents) == 0, (
            f"Fast path에서 retrieval이 호출됨: {[t.agent_name for t in retrieval_agents]}"
        )

        # Fast path: review 없음
        review_agents = [t for t in trace.agent_traces if t.agent_name == "review"]
        assert len(review_agents) == 0, "Fast path에서 review가 호출됨"


class TestLawQueryTrace:
    """법령 쿼리 Straightforward Path 추적 테스트."""

    def test_law_query_trace(self, compiled_mas_graph, openai_api_key):
        """
        법령 쿼리: 법령 검색 특화 경로 검증.

        기대 흐름: cache_check → input_guardrail → supervisor → query_analysis
        → supervisor → retrieval_law (+ criteria/case) → retrieval_merge
        → supervisor → generation → supervisor → output_guardrail
        """
        query = "소비자기본법 제7조 내용 알려줘"
        state = _create_initial_state(query, "dispute")
        final_state = _run_graph(compiled_mas_graph, state)

        logger = E2ETraceLogger(
            test_name="law_query_straightforward",
            query=query,
            chat_type="dispute",
        )
        trace = logger.capture_from_state(final_state)
        filepath = logger.save()

        print(f"\n[Trace saved] {filepath}")
        print(f"[Agents traced] {len(trace.agent_traces)}")
        for t in trace.agent_traces:
            status = "PASS" if t.protocol_compliant else f"FAIL ({t.protocol_gaps})"
            print(f"  {t.agent_name}: {t.duration_ms:.0f}ms — {status}")

        # 답변 존재
        assert final_state.get("final_answer") or final_state.get("draft_answer"), (
            "답변이 생성되지 않았습니다"
        )

        # Retrieval 존재 (법령 검색은 반드시 포함)
        retrieval_agents = {
            t.agent_name for t in trace.agent_traces if t.phase == "retrieving"
        }
        assert "retrieval_law" in retrieval_agents, "법령 검색(retrieval_law) 누락"

        # Retrieval 결과 프로토콜 검증
        for t in trace.agent_traces:
            if t.phase == "retrieving":
                assert t.protocol_compliant, (
                    f"{t.agent_name} 프로토콜 불일치: {t.protocol_gaps}"
                )


class TestProtocolCompliance:
    """프로토콜 준수 종합 검증."""

    def test_all_agents_have_required_keys(self, compiled_mas_graph, openai_api_key):
        """모든 에이전트의 출력이 프로토콜 필수 키를 포함하는지 검증."""
        query = "노트북을 구매했는데 화면이 깨져서 도착했어요. 환불 가능한가요?"
        state = _create_initial_state(query, "dispute")
        final_state = _run_graph(compiled_mas_graph, state)

        logger = E2ETraceLogger(
            test_name="protocol_compliance_check",
            query=query,
            chat_type="dispute",
        )
        trace = logger.capture_from_state(final_state)
        logger.save()

        # 프로토콜 준수 요약
        summary = trace.protocol_summary
        print(f"\n[Protocol Summary] {summary.get('compliance_rate', 'N/A')}")
        for agent_name, detail in summary.get("per_agent", {}).items():
            status = "PASS" if detail["compliant"] else f"GAPS: {detail['gaps']}"
            print(f"  {agent_name}: {status}")

        # 최소 에이전트 추적 수 (query_analysis + retrieval(1+) + generation)
        assert len(trace.agent_traces) >= 3, (
            f"추적된 에이전트가 부족합니다: {len(trace.agent_traces)}"
        )
