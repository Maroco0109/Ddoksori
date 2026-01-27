"""
PR-6: Redis 캐싱 테스트

실행 방법:
    PYTHONPATH=backend /home/maroco/miniconda3/envs/dsr/bin/python -m pytest backend/scripts/testing/supervisor/test_pr6_cache.py -v
"""
import pytest
import time
import asyncio
from typing import Dict, Any
from unittest.mock import patch, MagicMock


class TestSupervisorCache:
    """Supervisor 캐시 단위 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 캐시 초기화"""
        from app.supervisor.cache import clear_all_supervisor_caches
        clear_all_supervisor_caches()

    def test_query_normalization(self):
        """쿼리 정규화 테스트"""
        from app.supervisor.cache import _normalize_query

        assert _normalize_query("안녕?") == "안녕"
        assert _normalize_query("  안녕  ") == "안녕"
        assert _normalize_query("안녕!") == "안녕"
        assert _normalize_query("환불   받고   싶어요") == "환불 받고 싶어요"

    def test_l2_query_analysis_cache(self):
        """L2 Query Analysis 캐시 테스트"""
        from app.supervisor.cache import QueryAnalysisCache

        query = "소비자기본법 환불 조항"
        analysis = {
            'mode': 'NEED_RAG',
            'query_type': 'law_search',
            'keywords': ['소비자기본법', '환불'],
            'retriever_types': ['law', 'criteria'],
        }

        # 캐시 미스
        assert QueryAnalysisCache.get(query) is None

        # 캐시 저장
        assert QueryAnalysisCache.set(query, analysis) == True

        # 캐시 히트
        cached = QueryAnalysisCache.get(query)
        assert cached is not None
        assert cached['mode'] == 'NEED_RAG'
        assert cached['query_type'] == 'law_search'
        assert 'retriever_types' in cached

    def test_l1_supervisor_response_cache(self):
        """L1 Supervisor 응답 캐시 테스트"""
        from app.supervisor.cache import SupervisorResponseCache

        query = "안녕"
        session_id = "test-session-12345678"
        response = {
            'final_answer': '안녕하세요! 무엇을 도와드릴까요?',
            'mode': 'NO_RETRIEVAL',
        }

        # 캐시 미스
        assert SupervisorResponseCache.get(query, session_id) is None

        # 캐시 저장
        assert SupervisorResponseCache.set(query, response, session_id) == True

        # 캐시 히트
        cached = SupervisorResponseCache.get(query, session_id)
        assert cached is not None
        assert cached['final_answer'] == response['final_answer']
        assert cached['mode'] == 'NO_RETRIEVAL'

    def test_l1_session_isolation(self):
        """L1 캐시 세션 격리 테스트"""
        from app.supervisor.cache import SupervisorResponseCache

        query = "안녕"
        session_a = "session-aaaaaaaa"
        session_b = "session-bbbbbbbb"

        # 세션 A에 저장
        SupervisorResponseCache.set(query, {'answer': 'A'}, session_a)

        # 세션 B는 캐시 미스
        assert SupervisorResponseCache.get(query, session_b) is None

        # 세션 A는 캐시 히트
        cached = SupervisorResponseCache.get(query, session_a)
        assert cached is not None

    def test_cache_stats(self):
        """캐시 통계 테스트"""
        from app.supervisor.cache import (
            QueryAnalysisCache,
            SupervisorResponseCache,
            get_cache_stats,
            clear_all_supervisor_caches,
        )

        clear_all_supervisor_caches()

        # 데이터 추가
        QueryAnalysisCache.set("q1", {'mode': 'NEED_RAG'})
        QueryAnalysisCache.set("q2", {'mode': 'NO_RETRIEVAL'})
        SupervisorResponseCache.set("q1", {'answer': 'a1'}, "s1")

        # 통계 확인
        stats = get_cache_stats()
        assert stats['enabled'] == True
        assert stats['l2_query_analysis_count'] == 2
        assert stats['l1_supervisor_count'] == 1


