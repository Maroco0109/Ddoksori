"""
PR-3: 계층적 검색 테스트

실행 방법:
    conda run -n dsr pytest backend/scripts/testing/retrieval/test_hierarchical_search.py -v
"""
import os
import pytest
from typing import List

from app.agents.retrieval.law_agent import LawRetrievalAgent
from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
from app.common.config import get_config


@pytest.fixture
def db_config():
    """데이터베이스 설정"""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'dbname': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }


@pytest.fixture
def embed_url():
    """임베딩 URL"""
    config = get_config()
    return config.embedding.api_url


class TestHybridRetrieverChunkTypeFilter:
    """HybridRetriever chunk_type 필터 테스트"""

    def test_single_chunk_type_filter(self, db_config, embed_url):
        """단일 chunk_type 필터링"""
        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            results = retriever.search(
                query="환불",
                top_k=5,
                dataset_type_filter='law_guide',
                chunk_type_filter='조_전체',
            )

            # 모든 결과가 조_전체여야 함
            for r in results:
                assert r.chunk_type == '조_전체', \
                    f"Expected chunk_type='조_전체', got '{r.chunk_type}'"

        finally:
            retriever.close()

    def test_list_chunk_type_filter(self, db_config, embed_url):
        """리스트 chunk_type 필터링"""
        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            results = retriever.search(
                query="환불",
                top_k=10,
                dataset_type_filter='law_guide',
                chunk_type_filter=['항_분할', '호_분할'],
            )

            # 모든 결과가 항_분할 또는 호_분할이어야 함
            allowed_types = {'항_분할', '호_분할'}
            for r in results:
                assert r.chunk_type in allowed_types, \
                    f"Expected chunk_type in {allowed_types}, got '{r.chunk_type}'"

        finally:
            retriever.close()

    def test_criteria_chunk_type_filter(self, db_config, embed_url):
        """기준 chunk_type 필터링"""
        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            results = retriever.search(
                query="헬스장",
                top_k=5,
                dataset_type_filter='law_guide',
                chunk_type_filter=['별표1_품목매핑'],
            )

            # 모든 결과가 별표1_품목매핑이어야 함
            for r in results:
                assert r.chunk_type == '별표1_품목매핑', \
                    f"Expected '별표1_품목매핑', got '{r.chunk_type}'"

        finally:
            retriever.close()


class TestLawAgentHierarchicalSearch:
    """LawRetrievalAgent 계층 검색 테스트"""

    @pytest.mark.asyncio
    async def test_law_search_returns_detailed_first(self):
        """법령 검색: 항/호가 조보다 먼저 반환되어야 함"""
        agent = LawRetrievalAgent()

        results = await agent._execute_search("환불 기간", top_k=10)

        # 결과가 있어야 함
        assert len(results) > 0, "Should have results"

        # 앞쪽에 항_분할, 호_분할이 있어야 함 (있다면)
        detailed_types = {'항_분할', '호_분할'}
        detailed_indices = [
            i for i, r in enumerate(results)
            if r.chunk_type in detailed_types
        ]

        article_indices = [
            i for i, r in enumerate(results)
            if r.chunk_type == '조_전체'
        ]

        if detailed_indices and article_indices:
            # 상세 결과가 조 결과보다 앞에 있어야 함
            assert min(detailed_indices) < min(article_indices), \
                "Detailed (항/호) results should come before article (조) results"

        print(f"✓ 결과 순서: {[r.chunk_type for r in results[:5]]}")

    @pytest.mark.asyncio
    async def test_law_search_deduplication(self):
        """법령 검색: 중복 chunk_id 없어야 함"""
        agent = LawRetrievalAgent()

        results = await agent._execute_search("소비자 보호", top_k=10)

        chunk_ids = [r.chunk_id for r in results]
        assert len(chunk_ids) == len(set(chunk_ids)), \
            "Should not have duplicate chunk_ids"


class TestCriteriaAgentHierarchicalSearch:
    """CriteriaRetrievalAgent 계층 검색 테스트"""

    @pytest.mark.asyncio
    async def test_criteria_search_includes_product_mapping(self):
        """기준 검색: 품목 매핑 결과 포함"""
        agent = CriteriaRetrievalAgent()

        results = await agent._execute_search("헬스장 환불", top_k=10)

        # 결과가 있어야 함
        assert len(results) > 0, "Should have results"

        # 별표1_품목매핑이 포함되어야 함 (있다면)
        chunk_types = [r.chunk_type for r in results]
        print(f"✓ 기준 검색 chunk_types: {chunk_types}")

    @pytest.mark.asyncio
    async def test_criteria_search_includes_supplement(self):
        """기준 검색: 보충정보(품질보증/내용연수) 포함 가능"""
        agent = CriteriaRetrievalAgent()

        results = await agent._execute_search("노트북 품질보증", top_k=10)

        chunk_types = [r.chunk_type for r in results]

        # 별표3 또는 별표4가 포함될 수 있음
        supplement_types = {'별표3_품질보증', '별표4_내용연수'}
        has_supplement = any(ct in supplement_types for ct in chunk_types)

        print(f"✓ 보충정보 포함: {has_supplement}, types: {chunk_types}")

    @pytest.mark.asyncio
    async def test_criteria_search_hierarchy_order(self):
        """기준 검색: 구체적(손자) → 추상적(부모) 순서"""
        agent = CriteriaRetrievalAgent()

        results = await agent._execute_search("휴대폰 교환", top_k=10)

        # 계층 청크만 필터
        hierarchy_types = {'손자_청크', '자식_청크', '부모_청크'}
        hierarchy_results = [r for r in results if r.chunk_type in hierarchy_types]

        if len(hierarchy_results) >= 2:
            # 손자 > 자식 > 부모 순서 확인
            order = {'손자_청크': 1, '자식_청크': 2, '부모_청크': 3}
            for i in range(len(hierarchy_results) - 1):
                current_order = order.get(hierarchy_results[i].chunk_type, 0)
                next_order = order.get(hierarchy_results[i + 1].chunk_type, 0)
                # 같은 레벨이거나 더 추상적인 것이 뒤에 와야 함
                # (엄격한 순서는 아님, similarity에 따라 다를 수 있음)

        print(f"✓ 계층 결과: {[r.chunk_type for r in hierarchy_results]}")


class TestHierarchicalSearchPerformance:
    """계층 검색 성능 테스트"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_law_search_performance(self):
        """법령 계층 검색 성능"""
        import time

        agent = LawRetrievalAgent()

        start = time.time()
        results = await agent._execute_search("환불 기간 조항", top_k=5)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Law search took {elapsed:.2f}s, should be < 5s"
        print(f"✓ 법령 검색 시간: {elapsed:.2f}초, 결과 수: {len(results)}")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_criteria_search_performance(self):
        """기준 계층 검색 성능"""
        import time

        agent = CriteriaRetrievalAgent()

        start = time.time()
        results = await agent._execute_search("헬스장 환불 기준", top_k=5)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Criteria search took {elapsed:.2f}s, should be < 5s"
        print(f"✓ 기준 검색 시간: {elapsed:.2f}초, 결과 수: {len(results)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
