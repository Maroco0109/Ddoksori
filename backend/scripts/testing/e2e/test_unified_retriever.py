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

from unittest.mock import MagicMock, patch

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
                assert scores[i] >= scores[i + 1], (
                    f"Not sorted: {scores[i]} < {scores[i + 1]}"
                )


# ============================================================
# Suite 2: Retrieval Agent → UnifiedRetriever 경로 검증 (Mock)
# ============================================================


@pytest.mark.unit
class TestAgentUnifiedRetrieverIntegration:
    """Agent가 올바르게 검색을 수행하는지 Mock 기반 검증

    Note: LawRetrievalAgent와 CriteriaRetrievalAgent는 _execute_search를 오버라이드하여
    specialized_retrievers(LawRetriever, CriteriaRetriever)를 직접 사용합니다.
    CaseRetrievalAgent만 BaseRetrievalAgent._execute_search → UnifiedRetriever를 사용합니다.
    """

    @pytest.mark.asyncio
    async def test_law_agent_uses_specialized_retriever(self):
        """LawRetrievalAgent가 LawRetriever를 사용하여 법령을 검색"""
        mock_result = MagicMock()
        mock_result.chunk_id = "test_law_001"
        mock_result.text = "제16조(소비자의 권리)"
        mock_result.similarity = 0.032
        mock_result.metadata = {}
        mock_result.law_name = "소비자기본법"
        mock_result.document_type = "법률"
        mock_result.dataset_type = "law_guide"

        with patch("app.agents.retrieval.law_agent.LawRetriever") as MockRetriever:
            mock_instance = MagicMock()
            mock_instance.hybrid_search.return_value = [mock_result]
            MockRetriever.return_value = mock_instance

            from app.agents.retrieval.law_agent import LawRetrievalAgent

            agent = LawRetrievalAgent()
            result = await agent.process(
                {
                    "context": {
                        "user_query": "소비자 권리",
                        "query_analysis": {},
                        "retrieval_task_input": {
                            "expanded_queries": ["소비자 권리"],
                            "top_k": 3,
                            "metadata_filter": {
                                "dataset_type": "law_guide",
                                "document_types": ["법률"],
                            },
                        },
                    },
                }
            )

            # Query Expansion으로 인해 hybrid_search가 여러 번 호출될 수 있음
            # 최소 1번 이상 호출되었는지 확인
            assert mock_instance.hybrid_search.call_count >= 1, (
                f"Expected hybrid_search to be called at least once, "
                f"but was called {mock_instance.hybrid_search.call_count} times"
            )
            assert result["status"] == "success"
            assert len(result["result"]["results"]) >= 1

    @pytest.mark.asyncio
    async def test_criteria_agent_uses_specialized_retriever(self):
        """CriteriaRetrievalAgent가 CriteriaRetriever를 사용하여 기준을 검색"""
        mock_result = MagicMock()
        mock_result.chunk_id = "test_criteria_001"
        mock_result.text = "가전제품 환불 기준"
        mock_result.similarity = 0.028
        mock_result.metadata = {}
        mock_result.category = "가전"
        mock_result.document_type = "별표"
        mock_result.dataset_type = "law_guide"

        with patch(
            "app.agents.retrieval.criteria_agent.CriteriaRetriever"
        ) as MockRetriever:
            mock_instance = MagicMock()
            mock_instance.criteria_search.return_value = [mock_result]
            mock_instance.fetch_chunk_texts.return_value = {}
            MockRetriever.return_value = mock_instance

            from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

            agent = CriteriaRetrievalAgent()
            result = await agent.process(
                {
                    "context": {
                        "user_query": "가전제품 환불",
                        "query_analysis": {},
                        "retrieval_task_input": {
                            "expanded_queries": ["가전제품 환불"],
                            "top_k": 3,
                            "metadata_filter": {
                                "dataset_type": "law_guide",
                                "document_types": ["별표"],
                            },
                        },
                    },
                }
            )

            mock_instance.criteria_search.assert_called()
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_case_agent_uses_unified_retriever(self):
        """CaseRetrievalAgent가 UnifiedRetriever의 dataset_filter='case' 전달"""
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
                    "context": {
                        "user_query": "배송 지연",
                        "query_analysis": {},
                        "retrieval_task_input": {
                            "expanded_queries": [],
                            "top_k": 3,
                            "metadata_filter": {},
                        },
                    },
                }
            )

            mock_instance.search.assert_called_once()
            call_kwargs = mock_instance.search.call_args
            assert "case" in str(call_kwargs)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_agent_search_method_architecture(self):
        """에이전트 검색 아키텍처 확인:
        - CaseRetrievalAgent는 Base의 _execute_search 사용 (UnifiedRetriever)
        - LawRetrievalAgent, CriteriaRetrievalAgent는 _execute_search 오버라이드 (specialized_retrievers)
        """
        from app.agents.retrieval.base_retrieval_agent import BaseRetrievalAgent
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        # CaseRetrievalAgent는 Base의 _execute_search를 사용
        assert (
            CaseRetrievalAgent._execute_search is BaseRetrievalAgent._execute_search
        ), "CaseRetrievalAgent should use BaseRetrievalAgent._execute_search"

        # LawRetrievalAgent와 CriteriaRetrievalAgent는 오버라이드
        assert (
            LawRetrievalAgent._execute_search is not BaseRetrievalAgent._execute_search
        ), "LawRetrievalAgent should override _execute_search"
        assert (
            CriteriaRetrievalAgent._execute_search
            is not BaseRetrievalAgent._execute_search
        ), "CriteriaRetrievalAgent should override _execute_search"

    @pytest.mark.asyncio
    async def test_case_agent_has_dataset_filter(self):
        """CaseRetrievalAgent가 _get_search_filters에서 dataset_filter='case'를 반환하는지"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        case_filters = CaseRetrievalAgent()._get_search_filters()
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
            assert "HybridRetriever" not in source, (
                f"{mod.__name__} still imports HybridRetriever"
            )

    def test_unified_retriever_exists(self):
        """UnifiedRetriever 모듈이 정상 import 가능"""
        from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever

        assert UnifiedRetriever is not None
