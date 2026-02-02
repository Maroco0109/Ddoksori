"""
MAS Supervisor Architecture - Phase 2: BaseAgent 테스트

BaseAgent 추상 클래스의 기능을 검증합니다:
1. 에이전트 메타데이터 정의
2. process() 추상 메서드 구현 강제
3. report_to_supervisor() 응답 형식
4. create_agent_message() 메시지 생성
5. validate_request() 입력 검증
6. as_node() LangGraph 노드 변환
7. get_info() 메타데이터 조회
"""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

import asyncio
import time
from typing import Any, Dict, cast

import pytest

from app.agents.base import BaseAgent
from app.supervisor.state import ChatState
from app.supervisor.state.supervisor import AgentMessage


class ConcreteTestAgent(BaseAgent):
    """테스트용 구체 에이전트 구현"""

    agent_name = "test_agent"
    agent_description = "테스트용 에이전트입니다."
    required_inputs = ["user_query"]
    provided_outputs = ["result", "confidence"]

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        user_query = request.get("context", {}).get("user_query", "")
        return self.report_to_supervisor(
            status="success",
            result={"processed_query": user_query, "confidence": 0.95},
            message=f"처리 완료: {user_query[:20]}",
        )


class FailingAgent(BaseAgent):
    """실패 응답을 반환하는 테스트 에이전트"""

    agent_name = "failing_agent"
    agent_description = "항상 실패하는 에이전트입니다."
    required_inputs = ["user_query"]
    provided_outputs = []

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.report_to_supervisor(
            status="failure", result=None, message="처리 실패: 외부 서비스 연결 오류"
        )


class NeedMoreInfoAgent(BaseAgent):
    """추가 정보 요청 에이전트"""

    agent_name = "need_info_agent"
    agent_description = "추가 정보를 요청하는 에이전트입니다."
    required_inputs = ["user_query", "purchase_item"]
    provided_outputs = ["clarification_request"]

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.report_to_supervisor(
            status="need_more_info",
            result={"missing_fields": ["purchase_date"]},
            message="구매일자 정보가 필요합니다.",
        )


class TestBaseAgentInstantiation:
    """BaseAgent 인스턴스화 테스트"""

    def test_concrete_agent_instantiation(self):
        agent = ConcreteTestAgent()
        assert agent.agent_name == "test_agent"
        assert agent.agent_description == "테스트용 에이전트입니다."

    def test_agent_without_name_raises_error(self):
        class NoNameAgent(BaseAgent):
            agent_name = ""
            agent_description = "이름 없는 에이전트"
            required_inputs = []
            provided_outputs = []

            async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
                return {}

        with pytest.raises(ValueError, match="agent_name을 정의해야"):
            NoNameAgent()

    def test_abstract_class_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            BaseAgent()  # type: ignore[abstract]


class TestReportToSupervisor:
    """report_to_supervisor() 테스트"""

    def test_success_response_format(self):
        agent = ConcreteTestAgent()
        response = agent.report_to_supervisor(
            status="success", result={"data": "test"}, message="성공 메시지"
        )

        assert response["from_agent"] == "test_agent"
        assert response["status"] == "success"
        assert response["result"] == {"data": "test"}
        assert response["message"] == "성공 메시지"

    def test_failure_response_format(self):
        agent = FailingAgent()
        response = agent.report_to_supervisor(
            status="failure", result=None, message="실패 메시지"
        )

        assert response["from_agent"] == "failing_agent"
        assert response["status"] == "failure"
        assert response["result"] is None

    def test_need_more_info_response_format(self):
        agent = NeedMoreInfoAgent()
        response = agent.report_to_supervisor(
            status="need_more_info",
            result={"missing": ["field1"]},
            message="추가 정보 필요",
        )

        assert response["status"] == "need_more_info"
        assert "missing" in response["result"]


