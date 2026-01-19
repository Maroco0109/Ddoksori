"""
똑소리 프로젝트 - ReAct 패턴 테스트
작성일: 2026-01-17
S2-7: ReAct Orchestrator 단위 테스트

테스트 범위:
1. ReActStep 스키마 테스트
2. react_think_node 규칙 기반 추론 테스트
3. react_act_node 액션 실행 테스트
4. ReAct 그래프 라우팅 테스트
5. ReAct 루프 통합 테스트
"""

import pytest
import os
from typing import Dict, Any
from unittest.mock import patch, MagicMock

from app.orchestrator.state import (
    ChatState,
    ReActStep,
    create_initial_state,
)
from app.orchestrator.nodes.react_think import (
    react_think_node,
    _analyze_retrieval_status,
    _check_similarity_threshold,
    _determine_next_action,
)
from app.orchestrator.nodes.react_act import react_act_node
from app.orchestrator.graph import (
    create_react_chat_graph,
    _route_after_query_analysis_react,
    _route_after_react_think,
)


class TestReActStepSchema:
    """ReActStep TypedDict 스키마 테스트"""

    def test_react_step_structure(self):
        """ReActStep이 올바른 필드를 가지는지 확인"""
        step: ReActStep = {
            'thought': '검색 데이터가 없음. 전체 검색 필요.',
            'action': 'search_all',
            'action_input': {'query': '노트북 환불'},
            'observation': '전체 검색 완료: 분쟁사례 3건, 법령 2건',
        }

        assert 'thought' in step
        assert 'action' in step
        assert 'action_input' in step
        assert 'observation' in step

    def test_initial_state_has_react_fields(self):
        """create_initial_state가 ReAct 필드를 포함하는지 확인"""
        state = create_initial_state(
            user_query="테스트 쿼리",
            chat_type='general',
        )

        assert state.get('react_steps') == []
        assert state.get('current_iteration') == 0
        assert state.get('max_iterations') == 2
        assert state.get('should_continue') is True
        assert state.get('last_thought') is None
        assert state.get('last_action') is None
        assert state.get('last_observation') is None


