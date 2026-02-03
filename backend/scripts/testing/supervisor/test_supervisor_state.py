"""
슈퍼바이저 상태 스키마 테스트
작성일: 2026-01-26

테스트 대상:
- AgentMessage TypedDict 생성 및 필드 검증
- SupervisorState TypedDict 생성 및 필드 검증
- ChatState에 supervisor 필드 존재 확인
- create_initial_state()에서 supervisor 초기화 검증
"""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))


import pytest

# 전체 파일에 unit 마커 적용 (DB 의존성 없음)
pytestmark = pytest.mark.unit

from app.supervisor.state import (
    AgentMessage,
    SupervisorState,
    create_initial_state,
)


class TestAgentMessage:
    """AgentMessage TypedDict 테스트"""

    def test_agent_message_creation(self):
        """Test AgentMessage TypedDict creation with all fields"""
        msg: AgentMessage = {
            "from_agent": "supervisor",
            "to_agent": "query_analyst",
            "message_type": "request",
            "content": {"task": "analyze_query", "params": {"query": "환불 규정"}},
            "timestamp": 1705000000.0,
        }

        assert msg["from_agent"] == "supervisor"
        assert msg["to_agent"] == "query_analyst"
        assert msg["message_type"] == "request"
        assert msg["content"]["task"] == "analyze_query"
        assert msg["timestamp"] == 1705000000.0

    def test_agent_message_response_type(self):
        """Test AgentMessage with response message type"""
        msg: AgentMessage = {
            "from_agent": "query_analyst",
            "to_agent": "supervisor",
            "message_type": "response",
            "content": {
                "result": {"query_type": "dispute", "keywords": ["환불", "규정"]},
                "status": "success",
            },
            "timestamp": 1705000001.0,
        }

        assert msg["from_agent"] == "query_analyst"
        assert msg["message_type"] == "response"
        assert msg["content"]["status"] == "success"

    def test_agent_message_error_type(self):
        """Test AgentMessage with error message type"""
        msg: AgentMessage = {
            "from_agent": "retrieval_agent",
            "to_agent": "supervisor",
            "message_type": "error",
            "content": {
                "error_type": "retrieval_failed",
                "message": "No documents found",
            },
            "timestamp": 1705000002.0,
        }

        assert msg["message_type"] == "error"
        assert msg["content"]["error_type"] == "retrieval_failed"

    def test_agent_message_all_fields_present(self):
        """Test that AgentMessage has all required fields"""
        msg: AgentMessage = {
            "from_agent": "supervisor",
            "to_agent": "legal_reviewer",
            "message_type": "request",
            "content": {"task": "review_answer"},
            "timestamp": 1705000003.0,
        }

        # Verify all required fields exist
        assert "from_agent" in msg
        assert "to_agent" in msg
        assert "message_type" in msg
        assert "content" in msg
        assert "timestamp" in msg


class TestSupervisorState:
    """SupervisorState TypedDict 테스트"""

    def test_supervisor_state_creation(self):
        """Test SupervisorState TypedDict creation with all fields"""
        state: SupervisorState = {
            "current_phase": "analyzing",
            "agent_messages": [
                {
                    "from_agent": "supervisor",
                    "to_agent": "query_analyst",
                    "message_type": "request",
                    "content": {"task": "analyze_query"},
                    "timestamp": 1705000000.0,
                }
            ],
            "pending_tasks": ["retrieve_documents", "generate_answer"],
            "completed_tasks": ["analyze_query"],
            "supervisor_reasoning": "Query requires document retrieval",
            "next_agent": "retrieval_agent",
        }

        assert state["current_phase"] == "analyzing"
        assert len(state["agent_messages"]) == 1
        assert state["agent_messages"][0]["from_agent"] == "supervisor"
        assert "retrieve_documents" in state["pending_tasks"]
        assert "analyze_query" in state["completed_tasks"]
        assert state["next_agent"] == "retrieval_agent"

    def test_supervisor_state_retrieving_phase(self):
        """Test SupervisorState in retrieving phase"""
        state: SupervisorState = {
            "current_phase": "retrieving",
            "agent_messages": [],
            "pending_tasks": ["generate_answer", "review_answer"],
            "completed_tasks": ["analyze_query", "retrieve_documents"],
            "supervisor_reasoning": "Documents retrieved successfully",
            "next_agent": "generation_agent",
        }

        assert state["current_phase"] == "retrieving"
        assert len(state["completed_tasks"]) == 2

    def test_supervisor_state_done_phase(self):
        """Test SupervisorState in done phase"""
        state: SupervisorState = {
            "current_phase": "done",
            "agent_messages": [],
            "pending_tasks": [],
            "completed_tasks": [
                "analyze_query",
                "retrieve_documents",
                "generate_answer",
                "review_answer",
            ],
            "supervisor_reasoning": "All tasks completed successfully",
            "next_agent": None,
        }

        assert state["current_phase"] == "done"
        assert state["next_agent"] is None
        assert len(state["pending_tasks"]) == 0

    def test_supervisor_state_multiple_messages(self):
        """Test SupervisorState with multiple agent messages"""
        messages: list[AgentMessage] = [
            {
                "from_agent": "supervisor",
                "to_agent": "query_analyst",
                "message_type": "request",
                "content": {"task": "analyze"},
                "timestamp": 1705000000.0,
            },
            {
                "from_agent": "query_analyst",
                "to_agent": "supervisor",
                "message_type": "response",
                "content": {"result": "analysis_done"},
                "timestamp": 1705000001.0,
            },
            {
                "from_agent": "supervisor",
                "to_agent": "retrieval_agent",
                "message_type": "request",
                "content": {"task": "retrieve"},
                "timestamp": 1705000002.0,
            },
        ]

        state: SupervisorState = {
            "current_phase": "retrieving",
            "agent_messages": messages,
            "pending_tasks": ["generate_answer"],
            "completed_tasks": ["analyze_query", "retrieve_documents"],
            "supervisor_reasoning": "Proceeding to generation",
            "next_agent": "generation_agent",
        }

        assert len(state["agent_messages"]) == 3
        assert state["agent_messages"][0]["from_agent"] == "supervisor"
        assert state["agent_messages"][1]["message_type"] == "response"

    def test_supervisor_state_all_fields_present(self):
        """Test that SupervisorState has all required fields"""
        state: SupervisorState = {
            "current_phase": "analyzing",
            "agent_messages": [],
            "pending_tasks": [],
            "completed_tasks": [],
            "supervisor_reasoning": "Initial state",
            "next_agent": None,
        }

        # Verify all required fields exist
        assert "current_phase" in state
        assert "agent_messages" in state
        assert "pending_tasks" in state
        assert "completed_tasks" in state
        assert "supervisor_reasoning" in state
        assert "next_agent" in state


