"""
MAS Supervisor Graph 통합 테스트 (Phase 5)

작성일: 2026-01-26

테스트 대상:
- Supervisor 규칙 기반 의사결정 흐름
- Supervisor → Agent → Supervisor 왕복
- Fan-out 라우팅 동작
"""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 전체 파일에 unit 마커 적용 (Mock 사용, DB 불필요)
pytestmark = pytest.mark.unit


class TestSupervisorRuleBasedFallback:
    """Supervisor 규칙 기반 fallback 테스트

    _rule_based_fallback 동작 (현행):
    1. mode 확인 → NO_RETRIEVAL/RESTRICTED_DOMAIN → _no_retrieval_decision (Fast Path)
    2. 그 외 (기본 NEED_RAG) → _full_pipeline_decision
       - retrieval 없으면 → retrieval_team
       - draft_answer 없으면 → answer_drafter
       - review 없으면 → legal_reviewer
       - 전부 있으면 → respond
    """

    def test_rule_based_calls_retrieval_first(self):
        """NEED_RAG 모드에서 첫 단계: retrieval_team 호출"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            "user_query": "노트북 환불",
            "mode": "NEED_RAG",
            "supervisor": {
                "completed_tasks": [],
                "iteration_count": 0,
            },
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision["action"] == "call_agent"
        assert decision["target_agent"] == "retrieval_team"

    def test_rule_based_calls_drafter_after_retrieval(self):
        """retrieval 완료 후 answer_drafter 호출"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            "user_query": "노트북 환불",
            "mode": "NEED_RAG",
            "retrieval": {"laws": [{"content": "전자상거래법"}], "max_similarity": 0.8},
            "supervisor": {
                "completed_tasks": ["retrieval_team"],
                "iteration_count": 1,
            },
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision["action"] == "call_agent"
        assert decision["target_agent"] == "answer_drafter"

    def test_rule_based_calls_reviewer_after_draft(self):
        """draft 완료 후 legal_reviewer 호출"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            "user_query": "노트북 환불",
            "mode": "NEED_RAG",
            "retrieval": {"laws": [{"content": "전자상거래법"}], "max_similarity": 0.8},
            "draft_answer": "환불이 가능합니다.",
            "supervisor": {
                "completed_tasks": ["retrieval_team", "answer_drafter"],
                "iteration_count": 2,
            },
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision["action"] == "call_agent"
        assert decision["target_agent"] == "legal_reviewer"

    def test_rule_based_responds_after_all_complete(self):
        """모든 작업 완료 후 respond"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            "user_query": "노트북 환불",
            "mode": "NEED_RAG",
            "retrieval": {"laws": [{"content": "전자상거래법"}], "max_similarity": 0.8},
            "draft_answer": "환불이 가능합니다.",
            "review": {"passed": True, "violations": []},
            "supervisor": {
                "completed_tasks": [
                    "retrieval_team",
                    "answer_drafter",
                    "legal_reviewer",
                ],
                "iteration_count": 3,
            },
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision["action"] == "respond"

    def test_no_retrieval_mode_skips_retrieval(self):
        """NO_RETRIEVAL 모드에서는 retrieval 생략하고 바로 generation"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        state = {
            "user_query": "안녕하세요",
            "mode": "NO_RETRIEVAL",
            "supervisor": {
                "completed_tasks": [],
                "iteration_count": 0,
            },
        }

        decision = supervisor._rule_based_fallback(state)

        assert decision["action"] == "call_agent"
        assert decision["target_agent"] == "answer_drafter"


class TestSupervisorMaxIterations:
    """Supervisor 최대 반복 제한 테스트"""

    def test_max_iterations_forces_respond(self):
        """최대 반복 횟수 도달 시 강제 응답"""
        from app.supervisor.nodes.supervisor import (
            MAX_SUPERVISOR_ITERATIONS,
            SupervisorNode,
        )

        supervisor = SupervisorNode(llm=None)

        state = {
            "user_query": "노트북 환불",
            "supervisor": {
                "completed_tasks": [],
                "iteration_count": MAX_SUPERVISOR_ITERATIONS,  # 이미 최대 도달
            },
        }

        import asyncio

        decision = asyncio.run(supervisor.decide_next_action(state))

        assert decision["action"] == "respond"
        assert decision.get("partial") == True


class TestMasGraphRouting:
    """MAS 그래프 라우팅 통합 테스트"""

    def test_supervisor_to_query_analysis_routing(self):
        """Supervisor → query_analysis 라우팅"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {"supervisor": {"next_agent": "query_analyst"}}

        result = _route_mas_supervisor(state)
        assert result == "query_analysis"

    def test_supervisor_to_retrieval_fan_out(self):
        """Supervisor → 3개 Retrieval Agent Fan-out (v2: counsel 제거)"""
        from langgraph.types import Send

        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            "user_query": "노트북 환불",
            "supervisor": {"next_agent": "retrieval_team"},
        }

        result = _route_mas_supervisor(state)

        # List[Send] 반환
        assert isinstance(result, list)
        assert len(result) == 3  # v2: counsel 제거

        node_names = [s.node for s in result]
        assert "retrieval_law" in node_names
        assert "retrieval_criteria" in node_names
        assert "retrieval_case" in node_names


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
            "user_query": "노트북 환불",
            "supervisor": {
                "completed_tasks": [],
                "iteration_count": 0,
                "agent_messages": [],
            },
        }

        import asyncio

        result = asyncio.run(node_fn(state))

        assert result["supervisor"]["iteration_count"] == 1


