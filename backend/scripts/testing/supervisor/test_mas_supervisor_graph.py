"""
MAS Supervisor Graph 단위 테스트 (Phase 5)

작성일: 2026-01-26

테스트 대상: backend/app/orchestrator/graph.py - create_mas_supervisor_graph()
"""

import pytest
from typing import Dict, Any

# 전체 파일에 unit 마커 적용 (DB 의존성 없음)
pytestmark = pytest.mark.unit


class TestMasSupervisorGraphCreation:
    """그래프 생성 테스트"""

    def test_graph_has_all_required_nodes(self):
        """그래프에 모든 필수 노드가 있는지 확인"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        graph = create_mas_supervisor_graph()
        nodes = list(graph.nodes.keys())

        # 필수 노드 확인 (v2: counsel 제거, memory_save 추가)
        required_nodes = [
            'input_guardrail',
            'output_guardrail',
            'supervisor',
            'query_analysis',
            'generation',
            'review',
            'retrieval_law',
            'retrieval_criteria',
            'retrieval_case',
            'retrieval_merge',
            'memory_save',
        ]

        for node in required_nodes:
            assert node in nodes, f"Missing node: {node}"

    def test_graph_compiles_successfully(self):
        """그래프가 성공적으로 컴파일되는지 확인"""
        from app.supervisor.graph_mas import get_mas_supervisor_graph, reset_mas_graph

        reset_mas_graph()
        compiled = get_mas_supervisor_graph()

        assert compiled is not None
        assert hasattr(compiled, 'invoke')


class TestMasRouting:
    """MAS 라우팅 함수 테스트"""

    def test_route_to_query_analysis(self):
        """query_analyst → query_analysis 라우팅"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            'supervisor': {
                'next_agent': 'query_analyst',
            }
        }

        result = _route_mas_supervisor(state)
        assert result == 'query_analysis'

    def test_route_to_generation(self):
        """answer_drafter → generation 라우팅"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            'supervisor': {
                'next_agent': 'answer_drafter',
            }
        }

        result = _route_mas_supervisor(state)
        assert result == 'generation'

    def test_route_to_review(self):
        """legal_reviewer → review 라우팅"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            'supervisor': {
                'next_agent': 'legal_reviewer',
            }
        }

        result = _route_mas_supervisor(state)
        assert result == 'review'

    def test_route_to_output_on_respond(self):
        """respond → output_guardrail 라우팅"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            'supervisor': {
                'next_agent': None,
            }
        }

        result = _route_mas_supervisor(state)
        assert result == 'output_guardrail'

    def test_route_fan_out_returns_send_list(self):
        """retrieval_team → List[Send] 반환 (Fan-out, v2: 3개 Agent)"""
        from app.supervisor.graph_mas import _route_mas_supervisor
        from langgraph.types import Send

        state = {
            'supervisor': {
                'next_agent': 'retrieval_team',
            },
            'user_query': '노트북 환불',
        }

        result = _route_mas_supervisor(state)

        # List[Send] 반환 확인
        assert isinstance(result, list)
        assert len(result) == 3  # v2: counsel 제거

        # 각 요소가 Send 객체인지 확인
        for item in result:
            assert isinstance(item, Send)

        # 3개 에이전트 노드로 보내는지 확인
        node_names = [send.node for send in result]
        assert 'retrieval_law' in node_names
        assert 'retrieval_criteria' in node_names
        assert 'retrieval_case' in node_names


class TestRetrievalAgentNodes:
    """Retrieval Agent 노드 테스트"""

    def test_create_retrieval_agent_node_law(self):
        """Law Retrieval Agent 노드 생성 테스트"""
        from app.supervisor.graph_mas import _create_retrieval_agent_node

        node_fn = _create_retrieval_agent_node('law')
        assert callable(node_fn)

    def test_create_retrieval_agent_node_criteria(self):
        """Criteria Retrieval Agent 노드 생성 테스트"""
        from app.supervisor.graph_mas import _create_retrieval_agent_node

        node_fn = _create_retrieval_agent_node('criteria')
        assert callable(node_fn)


class TestGraphSingleton:
    """그래프 싱글톤 테스트"""

    def test_get_mas_supervisor_graph_returns_same_instance(self):
        """싱글톤 패턴 확인"""
        from app.supervisor.graph_mas import get_mas_supervisor_graph, reset_mas_graph

        # 리셋 후 새로 가져오기
        reset_mas_graph()
        graph1 = get_mas_supervisor_graph()
        graph2 = get_mas_supervisor_graph()

        assert graph1 is graph2

    def test_reset_mas_graph_clears_singleton(self):
        """리셋 후 새 인스턴스 생성"""
        from app.supervisor.graph_mas import get_mas_supervisor_graph, reset_mas_graph

        graph1 = get_mas_supervisor_graph()
        reset_mas_graph()
        graph2 = get_mas_supervisor_graph()

        # 새 인스턴스지만 동일한 구조
        assert graph1 is not graph2


class TestSupervisorNodeIntegration:
    """SupervisorNode 통합 테스트"""

    def test_supervisor_node_in_graph(self):
        """그래프에 SupervisorNode가 올바르게 등록되었는지 확인"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        graph = create_mas_supervisor_graph()

        assert 'supervisor' in graph.nodes


if __name__ == '__main__':
    # 직접 실행 테스트
    print("=== MAS Supervisor Graph Tests ===")

    # 그래프 생성 테스트
    test = TestMasSupervisorGraphCreation()
    test.test_graph_has_all_required_nodes()
    print("✓ test_graph_has_all_required_nodes")

    test.test_graph_compiles_successfully()
    print("✓ test_graph_compiles_successfully")

    # 라우팅 테스트
    test2 = TestMasRouting()
    test2.test_route_to_query_analysis()
    print("✓ test_route_to_query_analysis")

    test2.test_route_to_generation()
    print("✓ test_route_to_generation")

    test2.test_route_to_review()
    print("✓ test_route_to_review")

    test2.test_route_to_output_on_respond()
    print("✓ test_route_to_output_on_respond")

    test2.test_route_fan_out_returns_send_list()
    print("✓ test_route_fan_out_returns_send_list")

    # 싱글톤 테스트
    test3 = TestGraphSingleton()
    test3.test_get_mas_supervisor_graph_returns_same_instance()
    print("✓ test_get_mas_supervisor_graph_returns_same_instance")

    test3.test_reset_mas_graph_clears_singleton()
    print("✓ test_reset_mas_graph_clears_singleton")

    print("\n=== All tests passed! ===")
