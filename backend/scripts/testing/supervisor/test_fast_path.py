"""
PR-1: NO_RETRIEVAL Fast Path 테스트

실행 방법:
    conda run -n dsr pytest backend/scripts/testing/supervisor/test_fast_path.py -v
"""
import pytest
import time
import asyncio
from typing import Dict, Any

# 테스트 대상 모듈 import
from app.supervisor.graph import get_graph_for_chat_type
from app.supervisor.state import ChatState


@pytest.fixture
def graph():
    """테스트용 그래프 생성"""
    return get_graph_for_chat_type("general")


class TestNoRetrievalFastPath:
    """NO_RETRIEVAL 모드 Fast Path 테스트"""

    def test_greeting_skips_retrieval(self, graph):
        """
        테스트: "안녕" 인사말은 retrieval 없이 처리

        기대 결과:
        - mode == "NO_RETRIEVAL"
        - retrieval 상태가 None 또는 빈 값
        - 응답 시간 < 10초
        """
        async def run_test():
            start = time.time()

            result = await graph.ainvoke(
                {"messages": [{"role": "user", "content": "안녕"}]},
                config={"configurable": {"thread_id": "test-greeting"}}
            )

            return result, time.time() - start

        result, elapsed = asyncio.run(run_test())

        # 검증 1: mode 확인
        assert result.get("mode") == "NO_RETRIEVAL", \
            f"Expected mode='NO_RETRIEVAL', got '{result.get('mode')}'"

        # 검증 2: retrieval이 실행되지 않음
        retrieval = result.get("retrieval")
        assert retrieval is None or retrieval == {} or not retrieval, \
            f"Retrieval should be skipped, but got: {retrieval}"

        # 검증 3: 응답 시간
        assert elapsed < 10.0, \
            f"Response time {elapsed:.2f}s exceeds 10s limit"

        print(f"✓ 인사말 응답 시간: {elapsed:.2f}초")

    def test_system_meta_skips_retrieval(self, graph):
        """
        테스트: 시스템 질문은 retrieval 없이 처리
        """
        queries = [
            "네 이름이 뭐야?",
            "너 어떤 AI야?",
            "네 모델명이 뭐야?",
        ]

        async def run_test():
            results = []
            for i, query in enumerate(queries):
                start = time.time()

                result = await graph.ainvoke(
                    {"messages": [{"role": "user", "content": query}]},
                    config={"configurable": {"thread_id": f"test-system-{i}"}}
                )

                elapsed = time.time() - start
                results.append((query, result, elapsed))
            return results

        results = asyncio.run(run_test())

        for query, result, elapsed in results:
            assert result.get("mode") == "NO_RETRIEVAL", \
                f"Query '{query}' should be NO_RETRIEVAL, got '{result.get('mode')}'"

            print(f"✓ '{query}' → {elapsed:.2f}초")

    def test_need_rag_still_retrieves(self, graph):
        """
        테스트: NEED_RAG 쿼리는 여전히 retrieval 실행
        """
        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "소비자기본법 환불 조항은?"}]},
                config={"configurable": {"thread_id": "test-need-rag"}}
            )

        result = asyncio.run(run_test())

        # NEED_RAG여야 함
        assert result.get("mode") == "NEED_RAG", \
            f"Expected NEED_RAG, got '{result.get('mode')}'"

        # retrieval 결과가 있어야 함
        retrieval = result.get("retrieval")
        assert retrieval is not None and retrieval != {}, \
            "NEED_RAG query should have retrieval results"

        print(f"✓ 법령 쿼리는 retrieval 실행됨")

    @pytest.mark.parametrize("query,expected_mode", [
        ("안녕", "NO_RETRIEVAL"),
        ("고마워", "NO_RETRIEVAL"),
        ("알겠어", "NO_RETRIEVAL"),
        ("네 모델명이 뭐야?", "NO_RETRIEVAL"),
        ("환불 받고 싶어요", "NEED_RAG"),
        ("소비자기본법", "NEED_RAG"),
        ("헬스장 계약 취소", "NEED_RAG"),
    ])
    def test_mode_classification(self, graph, query: str, expected_mode: str):
        """
        테스트: 쿼리별 mode 분류 검증
        """
        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": query}]},
                config={"configurable": {"thread_id": f"test-mode-{query[:5]}"}}
            )

        result = asyncio.run(run_test())

        actual_mode = result.get("mode")
        assert actual_mode == expected_mode, \
            f"Query '{query}': expected {expected_mode}, got {actual_mode}"


class TestFastPathPerformance:
    """Fast Path 성능 테스트"""

    @pytest.mark.slow
    def test_no_retrieval_response_time(self, graph):
        """
        테스트: NO_RETRIEVAL 응답 시간 < 5초
        """
        test_queries = ["안녕", "고마워", "네 이름이 뭐야?"]

        async def run_test():
            results = []
            for query in test_queries:
                times = []

                for i in range(3):  # 3회 반복 측정
                    start = time.time()
                    await graph.ainvoke(
                        {"messages": [{"role": "user", "content": query}]},
                        config={"configurable": {"thread_id": f"test-perf-{query[:3]}-{i}"}}
                    )
                    times.append(time.time() - start)

                avg_time = sum(times) / len(times)
                results.append((query, avg_time))
            return results

        results = asyncio.run(run_test())

        for query, avg_time in results:
            assert avg_time < 5.0, \
                f"Query '{query}' avg time {avg_time:.2f}s exceeds 5s"

            print(f"✓ '{query}' 평균 응답 시간: {avg_time:.2f}초")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
