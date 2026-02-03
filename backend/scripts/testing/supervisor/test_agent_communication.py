"""
Integration tests for Supervisor ↔ Agent message exchange using SupervisorState schema.

This module tests the message communication patterns between the Supervisor and various
agents using the new SupervisorState schema. Tests verify message creation, accumulation,
and complete communication flows.

Test Coverage:
    - Message creation with proper timestamps
    - Agent message list accumulation (append, not replace)
    - Supervisor → Agent request flow
    - Agent → Supervisor response flow
    - Complete bidirectional communication cycles
    - Different message types (request, response, error)
"""

import time
from typing import Any, Dict

import pytest

# 전체 파일에 unit 마커 적용 (DB 의존성 없음)
pytestmark = pytest.mark.unit

from app.supervisor.state.supervisor import AgentMessage, SupervisorState


class MockAgent:
    """
    Mock Agent class that simulates agent behavior for testing.

    This mock agent processes requests and generates responses following
    the AgentMessage protocol.
    """

    def __init__(self, name: str):
        """
        Initialize mock agent.

        Args:
            name: Agent identifier (e.g., 'query_analyst', 'retrieval_agent')
        """
        self.name = name
        self.request_count = 0

    def process_request(self, request: AgentMessage) -> AgentMessage:
        """
        Process a request message and return a response.

        Args:
            request: AgentMessage with message_type='request'

        Returns:
            AgentMessage with message_type='response'
        """
        self.request_count += 1

        return {
            "from_agent": self.name,
            "to_agent": "supervisor",
            "message_type": "response",
            "content": {
                "status": "success",
                "result": {
                    "processed_request": request.get("content", {}),
                    "agent_name": self.name,
                    "request_number": self.request_count,
                },
            },
            "timestamp": time.time(),
        }

    def process_request_with_error(self, request: AgentMessage) -> AgentMessage:
        """
        Process a request and return an error response.

        Args:
            request: AgentMessage with message_type='request'

        Returns:
            AgentMessage with message_type='error'
        """
        return {
            "from_agent": self.name,
            "to_agent": "supervisor",
            "message_type": "error",
            "content": {
                "error_type": "ProcessingError",
                "message": f"Failed to process request in {self.name}",
                "original_request": request.get("content", {}),
            },
            "timestamp": time.time(),
        }


def create_initial_supervisor_state() -> SupervisorState:
    """
    Create an initial SupervisorState for testing.

    Returns:
        SupervisorState with empty message list and initial phase.
    """
    return {
        "current_phase": "analyzing",
        "agent_messages": [],
        "pending_tasks": ["analyze_query", "retrieve_documents", "generate_answer"],
        "completed_tasks": [],
        "supervisor_reasoning": "Starting workflow",
        "next_agent": "query_analyst",
    }


def create_request_message(
    from_agent: str,
    to_agent: str,
    task: str,
    params: Dict[str, Any],
) -> AgentMessage:
    """
    Create a request message from supervisor to agent.

    Args:
        from_agent: Sending agent name
        to_agent: Receiving agent name
        task: Task identifier
        params: Task parameters

    Returns:
        AgentMessage with message_type='request'
    """
    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "message_type": "request",
        "content": {
            "task": task,
            "params": params,
        },
        "timestamp": time.time(),
    }


class TestSupervisorToAgentRequest:
    """Test Supervisor sending requests to agents."""

    def test_supervisor_creates_request_message(self):
        """Test that supervisor can create a properly formatted request message."""
        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "헬스장 환불 규정"},
        )

        assert request["from_agent"] == "supervisor"
        assert request["to_agent"] == "query_analyst"
        assert request["message_type"] == "request"
        assert request["content"]["task"] == "analyze_query"
        assert request["content"]["params"]["query"] == "헬스장 환불 규정"
        assert isinstance(request["timestamp"], float)
        assert request["timestamp"] > 0

    def test_request_message_has_valid_timestamp(self):
        """Test that request messages have valid timestamps."""
        before = time.time()
        request = create_request_message(
            from_agent="supervisor",
            to_agent="retrieval_agent",
            task="retrieve_documents",
            params={"keywords": ["환불", "규정"]},
        )
        after = time.time()

        assert before <= request["timestamp"] <= after

    def test_supervisor_adds_request_to_state(self):
        """Test that supervisor can add request to agent_messages list."""
        state = create_initial_supervisor_state()

        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트"},
        )

        state["agent_messages"].append(request)

        assert len(state["agent_messages"]) == 1
        assert state["agent_messages"][0] == request

    def test_multiple_requests_accumulate(self):
        """Test that multiple requests accumulate in agent_messages list."""
        state = create_initial_supervisor_state()

        request1 = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "질문1"},
        )
        request2 = create_request_message(
            from_agent="supervisor",
            to_agent="retrieval_agent",
            task="retrieve_documents",
            params={"keywords": ["키워드"]},
        )

        state["agent_messages"].append(request1)
        state["agent_messages"].append(request2)

        assert len(state["agent_messages"]) == 2
        assert state["agent_messages"][0]["to_agent"] == "query_analyst"
        assert state["agent_messages"][1]["to_agent"] == "retrieval_agent"


