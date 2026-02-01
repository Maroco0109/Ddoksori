"""
Phase 6: E2E 통합 테스트 - 전체 워크플로우 검증
작성일: 2026-01-26

테스트 대상:
- MAS Supervisor Graph 전체 흐름
- Feature Flag 기반 그래프 전환
- 분쟁 질의 / 일반 질의 처리
- Supervisor 규칙 기반 fallback
- 4개 Retrieval Agent 병렬 실행

실행 방법:
    # E2E 테스트 (Docker DB 필요)
    pytest scripts/testing/orchestrator/test_e2e_queries.py -m e2e -v

    # Unit 테스트만 (DB 불필요)
    pytest scripts/testing/orchestrator/test_e2e_queries.py -m unit -v
"""

import sys
from pathlib import Path
import os
from unittest.mock import Mock, patch, MagicMock
import time

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest
from typing import Dict, Any, List

# Unit 테스트 마커 적용 (DB 없이 실행 가능)
pytestmark = pytest.mark.unit


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_supervisor_node():
    """SupervisorNode Mock - LLM 없이 규칙 기반 fallback 사용"""
    from app.supervisor.nodes.supervisor import SupervisorNode
    return SupervisorNode(llm=None)


@pytest.fixture
def mock_dispute_state() -> Dict[str, Any]:
    """분쟁 질의용 초기 상태"""
    from app.supervisor.state import create_initial_state
    return create_initial_state(
        user_query="노트북을 샀는데 일주일 만에 고장났어요. 환불 가능한가요?",
        chat_type='dispute',
        onboarding={'purchase_item': '노트북', 'dispute_type': '환불'}
    )


@pytest.fixture
def mock_general_state() -> Dict[str, Any]:
    """일반 질의용 초기 상태"""
    from app.supervisor.state import create_initial_state
    return create_initial_state(
        user_query="안녕하세요, 반갑습니다.",
        chat_type='general'
    )


@pytest.fixture
def mock_retrieval_results() -> List[Dict[str, Any]]:
    """Mock Retrieval 결과 (v2: 3개 Agent — counsel 제거)"""
    return [
        {
            'source': 'law',
            'documents': [
                {'content': '전자상거래법 제17조', 'similarity': 0.85},
            ],
            'max_similarity': 0.85,
            'avg_similarity': 0.85,
            'search_time_ms': 50.0,
        },
        {
            'source': 'criteria',
            'documents': [
                {'content': '환불 기준표', 'similarity': 0.78},
            ],
            'max_similarity': 0.78,
            'avg_similarity': 0.78,
            'search_time_ms': 45.0,
        },
        {
            'source': 'case',
            'documents': [],
            'max_similarity': 0.0,
            'avg_similarity': 0.0,
            'search_time_ms': 30.0,
        },
    ]


# ============================================================================
# E2E Test: 분쟁 질의 전체 플로우
# ============================================================================

