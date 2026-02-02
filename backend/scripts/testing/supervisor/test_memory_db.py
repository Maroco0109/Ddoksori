"""
똑소리 프로젝트 - 메모리 DB 통합 테스트

작성일: 2026-01-28
Track 3: Memory System Integration

Unit tests for ConversationMemory with DB persistence (mocked DB).
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.supervisor.memory import (
    MEMORY_POLICIES,
    CompactSummary,
    ConversationMemory,
    ConversationTurn,
)

# Mark all tests as unit tests
pytestmark = pytest.mark.unit


def run_async(coro):
    """Helper to run async functions in tests"""
    return asyncio.run(coro)


@pytest.fixture
def mock_conversation_db():
    """Mock ConversationDB for testing"""
    with patch("app.supervisor.persistence.db.ConversationDB") as mock_db_class:
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        # Mock async methods
        mock_db.create_conversation = AsyncMock(return_value=uuid4())
        mock_db.get_conversation_by_session = AsyncMock(return_value=None)
        mock_db.add_turn = AsyncMock(return_value=uuid4())
        mock_db.get_conversation_history = AsyncMock(return_value=[])
        mock_db.save_summary = AsyncMock(return_value=uuid4())
        mock_db.get_summary = AsyncMock(return_value=None)

        yield mock_db


class TestConversationMemoryInMemory:
    """In-memory mode tests (use_db=False)"""

    def test_memory_initialization_in_memory(self):
        """Test memory initialization without DB"""
        memory = ConversationMemory(
            chat_type="dispute", session_id="sess_123", user_id="user_456", use_db=False
        )

        assert memory.chat_type == "dispute"
        assert memory.session_id == "sess_123"
        assert memory.user_id == "user_456"
        assert memory.use_db is False
        assert memory.db is None
        assert len(memory.turns) == 0
        assert memory.total_turn_count == 0

    def test_add_turn_in_memory(self):
        """Test adding turns without DB"""

        async def _test():
            memory = ConversationMemory(chat_type="dispute", use_db=False)

            await memory.add_turn(role="user", content="환불 가능한가요?")
            await memory.add_turn(role="assistant", content="네, 가능합니다.")

            assert len(memory.turns) == 2
            assert memory.total_turn_count == 2
            assert memory.turns[0].role == "user"
            assert memory.turns[1].role == "assistant"

        run_async(_test())

    def test_general_chat_type_no_memory(self):
        """Test general chat type does not store memory"""

        async def _test():
            memory = ConversationMemory(chat_type="general", use_db=False)

            await memory.add_turn(role="user", content="안녕하세요")
            await memory.add_turn(role="assistant", content="반갑습니다")

            assert len(memory.turns) == 0
            assert memory.total_turn_count == 0

        run_async(_test())

    def test_compact_trigger_in_memory(self):
        """Test compaction triggers at max_turns"""

        async def _test():
            memory = ConversationMemory(chat_type="dispute", use_db=False)

            # Add 30 turns
            for i in range(30):
                await memory.add_turn(
                    role="user" if i % 2 == 0 else "assistant", content=f"Message {i}"
                )

            # Should keep only sliding_window (10) turns
            assert len(memory.turns) == 10
            assert memory.total_turn_count == 30
            assert memory.compact_summary is not None

        run_async(_test())

    def test_get_context_for_llm_in_memory(self):
        """Test getting context for LLM"""

        async def _test():
            memory = ConversationMemory(chat_type="dispute", use_db=False)

            await memory.add_turn(role="user", content="환불 가능한가요?")
            await memory.add_turn(role="assistant", content="네, 가능합니다.")

            context = memory.get_context_for_llm()

            assert "conversation_history" in context
            assert "compact_summary" in context
            assert len(context["conversation_history"]) == 2
            assert context["conversation_history"][0]["role"] == "user"

        run_async(_test())


class TestConversationMemoryWithDB:
    """DB mode tests (use_db=True, mocked DB)"""

    def test_memory_initialization_with_new_conversation(self, mock_conversation_db):
        """Test memory initialization creates new conversation in DB"""

        async def _test():
            memory = ConversationMemory(
                chat_type="dispute",
                session_id="sess_123",
                user_id="user_456",
                use_db=True,
            )

            assert memory.use_db is True
            assert memory.db is not None

            # Add turn to trigger DB load
            await memory.add_turn(role="user", content="환불 가능한가요?")

            # Should create new conversation
            mock_conversation_db.get_conversation_by_session.assert_called_once_with(
                "sess_123"
            )
            mock_conversation_db.create_conversation.assert_called_once()

        run_async(_test())

    def test_memory_initialization_with_existing_conversation(
        self, mock_conversation_db
    ):
        """Test memory initialization loads existing conversation from DB"""

        async def _test():
            conv_id = uuid4()
            mock_conversation_db.get_conversation_by_session.return_value = {
                "conversation_id": conv_id,
                "session_id": "sess_123",
                "user_id": "user_456",
                "chat_type": "dispute",
                "turn_count": 5,
                "is_active": True,
                "last_compaction_at": 0,
            }
            mock_conversation_db.get_conversation_history.return_value = [
                {
                    "turn_id": uuid4(),
                    "turn_number": 2,
                    "role": "assistant",
                    "content": "네, 가능합니다.",
                    "metadata": {},
                    "created_at": datetime.now(),
                },
                {
                    "turn_id": uuid4(),
                    "turn_number": 1,
                    "role": "user",
                    "content": "환불 가능한가요?",
                    "metadata": {},
                    "created_at": datetime.now(),
                },
            ]

            memory = ConversationMemory(
                chat_type="dispute",
                session_id="sess_123",
                user_id="user_456",
                use_db=True,
            )

            # Add turn to trigger DB load
            await memory.add_turn(role="user", content="언제까지 환불되나요?")

            # Should load existing conversation
            mock_conversation_db.get_conversation_by_session.assert_called_once_with(
                "sess_123"
            )
            mock_conversation_db.create_conversation.assert_not_called()

            # Should have loaded turns
            assert memory.conversation_id == conv_id
            assert memory.total_turn_count == 6  # 5 + 1 new turn

        run_async(_test())

    def test_add_turn_saves_to_db(self, mock_conversation_db):
        """Test adding turn saves to DB"""

        async def _test():
            conv_id = uuid4()
            mock_conversation_db.create_conversation.return_value = conv_id

            memory = ConversationMemory(
                chat_type="dispute",
                session_id="sess_123",
                user_id="user_456",
                use_db=True,
            )

            await memory.add_turn(role="user", content="환불 가능한가요?")

            # Should save to DB
            mock_conversation_db.add_turn.assert_called_once()
            call_args = mock_conversation_db.add_turn.call_args
            assert call_args[1]["conversation_id"] == conv_id
            assert call_args[1]["role"] == "user"
            assert call_args[1]["content"] == "환불 가능한가요?"

        run_async(_test())

    def test_compact_saves_summary_to_db(self, mock_conversation_db):
        """Test compaction saves summary to DB"""

        async def _test():
            conv_id = uuid4()
            mock_conversation_db.create_conversation.return_value = conv_id

            memory = ConversationMemory(
                chat_type="dispute",
                session_id="sess_123",
                user_id="user_456",
                use_db=True,
            )

            # Add 30 turns to trigger compaction
            for i in range(30):
                await memory.add_turn(
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"노트북 환불 요청 {i}",
                )

            # Should save summary to DB
            mock_conversation_db.save_summary.assert_called_once()
            call_args = mock_conversation_db.save_summary.call_args
            assert call_args[1]["conversation_id"] == conv_id
            assert call_args[1]["compacted_turn_count"] == 30

        run_async(_test())

    def test_load_summary_from_db(self, mock_conversation_db):
        """Test loading summary from DB"""

        async def _test():
            conv_id = uuid4()
            mock_conversation_db.get_conversation_by_session.return_value = {
                "conversation_id": conv_id,
                "session_id": "sess_123",
                "user_id": "user_456",
                "chat_type": "dispute",
                "turn_count": 35,
                "is_active": True,
                "last_compaction_at": 30,
            }
            mock_conversation_db.get_summary.return_value = {
                "purchase_item": "노트북",
                "purchase_date": "2024-01-15",
                "purchase_amount": "1500000원",
                "purchase_place": "온라인몰",
                "dispute_type": "환불",
                "dispute_details": None,
                "desired_resolution": None,
                "key_facts": {},
                "compacted_turn_count": 30,
            }

            memory = ConversationMemory(
                chat_type="dispute",
                session_id="sess_123",
                user_id="user_456",
                use_db=True,
            )

            # Add turn to trigger DB load
            await memory.add_turn(role="user", content="언제 환불되나요?")

            # Should load summary
            mock_conversation_db.get_summary.assert_called_once_with(conv_id)
            assert memory.compact_summary is not None
            assert memory.compact_summary.purchase_item == "노트북"
            assert memory.compact_summary.dispute_type == "환불"

        run_async(_test())

    def test_db_failure_falls_back_to_memory(self, mock_conversation_db):
        """Test DB failure falls back to in-memory mode"""

        async def _test():
            mock_conversation_db.get_conversation_by_session.side_effect = Exception(
                "DB connection failed"
            )

            memory = ConversationMemory(
                chat_type="dispute",
                session_id="sess_123",
                user_id="user_456",
                use_db=True,
            )

            # Should not raise exception
            await memory.add_turn(role="user", content="환불 가능한가요?")

            # Should fall back to in-memory mode
            assert memory.use_db is False
            assert memory.db is None
            assert len(memory.turns) == 1

        run_async(_test())


class TestConversationTurn:
    """Test ConversationTurn data class"""

    def test_conversation_turn_creation(self):
        """Test creating conversation turn"""
        turn = ConversationTurn(
            role="user",
            content="환불 가능한가요?",
            turn_number=1,
            metadata={"ip": "127.0.0.1"},
            timestamp=datetime.now(),
        )

        assert turn.role == "user"
        assert turn.content == "환불 가능한가요?"
        assert turn.turn_number == 1
        assert turn.metadata["ip"] == "127.0.0.1"
        assert turn.timestamp is not None


class TestCompactSummary:
    """Test CompactSummary data class"""

    def test_compact_summary_to_dict(self):
        """Test converting summary to dict"""
        summary = CompactSummary(
            purchase_item="노트북",
            purchase_date="2024-01-15",
            dispute_type="환불",
            key_facts=["배송 지연", "제품 불량"],
            compacted_turn_count=30,
        )

        data = summary.to_dict()

        assert data["purchase_item"] == "노트북"
        assert data["purchase_date"] == "2024-01-15"
        assert data["dispute_type"] == "환불"
        assert len(data["key_facts"]) == 2
        assert data["compacted_turn_count"] == 30

    def test_compact_summary_from_dict(self):
        """Test creating summary from dict"""
        data = {
            "purchase_item": "노트북",
            "purchase_date": "2024-01-15",
            "dispute_type": "환불",
            "key_facts": ["배송 지연", "제품 불량"],
            "compacted_turn_count": 30,
        }

        summary = CompactSummary.from_dict(data)

        assert summary.purchase_item == "노트북"
        assert summary.purchase_date == "2024-01-15"
        assert summary.dispute_type == "환불"
        assert len(summary.key_facts) == 2
        assert summary.compacted_turn_count == 30


class TestMemoryPolicies:
    """Test memory policies"""

    def test_dispute_policy(self):
        """Test dispute policy configuration"""
        policy = MEMORY_POLICIES["dispute"]

        assert policy.max_turns == 30
        assert policy.compact_enabled is True
        assert policy.sliding_window == 10

    def test_general_policy(self):
        """Test general policy configuration"""
        policy = MEMORY_POLICIES["general"]

        assert policy.max_turns == 0
        assert policy.compact_enabled is False
        assert policy.sliding_window == 0
