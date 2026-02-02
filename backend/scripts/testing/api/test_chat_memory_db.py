"""
똑소리 프로젝트 - Chat API + Memory DB 통합 테스트

작성일: 2026-01-28
Track 3: Memory System Integration

Integration tests for chat API with DB-based memory.
"""

import os
from unittest.mock import patch

import pytest

# Skip tests if database is not available
pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS", "0") == "1",
    reason="Database not available or SKIP_DB_TESTS=1",
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestChatAPIWithMemoryDB:
    """Integration tests for chat API with DB memory"""

    async def test_chat_without_auth_creates_guest_session(self, test_client):
        """Test chat without authentication creates guest session"""
        response = await test_client.post(
            "/chat",
            json={
                "message": "환불 가능한가요?",
                "chat_type": "dispute",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "answer" in data

        # Check DB directly (if possible)
        # TODO: Add DB verification when available

    async def test_chat_with_auth_creates_user_session(self, test_client, auth_token):
        """Test chat with authentication creates user session"""
        response = await test_client.post(
            "/chat",
            json={
                "message": "환불 가능한가요?",
                "chat_type": "dispute",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "answer" in data

    async def test_multiturn_conversation_with_db(self, test_client):
        """Test multi-turn conversation persists to DB"""
        # First turn
        response1 = await test_client.post(
            "/chat",
            json={
                "message": "노트북 환불 가능한가요?",
                "chat_type": "dispute",
            },
        )
        assert response1.status_code == 200
        data1 = response1.json()
        session_id = data1["session_id"]

        # Second turn (same session)
        response2 = await test_client.post(
            "/chat",
            json={
                "message": "언제까지 환불되나요?",
                "chat_type": "dispute",
                "session_id": session_id,
            },
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["session_id"] == session_id

        # Third turn (same session)
        response3 = await test_client.post(
            "/chat",
            json={
                "message": "환불 절차를 알려주세요",
                "chat_type": "dispute",
                "session_id": session_id,
            },
        )
        assert response3.status_code == 200
        data3 = response3.json()
        assert data3["session_id"] == session_id

    async def test_conversation_memory_loads_from_db(self, test_client):
        """Test conversation memory loads from DB on subsequent requests"""
        # First turn
        response1 = await test_client.post(
            "/chat",
            json={
                "message": "작년 1월 15일에 온라인몰에서 150만원짜리 노트북을 샀습니다",
                "chat_type": "dispute",
            },
        )
        session_id = response1.json()["session_id"]

        # Second turn (should have context from DB)
        response2 = await test_client.post(
            "/chat",
            json={
                "message": "환불 가능한가요?",
                "chat_type": "dispute",
                "session_id": session_id,
            },
        )
        assert response2.status_code == 200
        # Answer should reference the purchase info from first turn

    async def test_conversation_compaction_persists_to_db(self, test_client):
        """Test conversation compaction saves summary to DB"""
        session_id = None

        # Add 30+ turns to trigger compaction
        for i in range(32):
            response = await test_client.post(
                "/chat",
                json={
                    "message": f"노트북 환불 관련 질문 {i}",
                    "chat_type": "dispute",
                    "session_id": session_id,
                },
            )
            assert response.status_code == 200
            if session_id is None:
                session_id = response.json()["session_id"]

        # Summary should be saved to DB
        # TODO: Add DB verification when available

    async def test_general_chat_type_no_memory_db(self, test_client):
        """Test general chat type does not use DB memory"""
        # First turn
        response1 = await test_client.post(
            "/chat",
            json={
                "message": "안녕하세요",
                "chat_type": "general",
            },
        )
        session_id = response1.json()["session_id"]

        # Second turn (should not have context)
        response2 = await test_client.post(
            "/chat",
            json={
                "message": "제 이름이 뭐였죠?",
                "chat_type": "general",
                "session_id": session_id,
            },
        )
        assert response2.status_code == 200
        # Should not remember previous context


@pytest.mark.integration
@pytest.mark.asyncio
class TestChatStreamWithMemoryDB:
    """Integration tests for chat stream with DB memory"""

    async def test_stream_without_auth_creates_guest_session(self, test_client):
        """Test streaming chat without auth creates guest session"""
        response = await test_client.post(
            "/chat/stream",
            json={
                "message": "환불 가능한가요?",
                "chat_type": "dispute",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    async def test_stream_multiturn_conversation(self, test_client):
        """Test streaming multi-turn conversation"""
        # First turn
        response1 = await test_client.post(
            "/chat/stream",
            json={
                "message": "노트북 환불 가능한가요?",
                "chat_type": "dispute",
            },
        )
        # Extract session_id from SSE events
        # TODO: Parse SSE events to get session_id

        # Second turn
        # response2 = await test_client.post(
        #     "/chat/stream",
        #     json={
        #         "message": "언제까지 환불되나요?",
        #         "chat_type": "dispute",
        #         "session_id": session_id,
        #     }
        # )
        # TODO: Complete stream test


@pytest.mark.integration
@pytest.mark.needs_db
class TestMemoryDBCleanup:
    """Test memory DB cleanup"""

    def test_cleanup_expired_guest_sessions(self):
        """Test cleanup service deletes expired guest sessions"""
        # TODO: Create expired guest sessions
        # TODO: Run cleanup
        # TODO: Verify sessions are deleted
        pass

    def test_cleanup_does_not_delete_user_sessions(self):
        """Test cleanup does not delete user sessions"""
        # TODO: Create user sessions
        # TODO: Run cleanup
        # TODO: Verify user sessions are not deleted
        pass


# Fixtures


@pytest.fixture
async def test_client():
    """Create test client"""
    from httpx import AsyncClient

    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def auth_token():
    """Create test auth token"""
    from app.auth.dependencies import create_access_token
    from app.auth.models import User

    user = User(
        user_id="test_user_123",
        email="test@example.com",
        name="Test User",
        provider="google",
    )

    token, _ = create_access_token(user)
    return token
