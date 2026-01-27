"""
MAS Supervisor Graph 통합 테스트 (Phase 5)

작성일: 2026-01-26

테스트 대상:
- Supervisor 규칙 기반 의사결정 흐름
- Supervisor → Agent → Supervisor 왕복
- Fan-out 라우팅 동작
"""

import pytest
from typing import Dict, Any
from unittest.mock import patch, MagicMock, AsyncMock

# 전체 파일에 unit 마커 적용 (Mock 사용, DB 불필요)
pytestmark = pytest.mark.unit


class TestSupervisorRuleBasedFallback:
    """Supervisor 규칙 기반 fallback 테스트"""

    def test_rule_based_calls_query_analyst_first(self):
        """첫 단계: query_analyst 호출"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            'user_query': '노트북 환불',
            'supervisor': {
                'completed_tasks': [],
                'iteration_count': 0,
            }
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision['action'] == 'call_agent'
        assert decision['target_agent'] == 'query_analyst'

    def test_rule_based_calls_retrieval_after_analysis(self):
        """query_analysis 완료 후 retrieval_team 호출"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            'user_query': '노트북 환불',
            'supervisor': {
                'completed_tasks': ['query_analysis'],
                'iteration_count': 1,
            }
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision['action'] == 'call_agent'
        assert decision['target_agent'] == 'retrieval_team'

    def test_rule_based_calls_drafter_after_retrieval(self):
        """retrieval 완료 후 answer_drafter 호출"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            'user_query': '노트북 환불',
            'supervisor': {
                'completed_tasks': ['query_analysis', 'retrieval'],
                'iteration_count': 2,
            }
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision['action'] == 'call_agent'
        assert decision['target_agent'] == 'answer_drafter'

    def test_rule_based_calls_reviewer_after_draft(self):
        """draft 완료 후 legal_reviewer 호출"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            'user_query': '노트북 환불',
            'supervisor': {
                'completed_tasks': ['query_analysis', 'retrieval', 'draft'],
                'iteration_count': 3,
            }
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision['action'] == 'call_agent'
        assert decision['target_agent'] == 'legal_reviewer'

    def test_rule_based_responds_after_all_complete(self):
        """모든 작업 완료 후 respond"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            'user_query': '노트북 환불',
            'supervisor': {
                'completed_tasks': ['query_analysis', 'retrieval', 'draft', 'review'],
                'iteration_count': 4,
            }
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision['action'] == 'respond'


class TestSupervisorMaxIterations:
    """Supervisor 최대 반복 제한 테스트"""

    def test_max_iterations_forces_respond(self):
        """최대 반복 횟수 도달 시 강제 응답"""
        from app.supervisor.nodes.supervisor import SupervisorNode, MAX_SUPERVISOR_ITERATIONS

        supervisor = SupervisorNode(llm=None)

        state = {
            'user_query': '노트북 환불',
            'supervisor': {
                'completed_tasks': [],
                'iteration_count': MAX_SUPERVISOR_ITERATIONS,  # 이미 최대 도달
            }
        }

        import asyncio
        decision = asyncio.run(supervisor.decide_next_action(state))

        assert decision['action'] == 'respond'
        assert decision.get('partial') == True


class TestMasGraphRouting:
    """MAS 그래프 라우팅 통합 테스트"""

    def test_supervisor_to_query_analysis_routing(self):
        """Supervisor → query_analysis 라우팅"""
        from app.supervisor.graph import _route_mas_supervisor

        state = {
            'supervisor': {'next_agent': 'query_analyst'}
        }

        result = _route_mas_supervisor(state)
        assert result == 'query_analysis'

    def test_supervisor_to_retrieval_fan_out(self):
        """Supervisor → 4개 Retrieval Agent Fan-out"""
        from app.supervisor.graph import _route_mas_supervisor
        from langgraph.types import Send

        state = {
            'user_query': '노트북 환불',
            'supervisor': {'next_agent': 'retrieval_team'}
        }

        result = _route_mas_supervisor(state)

        # List[Send] 반환
        assert isinstance(result, list)
        assert len(result) == 4

        node_names = [s.node for s in result]
        assert 'retrieval_law' in node_names
        assert 'retrieval_criteria' in node_names
        assert 'retrieval_case' in node_names
        assert 'retrieval_counsel' in node_names


class TestSupervisorNodeFunction:
    """Supervisor 노드 함수 테스트"""

    def test_as_node_returns_callable(self):
        """as_node()가 호출 가능한 함수 반환"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)
        node_fn = supervisor.as_node()

        assert callable(node_fn)

    def test_node_increments_iteration_count(self):
        """노드 실행 시 iteration_count 증가"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)
        node_fn = supervisor.as_node()

        state = {
            'user_query': '노트북 환불',
            'supervisor': {
                'completed_tasks': [],
                'iteration_count': 0,
                'agent_messages': [],
            }
        }

        import asyncio
        result = asyncio.run(node_fn(state))

        assert result['supervisor']['iteration_count'] == 1


class TestSupervisorAgentMessage:
    """Supervisor 에이전트 메시지 테스트"""

    def test_create_supervisor_message(self):
        """Supervisor 메시지 생성"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        message = supervisor.create_supervisor_message(
            to_agent='query_analyst',
            message_type='request',
            content={'action': 'analyze'}
        )

        assert message['from_agent'] == 'supervisor'
        assert message['to_agent'] == 'query_analyst'
        assert message['message_type'] == 'request'
        assert 'timestamp' in message


