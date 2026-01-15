"""
PR3 Graph Definition 테스트
작성일: 2026-01-14

테스트 대상:
- create_chat_graph: 그래프 구조 검증
- get_graph: 싱글톤 및 컴파일 검증
- 전체 워크플로우 실행 검증
- 멀티턴 세션 검증
"""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest
from typing import cast, Any

from app.orchestrator.state import ChatState, create_initial_state
from app.orchestrator.graph import (
    create_chat_graph,
    get_graph,
    reset_graph,
    _route_after_query_analysis,
    _route_after_review,
)


class TestGraphDefinition:
    def test_graph_has_all_nodes(self):
        graph = create_chat_graph()
        node_names = list(graph.nodes.keys())
        
        expected_nodes = [
            'query_analysis',
            'retrieval', 
            'generation',
            'review',
            'ask_clarification',
        ]
        
        for node in expected_nodes:
            assert node in node_names, f"Missing node: {node}"
    
    def test_graph_compiles_and_runs(self):
        reset_graph()
        compiled = get_graph()
        assert compiled is not None
    
    def test_edges_defined(self):
        graph = create_chat_graph()
        assert len(graph.edges) > 0 or len(graph.branches) > 0


class TestRoutingFunctions:
    def test_route_to_clarification_when_needed(self):
        state: ChatState = cast(Any, {
            'query_analysis': {
                'query_type': 'dispute',
                'keywords': [],
                'agency_hint': 'KCA',
                'needs_clarification': True,
                'missing_fields': ['purchase_item'],
            }
        })
        
        result = _route_after_query_analysis(state)
        assert result == 'ask_clarification'
    
    def test_route_to_retrieval_when_complete(self):
        state: ChatState = cast(Any, {
            'query_analysis': {
                'query_type': 'dispute',
                'keywords': ['환불'],
                'agency_hint': 'KCA',
                'needs_clarification': False,
                'missing_fields': [],
            }
        })
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'
    
    def test_route_to_end_when_review_passed(self):
        from langgraph.graph import END
        state: ChatState = cast(Any, {
            'review': {'passed': True, 'violations': [], 'filtered_answer': None},
            'retry_count': 0,
        })
        
        result = _route_after_review(state)
        assert result == END
    
    def test_route_to_generation_on_retry(self):
        state: ChatState = cast(Any, {
            'review': {'passed': False, 'violations': ['금지 표현'], 'filtered_answer': None},
            'retry_count': 0,
        })
        
        result = _route_after_review(state)
        assert result == 'generation'
    
    def test_route_to_end_after_max_retries(self):
        from langgraph.graph import END
        state: ChatState = cast(Any, {
            'review': {'passed': False, 'violations': ['금지 표현'], 'filtered_answer': None},
            'retry_count': 2,
        })
        
        result = _route_after_review(state)
        assert result == END


class TestGraphExecution:
    def test_general_query_full_flow(self):
        reset_graph()
        graph = get_graph()
        
        initial_state = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        
        config = cast(Any, {"configurable": {"thread_id": "test-general-001"}})
        final_state = graph.invoke(initial_state, config)
        
        assert final_state.get('final_answer') is not None
        assert '똑소리' in final_state.get('final_answer', '')
    
    def test_dispute_query_with_clarification(self):
        reset_graph()
        graph = get_graph()
        
        initial_state = create_initial_state(
            user_query="환불 받고 싶어요",
            chat_type='dispute',
            onboarding=None,
        )
        
        config = cast(Any, {"configurable": {"thread_id": "test-dispute-001"}})
        final_state = graph.invoke(initial_state, config)
        
        query_analysis = final_state.get('query_analysis', {})
        assert query_analysis.get('needs_clarification') == True
        
        final_answer = final_state.get('final_answer', '')
        assert '제품' in final_answer or '서비스' in final_answer or '정보' in final_answer


class TestMultiTurn:
    def test_same_session_can_be_invoked_multiple_times(self):
        reset_graph()
        graph = get_graph()
        session_id = "test-multiturn-001"
        config = cast(Any, {"configurable": {"thread_id": session_id}})
        
        state1 = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        result1 = graph.invoke(state1, config)
        assert result1.get('final_answer') is not None
        
        state2 = create_initial_state(
            user_query="감사합니다",
            chat_type='general',
        )
        result2 = graph.invoke(state2, config)
        assert result2.get('final_answer') is not None
    
    def test_different_sessions_are_independent(self):
        reset_graph()
        graph = get_graph()
        
        config_a = cast(Any, {"configurable": {"thread_id": "session-a"}})
        config_b = cast(Any, {"configurable": {"thread_id": "session-b"}})
        
        state_a = create_initial_state(
            user_query="안녕",
            chat_type='general',
        )
        result_a = graph.invoke(state_a, config_a)
        
        state_b = create_initial_state(
            user_query="환불",
            chat_type='dispute',
        )
        result_b = graph.invoke(state_b, config_b)
        
        assert result_a.get('query_analysis', {}).get('query_type') == 'general'
        assert result_b.get('query_analysis', {}).get('query_type') == 'dispute'


class TestSingletonPattern:
    def test_get_graph_returns_same_instance(self):
        reset_graph()
        graph1 = get_graph()
        graph2 = get_graph()
        assert graph1 is graph2
    
    def test_reset_graph_creates_new_instance(self):
        graph1 = get_graph()
        reset_graph()
        graph2 = get_graph()
        assert graph1 is not graph2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