class TestE2EDisputeQueryFullFlow:
    """분쟁 질의 전체 워크플로우 테스트"""

    def test_supervisor_processes_dispute_query(
        self, mock_supervisor_node, mock_dispute_state
    ):
        """
        분쟁 질의가 Supervisor를 통해 정상 처리되는지 검증

        Expected flow (v2, _rule_based_fallback):
        supervisor → retrieval_team → supervisor → answer_drafter →
        supervisor → legal_reviewer → supervisor → output_guardrail

        Note: query_analyst는 decide_next_action에서 처리됨.
        _rule_based_fallback은 mode 기반 2-전략 라우팅으로, NEED_RAG 시
        retrieval → generation → review → respond 순서를 따름.
        """
        # 초기 상태에 supervisor 상태 설정
        mock_dispute_state['supervisor'] = {
            'current_phase': 'analyzing',
            'agent_messages': [],
            'pending_tasks': ['retrieve_documents', 'generate_answer', 'review_answer'],
            'completed_tasks': [],
            'supervisor_reasoning': 'Starting dispute resolution workflow',
            'next_agent': None,
            'iteration_count': 0,
        }
        mock_dispute_state['mode'] = 'NEED_RAG'

        # 첫 번째 결정: retrieval_team 호출 (NEED_RAG 모드, retrieval 없음)
        decision1 = mock_supervisor_node._rule_based_fallback(mock_dispute_state)

        assert decision1['action'] == 'call_agent'
        assert decision1['target_agent'] == 'retrieval_team'

    def test_supervisor_calls_retrieval_when_no_retrieval_result(
        self, mock_supervisor_node, mock_dispute_state
    ):
        """retrieval 결과 없을 때 retrieval_team 호출 검증"""
        mock_dispute_state['supervisor'] = {
            'current_phase': 'analyzing',
            'agent_messages': [],
            'pending_tasks': ['retrieve_documents', 'generate_answer', 'review_answer'],
            'completed_tasks': [],
            'supervisor_reasoning': 'No retrieval result, proceeding to retrieval',
            'next_agent': None,
            'iteration_count': 1,
        }
        mock_dispute_state['mode'] = 'NEED_RAG'
        mock_dispute_state['query_analysis'] = {
            'query_type': 'dispute',
            'keywords': ['노트북', '환불', '고장'],
        }

        decision = mock_supervisor_node._rule_based_fallback(mock_dispute_state)

        assert decision['action'] == 'call_agent'
        assert decision['target_agent'] == 'retrieval_team'

    def test_supervisor_calls_generation_after_retrieval(
        self, mock_supervisor_node, mock_dispute_state, mock_retrieval_results
    ):
        """retrieval 완료 후 answer_drafter 호출 검증"""
        mock_dispute_state['supervisor'] = {
            'current_phase': 'retrieving',
            'agent_messages': [],
            'pending_tasks': ['generate_answer', 'review_answer'],
            'completed_tasks': ['retrieval_team'],
            'supervisor_reasoning': 'Documents retrieved, generating answer',
            'next_agent': None,
            'iteration_count': 2,
        }
        mock_dispute_state['mode'] = 'NEED_RAG'
        mock_dispute_state['individual_retrieval_results'] = mock_retrieval_results
        # _full_pipeline_decision checks 'retrieval' field, not just completed_tasks
        mock_dispute_state['retrieval'] = {
            'laws': [{'content': '전자상거래법 제17조'}],
            'criteria': [{'content': '환불 기준표'}],
            'disputes': [],
            'counsels': [{'content': '상담 사례'}],
            'max_similarity': 0.85,
        }

        decision = mock_supervisor_node._rule_based_fallback(mock_dispute_state)

        assert decision['action'] == 'call_agent'
        assert decision['target_agent'] == 'answer_drafter'


# ============================================================================
# E2E Test: 일반 질의 Fast Path
# ============================================================================

class TestE2EGeneralQueryFastPath:
    """일반 질의 Fast Path 테스트 - legal_review 생략"""

    @pytest.mark.skip(reason="Legacy routing removed in Phase 7 - MAS Supervisor handles routing")
    def test_general_query_skips_legal_review(self, mock_general_state):
        """[DEPRECATED] Legacy 라우팅 테스트 - MAS Supervisor로 대체됨"""
        pass

    @pytest.mark.skip(reason="Legacy routing removed in Phase 7 - MAS Supervisor handles routing")
    def test_general_query_no_retrieval_mode(self, mock_general_state):
        """[DEPRECATED] Legacy 라우팅 테스트 - MAS Supervisor로 대체됨"""
        pass


# ============================================================================
# E2E Test: 병렬 Retrieval 실행
# ============================================================================

