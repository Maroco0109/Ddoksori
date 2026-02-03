"""
Unit tests for ConversationDB

작성일: 2026-01-28
설명: ConversationDB 단위 테스트 (모킹 사용, DB 접근 없음)
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.supervisor.persistence.db import ConversationDB


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_conversation():
    """대화 생성 테스트 (모킹)"""
    mock_uuid = uuid4()

    with patch(
        "app.supervisor.persistence.db.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_to_thread:
        mock_to_thread.return_value = mock_uuid

        db = ConversationDB()
        conv_id = await db.create_conversation(
            session_id="sess_123", chat_type="dispute", user_id="user_456"
        )

        assert conv_id == mock_uuid
        mock_to_thread.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_conversation_invalid_chat_type():
    """잘못된 chat_type으로 대화 생성 시 예외 발생 테스트"""
    db = ConversationDB()

    with pytest.raises(ValueError) as exc_info:
        await db.create_conversation(
            session_id="sess_123", chat_type="invalid", user_id="user_456"
        )

    assert "Invalid chat_type" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_conversation_by_session():
    """세션 ID로 대화 조회 테스트 (모킹)"""
    mock_conv = {
        "conversation_id": uuid4(),
        "session_id": "sess_123",
        "user_id": "user_456",
        "chat_type": "dispute",
        "is_active": True,
        "turn_count": 5,
        "last_compaction_at": 0,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "expires_at": None,
    }

    with patch(
        "app.supervisor.persistence.db.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_to_thread:
        mock_to_thread.return_value = mock_conv

        db = ConversationDB()
        result = await db.get_conversation_by_session("sess_123")

        assert result == mock_conv
        assert result["session_id"] == "sess_123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_turn():
    """대화 턴 추가 테스트 (모킹)"""
    mock_turn_id = uuid4()
    conv_id = uuid4()

    with patch(
        "app.supervisor.persistence.db.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_to_thread:
        mock_to_thread.return_value = mock_turn_id

        db = ConversationDB()
        turn_id = await db.add_turn(
            conversation_id=conv_id, role="user", content="테스트 메시지"
        )

        assert turn_id == mock_turn_id
        mock_to_thread.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_turn_invalid_role():
    """잘못된 role로 턴 추가 시 예외 발생 테스트"""
    db = ConversationDB()
    conv_id = uuid4()

    with pytest.raises(ValueError) as exc_info:
        await db.add_turn(
            conversation_id=conv_id, role="invalid", content="테스트 메시지"
        )

    assert "Invalid role" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_conversation_history():
    """대화 이력 조회 테스트 (모킹)"""
    mock_history = [
        {
            "turn_id": uuid4(),
            "turn_number": 2,
            "role": "assistant",
            "content": "답변입니다",
            "metadata": {},
            "created_at": datetime.now(),
        },
        {
            "turn_id": uuid4(),
            "turn_number": 1,
            "role": "user",
            "content": "질문입니다",
            "metadata": {},
            "created_at": datetime.now(),
        },
    ]

    with patch(
        "app.supervisor.persistence.db.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_to_thread:
        mock_to_thread.return_value = mock_history

        db = ConversationDB()
        result = await db.get_conversation_history(uuid4(), limit=10)

        assert len(result) == 2
        assert result[0]["turn_number"] == 2  # 최신순


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_summary():
    """대화 요약 저장 테스트 (모킹)"""
    mock_summary_id = uuid4()
    conv_id = uuid4()

    summary_data = {
        "purchase_item": "노트북",
        "purchase_date": "2026-01-01",
        "purchase_amount": "1,000,000원",
        "purchase_place": "온라인몰",
        "dispute_type": "환불",
        "dispute_details": "불량품",
        "desired_resolution": "전액 환불",
        "key_facts": {"fact1": "value1"},
    }

    with patch(
        "app.supervisor.persistence.db.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_to_thread:
        mock_to_thread.return_value = mock_summary_id

        db = ConversationDB()
        summary_id = await db.save_summary(
            conversation_id=conv_id, summary_data=summary_data, compacted_turn_count=10
        )

        assert summary_id == mock_summary_id
        mock_to_thread.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_expired_sessions():
    """만료된 세션 정리 테스트 (모킹)"""
    with patch(
        "app.supervisor.persistence.db.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_to_thread:
        mock_to_thread.return_value = 3  # 3개 삭제됨

        db = ConversationDB()
        deleted_count = await db.cleanup_expired_sessions()

        assert deleted_count == 3
        mock_to_thread.assert_called_once()