class TestCreateAgentMessage:
    """create_agent_message() 테스트"""

    def test_message_creation(self):
        agent = ConcreteTestAgent()
        before_time = time.time()

        msg = agent.create_agent_message(
            to_agent="supervisor", message_type="response", content={"result": "test"}
        )

        after_time = time.time()

        assert msg["from_agent"] == "test_agent"
        assert msg["to_agent"] == "supervisor"
        assert msg["message_type"] == "response"
        assert msg["content"] == {"result": "test"}
        assert before_time <= msg["timestamp"] <= after_time

    def test_request_message_type(self):
        agent = ConcreteTestAgent()
        msg = agent.create_agent_message(
            to_agent="retrieval_law",
            message_type="request",
            content={"task": "search", "query": "환불 규정"},
        )

        assert msg["message_type"] == "request"
        assert msg["to_agent"] == "retrieval_law"

    def test_error_message_type(self):
        agent = ConcreteTestAgent()
        msg = agent.create_agent_message(
            to_agent="supervisor",
            message_type="error",
            content={"error_type": "timeout", "message": "LLM 응답 시간 초과"},
        )

        assert msg["message_type"] == "error"
        assert "error_type" in msg["content"]


class TestValidateRequest:
    """validate_request() 테스트"""

    def test_valid_request_returns_none(self):
        agent = ConcreteTestAgent()
        request = {
            "task": "analyze",
            "params": {},
            "context": {"user_query": "환불 문의"},
        }

        error = agent.validate_request(request)
        assert error is None

    def test_missing_required_field_returns_error(self):
        agent = ConcreteTestAgent()
        request = {"task": "analyze", "params": {}, "context": {}}

        error = agent.validate_request(request)
        assert error is not None
        assert "user_query" in error

    def test_multiple_missing_fields(self):
        agent = NeedMoreInfoAgent()
        request = {"task": "analyze", "params": {}, "context": {}}

        error = agent.validate_request(request)
        assert error is not None
        assert "user_query" in error
        assert "purchase_item" in error

    def test_none_value_treated_as_missing(self):
        agent = ConcreteTestAgent()
        request = {"task": "analyze", "params": {}, "context": {"user_query": None}}

        error = agent.validate_request(request)
        assert error is not None


class TestProcessMethod:
    """process() 메서드 테스트"""

    def test_successful_processing(self):
        agent = ConcreteTestAgent()
        request = {
            "task": "analyze",
            "params": {},
            "context": {"user_query": "노트북 환불 가능한가요?"},
        }

        response = asyncio.run(agent.process(request))

        assert response["status"] == "success"
        assert response["from_agent"] == "test_agent"
        assert "processed_query" in response["result"]
        assert response["result"]["confidence"] == 0.95

    def test_failure_processing(self):
        agent = FailingAgent()
        request = {"task": "process", "params": {}, "context": {"user_query": "테스트"}}

        response = asyncio.run(agent.process(request))

        assert response["status"] == "failure"
        assert response["result"] is None

    def test_need_more_info_processing(self):
        agent = NeedMoreInfoAgent()
        request = {"task": "process", "params": {}, "context": {"user_query": "환불"}}

        response = asyncio.run(agent.process(request))

        assert response["status"] == "need_more_info"
        assert "missing_fields" in response["result"]


