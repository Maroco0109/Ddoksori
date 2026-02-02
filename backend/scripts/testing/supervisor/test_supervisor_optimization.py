"""
PR-5: Supervisor 최적화 테스트

실행 방법:
    /home/maroco/miniconda3/envs/dsr/bin/python -m pytest backend/scripts/testing/supervisor/test_supervisor_optimization.py -v

Note: 모든 테스트가 실제 LLM + DB를 사용하므로 llm 마커가 필요합니다.
"""

import asyncio
import time
from typing import Any, Dict

import pytest

from app.supervisor.graph import get_graph_for_chat_type

pytestmark = pytest.mark.llm


@pytest.fixture
def graph():
    """테스트용 그래프"""
    return get_graph_for_chat_type("general")


class TestDeterministicRouting:
    """Deterministic Routing 테스트"""

    def test_no_retrieval_skips_llm(self, graph):
        """NO_RETRIEVAL은 LLM 판단 없이 처리"""

        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "안녕"}]},
                config={"configurable": {"thread_id": "test-no-retrieval"}},
            )

        result = asyncio.run(run_test())

        # supervisor 상태 확인
        supervisor_state = result.get("supervisor", {})
        iteration_count = supervisor_state.get("iteration_count", 0)

        # NO_RETRIEVAL은 최대 3 iterations
        assert iteration_count <= 3, (
            f"NO_RETRIEVAL should have ≤3 iterations, got {iteration_count}"
        )

        print(f"✓ NO_RETRIEVAL iterations: {iteration_count}")

    def test_law_query_straightforward_path(self, graph):
        """LAW 쿼리는 Straightforward Path 사용"""

        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "소비자기본법 환불 조항"}]},
                config={"configurable": {"thread_id": "test-law-straightforward"}},
            )

        result = asyncio.run(run_test())

        supervisor_state = result.get("supervisor", {})
        iteration_count = supervisor_state.get("iteration_count", 0)

        # LAW 쿼리는 최대 4 iterations
        assert iteration_count <= 4, (
            f"LAW query should have ≤4 iterations, got {iteration_count}"
        )

        print(f"✓ LAW query iterations: {iteration_count}")

    def test_criteria_query_straightforward_path(self, graph):
        """CRITERIA 쿼리는 Straightforward Path 사용"""

        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "환불 기준 알려줘"}]},
                config={"configurable": {"thread_id": "test-criteria-straightforward"}},
            )

        result = asyncio.run(run_test())

        supervisor_state = result.get("supervisor", {})
        iteration_count = supervisor_state.get("iteration_count", 0)

        # CRITERIA 쿼리는 최대 4 iterations
        assert iteration_count <= 4, (
            f"CRITERIA query should have ≤4 iterations, got {iteration_count}"
        )

        print(f"✓ CRITERIA query iterations: {iteration_count}")


class TestLLMPath:
    """LLM Path 테스트 (DISPUTE 쿼리)"""

    def test_dispute_query_includes_review(self, graph):
        """DISPUTE 쿼리는 Review 단계 포함"""

        async def run_test():
            return await graph.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": "헬스장 3개월 등록했는데 환불 받고 싶어요",
                        }
                    ]
                },
                config={"configurable": {"thread_id": "test-dispute-review"}},
            )

        result = asyncio.run(run_test())

        # Review 결과가 있어야 함
        review = result.get("review")
        assert review is not None, "DISPUTE query should have review results"

        print(f"✓ DISPUTE query has review: {bool(review)}")

    def test_dispute_query_has_more_iterations(self, graph):
        """DISPUTE 쿼리는 더 많은 iterations"""

        async def run_test():
            return await graph.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": "휴대폰 불량으로 교환 요청했는데 거부당했어요",
                        }
                    ]
                },
                config={"configurable": {"thread_id": "test-dispute-iterations"}},
            )

        result = asyncio.run(run_test())

        supervisor_state = result.get("supervisor", {})
        iteration_count = supervisor_state.get("iteration_count", 0)

        # DISPUTE 쿼리는 4-6 iterations (Review 포함)
        assert iteration_count >= 4, (
            f"DISPUTE query should have ≥4 iterations, got {iteration_count}"
        )

        print(f"✓ DISPUTE query iterations: {iteration_count}")


class TestIterationReduction:
    """Iteration 수 감소 테스트"""

    @pytest.mark.parametrize(
        "query,max_iterations",
        [
            ("안녕", 3),  # NO_RETRIEVAL
            ("네 이름이 뭐야?", 3),  # NO_RETRIEVAL
            ("소비자기본법 환불", 4),  # LAW
            ("환불 기준", 4),  # CRITERIA
            ("헬스장 환불 받고 싶어요", 6),  # DISPUTE
        ],
    )
    def test_iteration_limits(self, graph, query: str, max_iterations: int):
        """쿼리별 iteration 제한 검증"""

        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": query}]},
                config={"configurable": {"thread_id": f"test-limit-{query[:5]}"}},
            )

        result = asyncio.run(run_test())

        supervisor_state = result.get("supervisor", {})
        iteration_count = supervisor_state.get("iteration_count", 0)

        assert iteration_count <= max_iterations, (
            f"Query '{query}' exceeded {max_iterations} iterations (got {iteration_count})"
        )

        print(f"✓ '{query}' → {iteration_count} iterations (max: {max_iterations})")


class TestPerformanceImprovement:
    """성능 개선 테스트"""

    @pytest.mark.slow
    def test_no_retrieval_response_time(self, graph):
        """NO_RETRIEVAL 응답 시간 < 5초"""

        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "안녕"}]},
                config={"configurable": {"thread_id": "test-perf-no-retrieval"}},
            )

        start = time.time()
        asyncio.run(run_test())
        elapsed = time.time() - start

        assert elapsed < 5.0, f"NO_RETRIEVAL took {elapsed:.2f}s, should be < 5s"
        print(f"✓ NO_RETRIEVAL 응답 시간: {elapsed:.2f}초")

    @pytest.mark.slow
    def test_law_query_response_time(self, graph):
        """LAW 쿼리 응답 시간 < 15초"""

        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "소비자기본법 환불 조항"}]},
                config={"configurable": {"thread_id": "test-perf-law"}},
            )

        start = time.time()
        asyncio.run(run_test())
        elapsed = time.time() - start

        assert elapsed < 15.0, f"LAW query took {elapsed:.2f}s, should be < 15s"
        print(f"✓ LAW 쿼리 응답 시간: {elapsed:.2f}초")

    @pytest.mark.slow
    def test_dispute_query_response_time(self, graph):
        """DISPUTE 쿼리 응답 시간 < 20초"""

        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "헬스장 환불 받고 싶어요"}]},
                config={"configurable": {"thread_id": "test-perf-dispute"}},
            )

        start = time.time()
        asyncio.run(run_test())
        elapsed = time.time() - start

        assert elapsed < 20.0, f"DISPUTE query took {elapsed:.2f}s, should be < 20s"
        print(f"✓ DISPUTE 쿼리 응답 시간: {elapsed:.2f}초")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