class TestReactThinkNode:
    """react_think_node 테스트"""

    def test_first_iteration_no_data_returns_search_all(self):
        """첫 번째 반복, 데이터 없음 → search_all 액션"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )

        result = react_think_node(state)

        assert result['last_action'] == 'search_all'
        assert result['should_continue'] is True
        assert result['current_iteration'] == 1
        assert '검색' in result['last_thought']

    def test_max_iterations_reached_stops_loop(self):
        """최대 반복 도달 → 루프 종료"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )
        state['current_iteration'] = 2
        state['max_iterations'] = 2

        result = react_think_node(state)

        assert result['last_action'] is None
        assert result['should_continue'] is False
        assert '최대 반복' in result['last_thought']

    def test_sufficient_data_stops_loop(self):
        """충분한 데이터 → 루프 종료"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )
        state['current_iteration'] = 1
        state['retrieval'] = {
            'disputes': [{'chunk_id': '1', 'similarity': 0.8}],
            'counsels': [{'chunk_id': '2', 'similarity': 0.75}],
            'laws': [{'unit_id': '1'}],
            'criteria': [{'unit_id': '1'}],
            'max_similarity': 0.8,
            'avg_similarity': 0.775,
        }

        result = react_think_node(state)

        assert result['last_action'] is None
        assert result['should_continue'] is False
        assert '충분한 정보' in result['last_thought']

    def test_low_similarity_triggers_additional_search(self):
        """유사도 낮음 → 추가 검색"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )
        state['current_iteration'] = 0
        state['retrieval'] = {
            'disputes': [{'chunk_id': '1', 'similarity': 0.4}],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'max_similarity': 0.4,
            'avg_similarity': 0.4,
        }

        result = react_think_node(state)

        assert result['last_action'] == 'search_all'
        assert result['should_continue'] is True

    def test_missing_criteria_triggers_criteria_search(self):
        """분쟁사례 있지만 기준 없음 → 기준 검색"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )
        state['current_iteration'] = 1
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = {
            'disputes': [{'chunk_id': '1', 'similarity': 0.8}],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'max_similarity': 0.8,
            'avg_similarity': 0.8,
        }

        result = react_think_node(state)

        assert result['last_action'] == 'search_criteria'
        assert result['should_continue'] is True


class TestAnalyzeRetrievalStatus:
    """_analyze_retrieval_status 헬퍼 함수 테스트"""

    def test_empty_state_returns_all_false(self):
        """빈 상태 → 모든 필드 False"""
        state = create_initial_state(user_query="테스트", chat_type='general')

        status = _analyze_retrieval_status(state)

        assert status['has_disputes'] is False
        assert status['has_counsels'] is False
        assert status['has_laws'] is False
        assert status['has_criteria'] is False

    def test_with_data_returns_correct_status(self):
        """데이터 있음 → 해당 필드 True"""
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['retrieval'] = {
            'disputes': [{'id': 1}],
            'counsels': [],
            'laws': [{'id': 1}],
            'criteria': [],
        }

        status = _analyze_retrieval_status(state)

        assert status['has_disputes'] is True
        assert status['has_counsels'] is False
        assert status['has_laws'] is True
        assert status['has_criteria'] is False


class TestCheckSimilarityThreshold:
    """_check_similarity_threshold 헬퍼 함수 테스트"""

    def test_above_threshold_returns_true(self):
        """유사도 >= 임계값 → True"""
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['retrieval'] = {'max_similarity': 0.6}

        assert _check_similarity_threshold(state, threshold=0.55) is True

    def test_below_threshold_returns_false(self):
        """유사도 < 임계값 → False"""
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['retrieval'] = {'max_similarity': 0.4}

        assert _check_similarity_threshold(state, threshold=0.55) is False


class TestReactActNode:
    """react_act_node 테스트"""

    @patch('app.orchestrator.nodes.react_act._execute_search_all')
    def test_search_all_action(self, mock_search):
        """search_all 액션 실행 테스트"""
        mock_search.return_value = (
            {
                'disputes': [{'chunk_id': '1', 'similarity': 0.8}],
                'counsels': [],
                'laws': [],
                'criteria': [],
            },
            '전체 검색 완료: 분쟁사례 1건, 상담사례 0건, 법령 0건, 기준 0건'
        )

        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )
        state['last_action'] = 'search_all'
        state['last_thought'] = '검색 데이터 없음'

        result = react_act_node(state)

        assert 'retrieval' in result
        assert 'sources' in result
        assert 'last_observation' in result
        assert 'react_steps' in result
        assert len(result['react_steps']) == 1
        assert result['react_steps'][0]['action'] == 'search_all'

    @patch('app.orchestrator.nodes.react_act._execute_search_criteria')
    def test_search_criteria_action(self, mock_search):
        """search_criteria 액션 실행 테스트"""
        mock_search.return_value = (
            [{'unit_id': '1', 'category': '전자제품'}],
            '분쟁해결기준 1건 검색 완료'
        )

        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )
        state['last_action'] = 'search_criteria'
        state['last_thought'] = '기준 검색 필요'
        state['retrieval'] = {
            'disputes': [{'chunk_id': '1'}],
            'counsels': [],
            'laws': [],
            'criteria': [],
        }

        result = react_act_node(state)

        assert 'retrieval' in result
        assert result['retrieval'].get('criteria') is not None
        assert result['react_steps'][0]['action'] == 'search_criteria'

    def test_unknown_action_returns_error(self):
        """알 수 없는 액션 → 에러 메시지"""
        state = create_initial_state(
            user_query="테스트",
            chat_type='general',
        )
        state['last_action'] = 'invalid_action'
        state['last_thought'] = '테스트'

        result = react_act_node(state)

        assert '알 수 없는 액션' in result['last_observation']


class TestReactGraphRouting:
    """ReAct 그래프 라우팅 테스트"""

    def test_route_after_query_analysis_to_react_think(self):
        """query_analysis 후 react_think로 라우팅"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': False,
            'extracted_info': {'purchase_item': '노트북'},
        }

        result = _route_after_query_analysis_react(state)

        assert result == 'react_think'

    def test_route_after_query_analysis_to_clarification(self):
        """query_analysis 후 ask_clarification으로 라우팅"""
        state = create_initial_state(
            user_query="환불해주세요",
            chat_type='dispute',
        )
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': True,
            'extracted_info': {},
        }

        result = _route_after_query_analysis_react(state)

        assert result == 'ask_clarification'

    def test_route_after_react_think_to_act(self):
        """react_think 후 react_act로 라우팅"""
        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )
        state['should_continue'] = True
        state['last_action'] = 'search_all'

        result = _route_after_react_think(state)

        assert result == 'react_act'

    def test_route_after_react_think_to_generation(self):
        """react_think 후 generation으로 라우팅"""
        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )
        state['should_continue'] = False
        state['last_action'] = None

        result = _route_after_react_think(state)

        assert result == 'generation'

    def test_route_after_react_think_to_clarification(self):
        """react_think 후 ask_clarification으로 라우팅"""
        state = create_initial_state(
            user_query="환불",
            chat_type='dispute',
        )
        state['should_continue'] = True
        state['last_action'] = 'ask_clarification'

        result = _route_after_react_think(state)

        assert result == 'ask_clarification'


