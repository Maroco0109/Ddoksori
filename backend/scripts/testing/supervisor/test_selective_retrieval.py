"""
PR-2: Selective Retrieval 테스트

실행 방법:
    conda run -n dsr pytest backend/scripts/testing/supervisor/test_selective_retrieval.py -v
"""
import pytest
import asyncio
from typing import List

from app.supervisor.graph import get_graph_for_chat_type
from app.agents.query_analysis.agent import QUERY_TYPE_TO_RETRIEVERS


@pytest.fixture
def graph():
    """테스트용 그래프 생성"""
    return get_graph_for_chat_type("general")


class TestQueryTypeToRetrievers:
    """QUERY_TYPE_TO_RETRIEVERS 매핑 검증"""

    def test_law_query_maps_to_law_only(self):
        """law 쿼리는 law retriever만 사용"""
        assert QUERY_TYPE_TO_RETRIEVERS["law"] == ["law"]

    def test_criteria_query_maps_to_law_and_criteria(self):
        """criteria 쿼리는 law + criteria 사용"""
        assert QUERY_TYPE_TO_RETRIEVERS["criteria"] == ["law", "criteria"]

    def test_dispute_query_maps_to_all(self):
        """dispute 쿼리는 전체 retriever 사용"""
        assert QUERY_TYPE_TO_RETRIEVERS["dispute"] == ["law", "criteria", "case"]

    def test_general_query_maps_to_empty(self):
        """general 쿼리는 검색 불필요"""
        assert QUERY_TYPE_TO_RETRIEVERS["general"] == []

    def test_system_meta_query_maps_to_empty(self):
        """system_meta 쿼리는 검색 불필요"""
        assert QUERY_TYPE_TO_RETRIEVERS["system_meta"] == []

    def test_ambiguous_query_maps_to_law_and_criteria(self):
        """ambiguous 쿼리는 law + criteria 사용"""
        assert QUERY_TYPE_TO_RETRIEVERS["ambiguous"] == ["law", "criteria"]


class TestRetrieverTypesInQueryAnalysis:
    """Query Analysis 결과에 retriever_types 포함 검증"""

    def test_query_analysis_has_retriever_types_field(self, graph):
        """쿼리 분석 결과에 retriever_types 필드 포함"""
        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": "안녕"}]},
                config={"configurable": {"thread_id": "test-retriever-types"}}
            )

        result = asyncio.run(run_test())
        query_analysis = result.get("query_analysis", {})

        # retriever_types 필드 존재
        assert "retriever_types" in query_analysis, \
            "query_analysis should have 'retriever_types' field"


class TestSelectiveFanOut:
    """Selective Fan-out 동작 검증"""

    @pytest.mark.parametrize("query,expected_contains", [
        ("소비자기본법 제10조", ["law"]),  # law 쿼리
        ("안녕", []),  # general 쿼리 (NO_RETRIEVAL)
    ])
    def test_retriever_selection_by_query(
        self, graph, query: str, expected_contains: List[str]
    ):
        """쿼리별 retriever 선택 검증"""
        async def run_test():
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": query}]},
                config={"configurable": {"thread_id": f"test-selective-{query[:5]}"}}
            )

        result = asyncio.run(run_test())

        query_analysis = result.get("query_analysis", {})
        retriever_types = query_analysis.get("retriever_types", [])

        for expected in expected_contains:
            assert expected in retriever_types, \
                f"Query '{query}' should use '{expected}' retriever, got {retriever_types}"

        print(f"✓ '{query}' → retriever_types={retriever_types}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