class TestSupervisorAgentMessage:
    """Supervisor 에이전트 메시지 테스트"""

    def test_create_supervisor_message(self):
        """Supervisor 메시지 생성"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)

        message = supervisor.create_supervisor_message(
            to_agent="query_analyst",
            message_type="request",
            content={"action": "analyze"},
        )

        assert message["from_agent"] == "supervisor"
        assert message["to_agent"] == "query_analyst"
        assert message["message_type"] == "request"
        assert "timestamp" in message


class TestGraphEndToEnd:
    """그래프 전체 흐름 테스트 (Mock 기반)"""

    def test_graph_structure_is_valid(self):
        """그래프 구조 유효성 검증"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        graph = create_mas_supervisor_graph()

        # 노드 연결 확인
        nodes = list(graph.nodes.keys())

        # 필수 노드 존재 (v2: counsel 제거, memory_save 추가)
        assert "input_guardrail" in nodes
        assert "supervisor" in nodes
        assert "query_analysis" in nodes
        assert "retrieval_law" in nodes
        assert "retrieval_merge" in nodes
        assert "generation" in nodes
        assert "review" in nodes
        assert "output_guardrail" in nodes
        assert "memory_save" in nodes

    def test_compiled_graph_has_invoke_method(self):
        """컴파일된 그래프에 invoke 메서드 존재"""
        from app.supervisor.graph_mas import get_mas_supervisor_graph, reset_mas_graph

        reset_mas_graph()
        compiled = get_mas_supervisor_graph()

        assert hasattr(compiled, "invoke")
        assert hasattr(compiled, "ainvoke")


if __name__ == "__main__":
    # 직접 실행 테스트
    print("=== MAS Integration Tests ===")

    # Rule-based fallback 테스트
    test1 = TestSupervisorRuleBasedFallback()
    test1.test_rule_based_calls_retrieval_first()
    print("✓ test_rule_based_calls_retrieval_first")

    test1.test_rule_based_calls_drafter_after_retrieval()
    print("✓ test_rule_based_calls_drafter_after_retrieval")

    test1.test_rule_based_calls_reviewer_after_draft()
    print("✓ test_rule_based_calls_reviewer_after_draft")

    test1.test_rule_based_responds_after_all_complete()
    print("✓ test_rule_based_responds_after_all_complete")

    test1.test_no_retrieval_mode_skips_retrieval()
    print("✓ test_no_retrieval_mode_skips_retrieval")

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