class TestE2ERetrievalParallelExecution:
    """4개 Retrieval Agent 병렬 실행 테스트"""

    def test_retrieval_fan_out_returns_send_list(self, mock_dispute_state):
        """retrieval_team이 3개 Send 객체 리스트를 반환하는지 검증 (v2: counsel 제거)"""
        mock_dispute_state['supervisor'] = {
            'current_phase': 'retrieving',
            'agent_messages': [],
            'pending_tasks': ['retrieve_documents'],
            'completed_tasks': ['query_analysis'],
            'supervisor_reasoning': 'Starting parallel retrieval',
            'next_agent': 'retrieval_team',
            'iteration_count': 1,
        }
        # _route_mas_supervisor는 query_analysis.get('retriever_types') 참조
        mock_dispute_state['query_analysis'] = {
            'query_type': 'dispute',
            'keywords': ['노트북', '환불'],
            'retriever_types': ['law', 'criteria', 'case'],
        }

        from app.supervisor.graph_mas import _route_mas_supervisor
        from langgraph.types import Send

        result = _route_mas_supervisor(mock_dispute_state)

        # Fan-out: 3개 Send 객체 반환 (v2: counsel 제거)
        assert isinstance(result, list)
        assert len(result) == 3

        # 각 Send 객체가 올바른 노드를 타겟으로 하는지 확인
        target_nodes = [send.node for send in result]
        assert 'retrieval_law' in target_nodes
        assert 'retrieval_criteria' in target_nodes
        assert 'retrieval_case' in target_nodes

    @pytest.mark.asyncio
    async def test_retrieval_merge_combines_results(self, mock_retrieval_results):
        """retrieval_merge가 4개 결과를 올바르게 병합하는지 검증"""
        from app.supervisor.nodes.retrieval_merge import retrieval_merge_node

        state = {
            'user_query': '환불 받고 싶어요',
            'individual_retrieval_results': mock_retrieval_results,
            'supervisor': {
                'completed_tasks': ['query_analysis'],
                'pending_tasks': ['generate_answer'],
            },
        }

        result = await retrieval_merge_node(state)

        # 병합 결과 검증
        assert 'retrieval' in result
        retrieval = result['retrieval']

        # 섹션 존재 확인 (v2: 3개 Agent 결과)
        assert 'laws' in retrieval
        assert 'criteria' in retrieval
        assert 'disputes' in retrieval  # case → disputes로 매핑

        # 문서 수 검증 (law(1) + criteria(1) + case(0) = 2)
        total_docs = (
            len(retrieval.get('laws', [])) +
            len(retrieval.get('criteria', [])) +
            len(retrieval.get('disputes', []))
        )
        assert total_docs >= 2

        # 유사도 통계 검증
        assert retrieval.get('max_similarity') == 0.85  # law의 max

        # supervisor 상태 업데이트 검증
        assert 'retrieval' in result['supervisor']['completed_tasks']


# ============================================================================
# E2E Test: Supervisor Fallback
# ============================================================================

class TestE2EFallbackOnFailure:
    """Supervisor 실패 시 규칙 기반 fallback 테스트"""

    def test_rule_based_fallback_order(self, mock_supervisor_node):
        """규칙 기반 fallback이 올바른 순서로 진행되는지 검증

        _rule_based_fallback (NEED_RAG 모드) 흐름:
        retrieval_team → answer_drafter → legal_reviewer → respond

        Note: _full_pipeline_decision은 state 필드(retrieval, draft_answer, review)를
        기준으로 다음 단계를 결정합니다. completed_tasks만으로는 판단하지 않습니다.
        """
        # 순서: retrieval_team → answer_drafter → legal_reviewer → respond
        states = [
            # 1. retrieval 없음 → retrieval_team
            {
                'mode': 'NEED_RAG',
                'supervisor': {'completed_tasks': [], 'iteration_count': 0},
            },
            # 2. retrieval 있음, draft 없음 → answer_drafter
            {
                'mode': 'NEED_RAG',
                'retrieval': {'laws': [{'content': '법령'}], 'max_similarity': 0.8},
                'supervisor': {'completed_tasks': ['retrieval_team'], 'iteration_count': 1},
            },
            # 3. retrieval+draft 있음, review 없음 → legal_reviewer
            {
                'mode': 'NEED_RAG',
                'retrieval': {'laws': [{'content': '법령'}], 'max_similarity': 0.8},
                'draft_answer': '환불 가능합니다.',
                'supervisor': {'completed_tasks': ['retrieval_team', 'answer_drafter'], 'iteration_count': 2},
            },
            # 4. 전부 있음 → respond
            {
                'mode': 'NEED_RAG',
                'retrieval': {'laws': [{'content': '법령'}], 'max_similarity': 0.8},
                'draft_answer': '환불 가능합니다.',
                'review': {'passed': True, 'violations': []},
                'supervisor': {'completed_tasks': ['retrieval_team', 'answer_drafter', 'legal_reviewer'], 'iteration_count': 3},
            },
        ]

        expected_targets = [
            'retrieval_team',
            'answer_drafter',
            'legal_reviewer',
            None,  # respond (모든 작업 완료)
        ]

        for state, expected in zip(states, expected_targets):
            decision = mock_supervisor_node._rule_based_fallback(state)

            if expected is None:
                assert decision['action'] == 'respond'
            else:
                assert decision['action'] == 'call_agent'
                assert decision['target_agent'] == expected


