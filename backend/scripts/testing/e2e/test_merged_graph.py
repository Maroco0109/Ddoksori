"""
E2E tests for MAS graph integration after retrieval agent merge.
Tests graph structure, node registration, and tool integration.

실행:
    PYTHONPATH=backend conda run -n dsr pytest backend/scripts/testing/e2e/test_merged_graph.py -v
"""

import sys
from pathlib import Path

import pytest

# Ensure backend is on sys.path
_backend = str(Path(__file__).parent.parent.parent.parent)
if _backend not in sys.path:
    sys.path.insert(0, _backend)


# ============================================================
# Test 1: MAS 그래프 Retrieval 통합 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestMASGraphRetrieval:
    """MAS 그래프에 Retrieval Agent가 올바르게 통합되었는지 검증합니다."""

    def test_graph_imports(self):
        """MAS 그래프 빌더 임포트 검증"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        assert create_mas_supervisor_graph is not None
        assert callable(create_mas_supervisor_graph)

    def test_retrieval_agents_registered(self):
        """그래프에 retrieval 관련 노드가 등록되었는지 확인"""
        from app.supervisor.graph_mas import reset_mas_graph, create_mas_supervisor_graph

        reset_mas_graph()
        graph = create_mas_supervisor_graph()

        node_names = set(graph.nodes.keys())

        # 4개 retrieval agent 노드가 있어야 함
        expected_retrieval_nodes = {
            "retrieval_law",
            "retrieval_criteria",
            "retrieval_case",
        }

        for node in expected_retrieval_nodes:
            assert node in node_names, \
                f"Retrieval node '{node}' not found in graph nodes: {node_names}"

    def test_retrieval_merge_node_exists(self):
        """retrieval_merge 노드가 존재하는지 확인"""
        from app.supervisor.graph_mas import reset_mas_graph, create_mas_supervisor_graph

        reset_mas_graph()
        graph = create_mas_supervisor_graph()
        node_names = set(graph.nodes.keys())

        assert "retrieval_merge" in node_names, \
            "retrieval_merge node not found in graph"

    def test_graph_compiles_successfully(self):
        """그래프가 오류 없이 컴파일되는지 확인"""
        from app.supervisor.graph_mas import reset_mas_graph, create_mas_supervisor_graph

        reset_mas_graph()
        graph = create_mas_supervisor_graph()

        # 그래프 컴파일 확인 (실제로 노드가 연결되어 있는지)
        assert graph is not None
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0


# ============================================================
# Test 2: SimilarChunkResult 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestSimilarChunkResult:
    """SimilarChunkResult 데이터 클래스가 올바르게 정의되었는지 검증합니다."""

    def test_similar_chunk_result_importable(self):
        """SimilarChunkResult 임포트 검증"""
        from app.agents.retrieval.tools.rds_internal_retriever import SimilarChunkResult

        assert SimilarChunkResult is not None

    def test_similar_chunk_result_fields(self):
        """SimilarChunkResult가 예상된 필드를 가지고 있는지 확인"""
        from app.agents.retrieval.tools.rds_internal_retriever import SimilarChunkResult
        from dataclasses import fields

        field_names = {f.name for f in fields(SimilarChunkResult)}

        expected_fields = {
            "chunk_id",
            "dataset_type",
            "text",
            "similarity",
            "law_name",
            "chunk_type",
            "category",
            "document_type",
            "source_url",
            "source_file",
            "printed_page",
            "source_year",
            "metadata",
        }

        assert expected_fields.issubset(field_names), \
            f"Missing fields: {expected_fields - field_names}"

    def test_similar_chunk_result_instantiation(self):
        """SimilarChunkResult가 올바르게 인스턴스화되는지 확인"""
        from app.agents.retrieval.tools.rds_internal_retriever import SimilarChunkResult

        result = SimilarChunkResult(
            chunk_id="test_chunk_001",
            dataset_type="law",
            text="테스트 텍스트",
            similarity=0.85,
            law_name="소비자기본법",
            chunk_type="article",
            category=None,
            document_type="법령",
            source_url="https://example.com",
            source_file="test.pdf",
            printed_page=1,
            source_year=2024,
            metadata={"key": "value"}
        )

        assert result.chunk_id == "test_chunk_001"
        assert result.dataset_type == "law"
        assert result.similarity == 0.85
        assert result.metadata == {"key": "value"}


# ============================================================
# Test 3: SearchResult 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestSearchResult:
    """SearchResult 데이터 클래스가 올바르게 정의되었는지 검증합니다."""

    def test_search_result_importable(self):
        """SearchResult 임포트 검증"""
        from app.agents.retrieval.tools.retriever import SearchResult

        assert SearchResult is not None

    def test_search_result_fields(self):
        """SearchResult가 예상된 필드를 가지고 있는지 확인"""
        from app.agents.retrieval.tools.retriever import SearchResult
        from dataclasses import fields

        field_names = {f.name for f in fields(SearchResult)}

        expected_fields = {
            "chunk_id",
            "doc_id",
            "chunk_type",
            "content",
            "doc_title",
            "source_org",
            "url",
            "decision_date",
            "similarity",
        }

        assert expected_fields.issubset(field_names), \
            f"Missing fields: {expected_fields - field_names}"


# ============================================================
# Test 4: 통합 Retriever 임포트 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestRetrieverImports:
    """다양한 Retriever 클래스가 올바르게 임포트 가능한지 검증합니다."""

    def test_unified_retriever_importable(self):
        """UnifiedRetriever 임포트 검증"""
        from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever

        assert UnifiedRetriever is not None

    def test_rds_internal_retriever_importable(self):
        """RDSInternalRetriever 임포트 검증"""
        from app.agents.retrieval.tools.rds_internal_retriever import RDSInternalRetriever

        assert RDSInternalRetriever is not None

    def test_law_retriever_importable(self):
        """LawRetriever 임포트 검증 (specialized_retrievers)"""
        from app.agents.retrieval.tools.specialized_retrievers import LawRetriever

        assert LawRetriever is not None

    def test_criteria_retriever_importable(self):
        """CriteriaRetriever 임포트 검증 (specialized_retrievers)"""
        from app.agents.retrieval.tools.specialized_retrievers import CriteriaRetriever

        assert CriteriaRetriever is not None


# ============================================================
# Test 5: Agent 팩토리 함수 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestAgentFactoryFunctions:
    """각 retrieval agent의 팩토리 함수가 올바르게 동작하는지 검증합니다."""

    def test_law_agent_factory(self):
        """law_retrieval_agent 팩토리 인스턴스 검증"""
        from app.agents.retrieval.law_agent import law_retrieval_agent, LawRetrievalAgent

        assert law_retrieval_agent is not None
        assert isinstance(law_retrieval_agent, LawRetrievalAgent)
        assert law_retrieval_agent.agent_name == "retrieval_law"

    def test_criteria_agent_factory(self):
        """criteria_retrieval_agent 팩토리 인스턴스 검증"""
        from app.agents.retrieval.criteria_agent import criteria_retrieval_agent, CriteriaRetrievalAgent

        assert criteria_retrieval_agent is not None
        assert isinstance(criteria_retrieval_agent, CriteriaRetrievalAgent)
        assert criteria_retrieval_agent.agent_name == "retrieval_criteria"

    def test_case_agent_factory(self):
        """case_retrieval_agent 팩토리 인스턴스 검증"""
        from app.agents.retrieval.case_agent import case_retrieval_agent, CaseRetrievalAgent

        assert case_retrieval_agent is not None
        assert isinstance(case_retrieval_agent, CaseRetrievalAgent)
        assert case_retrieval_agent.agent_name == "retrieval_case"

    def test_counsel_agent_factory(self):
        """counsel_retrieval_agent 팩토리 인스턴스 검증"""
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent, CounselRetrievalAgent

        assert counsel_retrieval_agent is not None
        assert isinstance(counsel_retrieval_agent, CounselRetrievalAgent)
        assert counsel_retrieval_agent.agent_name == "retrieval_counsel"


# ============================================================
# Test 6: Hybrid Search 메서드 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestHybridSearchMethods:
    """Law와 Criteria agent가 hybrid_search를 사용하는지 검증합니다."""

    def test_law_agent_uses_hybrid_search(self):
        """LawRetrievalAgent가 hybrid_search를 사용하는지 확인"""
        import inspect
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        source = inspect.getsource(LawRetrievalAgent._execute_search)

        assert "hybrid_search" in source, \
            "LawRetrievalAgent._execute_search must use hybrid_search method"

    def test_criteria_agent_uses_hybrid_search(self):
        """CriteriaRetrievalAgent가 hybrid_search를 사용하는지 확인"""
        import inspect
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        source = inspect.getsource(CriteriaRetrievalAgent._execute_search)

        assert "hybrid_search" in source, \
            "CriteriaRetrievalAgent._execute_search must use hybrid_search method"


# ============================================================
# Test 7: RRF (Reciprocal Rank Fusion) 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestRRFFusion:
    """Law와 Criteria agent가 RRF를 구현하는지 검증합니다."""

    def test_law_agent_implements_rrf(self):
        """LawRetrievalAgent가 RRF를 구현하는지 확인"""
        import inspect
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        source = inspect.getsource(LawRetrievalAgent._execute_search)

        # RRF 관련 키워드 확인
        assert "rrf_k" in source, \
            "LawRetrievalAgent must implement RRF with rrf_k parameter"
        assert "fused_scores" in source or "fused" in source, \
            "LawRetrievalAgent must implement score fusion"

    def test_criteria_agent_implements_rrf(self):
        """CriteriaRetrievalAgent가 RRF를 구현하는지 확인"""
        import inspect
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        source = inspect.getsource(CriteriaRetrievalAgent._execute_search)

        # RRF 관련 키워드 확인
        assert "rrf_k" in source, \
            "CriteriaRetrievalAgent must implement RRF with rrf_k parameter"
        assert "fused_scores" in source or "fused" in source, \
            "CriteriaRetrievalAgent must implement score fusion"


# ============================================================
# Test 8: Base Agent Process Method 검증
# ============================================================

@pytest.mark.e2e
@pytest.mark.unit
class TestBaseAgentProcess:
    """BaseRetrievalAgent의 process 메서드가 올바르게 정의되었는지 검증합니다."""

    def test_base_agent_has_process_method(self):
        """BaseRetrievalAgent가 process 메서드를 가지고 있는지 확인"""
        from app.agents.retrieval.base_retrieval_agent import BaseRetrievalAgent

        assert hasattr(BaseRetrievalAgent, "process"), \
            "BaseRetrievalAgent must have process method"

        method = getattr(BaseRetrievalAgent, "process")
        assert callable(method), \
            "BaseRetrievalAgent.process must be callable"

    def test_all_agents_inherit_process_method(self):
        """모든 retrieval agent가 process 메서드를 상속하는지 확인"""
        from app.agents.retrieval.law_agent import LawRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent_classes = [
            LawRetrievalAgent,
            CriteriaRetrievalAgent,
            CaseRetrievalAgent,
            CounselRetrievalAgent,
        ]

        for agent_cls in agent_classes:
            assert hasattr(agent_cls, "process"), \
                f"{agent_cls.__name__} must have process method"

            method = getattr(agent_cls, "process")
            assert callable(method), \
                f"{agent_cls.__name__}.process must be callable"
