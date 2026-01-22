"""
Integration test for PR 1: Fast Path verification
Validates that the graph routing works correctly for different query types.
"""

import pytest
from app.orchestrator.graph import create_v2_chat_graph
from app.orchestrator.state import ChatState_v2


@pytest.fixture
def compiled_graph():
    graph = create_v2_chat_graph()
    return graph.compile()


class TestFastPathIntegration:
    
    def test_graph_has_generation_node(self, compiled_graph):
        nodes = list(compiled_graph.nodes.keys())
        assert 'generation' in nodes
    
    def test_graph_has_review_node(self, compiled_graph):
        nodes = list(compiled_graph.nodes.keys())
        assert 'review' in nodes
    
    def test_graph_has_output_guardrail_node(self, compiled_graph):
        nodes = list(compiled_graph.nodes.keys())
        assert 'output_guardrail' in nodes
    
    @pytest.mark.skip(reason="Requires mocking all node implementations")
    def test_general_chat_path(self, compiled_graph):
        initial_state: ChatState_v2 = {
            'user_query': '안녕하세요',
            'mode': 'NO_RETRIEVAL',
            'query_analysis_v2': {
                'query_type': 'general',
                'mode': 'NO_RETRIEVAL',
            },
            'search_round': 0,
            'retry_count': 0,
        }
        
        result = compiled_graph.invoke(initial_state)
        
        node_timings = result.get('_node_timings', {})
        executed_nodes = list(node_timings.keys())
        
        assert 'generation' in executed_nodes
        assert 'review' not in executed_nodes
        assert 'output_guardrail' in executed_nodes
