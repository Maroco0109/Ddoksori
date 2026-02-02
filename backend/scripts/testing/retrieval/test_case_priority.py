"""
PR-4: 사례 우선순위 검색 테스트

실행 방법:
    conda run -n dsr pytest backend/scripts/testing/retrieval/test_case_priority.py -v
"""

import os
from typing import List

import pytest

from app.agents.retrieval.case_agent import CaseRetrievalAgent
from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
from app.common.config import get_config


@pytest.fixture
def db_config():
    """데이터베이스 설정"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "ddoksori"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }


@pytest.fixture
def embed_url():
    """임베딩 URL"""
    config = get_config()
    return config.embedding.api_url


def get_category(result):
    """Extract category from SearchResult (category_path[0])"""
    return result.category_path[0] if result.category_path else None


class TestHybridRetrieverCategoryFilter:
    """HybridRetriever category 필터 테스트"""

    def test_single_category_filter(self, db_config, embed_url):
        """단일 category 필터링"""
        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            results = retriever.search(
                query="환불",
                top_k=5,
                dataset_type_filter="case",
                category_filter="해결",
            )

            # 모든 결과가 해결 category여야 함
            for r in results:
                category = get_category(r)
                assert category == "해결", f"Expected category='해결', got '{category}'"

            print(f"✓ 해결 사례 {len(results)}건 검색됨")

        finally:
            retriever.close()

    def test_list_category_filter(self, db_config, embed_url):
        """리스트 category 필터링"""
        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            results = retriever.search(
                query="환불",
                top_k=10,
                dataset_type_filter="case",
                category_filter=["해결", "조정"],
            )

            # 모든 결과가 해결 또는 조정이어야 함
            allowed_categories = {"해결", "조정"}
            for r in results:
                category = get_category(r)
                assert (
                    category in allowed_categories
                ), f"Expected category in {allowed_categories}, got '{category}'"

            print(f"✓ 해결+조정 사례 {len(results)}건 검색됨")

        finally:
            retriever.close()

    def test_counsel_category_filter(self, db_config, embed_url):
        """상담 category 필터링"""
        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            results = retriever.search(
                query="환불",
                top_k=5,
                dataset_type_filter="case",
                category_filter="상담",
            )

            # 모든 결과가 상담 category여야 함
            for r in results:
                category = get_category(r)
                assert category == "상담", f"Expected category='상담', got '{category}'"

            print(f"✓ 상담 사례 {len(results)}건 검색됨")

        finally:
            retriever.close()


class TestCaseAgentPrioritySearch:
    """CaseRetrievalAgent 우선순위 검색 테스트"""

    @pytest.mark.asyncio
    async def test_primary_results_come_first(self):
        """해결+조정 사례가 먼저 반환되어야 함"""
        agent = CaseRetrievalAgent()

        results = await agent._execute_search("헬스장 환불", top_k=10)

        # 결과가 있어야 함
        assert len(results) > 0, "Should have results"

        # 앞쪽에 해결/조정 사례가 있어야 함
        primary_categories = {"해결", "조정"}
        counsel_category = "상담"

        primary_indices = [
            i for i, r in enumerate(results) if get_category(r) in primary_categories
        ]

        counsel_indices = [
            i for i, r in enumerate(results) if get_category(r) == counsel_category
        ]

        if primary_indices and counsel_indices:
            # 해결/조정 사례가 상담 사례보다 앞에 있어야 함
            assert min(primary_indices) < min(
                counsel_indices
            ), "Primary (해결/조정) results should come before counsel (상담) results"

        # 결과 분포 출력
        categories = [get_category(r) for r in results]
        print(f"✓ 결과 순서: {categories}")

    @pytest.mark.asyncio
    async def test_deduplication(self):
        """중복 chunk_id 없어야 함"""
        agent = CaseRetrievalAgent()

        results = await agent._execute_search("노트북 환불", top_k=10)

        chunk_ids = [r.chunk_id for r in results]
        assert len(chunk_ids) == len(
            set(chunk_ids)
        ), "Should not have duplicate chunk_ids"

    @pytest.mark.asyncio
    async def test_counsel_supplement_when_primary_insufficient(self):
        """해결+조정 결과 부족 시 상담으로 보충"""
        agent = CaseRetrievalAgent()

        # 매우 구체적인 쿼리로 결과가 적을 수 있음
        results = await agent._execute_search("아주 특수한 제품 환불", top_k=10)

        if len(results) > 0:
            categories = [get_category(r) for r in results]
            print(f"✓ 검색 결과 categories: {categories}")

            # 상담 사례가 보충으로 포함될 수 있음
            has_counsel = "상담" in categories
            print(f"✓ 상담 보충 여부: {has_counsel}")


class TestCasePriorityDistribution:
    """사례 우선순위 분포 검증"""

    @pytest.mark.asyncio
    async def test_category_distribution(self):
        """검색 결과의 category 분포 확인"""
        agent = CaseRetrievalAgent()

        test_queries = [
            "헬스장 환불",
            "휴대폰 교환",
            "온라인 쇼핑 취소",
        ]

        for query in test_queries:
            results = await agent._execute_search(query, top_k=10)

            if results:
                categories = [get_category(r) for r in results]
                해결_count = categories.count("해결")
                조정_count = categories.count("조정")
                상담_count = categories.count("상담")

                print(f"Query: '{query}'")
                print(f"  - 해결: {해결_count}")
                print(f"  - 조정: {조정_count}")
                print(f"  - 상담: {상담_count}")
                print(f"  - 총: {len(results)}")


class TestCasePriorityPerformance:
    """사례 우선순위 검색 성능 테스트"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_search_performance(self):
        """사례 검색 성능"""
        import time

        agent = CaseRetrievalAgent()

        start = time.time()
        results = await agent._execute_search("헬스장 환불 사례", top_k=5)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Case search took {elapsed:.2f}s, should be < 5s"
        print(f"✓ 사례 검색 시간: {elapsed:.2f}초, 결과 수: {len(results)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
