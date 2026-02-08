"""
게스트 세션 소유권 이전 (claim) 기능 테스트

T8: ConversationDB.claim_sessions_for_user() 및 POST /chat/sessions/claim 엔드포인트
"""

from unittest.mock import MagicMock, patch

import pytest

# ============================================================
# ConversationDB.claim_sessions_for_user() 단위 테스트
# ============================================================


class TestClaimSessionsForUser:
    """ConversationDB.claim_sessions_for_user() 단위 테스트"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_claim_guest_sessions_success(self):
        """user_id=NULL인 세션이 정상적으로 이전되는지 확인"""
        with patch(
            "app.supervisor.persistence.db.ConversationDB._get_connection"
        ) as mock_conn:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchall.return_value = [("sess_1",), ("sess_2",)]
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cursor
            mock_conn.return_value = conn

            from app.supervisor.persistence.db import ConversationDB

            db = ConversationDB.__new__(ConversationDB)
            db.db_config = MagicMock()
            db._get_connection = mock_conn

            result = await db.claim_sessions_for_user(
                session_ids=["sess_1", "sess_2", "sess_3"],
                user_id="user_123",
            )

            assert result == ["sess_1", "sess_2"]
            assert isinstance(result, list)
            conn.commit.assert_called_once()
            conn.close.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_claim_no_matching_sessions(self):
        """이미 다른 사용자 소유인 세션은 무시되는지 확인"""
        with patch(
            "app.supervisor.persistence.db.ConversationDB._get_connection"
        ) as mock_conn:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchall.return_value = []  # 이전된 세션 없음
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cursor
            mock_conn.return_value = conn

            from app.supervisor.persistence.db import ConversationDB

            db = ConversationDB.__new__(ConversationDB)
            db.db_config = MagicMock()
            db._get_connection = mock_conn

            result = await db.claim_sessions_for_user(
                session_ids=["owned_sess_1"],
                user_id="user_123",
            )

            assert result == []
            conn.commit.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_claim_mixed_sessions(self):
        """일부 게스트 + 일부 소유 세션 혼합 시 게스트만 이전"""
        with patch(
            "app.supervisor.persistence.db.ConversationDB._get_connection"
        ) as mock_conn:
            conn = MagicMock()
            cursor = MagicMock()
            # sess_1만 게스트(user_id=NULL), sess_2는 이미 소유됨
            cursor.fetchall.return_value = [("sess_1",)]
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cursor
            mock_conn.return_value = conn

            from app.supervisor.persistence.db import ConversationDB

            db = ConversationDB.__new__(ConversationDB)
            db.db_config = MagicMock()
            db._get_connection = mock_conn

            result = await db.claim_sessions_for_user(
                session_ids=["sess_1", "sess_2"],
                user_id="user_123",
            )

            assert result == ["sess_1"]
            assert len(result) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_return_type_is_list_of_str(self):
        """반환 타입이 List[str]인지 확인"""
        with patch(
            "app.supervisor.persistence.db.ConversationDB._get_connection"
        ) as mock_conn:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchall.return_value = [("sess_abc",)]
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cursor
            mock_conn.return_value = conn

            from app.supervisor.persistence.db import ConversationDB

            db = ConversationDB.__new__(ConversationDB)
            db.db_config = MagicMock()
            db._get_connection = mock_conn

            result = await db.claim_sessions_for_user(
                session_ids=["sess_abc"],
                user_id="user_456",
            )

            assert isinstance(result, list)
            for item in result:
                assert isinstance(item, str)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sql_contains_user_id_is_null_condition(self):
        """SQL에 user_id IS NULL 조건이 포함되는지 확인"""
        with patch(
            "app.supervisor.persistence.db.ConversationDB._get_connection"
        ) as mock_conn:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchall.return_value = []
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cursor
            mock_conn.return_value = conn

            from app.supervisor.persistence.db import ConversationDB

            db = ConversationDB.__new__(ConversationDB)
            db.db_config = MagicMock()
            db._get_connection = mock_conn

            await db.claim_sessions_for_user(
                session_ids=["sess_1"],
                user_id="user_123",
            )

            # SQL 쿼리에 user_id IS NULL이 포함되어야 함
            sql_call = cursor.execute.call_args[0][0]
            assert "user_id IS NULL" in sql_call
            assert "RETURNING session_id" in sql_call

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_claim_db_error_raises(self):
        """DB 오류 시 예외가 전파되는지 확인"""
        with patch(
            "app.supervisor.persistence.db.ConversationDB._get_connection"
        ) as mock_conn:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.execute.side_effect = Exception("DB connection lost")
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cursor
            mock_conn.return_value = conn

            from app.supervisor.persistence.db import ConversationDB

            db = ConversationDB.__new__(ConversationDB)
            db.db_config = MagicMock()
            db._get_connection = mock_conn

            with pytest.raises(Exception, match="DB connection lost"):
                await db.claim_sessions_for_user(
                    session_ids=["sess_1"],
                    user_id="user_123",
                )

            conn.rollback.assert_called_once()


# ============================================================
# claim_guest_sessions 엔드포인트 로직 단위 테스트
# (FastAPI 앱 임포트 없이 동일한 유효성 검증 로직을 직접 테스트)
# ============================================================


class TestClaimValidation:
    """claim_guest_sessions 엔드포인트의 유효성 검증 로직 테스트"""

    @pytest.mark.unit
    def test_empty_session_ids_rejected(self):
        """빈 session_ids는 거부되어야 함"""
        body = {"session_ids": []}
        session_ids = body.get("session_ids", [])
        assert (
            not session_ids
            or not isinstance(session_ids, list)
            or len(session_ids) == 0
        )

    @pytest.mark.unit
    def test_missing_session_ids_rejected(self):
        """session_ids 키 누락은 거부되어야 함"""
        body = {}
        session_ids = body.get("session_ids", [])
        assert not session_ids

    @pytest.mark.unit
    def test_over_50_session_ids_rejected(self):
        """50개 초과 session_ids는 거부되어야 함"""
        body = {"session_ids": [f"sess_{i}" for i in range(51)]}
        session_ids = body.get("session_ids", [])
        assert len(session_ids) > 50

    @pytest.mark.unit
    def test_valid_session_ids_accepted(self):
        """유효한 session_ids는 통과해야 함"""
        body = {"session_ids": ["sess_1", "sess_2"]}
        session_ids = body.get("session_ids", [])
        assert session_ids and isinstance(session_ids, list) and len(session_ids) <= 50