class TestAgentToSupervisorResponse:
    """Test agents responding to supervisor requests."""

    def test_agent_processes_request_and_responds(self):
        """Test that agent can process request and generate response."""
        agent = MockAgent("query_analyst")

        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트 질문"},
        )

        response = agent.process_request(request)

        assert response["from_agent"] == "query_analyst"
        assert response["to_agent"] == "supervisor"
        assert response["message_type"] == "response"
        assert response["content"]["status"] == "success"
        assert "result" in response["content"]

    def test_response_contains_processed_data(self):
        """Test that response contains processed request data."""
        agent = MockAgent("retrieval_agent")

        request = create_request_message(
            from_agent="supervisor",
            to_agent="retrieval_agent",
            task="retrieve_documents",
            params={"keywords": ["환불", "규정"]},
        )

        response = agent.process_request(request)

        assert response["content"]["result"]["agent_name"] == "retrieval_agent"
        assert response["content"]["result"]["request_number"] == 1
        assert response["content"]["result"]["processed_request"] == request["content"]

    def test_agent_response_has_valid_timestamp(self):
        """Test that agent response has valid timestamp."""
        agent = MockAgent("query_analyst")
        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트"},
        )

        before = time.time()
        response = agent.process_request(request)
        after = time.time()

        assert before <= response["timestamp"] <= after

    def test_agent_error_response(self):
        """Test that agent can generate error responses."""
        agent = MockAgent("query_analyst")

        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트"},
        )

        error_response = agent.process_request_with_error(request)

        assert error_response["message_type"] == "error"
        assert error_response["content"]["error_type"] == "ProcessingError"
        assert "message" in error_response["content"]
        assert error_response["from_agent"] == "query_analyst"


class TestMessageAccumulation:
    """Test that agent_messages list properly accumulates messages."""

    def test_messages_accumulate_not_replace(self):
        """Test that messages are appended, not replaced."""
        state = create_initial_supervisor_state()

        msg1 = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "Q1"},
        )
        state["agent_messages"].append(msg1)
        assert len(state["agent_messages"]) == 1

        msg2 = create_request_message(
            from_agent="supervisor",
            to_agent="retrieval_agent",
            task="retrieve_documents",
            params={"keywords": ["K1"]},
        )
        state["agent_messages"].append(msg2)
        assert len(state["agent_messages"]) == 2

        assert state["agent_messages"][0] == msg1
        assert state["agent_messages"][1] == msg2

    def test_request_response_accumulation(self):
        """Test that requests and responses accumulate together."""
        state = create_initial_supervisor_state()
        agent = MockAgent("query_analyst")

        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트"},
        )
        state["agent_messages"].append(request)

        response = agent.process_request(request)
        state["agent_messages"].append(response)

        assert len(state["agent_messages"]) == 2
        assert state["agent_messages"][0]["message_type"] == "request"
        assert state["agent_messages"][1]["message_type"] == "response"

    def test_message_order_preserved(self):
        """Test that message order is preserved in accumulation."""
        state = create_initial_supervisor_state()

        messages = []
        for i in range(5):
            msg = create_request_message(
                from_agent="supervisor",
                to_agent=f"agent_{i}",
                task=f"task_{i}",
                params={"index": i},
            )
            messages.append(msg)
            state["agent_messages"].append(msg)

        for i, msg in enumerate(state["agent_messages"]):
            assert msg["content"]["params"]["index"] == i
            assert msg["to_agent"] == f"agent_{i}"

    def test_mixed_message_types_accumulate(self):
        """Test that different message types accumulate correctly."""
        state = create_initial_supervisor_state()
        agent = MockAgent("test_agent")

        request = create_request_message(
            from_agent="supervisor",
            to_agent="test_agent",
            task="test_task",
            params={"data": "test"},
        )
        state["agent_messages"].append(request)

        response = agent.process_request(request)
        state["agent_messages"].append(response)

        error = agent.process_request_with_error(request)
        state["agent_messages"].append(error)

        assert len(state["agent_messages"]) == 3
        assert state["agent_messages"][0]["message_type"] == "request"
        assert state["agent_messages"][1]["message_type"] == "response"
        assert state["agent_messages"][2]["message_type"] == "error"