class TestReactGraphStructure:
    """ReAct 그래프 구조 테스트"""

    def test_react_graph_has_required_nodes(self):
        """ReAct 그래프가 필수 노드를 포함하는지 확인"""
        graph = create_react_chat_graph()

        node_names = list(graph.nodes.keys())

        assert 'query_analysis' in node_names
        assert 'react_think' in node_names
        assert 'react_act' in node_names
        assert 'generation' in node_names
        assert 'review' in node_names
        assert 'ask_clarification' in node_names

    def test_react_graph_entry_point(self):
        """ReAct 그래프 진입점이 query_analysis인지 확인"""
        from langgraph.checkpoint.memory import MemorySaver

        graph = create_react_chat_graph()
        compiled = graph.compile(checkpointer=MemorySaver())

        # 컴파일된 그래프의 노드 확인으로 구조 검증
        # __start__ 노드에서 query_analysis로의 엣지가 있어야 함
        node_names = list(graph.nodes.keys())
        assert 'query_analysis' in node_names
        # 진입점 설정 확인 (edges에서 __start__가 query_analysis를 가리킴)
        edges = graph.edges
        start_edge_found = any(
            edge[0] == '__start__' and edge[1] == 'query_analysis'
            for edge in edges
        )
        assert start_edge_found, "Entry point should be query_analysis"


class TestDetermineNextAction:
    """_determine_next_action 헬퍼 함수 테스트"""

    def test_max_iteration_reached(self):
        """최대 반복 도달 시 종료"""
        thought, action, should_continue = _determine_next_action(
            iteration=2,
            max_iterations=2,
            retrieval_status={'has_disputes': False, 'has_counsels': False, 'has_laws': False, 'has_criteria': False},
            has_good_similarity=False,
            query_type='dispute',
        )

        assert action is None
        assert should_continue is False

    def test_first_iteration_no_data(self):
        """첫 반복, 데이터 없음 → search_all"""
        thought, action, should_continue = _determine_next_action(
            iteration=0,
            max_iterations=2,
            retrieval_status={'has_disputes': False, 'has_counsels': False, 'has_laws': False, 'has_criteria': False},
            has_good_similarity=False,
            query_type='dispute',
        )

        assert action == 'search_all'
        assert should_continue is True

    def test_dispute_query_missing_criteria(self):
        """분쟁 쿼리, 기준 부족 → search_criteria"""
        thought, action, should_continue = _determine_next_action(
            iteration=1,
            max_iterations=2,
            retrieval_status={'has_disputes': True, 'has_counsels': False, 'has_laws': False, 'has_criteria': False},
            has_good_similarity=True,
            query_type='dispute',
        )

        assert action == 'search_criteria'
        assert should_continue is True

    def test_sufficient_data_ends_loop(self):
        """충분한 데이터 → 루프 종료"""
        thought, action, should_continue = _determine_next_action(
            iteration=1,
            max_iterations=2,
            retrieval_status={'has_disputes': True, 'has_counsels': True, 'has_laws': True, 'has_criteria': True},
            has_good_similarity=True,
            query_type='dispute',
        )

        assert action is None
        assert should_continue is False
