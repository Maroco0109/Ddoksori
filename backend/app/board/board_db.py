"""
똑소리 프로젝트 - 게시판 데이터베이스 접근 계층

게시글, 댓글 관련 DB 작업을 담당합니다.
"""

import asyncio
import psycopg2
import psycopg2.extras
import math
from typing import Dict, List, Optional, Any

from app.common.config import DatabaseConfig, get_config
import logging

logger = logging.getLogger(__name__)


class BoardDB:
    """게시판 데이터베이스 접근 계층."""

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        try:
            conn = psycopg2.connect(**self.db_config.get_connection_dict())
            return conn
        except psycopg2.Error as e:
            logger.error(f"[BoardDB] DB 연결 실패: {e}")
            raise

    async def get_user_posts(
        self, user_id: str, page: int = 1, limit: int = 10
    ) -> Dict[str, Any]:
        """사용자의 게시글 목록을 조회합니다."""
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    offset = (page - 1) * limit

                    # 게시글 목록
                    cur.execute(
                        """
                        SELECT
                            p.id,
                            p.category,
                            p.sub_category AS "subCategory",
                            p.title,
                            TO_CHAR(p.created_at, 'YYYY.MM.DD') AS date,
                            p.views,
                            p.likes,
                            (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.is_deleted = false) AS comments
                        FROM posts p
                        WHERE p.user_id = %s AND p.is_deleted = false
                        ORDER BY p.created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, limit, offset)
                    )
                    posts = [dict(row) for row in cur.fetchall()]

                    # 총 개수
                    cur.execute(
                        "SELECT COUNT(*) FROM posts WHERE user_id = %s AND is_deleted = false",
                        (user_id,)
                    )
                    total = cur.fetchone()["count"]

                    return {
                        "posts": posts,
                        "total": total,
                        "page": page,
                        "totalPages": math.ceil(total / limit) if total > 0 else 0
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_user_commented_posts(
        self, user_id: str, page: int = 1, limit: int = 10
    ) -> Dict[str, Any]:
        """사용자가 댓글을 단 게시글 목록을 조회합니다."""
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    offset = (page - 1) * limit

                    cur.execute(
                        """
                        SELECT DISTINCT ON (p.id)
                            p.id,
                            p.category,
                            p.title,
                            TO_CHAR(p.created_at, 'YYYY.MM.DD') AS date,
                            p.views,
                            p.likes,
                            (SELECT COUNT(*) FROM comments c2 WHERE c2.post_id = p.id AND c2.is_deleted = false) AS comments,
                            TO_CHAR(c.created_at, 'YYYY.MM.DD') AS "myCommentDate",
                            c.content AS "myCommentContent"
                        FROM posts p
                        INNER JOIN comments c ON p.id = c.post_id AND c.user_id = %s AND c.is_deleted = false
                        WHERE p.is_deleted = false
                        ORDER BY p.id, c.created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, limit, offset)
                    )
                    posts = [dict(row) for row in cur.fetchall()]

                    cur.execute(
                        """
                        SELECT COUNT(DISTINCT p.id)
                        FROM posts p
                        INNER JOIN comments c ON p.id = c.post_id
                        WHERE c.user_id = %s AND p.is_deleted = false AND c.is_deleted = false
                        """,
                        (user_id,)
                    )
                    total = cur.fetchone()["count"]

                    return {
                        "posts": posts,
                        "total": total,
                        "page": page,
                        "totalPages": math.ceil(total / limit) if total > 0 else 0
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)