class TestFullCommunicationFlow:
    """Test complete Supervisor → Agent → Supervisor communication cycles."""

    def test_full_communication_flow_single_agent(self):
        """Test complete Supervisor → Agent → Supervisor message flow."""
        state = create_initial_supervisor_state()
        assert state["current_phase"] == "analyzing"
        assert len(state["agent_messages"]) == 0

        request_msg = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "헬스장 환불 규정"},
        )
        state["agent_messages"].append(request_msg)
        state["current_phase"] = "analyzing"

        agent = MockAgent("query_analyst")
        response_msg = agent.process_request(request_msg)

        state["agent_messages"].append(response_msg)
        state["current_phase"] = "retrieving"

        assert len(state["agent_messages"]) == 2
        assert state["agent_messages"][0]["message_type"] == "request"
        assert state["agent_messages"][0]["from_agent"] == "supervisor"
        assert state["agent_messages"][0]["to_agent"] == "query_analyst"

        assert state["agent_messages"][1]["message_type"] == "response"
        assert state["agent_messages"][1]["from_agent"] == "query_analyst"
        assert state["agent_messages"][1]["to_agent"] == "supervisor"

        assert state["current_phase"] == "retrieving"

    def test_multi_agent_communication_flow(self):
        """Test communication flow with multiple agents."""
        state = create_initial_supervisor_state()

        query_analyst = MockAgent("query_analyst")
        request1 = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트 질문"},
        )
        state["agent_messages"].append(request1)
        response1 = query_analyst.process_request(request1)
        state["agent_messages"].append(response1)

        retrieval_agent = MockAgent("retrieval_agent")
        request2 = create_request_message(
            from_agent="supervisor",
            to_agent="retrieval_agent",
            task="retrieve_documents",
            params={"keywords": ["환불"]},
        )
        state["agent_messages"].append(request2)
        response2 = retrieval_agent.process_request(request2)
        state["agent_messages"].append(response2)

        generation_agent = MockAgent("generation_agent")
        request3 = create_request_message(
            from_agent="supervisor",
            to_agent="generation_agent",
            task="generate_answer",
            params={"context": "retrieved_docs"},
        )
        state["agent_messages"].append(request3)
        response3 = generation_agent.process_request(request3)
        state["agent_messages"].append(response3)

        assert len(state["agent_messages"]) == 6

        for i in range(0, 6, 2):
            assert state["agent_messages"][i]["message_type"] == "request"
            assert state["agent_messages"][i + 1]["message_type"] == "response"

        assert state["agent_messages"][0]["to_agent"] == "query_analyst"
        assert state["agent_messages"][2]["to_agent"] == "retrieval_agent"
        assert state["agent_messages"][4]["to_agent"] == "generation_agent"

    def test_communication_with_error_handling(self):
        """Test communication flow with error responses."""
        state = create_initial_supervisor_state()
        agent = MockAgent("query_analyst")

        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트"},
        )
        state["agent_messages"].append(request)

        error_response = agent.process_request_with_error(request)
        state["agent_messages"].append(error_response)

        retry_request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트", "retry": True},
        )
        state["agent_messages"].append(retry_request)

        success_response = agent.process_request(retry_request)
        state["agent_messages"].append(success_response)

        assert len(state["agent_messages"]) == 4
        assert state["agent_messages"][1]["message_type"] == "error"
        assert state["agent_messages"][3]["message_type"] == "response"
        assert state["agent_messages"][3]["content"]["status"] == "success"

    def test_supervisor_state_updates_during_flow(self):
        """Test that supervisor state updates correctly during communication."""
        state = create_initial_supervisor_state()

        assert state["current_phase"] == "analyzing"
        assert "analyze_query" in state["pending_tasks"]
        assert len(state["completed_tasks"]) == 0

        request = create_request_message(
            from_agent="supervisor",
            to_agent="query_analyst",
            task="analyze_query",
            params={"query": "테스트"},
        )
        state["agent_messages"].append(request)

        state["pending_tasks"].remove("analyze_query")
        state["completed_tasks"].append("analyze_query")
        state["current_phase"] = "retrieving"
        state["next_agent"] = "retrieval_agent"
        state["supervisor_reasoning"] = (
            "Query analysis complete. Routing to retrieval_agent."
        )

        assert state["current_phase"] == "retrieving"
        assert "analyze_query" not in state["pending_tasks"]
        assert "analyze_query" in state["completed_tasks"]
        assert state["next_agent"] == "retrieval_agent"
        assert "retrieval_agent" in state["supervisor_reasoning"]