class TestChatStateWithSupervisor:
    """ChatState에서 supervisor 필드 테스트"""

    def test_chatstate_has_supervisor_field(self):
        """Test that ChatState has supervisor field"""
        state = create_initial_state(user_query="테스트 질문", chat_type="general")

        # Verify supervisor field exists
        assert "supervisor" in state
        assert state["supervisor"] is None

    def test_chatstate_supervisor_field_type(self):
        """Test that supervisor field can hold SupervisorState"""
        initial_state = create_initial_state(
            user_query="테스트 질문", chat_type="general"
        )

        # Create a SupervisorState
        supervisor_state: SupervisorState = {
            "current_phase": "analyzing",
            "agent_messages": [],
            "pending_tasks": ["analyze_query"],
            "completed_tasks": [],
            "supervisor_reasoning": "Starting analysis",
            "next_agent": "query_analyst",
        }

        # Assign to ChatState
        initial_state["supervisor"] = supervisor_state

        assert initial_state["supervisor"] is not None
        assert initial_state["supervisor"]["current_phase"] == "analyzing"

    def test_chatstate_supervisor_field_optional(self):
        """Test that supervisor field is optional (can be None)"""
        state = create_initial_state(
            user_query="테스트 질문",
            chat_type="dispute",
            onboarding={"purchase_item": "상품"},
        )

        # supervisor should be None initially
        assert state["supervisor"] is None

        # Should be able to set it to None again
        state["supervisor"] = None
        assert state["supervisor"] is None


class TestCreateInitialStateSupervisor:
    """create_initial_state() 함수의 supervisor 필드 초기화 테스트"""

    def test_create_initial_state_supervisor_none(self):
        """Test that create_initial_state() initializes supervisor=None"""
        state = create_initial_state(user_query="환불 규정 알려줘", chat_type="dispute")

        assert state["supervisor"] is None

    def test_create_initial_state_general_chat(self):
        """Test create_initial_state with general chat type"""
        state = create_initial_state(user_query="안녕하세요", chat_type="general")

        assert state["chat_type"] == "general"
        assert state["supervisor"] is None
        assert state["user_query"] == "안녕하세요"

    def test_create_initial_state_dispute_chat(self):
        """Test create_initial_state with dispute chat type"""
        state = create_initial_state(
            user_query="환불 받고 싶어요",
            chat_type="dispute",
            onboarding={"purchase_item": "헬스장 회원권"},
        )

        assert state["chat_type"] == "dispute"
        assert state["supervisor"] is None
        assert state["onboarding"] is not None

    def test_create_initial_state_all_fields_initialized(self):
        """Test that create_initial_state initializes all required fields"""
        state = create_initial_state(user_query="테스트", chat_type="general")

        # Check supervisor field
        assert "supervisor" in state
        assert state["supervisor"] is None

        # Check other essential fields
        assert "messages" in state
        assert "user_query" in state
        assert "chat_type" in state
        assert "query_analysis" in state
        assert "retrieval" in state
        assert "final_answer" in state

    def test_create_initial_state_supervisor_independent_from_other_fields(self):
        """Test that supervisor field is independent from other state fields"""
        state1 = create_initial_state(user_query="질문 1", chat_type="general")

        state2 = create_initial_state(user_query="질문 2", chat_type="dispute")

        # Both should have supervisor=None
        assert state1["supervisor"] is None
        assert state2["supervisor"] is None

        # Modifying one shouldn't affect the other
        state1["supervisor"] = {
            "current_phase": "analyzing",
            "agent_messages": [],
            "pending_tasks": [],
            "completed_tasks": [],
            "supervisor_reasoning": "test",
            "next_agent": None,
        }

        assert state2["supervisor"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
