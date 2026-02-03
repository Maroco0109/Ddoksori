"""
똑소리 프로젝트 - 사용자 데이터베이스 접근 계층

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
PostgreSQL users 테이블 접근을 담당합니다.
- 사용자 생성/조회/갱신
- OAuth 제공자별 사용자 조회
- 마지막 로그인 시각 갱신

[사용 예시]
    from app.auth.user_db import UserDB
    from app.common.config import get_config

    config = get_config()
    user_db = UserDB(config.database)

    # 사용자 생성 또는 갱신
    user = await user_db.upsert_user(
        provider="google",
        provider_user_id="123456",
        email="user@example.com",
        name="홍길동",
        avatar_url="https://example.com/avatar.jpg"
    )

    # 사용자 조회
    user = await user_db.get_user_by_id("google:123456")
"""

import asyncio
import logging
from typing import Optional

import psycopg2
import psycopg2.extras

from app.auth.models import User
from app.common.config import DatabaseConfig, get_config

logger = logging.getLogger(__name__)


class UserDB:
    """
    사용자 데이터베이스 접근 계층.

    PostgreSQL users 테이블을 사용하여 사용자 정보를 저장하고 조회합니다.
    각 메서드 호출마다 새 연결을 생성하고 종료합니다 (동시성 안전).
    """

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        """
        UserDB를 초기화합니다.

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
            logger.error(f"[UserDB] DB 연결 실패: {e}")
            raise

    @staticmethod
    def _make_user_id(provider: str, provider_user_id: str) -> str:
        """
        user_id를 생성합니다.

        Args:
            provider: OAuth 제공자 (google, naver)
            provider_user_id: 제공자에서의 사용자 ID

        Returns:
            "{provider}:{provider_user_id}" 형식의 user_id
        """
        return f"{provider}:{provider_user_id}"

    async def upsert_user(
        self,
        provider: str,
        provider_user_id: str,
        email: str,
        name: str,
        avatar_url: Optional[str] = None,
    ) -> User:
        """
        사용자를 생성하거나 갱신합니다 (UPSERT).

        기존 사용자가 있으면 정보를 갱신하고, 없으면 새로 생성합니다.

        Args:
            provider: OAuth 제공자 (google, naver)
            provider_user_id: 제공자에서의 사용자 ID
            email: 이메일 주소
            name: 사용자 이름
            avatar_url: 프로필 이미지 URL (선택사항)

        Returns:
            User 모델 인스턴스

        Raises:
            ValueError: 잘못된 provider
            psycopg2.Error: DB 오류
        """
        if provider not in ("google", "naver"):
            raise ValueError(f"Invalid provider: {provider}")

        user_id = self._make_user_id(provider, provider_user_id)

        def _upsert():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO users (user_id, email, name, avatar_url, provider, provider_user_id, last_login_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (provider, provider_user_id) DO UPDATE SET
                            email = EXCLUDED.email,
                            name = EXCLUDED.name,
                            avatar_url = EXCLUDED.avatar_url,
                            last_login_at = NOW()
                        RETURNING *
                        """,
                        (user_id, email, name, avatar_url, provider, provider_user_id),
                    )
                    row = cur.fetchone()
                conn.commit()
                logger.info(f"[UserDB] 사용자 UPSERT: user_id={user_id}, email={email}")
                return User(**dict(row))
            except Exception as e:
                conn.rollback()
                logger.error(f"[UserDB] 사용자 UPSERT 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_upsert)

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        user_id로 사용자를 조회합니다.

        Args:
            user_id: 사용자 ID ("{provider}:{provider_user_id}" 형식)

        Returns:
            User 모델 인스턴스 (없으면 None)
        """

        def _get():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM users WHERE user_id = %s
                        """,
                        (user_id,),
                    )
                    row = cur.fetchone()
                    return User(**dict(row)) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        이메일로 사용자를 조회합니다.

        Args:
            email: 이메일 주소

        Returns:
            User 모델 인스턴스 (없으면 None)
        """

        def _get():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM users WHERE email = %s
                        """,
                        (email,),
                    )
                    row = cur.fetchone()
                    return User(**dict(row)) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def get_user_by_provider(
        self, provider: str, provider_user_id: str
    ) -> Optional[User]:
        """
        OAuth 제공자와 제공자 사용자 ID로 사용자를 조회합니다.

        Args:
            provider: OAuth 제공자 (google, naver)
            provider_user_id: 제공자에서의 사용자 ID

        Returns:
            User 모델 인스턴스 (없으면 None)
        """

        def _get():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM users WHERE provider = %s AND provider_user_id = %s
                        """,
                        (provider, provider_user_id),
                    )
                    row = cur.fetchone()
                    return User(**dict(row)) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def update_last_login(self, user_id: str) -> None:
        """
        마지막 로그인 시각을 갱신합니다.

        Args:
            user_id: 사용자 ID
        """

        def _update():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE users
                        SET last_login_at = NOW()
                        WHERE user_id = %s
                        """,
                        (user_id,),
                    )
                conn.commit()
                logger.info(f"[UserDB] 마지막 로그인 갱신: user_id={user_id}")
            except Exception as e:
                conn.rollback()
                logger.error(f"[UserDB] 마지막 로그인 갱신 실패: {e}")
                raise
            finally:
                conn.close()

        await asyncio.to_thread(_update)

    async def delete_user(self, user_id: str) -> None:
        """
        사용자와 관련 데이터를 삭제합니다 (트랜잭션).

        Args:
            user_id: 사용자 ID

        Raises:
            psycopg2.Error: DB 오류
        """

        def _delete():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    # 1. OAuth 세션 삭제
                    cur.execute(
                        "DELETE FROM oauth_sessions WHERE user_id = %s", (user_id,)
                    )
                    # 2. 대화 요약 삭제 (conversation_summaries → conversations FK)
                    cur.execute(
                        """
                        DELETE FROM conversation_summaries
                        WHERE conversation_id IN (
                            SELECT conversation_id FROM conversations WHERE user_id = %s
                        )
                    """,
                        (user_id,),
                    )
                    # 3. 대화 턴 삭제
                    cur.execute(
                        """
                        DELETE FROM conversation_turns
                        WHERE conversation_id IN (
                            SELECT conversation_id FROM conversations WHERE user_id = %s
                        )
                    """,
                        (user_id,),
                    )
                    # 4. 대화 삭제
                    cur.execute(
                        "DELETE FROM conversations WHERE user_id = %s", (user_id,)
                    )
                    # 5. 사용자 삭제
                    cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
                conn.commit()
                logger.info(f"[UserDB] 사용자 삭제 완료: user_id={user_id}")
            except Exception as e:
                conn.rollback()
                logger.error(f"[UserDB] 사용자 삭제 실패: {e}")
                raise
            finally:
                conn.close()

        await asyncio.to_thread(_delete)
