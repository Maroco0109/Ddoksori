import pytest
from unittest.mock import patch, MagicMock

from app.orchestrator.state import (
    ChatState_v2,
    create_initial_state_v2,
    QueryAnalysisResult_v2,
    SearchPlan,
)
from app.orchestrator.nodes.search_plan import (
    search_plan_node,
    _select_retrievers,
    _determine_top_k,
    _should_rerank,
    RETRIEVER_TYPE_STRUCTURED,
    RETRIEVER_TYPE_HYBRID,
    RETRIEVER_TYPE_LAW,
    RETRIEVER_TYPE_CRITERIA,
    RETRIEVER_TYPE_DISPUTE,
    RETRIEVER_TYPE_COUNSEL,
)
from app.agents.retrieval.agent import (
    retrieval_node_v2,
    _build_search_query_from_plan,
    _merge_retrieval_results,
    _execute_retrieval_by_type,
)


class TestRetrieverSelection:
    def test_dispute_type_selects_hybrid_dispute_counsel(self):
        retrievers = _select_retrievers('dispute')
        assert RETRIEVER_TYPE_HYBRID in retrievers
        assert RETRIEVER_TYPE_DISPUTE in retrievers
        assert RETRIEVER_TYPE_COUNSEL in retrievers

    def test_law_type_selects_law_hybrid(self):
        retrievers = _select_retrievers('law')
        assert RETRIEVER_TYPE_LAW in retrievers
        assert RETRIEVER_TYPE_HYBRID in retrievers

    def test_criteria_type_selects_criteria_hybrid(self):
        retrievers = _select_retrievers('criteria')
        assert RETRIEVER_TYPE_CRITERIA in retrievers
        assert RETRIEVER_TYPE_HYBRID in retrievers

    def test_general_type_selects_hybrid_only(self):
        retrievers = _select_retrievers('general')
        assert retrievers == [RETRIEVER_TYPE_HYBRID]

    def test_keywords_add_law_retriever(self):
        retrievers = _select_retrievers('dispute', keywords=['법률', '소비자보호법'])
        assert RETRIEVER_TYPE_LAW in retrievers

    def test_keywords_add_criteria_retriever(self):
        retrievers = _select_retrievers('dispute', keywords=['환불', '위약금', '기준'])
        assert RETRIEVER_TYPE_CRITERIA in retrievers


class TestTopKDetermination:
    def test_dispute_default_top_k(self):
        assert _determine_top_k('dispute', has_filters=False) == 10

    def test_law_default_top_k(self):
        assert _determine_top_k('law', has_filters=False) == 5

    def test_general_default_top_k(self):
        assert _determine_top_k('general', has_filters=False) == 5

    def test_with_filters_increases_top_k(self):
        without = _determine_top_k('dispute', has_filters=False)
        with_filters = _determine_top_k('dispute', has_filters=True)
        assert with_filters > without

    def test_top_k_max_limit(self):
        top_k = _determine_top_k('dispute', has_filters=True)
        assert top_k <= 20


class TestRerankDecision:
    def test_dispute_should_rerank(self):
        assert _should_rerank('dispute') is True

    def test_law_should_rerank(self):
        assert _should_rerank('law') is True

    def test_criteria_should_rerank(self):
        assert _should_rerank('criteria') is True

    def test_general_should_not_rerank(self):
        assert _should_rerank('general') is False


class TestSearchPlanNode:
    def test_creates_plan_with_dispute_analysis(self):
        state = create_initial_state_v2("헬스장 환불")
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'uncertainties': [],
            'need_evidence': True,
            'required_slots': [],
            'filters_candidate': {},
            'sql_params_candidate': {},
            'query_type': 'dispute',
            'keywords': ['헬스장', '환불'],
            'agency_hint': 'KCA',
            'rewritten_query': '헬스장 환불 분쟁조정',
            'search_queries': ['헬스장 환불'],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert RETRIEVER_TYPE_HYBRID in plan['retrievers']
        assert RETRIEVER_TYPE_DISPUTE in plan['retrievers']
        assert plan['top_k'] == 10
        assert plan['rerank'] is True
        assert plan['query'] == '헬스장 환불 분쟁조정'

    def test_creates_plan_with_law_analysis(self):
        state = create_initial_state_v2("소비자보호법 조항")
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'uncertainties': [],
            'need_evidence': True,
            'required_slots': [],
            'filters_candidate': {},
            'sql_params_candidate': {},
            'query_type': 'law',
            'keywords': ['소비자보호법', '조항'],
            'agency_hint': None,
            'rewritten_query': '소비자보호법 조항 조문',
            'search_queries': [],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert RETRIEVER_TYPE_LAW in plan['retrievers']
        assert plan['top_k'] == 5

    def test_round_increases_top_k(self):
        state = create_initial_state_v2("헬스장 환불")
        state['search_round'] = 1
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'uncertainties': [],
            'need_evidence': True,
            'required_slots': [],
            'filters_candidate': {},
            'sql_params_candidate': {},
            'query_type': 'dispute',
            'keywords': [],
            'agency_hint': 'KCA',
            'rewritten_query': '헬스장 환불',
            'search_queries': ['헬스장 환불', '헬스 해지 위약금'],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert plan['top_k'] == 15
        assert plan['query'] == '헬스 해지 위약금'