class TestCacheIntegration:
    """캐시 통합 테스트 (실제 그래프)"""

    @pytest.fixture
    def graph(self):
        from app.supervisor.graph import get_graph_for_chat_type
        return get_graph_for_chat_type("general")

    def test_repeated_query_uses_cache(self, graph):
        """
        테스트: 동일 쿼리 반복 시 캐시 사용

        기대 결과:
        - 첫 번째 호출: 캐시 미스, 전체 파이프라인 실행
        - 두 번째 호출: 캐시 히트, 즉시 응답 (<1초)
        """
        async def run_test():
            from app.supervisor.cache import clear_all_supervisor_caches
            clear_all_supervisor_caches()

            query = "안녕하세요"

            # 첫 번째 호출 (캐시 미스)
            start1 = time.time()
            result1 = await graph.ainvoke(
                {"messages": [{"role": "user", "content": query}], "session_id": "cache-test-session"},
                config={"configurable": {"thread_id": "pr6-cache-test"}}
            )
            time1 = time.time() - start1

            # 두 번째 호출 (캐시 히트 기대)
            start2 = time.time()
            result2 = await graph.ainvoke(
                {"messages": [{"role": "user", "content": query}], "session_id": "cache-test-session"},
                config={"configurable": {"thread_id": "pr6-cache-test"}}
            )
            time2 = time.time() - start2

            return result1, result2, time1, time2

        result1, result2, time1, time2 = asyncio.run(run_test())

        # 검증
        assert result1.get('final_answer') is not None
        assert result2.get('final_answer') is not None

        # 캐시 히트 시 응답 시간이 현저히 빨라야 함
        assert time2 < time1, f"Cache should be faster: {time2:.2f}s vs {time1:.2f}s"

        # 캐시 히트 시 1초 미만
        if time2 < 1.0:
            print(f"✓ 캐시 히트 응답 시간: {time2:.3f}초 (첫 응답: {time1:.2f}초)")
        else:
            print(f"! 캐시 미스 또는 Redis 미연결: {time2:.2f}초")

    def test_different_queries_no_cache(self, graph):
        """
        테스트: 다른 쿼리는 캐시 공유 안 함
        """
        async def run_test():
            from app.supervisor.cache import clear_all_supervisor_caches
            clear_all_supervisor_caches()

            result1 = await graph.ainvoke(
                {"messages": [{"role": "user", "content": "안녕"}], "session_id": "test-session"},
                config={"configurable": {"thread_id": "pr6-diff-queries-1"}}
            )

            result2 = await graph.ainvoke(
                {"messages": [{"role": "user", "content": "고맙습니다"}], "session_id": "test-session"},
                config={"configurable": {"thread_id": "pr6-diff-queries-2"}}
            )

            return result1, result2

        result1, result2 = asyncio.run(run_test())

        # 두 쿼리 모두 응답이 있어야 함
        assert result1.get('final_answer') is not None
        assert result2.get('final_answer') is not None

        # L1 캐시는 session-aware이므로, 같은 session이라도 다른 쿼리면 다른 캐시 키 사용
        # (정규화 후 해시가 다름)


class TestCachePerformance:
    """캐시 성능 테스트"""

    @pytest.fixture
    def graph(self):
        from app.supervisor.graph import get_graph_for_chat_type
        return get_graph_for_chat_type("general")

    @pytest.mark.slow
    def test_cache_hit_under_one_second(self, graph):
        """
        테스트: 캐시 히트 시 응답 시간 <1초
        """
        async def run_test():
            from app.supervisor.cache import SupervisorResponseCache

            query = "테스트 쿼리"
            session = "perf-test"

            # 사전 캐싱
            SupervisorResponseCache.set(query, {
                'final_answer': '테스트 응답입니다.',
                'mode': 'NO_RETRIEVAL',
            }, session)

            # 응답 시간 측정
            times = []
            for i in range(5):
                start = time.time()
                result = await graph.ainvoke(
                    {"messages": [{"role": "user", "content": query}], "session_id": session},
                    config={"configurable": {"thread_id": f"pr6-perf-test-{i}"}}
                )
                times.append(time.time() - start)

            return times

        times = asyncio.run(run_test())
        avg_time = sum(times) / len(times)

        assert avg_time < 1.0, f"Cache hit avg time {avg_time:.3f}s exceeds 1s"
        print(f"✓ 캐시 히트 평균 응답 시간: {avg_time:.3f}초")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