class TestGraphEndToEnd:
    """그래프 전체 흐름 테스트 (Mock 기반)"""

    def test_graph_structure_is_valid(self):
        """그래프 구조 유효성 검증"""
        from app.supervisor.graph import create_mas_supervisor_graph

        graph = create_mas_supervisor_graph()

        # 노드 연결 확인
        nodes = list(graph.nodes.keys())

        # 필수 노드 존재
        assert 'input_guardrail' in nodes
        assert 'supervisor' in nodes
        assert 'query_analysis' in nodes
        assert 'retrieval_law' in nodes
        assert 'retrieval_merge' in nodes
        assert 'generation' in nodes
        assert 'review' in nodes
        assert 'output_guardrail' in nodes

    def test_compiled_graph_has_invoke_method(self):
        """컴파일된 그래프에 invoke 메서드 존재"""
        from app.supervisor.graph import get_mas_supervisor_compiled_graph

        compiled = get_mas_supervisor_compiled_graph()

        assert hasattr(compiled, 'invoke')
        assert hasattr(compiled, 'ainvoke')


if __name__ == '__main__':
    # 직접 실행 테스트
    print("=== MAS Integration Tests ===")

    # Rule-based fallback 테스트
    test1 = TestSupervisorRuleBasedFallback()
    test1.test_rule_based_calls_query_analyst_first()
    print("✓ test_rule_based_calls_query_analyst_first")

    test1.test_rule_based_calls_retrieval_after_analysis()
    print("✓ test_rule_based_calls_retrieval_after_analysis")

    test1.test_rule_based_calls_drafter_after_retrieval()
    print("✓ test_rule_based_calls_drafter_after_retrieval")

    test1.test_rule_based_calls_reviewer_after_draft()
    print("✓ test_rule_based_calls_reviewer_after_draft")

    test1.test_rule_based_responds_after_all_complete()
    print("✓ test_rule_based_responds_after_all_complete")

    # Max iterations 테스트
    test2 = TestSupervisorMaxIterations()
    test2.test_max_iterations_forces_respond()
    print("✓ test_max_iterations_forces_respond")

    # Routing 테스트
    test3 = TestMasGraphRouting()
    test3.test_supervisor_to_query_analysis_routing()
    print("✓ test_supervisor_to_query_analysis_routing")

    test3.test_supervisor_to_retrieval_fan_out()
    print("✓ test_supervisor_to_retrieval_fan_out")

    # Node function 테스트
    test4 = TestSupervisorNodeFunction()
    test4.test_as_node_returns_callable()
    print("✓ test_as_node_returns_callable")

    test4.test_node_increments_iteration_count()
    print("✓ test_node_increments_iteration_count")

    # Message 테스트
    test5 = TestSupervisorAgentMessage()
    test5.test_create_supervisor_message()
    print("✓ test_create_supervisor_message")

    # E2E 테스트
    test6 = TestGraphEndToEnd()
    test6.test_graph_structure_is_valid()
    print("✓ test_graph_structure_is_valid")

    test6.test_compiled_graph_has_invoke_method()
    print("✓ test_compiled_graph_has_invoke_method")

    print("\n=== All integration tests passed! ===")
