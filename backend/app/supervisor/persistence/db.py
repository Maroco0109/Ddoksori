"""
똑소리 프로젝트 - 대화 메모리 데이터베이스 접근 계층

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
PostgreSQL 기반 대화 이력 저장 및 조회를 담당합니다.
- 대화 세션 생성/조회/갱신
- 대화 턴 저장/조회
- 대화 요약 (Compaction) 저장/조회
- 만료된 게스트 세션 정리

[사용 예시]
    from app.supervisor.persistence.db import ConversationDB
    from app.common.config import get_config

    config = get_config()
    db = ConversationDB(config.database)

    # 새 대화 생성
    conv_id = await db.create_conversation(
        session_id="sess_123",
        user_id="user_456",
        chat_type="dispute"
    )

    # 대화 턴 추가
    await db.add_turn(
        conversation_id=conv_id,
        role="user",
        content="환불 가능한가요?"
    )

    # 대화 이력 조회
    history = await db.get_conversation_history(conv_id, limit=10)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2
import psycopg2.extras

from app.common.config import DatabaseConfig, get_config

logger = logging.getLogger(__name__)


class ConversationDB:
    """
    대화 메모리 데이터베이스 접근 계층.

    PostgreSQL을 사용하여 대화 세션, 턴, 요약 정보를 저장하고 조회합니다.
    각 메서드 호출마다 새 연결을 생성하고 종료합니다 (동시성 안전).
    """

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        """
        ConversationDB를 초기화합니다.

        Args:
            db_config: 데이터베이스 설정 (None이면 get_config()에서 가져옴)
        """
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        """
        데이터베이스 연결을 생성합니다.

        Returns:
            psycopg2 connection 객체

        Raises:
            psycopg2.Error: 연결 실패 시
        """
        try:
            conn = psycopg2.connect(**self.db_config.get_connection_dict())
            return conn
        except psycopg2.Error as e:
            logger.error(f"[ConversationDB] DB 연결 실패: {e}")
            raise

    async def create_conversation(
        self,
        session_id: str,
        chat_type: str,
        user_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> UUID:
        """
        새 대화 세션을 생성합니다.

        Args:
            session_id: 프론트엔드 세션 ID (고유해야 함)
            chat_type: 채팅 유형 ("dispute" | "general")
            user_id: 사용자 ID (로그인 사용자만, None = 게스트)
            expires_at: 만료 시각 (게스트 세션만, None = 자동 계산)

        Returns:
            생성된 conversation_id (UUID)

        Raises:
            psycopg2.IntegrityError: session_id 중복 시
            ValueError: 잘못된 chat_type
        """
        if chat_type not in ("dispute", "general"):
            raise ValueError(f"Invalid chat_type: {chat_type}")

        # 게스트 세션인 경우 만료 시각 자동 설정
        if user_id is None and expires_at is None:
            ttl_hours = get_config().memory.guest_session_ttl_hours
            expires_at = datetime.now() + timedelta(hours=ttl_hours)

        def _create():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO conversations (session_id, user_id, chat_type, expires_at)
                        VALUES (%s, %s, %s, %s)
                        RETURNING conversation_id
                        """,
                        (session_id, user_id, chat_type, expires_at),
                    )
                    conv_id = cur.fetchone()[0]
                conn.commit()
                logger.info(
                    f"[ConversationDB] 대화 생성: session_id={session_id}, conv_id={conv_id}"
                )
                return conv_id
            except Exception as e:
                conn.rollback()
                logger.error(f"[ConversationDB] 대화 생성 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_create)

    async def get_conversation_by_session(
        self, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        세션 ID로 대화 정보를 조회합니다.

        Args:
            session_id: 프론트엔드 세션 ID

        Returns:
            대화 정보 딕셔너리 (없으면 None)
            {
                "conversation_id": UUID,
                "session_id": str,
                "user_id": str | None,
                "chat_type": str,
                "is_active": bool,
                "turn_count": int,
                "last_compaction_at": int,
                "created_at": datetime,
                "updated_at": datetime,
                "expires_at": datetime | None
            }
        """

        def _get():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM conversations WHERE session_id = %s
                        """,
                        (session_id,),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def add_turn(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> UUID:
        """
        대화에 새 턴을 추가합니다.

        Args:
            conversation_id: 대화 ID
            role: 역할 ("user" | "assistant" | "system")
            content: 메시지 내용
            metadata: 메타데이터 (선택사항)

        Returns:
            생성된 turn_id (UUID)

        Raises:
            ValueError: 잘못된 role
            psycopg2.ForeignKeyViolation: 존재하지 않는 conversation_id
        """
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid role: {role}")

        def _add():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    # 현재 turn_count 조회 및 증가
                    cur.execute(
                        """
                        UPDATE conversations
                        SET turn_count = turn_count + 1
                        WHERE conversation_id = %s
                        RETURNING turn_count
                        """,
                        (conversation_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError(f"Conversation not found: {conversation_id}")
                    turn_number = row[0]

                    # 턴 삽입
                    cur.execute(
                        """
                        INSERT INTO conversation_turns
                        (conversation_id, turn_number, role, content, metadata)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING turn_id
                        """,
                        (
                            conversation_id,
                            turn_number,
                            role,
                            content,
                            psycopg2.extras.Json(metadata or {}),
                        ),
                    )
                    turn_id = cur.fetchone()[0]
                conn.commit()
                logger.info(
                    f"[ConversationDB] 턴 추가: conv_id={conversation_id}, "
                    f"turn={turn_number}, role={role}"
                )
                return turn_id
            except Exception as e:
                conn.rollback()
                logger.error(f"[ConversationDB] 턴 추가 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_add)

    async def get_conversation_history(
        self, conversation_id: UUID, limit: Optional[int] = None, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        대화 이력을 조회합니다.

        Args:
            conversation_id: 대화 ID
            limit: 최대 턴 수 (None = 전체)
            offset: 건너뛸 턴 수 (최신 턴부터)

        Returns:
            턴 목록 (최신순)
            [
                {
                    "turn_id": UUID,
                    "turn_number": int,
                    "role": str,
                    "content": str,
                    "metadata": dict,
                    "created_at": datetime
                },
                ...
            ]
        """

        def _get():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    query = """
                        SELECT turn_id, turn_number, role, content, metadata, created_at
                        FROM conversation_turns
                        WHERE conversation_id = %s
                        ORDER BY turn_number DESC
                    """
                    params = [conversation_id]

                    if limit is not None:
                        query += " LIMIT %s"
                        params.append(limit)

                    if offset > 0:
                        query += " OFFSET %s"
                        params.append(offset)

                    cur.execute(query, params)
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def save_summary(
        self,
        conversation_id: UUID,
        summary_data: Dict[str, Any],
        compacted_turn_count: int,
    ) -> UUID:
        """
        대화 요약을 저장합니다 (Compaction).

        Args:
            conversation_id: 대화 ID
            summary_data: 요약 데이터
                {
                    "purchase_item": str,
                    "purchase_date": str,
                    "purchase_amount": str,
                    "purchase_place": str,
                    "dispute_type": str,
                    "dispute_details": str,
                    "desired_resolution": str,
                    "key_facts": dict
                }
            compacted_turn_count: Compaction된 턴 수

        Returns:
            생성된 summary_id (UUID)

        Note:
            conversation_id당 하나의 요약만 존재 (UPSERT)
        """

        def _save():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    # UPSERT
                    cur.execute(
                        """
                        INSERT INTO conversation_summaries
                        (conversation_id, purchase_item, purchase_date, purchase_amount,
                         purchase_place, dispute_type, dispute_details, desired_resolution,
                         key_facts, compacted_turn_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (conversation_id) DO UPDATE SET
                            purchase_item = EXCLUDED.purchase_item,
                            purchase_date = EXCLUDED.purchase_date,
                            purchase_amount = EXCLUDED.purchase_amount,
                            purchase_place = EXCLUDED.purchase_place,
                            dispute_type = EXCLUDED.dispute_type,
                            dispute_details = EXCLUDED.dispute_details,
                            desired_resolution = EXCLUDED.desired_resolution,
                            key_facts = EXCLUDED.key_facts,
                            compacted_turn_count = EXCLUDED.compacted_turn_count,
                            compacted_at = NOW()
                        RETURNING summary_id
                        """,
                        (
                            conversation_id,
                            summary_data.get("purchase_item"),
                            summary_data.get("purchase_date"),
                            summary_data.get("purchase_amount"),
                            summary_data.get("purchase_place"),
                            summary_data.get("dispute_type"),
                            summary_data.get("dispute_details"),
                            summary_data.get("desired_resolution"),
                            psycopg2.extras.Json(summary_data.get("key_facts", {})),
                            compacted_turn_count,
                        ),
                    )
                    summary_id = cur.fetchone()[0]

                    # conversations 테이블 갱신
                    cur.execute(
                        """
                        UPDATE conversations
                        SET last_compaction_at = %s
                        WHERE conversation_id = %s
                        """,
                        (compacted_turn_count, conversation_id),
                    )

                conn.commit()
                logger.info(
                    f"[ConversationDB] 요약 저장: conv_id={conversation_id}, "
                    f"compacted_turns={compacted_turn_count}"
                )
                return summary_id
            except Exception as e:
                conn.rollback()
                logger.error(f"[ConversationDB] 요약 저장 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_save)

    async def get_summary(self, conversation_id: UUID) -> Optional[Dict[str, Any]]:
        """
        대화 요약을 조회합니다.

        Args:
            conversation_id: 대화 ID

        Returns:
            요약 딕셔너리 (없으면 None)
        """

        def _get():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM conversation_summaries
                        WHERE conversation_id = %s
                        """,
                        (conversation_id,),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def cleanup_expired_sessions(self) -> int:
        """
        만료된 게스트 세션을 정리합니다.

        Returns:
            삭제된 세션 수

        Note:
            CASCADE로 turns, summaries도 자동 삭제됨
        """

        def _cleanup():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM conversations
                        WHERE expires_at IS NOT NULL
                          AND expires_at < NOW()
                        """,
                    )
                    deleted_count = cur.rowcount
                conn.commit()
                if deleted_count > 0:
                    logger.info(
                        f"[ConversationDB] 만료 세션 정리: {deleted_count}개 삭제"
                    )
                return deleted_count
            except Exception as e:
                conn.rollback()
                logger.error(f"[ConversationDB] 만료 세션 정리 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_cleanup)

    async def deactivate_conversation(self, conversation_id: UUID) -> None:
        """
        대화를 비활성화합니다.

        Args:
            conversation_id: 대화 ID
        """

        def _deactivate():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE conversations
                        SET is_active = false
                        WHERE conversation_id = %s
                        """,
                        (conversation_id,),
                    )
                conn.commit()
                logger.info(
                    f"[ConversationDB] 대화 비활성화: conv_id={conversation_id}"
                )
            except Exception as e:
                conn.rollback()
                logger.error(f"[ConversationDB] 대화 비활성화 실패: {e}")
                raise
            finally:
                conn.close()

        await asyncio.to_thread(_deactivate)

    async def claim_sessions_for_user(
        self,
        session_ids: List[str],
        user_id: str,
    ) -> List[str]:
        """
        게스트 세션(user_id=NULL)의 소유권을 특정 사용자에게 이전합니다.

        Args:
            session_ids: 이전할 세션 ID 목록
            user_id: 새 소유자 ID

        Returns:
            실제로 이전된 세션 ID 목록
        """

        def _claim():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE conversations
                        SET user_id = %s,
                            expires_at = NULL,
                            updated_at = NOW()
                        WHERE session_id = ANY(%s)
                          AND user_id IS NULL
                        RETURNING session_id
                        """,
                        (user_id, session_ids),
                    )
                    claimed = [row[0] for row in cur.fetchall()]
                conn.commit()
                if claimed:
                    logger.info(
                        f"[ConversationDB] 세션 소유권 이전: user_id={user_id}, "
                        f"claimed={len(claimed)}/{len(session_ids)}"
                    )
                return claimed
            except Exception as e:
                conn.rollback()
                logger.error(f"[ConversationDB] 세션 소유권 이전 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_claim)

    async def get_user_conversations(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        사용자의 대화 목록을 조회합니다.

        Args:
            user_id: 사용자 ID
            limit: 최대 개수
            offset: 건너뛸 개수
            include_inactive: 비활성 대화 포함 여부

        Returns:
            대화 목록 (최신순)
        """

        def _get():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    query = """
                        SELECT * FROM conversations
                        WHERE user_id = %s
                    """
                    params = [user_id]

                    if not include_inactive:
                        query += " AND is_active = true"

                    query += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                    params.extend([limit, offset])

                    cur.execute(query, params)
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
            finally:
                conn.close()

        return await asyncio.to_thread(_get)