class TestBuildSearchQueryFromPlan:
    def test_uses_plan_query_if_present(self):
        state = create_initial_state_v2("원본 쿼리")
        plan: SearchPlan = {
            'retrievers': ['hybrid'],
            'top_k': 10,
            'rerank': True,
            'rounds_budget': 3,
            'time_budget_ms': 10000,
            'filters': {},
            'query': '재작성된 쿼리',
        }
        
        query = _build_search_query_from_plan(state, plan)
        assert query == '재작성된 쿼리'

    def test_falls_back_to_state_query(self):
        state = create_initial_state_v2("원본 쿼리")
        plan: SearchPlan = {
            'retrievers': ['hybrid'],
            'top_k': 10,
            'rerank': True,
            'rounds_budget': 3,
            'time_budget_ms': 10000,
            'filters': {},
        }
        
        query = _build_search_query_from_plan(state, plan)
        assert query == '원본 쿼리'

    def test_no_plan_uses_state_query(self):
        state = create_initial_state_v2("원본 쿼리")
        query = _build_search_query_from_plan(state, None)
        assert query == '원본 쿼리'


class TestMergeRetrievalResults:
    def test_merges_disputes_from_multiple_results(self):
        results = [
            {
                'agency': {'name': 'KCA'},
                'disputes': [{'chunk_id': 'd1', 'content': 'dispute 1'}],
                'counsels': [],
                'laws': [],
                'criteria': [],
            },
            {
                'agency': {},
                'disputes': [{'chunk_id': 'd2', 'content': 'dispute 2'}],
                'counsels': [],
                'laws': [],
                'criteria': [],
            },
        ]
        
        merged = _merge_retrieval_results(results)
        
        assert len(merged['disputes']) == 2
        assert merged['agency']['name'] == 'KCA'

    def test_deduplicates_by_chunk_id(self):
        results = [
            {
                'agency': {},
                'disputes': [{'chunk_id': 'd1', 'content': 'dispute 1'}],
                'counsels': [],
                'laws': [],
                'criteria': [],
            },
            {
                'agency': {},
                'disputes': [{'chunk_id': 'd1', 'content': 'duplicate'}],
                'counsels': [],
                'laws': [],
                'criteria': [],
            },
        ]
        
        merged = _merge_retrieval_results(results)
        
        assert len(merged['disputes']) == 1

    def test_merges_all_sections(self):
        results = [
            {
                'agency': {'name': 'KCA'},
                'disputes': [{'chunk_id': 'd1'}],
                'counsels': [{'chunk_id': 'c1'}],
                'laws': [{'unit_id': 'l1'}],
                'criteria': [{'unit_id': 'cr1'}],
            },
        ]
        
        merged = _merge_retrieval_results(results)
        
        assert len(merged['disputes']) == 1
        assert len(merged['counsels']) == 1
        assert len(merged['laws']) == 1
        assert len(merged['criteria']) == 1


class TestRetrievalNodeV2:
    def test_no_retrieval_mode_returns_empty(self):
        state = create_initial_state_v2("안녕하세요")
        state['mode'] = 'NO_RETRIEVAL'
        
        result = retrieval_node_v2(state)
        
        assert result['retrieval']['disputes'] == []
        assert result['retrieval']['counsels'] == []
        assert result['sources'] == []

    def test_uses_search_plan_retrievers(self):
        state = create_initial_state_v2("테스트 쿼리")
        state['mode'] = 'NEED_RAG'
        plan: SearchPlan = {
            'retrievers': [RETRIEVER_TYPE_STRUCTURED],
            'top_k': 5,
            'rerank': True,
            'rounds_budget': 3,
            'time_budget_ms': 10000,
            'filters': {},
            'query': '테스트 쿼리',
        }
        state['search_plan'] = plan
        
        with patch('app.agents.retrieval.agent._execute_retrieval_by_type') as mock_exec:
            mock_exec.return_value = {
                'agency': {},
                'disputes': [],
                'counsels': [],
                'laws': [],
                'criteria': [],
            }
            
            retrieval_node_v2(state)
            
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args
            assert call_args[1]['retriever_type'] == RETRIEVER_TYPE_STRUCTURED
            assert call_args[1]['top_k'] == 5

    def test_handles_error_gracefully(self):
        state = create_initial_state_v2("테스트 쿼리")
        state['mode'] = 'NEED_RAG'
        
        with patch('app.agents.retrieval.agent._execute_retrieval_by_type') as mock_exec:
            mock_exec.side_effect = Exception("DB connection failed")
            
            result = retrieval_node_v2(state)
            
            assert result['retrieval']['disputes'] == []
            assert result['sources'] == []


class TestV2GraphWithRetrieval:
    def test_v2_graph_uses_retrieval_node_v2(self):
        from app.orchestrator.graph import create_v2_chat_graph
        
        graph = create_v2_chat_graph()
        nodes = list(graph.nodes.keys())
        
        assert 'retrieval' in nodes
        assert 'search_plan' in nodes
        assert 'sufficiency' in nodes


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-p', 'no:asyncio'])