class TestAsNode:
    """as_node() LangGraph 노드 변환 테스트"""

    def test_node_function_returns_callable(self):
        agent = ConcreteTestAgent()
        node_fn = agent.as_node()

        assert callable(node_fn)

    def test_node_function_updates_supervisor_state(self):
        agent = ConcreteTestAgent()
        node_fn = agent.as_node()

        initial_state = cast(
            ChatState,
            {
                "user_query": "환불 문의",
                "chat_type": "dispute",
                "supervisor": {
                    "current_phase": "analyzing",
                    "agent_messages": [],
                    "pending_tasks": ["test_agent"],
                    "completed_tasks": [],
                    "supervisor_reasoning": "",
                    "next_agent": "test_agent",
                },
            },
        )

        result = asyncio.run(node_fn(initial_state))

        assert "supervisor" in result
        assert len(result["supervisor"]["agent_messages"]) == 1
        assert "test_agent" in result["supervisor"]["completed_tasks"]

    def test_node_function_preserves_existing_messages(self):
        agent = ConcreteTestAgent()
        node_fn = agent.as_node()

        existing_message: AgentMessage = {
            "from_agent": "supervisor",
            "to_agent": "test_agent",
            "message_type": "request",
            "content": {"task": "analyze"},
            "timestamp": time.time() - 1.0,
        }

        initial_state = cast(
            ChatState,
            {
                "user_query": "환불",
                "supervisor": {
                    "current_phase": "analyzing",
                    "agent_messages": [existing_message],
                    "pending_tasks": [],
                    "completed_tasks": [],
                    "supervisor_reasoning": "",
                    "next_agent": None,
                },
            },
        )

        result = asyncio.run(node_fn(initial_state))

        assert len(result["supervisor"]["agent_messages"]) == 2
        assert result["supervisor"]["agent_messages"][0] == existing_message

    def test_node_function_does_not_duplicate_completed_tasks(self):
        agent = ConcreteTestAgent()
        node_fn = agent.as_node()

        initial_state = cast(
            ChatState,
            {
                "user_query": "테스트",
                "supervisor": {
                    "current_phase": "analyzing",
                    "agent_messages": [],
                    "pending_tasks": [],
                    "completed_tasks": ["test_agent"],
                    "supervisor_reasoning": "",
                    "next_agent": None,
                },
            },
        )

        result = asyncio.run(node_fn(initial_state))

        assert result["supervisor"]["completed_tasks"].count("test_agent") == 1


class TestGetInfo:
    """get_info() 테스트"""

    def test_returns_agent_metadata(self):
        agent = ConcreteTestAgent()
        info = agent.get_info()

        assert info["name"] == "test_agent"
        assert info["description"] == "테스트용 에이전트입니다."
        assert info["required_inputs"] == ["user_query"]
        assert info["provided_outputs"] == ["result", "confidence"]

    def test_info_structure_for_supervisor(self):
        agent = NeedMoreInfoAgent()
        info = agent.get_info()

        assert "name" in info
        assert "description" in info
        assert "required_inputs" in info
        assert "provided_outputs" in info
        assert len(info["required_inputs"]) == 2


class TestAgentRepr:
    """__repr__() 테스트"""

    def test_repr_format(self):
        agent = ConcreteTestAgent()
        repr_str = repr(agent)

        assert "ConcreteTestAgent" in repr_str
        assert "test_agent" in repr_str


class TestAgentIntegration:
    """에이전트 통합 시나리오 테스트"""

    def test_full_request_response_cycle(self):
        agent = ConcreteTestAgent()

        request = {
            "task": "analyze_query",
            "params": {"top_k": 5},
            "context": {
                "user_query": "노트북 구매 후 3일 만에 환불 요청",
                "chat_type": "dispute",
                "onboarding": {"purchase_item": "노트북"},
            },
        }

        validation_error = agent.validate_request(request)
        assert validation_error is None

        response = asyncio.run(agent.process(request))

        assert response["status"] == "success"
        assert response["from_agent"] == agent.agent_name

        message = agent.create_agent_message(
            to_agent="supervisor",
            message_type="response",
            content=response,
        )

        assert message["from_agent"] == "test_agent"
        assert message["to_agent"] == "supervisor"
        assert message["content"]["status"] == "success"

    def test_agent_chain_simulation(self):
        """여러 에이전트가 순차적으로 처리하는 시나리오"""
        agent1 = ConcreteTestAgent()
        agent2 = NeedMoreInfoAgent()

        state = cast(
            ChatState,
            {
                "user_query": "환불",
                "supervisor": {
                    "current_phase": "analyzing",
                    "agent_messages": [],
                    "pending_tasks": ["test_agent", "need_info_agent"],
                    "completed_tasks": [],
                    "supervisor_reasoning": "",
                    "next_agent": "test_agent",
                },
            },
        )

        node1 = agent1.as_node()
        result1 = asyncio.run(node1(state))

        merged_state = cast(ChatState, {**state, **result1})

        node2 = agent2.as_node()
        result2 = asyncio.run(node2(merged_state))

        final_messages = result2["supervisor"]["agent_messages"]
        assert len(final_messages) == 2

        final_completed = result2["supervisor"]["completed_tasks"]
        assert "test_agent" in final_completed
        assert "need_info_agent" in final_completed