# ============================================================================
# E2E Test: Max Iteration Protection
# ============================================================================

class TestE2EMaxIterationProtection:
    """무한 루프 방지 (10회 제한) 테스트"""

    def test_max_iteration_forces_respond(self, mock_supervisor_node, mock_dispute_state):
        """10회 반복 시 강제 종료되는지 검증"""
        from app.supervisor.nodes.supervisor import MAX_SUPERVISOR_ITERATIONS

        mock_dispute_state['supervisor'] = {
            'current_phase': 'analyzing',
            'agent_messages': [],
            'pending_tasks': ['some_task'],
            'completed_tasks': [],
            'supervisor_reasoning': 'Iteration limit test',
            'next_agent': None,
            'iteration_count': MAX_SUPERVISOR_ITERATIONS,  # 10
        }

        decision = mock_supervisor_node._fallback_respond(mock_dispute_state)

        assert decision['action'] == 'respond'
        assert decision.get('partial') is True

    def test_iteration_count_below_limit_continues(self, mock_supervisor_node, mock_dispute_state):
        """10회 미만일 때는 정상 진행되는지 검증"""
        mock_dispute_state['supervisor'] = {
            'current_phase': 'analyzing',
            'agent_messages': [],
            'pending_tasks': ['retrieve_documents'],
            'completed_tasks': [],
            'supervisor_reasoning': 'Normal iteration',
            'next_agent': None,
            'iteration_count': 5,  # < 10
        }
        mock_dispute_state['mode'] = 'NEED_RAG'

        decision = mock_supervisor_node._rule_based_fallback(mock_dispute_state)

        # 5회 반복 후에도 정상 진행 (NEED_RAG, retrieval 없음 → retrieval_team)
        assert decision['action'] == 'call_agent'
        assert decision['target_agent'] == 'retrieval_team'


# ============================================================================
# Graph Structure Validation
# ============================================================================

class TestMASGraphStructure:
    """MAS Supervisor 그래프 구조 검증"""

    def test_mas_graph_has_all_required_nodes(self):
        """MAS 그래프에 필수 노드가 모두 있는지 검증"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        graph = create_mas_supervisor_graph()
        nodes = list(graph.nodes.keys())

        # v2: counsel 제거, memory_save 추가
        required_nodes = [
            'input_guardrail',
            'supervisor',
            'query_analysis',
            'retrieval_law',
            'retrieval_criteria',
            'retrieval_case',
            'retrieval_merge',
            'generation',
            'review',
            'output_guardrail',
            'memory_save',
        ]

        for node in required_nodes:
            assert node in nodes, f"Missing node: {node}"

    def test_mas_graph_entry_point_is_cache_check(self):
        """MAS 그래프 진입점이 cache_check인지 검증"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph
        from langgraph.graph import START

        graph = create_mas_supervisor_graph()

        # 진입점 확인 (edges에서 START → cache_check)
        # LangGraph에서는 set_entry_point()가 START → node 엣지 생성
        entry_edges = [edge for edge in graph.edges if edge[0] == START]

        assert len(entry_edges) == 1
        assert entry_edges[0][1] == 'cache_check'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
