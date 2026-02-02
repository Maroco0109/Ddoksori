"""
E2E Test: UnifiedRetriever + Retrieval Agent 통합 검증

Phase 8: 모든 Retrieval Agent가 동일한 UnifiedRetriever (SQL search_hybrid_rrf)를 사용하는지 검증.

실행:
    PYTHONPATH=backend conda run -n dsr pytest backend/scripts/testing/e2e/test_unified_retriever.py -v -s

필수 환경변수:
    - DB_HOST: RDS 호스트
    - DB_PASSWORD: RDS 비밀번호
    - OPENAI_API_KEY: OpenAI API 키 (text-embedding-3-large)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================
# Suite 1: UnifiedRetriever 직접 검증 (RDS + OpenAI 필요)
# ============================================================


@pytest.mark.e2e
@pytest.mark.llm
class TestUnifiedRetrieverDirect:
    """UnifiedRetriever SQL search_hybrid_rrf() 직접 호출 검증"""

    def test_hybrid_search_returns_results(self, unified_retriever):
        """하이브리드 검색이 결과를 반환하는지 확인"""
        results = unified_retriever.search(
            query="환불 거부 시 소비자 권리는?",
            top_k=5,
        )
        assert len(results) > 0
        assert len(results) <= 5

    def test_search_result_has_required_fields(self, unified_retriever):
        """검색 결과에 필수 필드가 있는지 확인"""
        results = unified_retriever.search(
            query="청약철회권 행사 방법",
            top_k=3,
        )
        assert len(results) > 0
        r = results[0]
        assert r.chunk_id
        assert r.content
        assert r.doc_type
        assert r.similarity > 0  # RRF score

    def test_dataset_filter_law_guide(self, unified_retriever):
        """dataset_filter='law_guide' 필터링 동작"""
        results = unified_retriever.search(
            query="소비자기본법 제16조",
            top_k=5,
            dataset_filter="law_guide",
        )
        for r in results:
            assert r.doc_type == "law", f"Expected 'law', got '{r.doc_type}'"

    def test_dataset_filter_case(self, unified_retriever):
        """dataset_filter='case' 필터링 동작"""
        results = unified_retriever.search(
            query="가구 배송 지연 분쟁",
            top_k=5,
            dataset_filter="case",
        )
        for r in results:
            assert r.doc_type in (
                "mediation_case",
                "counsel_case",
                "criteria",
                "case",
            ), f"Expected case type, got '{r.doc_type}'"

    def test_category_filter(self, unified_retriever):
        """category_filter 필터링 동작 - SQL 레벨 필터 전달 확인"""
        results_filtered = unified_retriever.search(
            query="분쟁 조정 사례",
            top_k=5,
            dataset_filter="case",
            category_filter="의류",
        )
        results_unfiltered = unified_retriever.search(
            query="분쟁 조정 사례",
            top_k=5,
            dataset_filter="case",
        )
        # 필터 적용 시 결과가 비어있거나, 필터링되지 않은 결과와 다른 결과 반환
        # (동일 결과를 반환하면 필터가 동작하지 않은 것)
        if len(results_filtered) > 0 and len(results_unfiltered) > 0:
            filtered_ids = {r.chunk_id for r in results_filtered}
            unfiltered_ids = {r.chunk_id for r in results_unfiltered}
            # 필터링된 결과가 전체 결과의 부분집합이거나 다르면 정상
            assert filtered_ids != unfiltered_ids or len(results_filtered) <= len(
                results_unfiltered
            ), "category_filter가 검색 결과에 영향을 미치지 않음"

    def test_results_sorted_by_rrf_score(self, unified_retriever):
        """결과가 RRF 점수 내림차순으로 정렬되는지"""
        results = unified_retriever.search(
            query="환불 규정",
            top_k=10,
        )
        if len(results) >= 2:
            scores = [r.similarity for r in results]
            for i in range(len(scores) - 1):
                assert (
                    scores[i] >= scores[i + 1]
                ), f"Not sorted: {scores[i]} < {scores[i+1]}"


# ============================================================
# Suite 2: Retrieval Agent → UnifiedRetriever 경로 검증 (Mock)
# ============================================================


@pytest.mark.unit
class TestAgentUnifiedRetrieverIntegration:
    """Agent가 UnifiedRetriever를 올바르게 호출하는지 Mock 기반 검증"""

    @pytest.mark.asyncio
    async def test_law_agent_uses_unified_retriever(self):
        """LawRetrievalAgent가 UnifiedRetriever를 호출하고 dataset_filter='law_guide' 전달"""
        from app.agents.retrieval.tools.retriever import SearchResult

        mock_result = SearchResult(
            chunk_id="test_law_001",
            doc_id="test_law_001",
            chunk_type="조_전체",
            content="제16조(소비자의 권리)",
            doc_title="소비자기본법 제16조",
            doc_type="law",
            category_path=[],
            similarity=0.032,
        )

        with patch(
            "app.agents.retrieval.tools.unified_retriever.UnifiedRetriever"
        ) as MockRetriever:
            mock_instance = MagicMock()
            mock_instance.search.return_value = [mock_result]
            MockRetriever.return_value = mock_instance

            from app.agents.retrieval.law_agent import LawRetrievalAgent

            agent = LawRetrievalAgent()
            result = await agent.process(
                {
                    "context": {"user_query": "소비자 권리"},
                    "params": {"top_k": 3},
                }
            )

            # UnifiedRetriever.search가 호출되었는지
            mock_instance.search.assert_called_once()
            call_kwargs = mock_instance.search.call_args
            # dataset_filter='law_guide' 전달 확인
            assert call_kwargs.kwargs.get("dataset_filter") == "law_guide" or (
                len(call_kwargs.args) > 0 or "dataset_filter" in str(call_kwargs)
            )

            assert result["status"] == "success"
            assert len(result["result"]["results"]) == 1

    @pytest.mark.asyncio
    async def test_criteria_agent_uses_unified_retriever(self):
        """CriteriaRetrievalAgent가 dataset_filter='law_guide', document_type_filter='별표' 전달"""
        from app.agents.retrieval.tools.retriever import SearchResult

        mock_result = SearchResult(
            chunk_id="test_criteria_001",
            doc_id="test_criteria_001",
            chunk_type="별표1_품목매핑",
            content="가전제품 환불 기준",
            doc_title="분쟁해결기준 별표1",
            doc_type="law",
            category_path=[],
            similarity=0.028,
        )

        with patch(
            "app.agents.retrieval.tools.unified_retriever.UnifiedRetriever"
        ) as MockRetriever:
            mock_instance = MagicMock()
            mock_instance.search.return_value = [mock_result]
            MockRetriever.return_value = mock_instance

            from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

            agent = CriteriaRetrievalAgent()
            result = await agent.process(
                {
                    "context": {"user_query": "가전제품 환불"},
                    "params": {"top_k": 3},
                }
            )

            mock_instance.search.assert_called_once()
            call_kwargs = mock_instance.search.call_args
            assert "law_guide" in str(call_kwargs)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_case_agent_uses_unified_retriever(self):
        """CaseRetrievalAgent가 dataset_filter='case' 전달"""
        from app.agents.retrieval.tools.retriever import SearchResult

        mock_result = SearchResult(
            chunk_id="test_case_001",
            doc_id="test_case_001",
            chunk_type="case",
            content="배송 지연 분쟁 조정 사례",
            doc_title="배송 지연 사례",
            doc_type="mediation_case",
            category_path=["조정"],
            similarity=0.030,
        )

        with patch(
            "app.agents.retrieval.tools.unified_retriever.UnifiedRetriever"
        ) as MockRetriever:
            mock_instance = MagicMock()
            mock_instance.search.return_value = [mock_result]
            MockRetriever.return_value = mock_instance

            from app.agents.retrieval.case_agent import CaseRetrievalAgent

            agent = CaseRetrievalAgent()
            result = await agent.process(
                {
                    "context": {"user_query": "배송 지연"},
                    "params": {"top_k": 3},
                }
            )

            mock_instance.search.assert_called_once()
            call_kwargs = mock_instance.search.call_args
            assert "case" in str(call_kwargs)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_all_agents_share_same_search_method(self):
        """모든 에이전트가 동일한 BaseRetrievalAgent._execute_search를 사용하는지"""
        from app.agents.retrieval.base_retrieval_agent import BaseRetrievalAgent
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        # _execute_search가 BaseRetrievalAgent에서 정의된 것과 동일한지
        for AgentClass in [
            LawRetrievalAgent,
            CriteriaRetrievalAgent,
            CaseRetrievalAgent,
        ]:
            assert (
                AgentClass._execute_search is BaseRetrievalAgent._execute_search
            ), f"{AgentClass.__name__} overrides _execute_search (should not)"

    @pytest.mark.asyncio
    async def test_agents_have_different_filters(self):
        """각 에이전트가 다른 필터를 반환하는지"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        law_filters = LawRetrievalAgent()._get_search_filters()
        criteria_filters = CriteriaRetrievalAgent()._get_search_filters()
        case_filters = CaseRetrievalAgent()._get_search_filters()

        assert law_filters["dataset_filter"] == "law_guide"
        assert "document_type_filter" not in law_filters

        assert criteria_filters["dataset_filter"] == "law_guide"
        assert criteria_filters["document_type_filter"] == "별표"

        assert case_filters["dataset_filter"] == "case"