class TestMessageTypeVariations:
    """Test different message types and content variations."""

    def test_request_message_structure(self):
        """Test request message has correct structure."""
        msg = create_request_message(
            from_agent="supervisor",
            to_agent="agent",
            task="task_name",
            params={"key": "value"},
        )

        assert "from_agent" in msg
        assert "to_agent" in msg
        assert "message_type" in msg
        assert "content" in msg
        assert "timestamp" in msg

        assert "task" in msg["content"]
        assert "params" in msg["content"]

    def test_response_message_structure(self):
        """Test response message has correct structure."""
        agent = MockAgent("test_agent")
        request = create_request_message(
            from_agent="supervisor",
            to_agent="test_agent",
            task="test",
            params={},
        )

        response = agent.process_request(request)

        assert "from_agent" in response
        assert "to_agent" in response
        assert "message_type" in response
        assert "content" in response
        assert "timestamp" in response

        assert "status" in response["content"]
        assert "result" in response["content"]

    def test_error_message_structure(self):
        """Test error message has correct structure."""
        agent = MockAgent("test_agent")
        request = create_request_message(
            from_agent="supervisor",
            to_agent="test_agent",
            task="test",
            params={},
        )

        error = agent.process_request_with_error(request)

        assert "from_agent" in error
        assert "to_agent" in error
        assert "message_type" in error
        assert "content" in error
        assert "timestamp" in error

        assert "error_type" in error["content"]
        assert "message" in error["content"]

    def test_message_type_values(self):
        """Test that message_type has valid values."""
        request = create_request_message(
            from_agent="supervisor",
            to_agent="agent",
            task="task",
            params={},
        )
        assert request["message_type"] == "request"

        agent = MockAgent("agent")
        response = agent.process_request(request)
        assert response["message_type"] == "response"

        error = agent.process_request_with_error(request)
        assert error["message_type"] == "error"


class TestAgentMessageTyping:
    """Test AgentMessage TypedDict compliance."""

    def test_agent_message_type_compliance(self):
        """Test that created messages comply with AgentMessage TypedDict."""
        msg = create_request_message(
            from_agent="supervisor",
            to_agent="agent",
            task="task",
            params={"key": "value"},
        )

        required_fields = [
            "from_agent",
            "to_agent",
            "message_type",
            "content",
            "timestamp",
        ]
        for field in required_fields:
            assert field in msg, f"Missing required field: {field}"

        assert isinstance(msg["from_agent"], str)
        assert isinstance(msg["to_agent"], str)
        assert isinstance(msg["message_type"], str)
        assert isinstance(msg["content"], dict)
        assert isinstance(msg["timestamp"], float)

    def test_supervisor_state_type_compliance(self):
        """Test that created state complies with SupervisorState TypedDict."""
        state = create_initial_supervisor_state()

        required_fields = [
            "current_phase",
            "agent_messages",
            "pending_tasks",
            "completed_tasks",
            "supervisor_reasoning",
            "next_agent",
        ]
        for field in required_fields:
            assert field in state, f"Missing required field: {field}"

        assert isinstance(state["current_phase"], str)
        assert isinstance(state["agent_messages"], list)
        assert isinstance(state["pending_tasks"], list)
        assert isinstance(state["completed_tasks"], list)
        assert isinstance(state["supervisor_reasoning"], str)
        assert state["next_agent"] is None or isinstance(state["next_agent"], str)


@pytest.mark.integration
class TestAgentCommunicationIntegration:
    """Integration tests for complete agent communication scenarios."""

    def test_complete_workflow_simulation(self):
        """Simulate a complete workflow with multiple agents."""
        state = create_initial_supervisor_state()
        agents = {
            "query_analyst": MockAgent("query_analyst"),
            "retrieval_agent": MockAgent("retrieval_agent"),
            "generation_agent": MockAgent("generation_agent"),
            "legal_reviewer": MockAgent("legal_reviewer"),
        }

        workflow_tasks = [
            ("query_analyst", "analyze_query", {"query": "헬스장 환불"}),
            ("retrieval_agent", "retrieve_documents", {"keywords": ["환불"]}),
            ("generation_agent", "generate_answer", {"context": "docs"}),
            ("legal_reviewer", "review_answer", {"answer": "draft"}),
        ]

        for agent_name, task, params in workflow_tasks:
            request = create_request_message(
                from_agent="supervisor",
                to_agent=agent_name,
                task=task,
                params=params,
            )
            state["agent_messages"].append(request)

            agent = agents[agent_name]
            response = agent.process_request(request)
            state["agent_messages"].append(response)

        assert len(state["agent_messages"]) == 8

        agent_names = set()
        for msg in state["agent_messages"]:
            if msg["message_type"] == "response":
                agent_names.add(msg["from_agent"])

        assert agent_names == set(agents.keys())
