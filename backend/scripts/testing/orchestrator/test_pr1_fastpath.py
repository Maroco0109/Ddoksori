"""
PR 1: Fast Path & Architecture Optimization Test
Tests conditional routing after generation node based on query type.
"""

import pytest
from app.orchestrator.routing import route_after_generation
from app.orchestrator.state import ChatState_v2


@pytest.fixture
def base_state() -> ChatState_v2:
    return {
        'user_query': '',
        'mode': 'NEED_RAG',
        'query_analysis_v2': {},
        'search_round': 0,
        'retry_count': 0,
    }


class TestFastPathRouting:
    
    def test_general_chat_skips_review(self, base_state):
        state = base_state.copy()
        state['query_analysis_v2'] = {'query_type': 'general'}
        
        result = route_after_generation(state)
        
        assert result == 'output_guardrail', "General chat should skip review"
    
    def test_system_meta_skips_review(self, base_state):
        state = base_state.copy()
        state['query_analysis_v2'] = {'query_type': 'system_meta'}
        
        result = route_after_generation(state)
        
        assert result == 'output_guardrail', "System meta query should skip review"
    
    def test_dispute_goes_to_review(self, base_state):
        state = base_state.copy()
        state['query_analysis_v2'] = {'query_type': 'dispute'}
        
        result = route_after_generation(state)
        
        assert result == 'review', "Dispute query should go to review"
    
    def test_law_query_goes_to_review(self, base_state):
        state = base_state.copy()
        state['query_analysis_v2'] = {'query_type': 'law'}
        
        result = route_after_generation(state)
        
        assert result == 'review', "Law query should go to review"
    
    def test_criteria_query_goes_to_review(self, base_state):
        state = base_state.copy()
        state['query_analysis_v2'] = {'query_type': 'criteria'}
        
        result = route_after_generation(state)
        
        assert result == 'review', "Criteria query should go to review"
    
    def test_missing_query_analysis_defaults_to_review(self, base_state):
        state = base_state.copy()
        
        result = route_after_generation(state)
        
        assert result == 'review', "Missing query_analysis should default to dispute (review)"
    
    def test_legacy_query_analysis_field_fallback(self, base_state):
        state = base_state.copy()
        state['query_analysis'] = {'query_type': 'general'}
        
        result = route_after_generation(state)
        
        assert result == 'output_guardrail', "Should support legacy query_analysis field"


class TestGraphIntegration:
    
    @pytest.mark.skip(reason="Graph compilation test - requires full environment")
    def test_v2_graph_compiles_with_conditional_edge(self):
        from app.orchestrator.graph import create_v2_chat_graph
        
        graph = create_v2_chat_graph()
        compiled = graph.compile()
        
        assert compiled is not None, "Graph should compile successfully"
    
    @pytest.mark.skip(reason="E2E test - requires DB and LLM")
    def test_general_chat_e2e_skips_review_node(self):
        from app.orchestrator.graph import create_v2_chat_graph
        
        graph = create_v2_chat_graph().compile()
        
        initial_state = {
            'user_query': '안녕하세요',
            'mode': 'NO_RETRIEVAL',
            'query_analysis_v2': {'query_type': 'general'},
        }
        
        result = graph.invoke(initial_state)
        
        node_timings = result.get('_node_timings', {})
        assert 'review' not in node_timings, "Review node should not execute for general chat"
        assert 'generation' in node_timings, "Generation node should execute"
        assert 'output_guardrail' in node_timings, "Output guardrail should execute"