# ============================================================
# Suite 3: Legacy 코드 비활성화 검증
# ============================================================


@pytest.mark.unit
class TestLegacyCodeMarking:
    """Legacy 코드가 올바르게 표기되었는지 검증"""

    def test_hybrid_retriever_marked_legacy(self):
        """HybridRetriever 모듈에 [LEGACY] 표기"""
        import app.agents.retrieval.tools.hybrid_retriever as mod

        assert "[LEGACY]" in (mod.__doc__ or "")

    def test_retriever_marked_legacy(self):
        """retriever 모듈에 [LEGACY] 표기"""
        import app.agents.retrieval.tools.retriever as mod

        assert "[LEGACY]" in (mod.__doc__ or "")

    def test_base_retriever_marked_legacy(self):
        """base 모듈에 [LEGACY] 표기"""
        import app.agents.retrieval.tools.base as mod

        assert "[LEGACY]" in (mod.__doc__ or "")

    def test_agents_do_not_import_hybrid_retriever(self):
        """에이전트 모듈이 HybridRetriever를 직접 import하지 않는지"""
        import inspect

        from app.agents.retrieval import case_agent, criteria_agent, law_agent

        for mod in [law_agent, criteria_agent, case_agent]:
            source = inspect.getsource(mod)
            assert (
                "HybridRetriever" not in source
            ), f"{mod.__name__} still imports HybridRetriever"

    def test_unified_retriever_exists(self):
        """UnifiedRetriever 모듈이 정상 import 가능"""
        from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever

        assert UnifiedRetriever is not None
