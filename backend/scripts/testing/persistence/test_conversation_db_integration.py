"""
Integration tests for ConversationDB

작성일: 2026-01-28
설명: ConversationDB 통합 테스트 (실제 DB 필요)

⚠️ 주의: DB가 READ_ONLY이거나 테이블이 없으면 SKIP됩니다.
"""

from datetime import datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio

from app.common.config import get_config
from app.supervisor.persistence.db import ConversationDB

# 모든 테스트는 실제 DB 연결이 필요하므로 CI에서 제외
pytestmark = pytest.mark.skip_ci


# DB 연결 확인용 픽스처
@pytest_asyncio.fixture
async def db():
    """ConversationDB 인스턴스 생성"""
    db_instance = ConversationDB()
    yield db_instance


@pytest_asyncio.fixture
async def check_db_available(db):
    """DB 테이블 존재 여부 확인"""
    import psycopg2

    try:
        conn = db._get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM conversations LIMIT 1")
        conn.close()
        return True
    except (psycopg2.Error, Exception):
        pytest.skip(
            "DB 테이블이 없거나 READ_ONLY입니다. 수동으로 마이그레이션을 실행하세요."
        )


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_create_and_get_conversation_integration(db, check_db_available):
    """대화 생성 및 조회 통합 테스트"""
    session_id = f"test_sess_{datetime.now().timestamp()}"

    # 대화 생성
    conv_id = await db.create_conversation(
        session_id=session_id, chat_type="dispute", user_id="test_user"
    )

    assert isinstance(conv_id, UUID)

    # 대화 조회
    conv = await db.get_conversation_by_session(session_id)
    assert conv is not None
    assert conv["session_id"] == session_id
    assert conv["chat_type"] == "dispute"
    assert conv["user_id"] == "test_user"


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_add_turn_integration(db, check_db_available):
    """대화 턴 추가 통합 테스트"""
    session_id = f"test_sess_{datetime.now().timestamp()}"

    # 대화 생성
    conv_id = await db.create_conversation(session_id=session_id, chat_type="dispute")

    # 턴 추가
    turn_id1 = await db.add_turn(
        conversation_id=conv_id, role="user", content="첫 번째 메시지"
    )
    assert isinstance(turn_id1, UUID)

    turn_id2 = await db.add_turn(
        conversation_id=conv_id, role="assistant", content="두 번째 메시지"
    )
    assert isinstance(turn_id2, UUID)

    # 이력 조회
    history = await db.get_conversation_history(conv_id)
    assert len(history) == 2
    assert history[0]["role"] == "assistant"  # 최신순
    assert history[1]["role"] == "user"


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_save_summary_integration(db, check_db_available):
    """대화 요약 저장 통합 테스트"""
    session_id = f"test_sess_{datetime.now().timestamp()}"

    # 대화 생성
    conv_id = await db.create_conversation(session_id=session_id, chat_type="dispute")

    # 요약 저장
    summary_data = {
        "purchase_item": "테스트 상품",
        "purchase_date": "2026-01-28",
        "dispute_type": "환불",
        "key_facts": {"test": "data"},
    }

    summary_id = await db.save_summary(
        conversation_id=conv_id, summary_data=summary_data, compacted_turn_count=5
    )

    assert isinstance(summary_id, UUID)

    # 요약 조회
    summary = await db.get_summary(conv_id)
    assert summary is not None
    assert summary["purchase_item"] == "테스트 상품"


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_cleanup_expired_sessions_integration(db, check_db_available):
    """만료된 세션 정리 통합 테스트"""
    # 이미 만료된 게스트 세션 생성
    session_id = f"test_expired_{datetime.now().timestamp()}"
    expires_at = datetime.now() - timedelta(hours=1)  # 1시간 전 만료

    conv_id = await db.create_conversation(
        session_id=session_id,
        chat_type="dispute",
        user_id=None,  # 게스트
        expires_at=expires_at,
    )

    # Cleanup 실행
    deleted_count = await db.cleanup_expired_sessions()

    # 최소 1개 이상 삭제되어야 함
    assert deleted_count >= 1

    # 삭제된 대화 조회 시 None 반환
    conv = await db.get_conversation_by_session(session_id)
    assert conv is None
