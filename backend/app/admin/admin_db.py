"""관리자 데이터베이스 접근 계층"""

import asyncio
import logging
import math
from datetime import date
from typing import Any, Dict, Optional

import psycopg2
import psycopg2.extras

from app.common.config import DatabaseConfig, get_config

logger = logging.getLogger(__name__)


class AdminDB:
    """관리자 DB 접근 계층 (psycopg2 + asyncio.to_thread 패턴)"""

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        try:
            conn = psycopg2.connect(**self.db_config.get_connection_dict())
            return conn
        except psycopg2.Error as e:
            logger.error(f"[AdminDB] DB 연결 실패: {e}")
            raise

    # ============================================================
    # Admin Auth
    # ============================================================

    async def get_admin_by_username(self, username: str) -> Optional[Dict]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM admins WHERE username = %s", (username,))
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def update_admin_last_login(self, admin_id: str) -> None:
        def _update():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE admins SET last_login_at = NOW() WHERE id = %s",
                        (admin_id,),
                    )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_update)

    # ============================================================
    # Dashboard Stats
    # ============================================================

    async def get_stats(self) -> Dict[str, int]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    today = date.today()

                    cur.execute("SELECT COUNT(*) as count FROM users")
                    total_users = cur.fetchone()["count"]

                    cur.execute(
                        "SELECT COUNT(*) as count FROM posts WHERE is_deleted = false"
                    )
                    total_posts = cur.fetchone()["count"]

                    cur.execute(
                        "SELECT COUNT(*) as count FROM comments WHERE is_deleted = false"
                    )
                    total_comments = cur.fetchone()["count"]

                    cur.execute(
                        "SELECT COUNT(*) as count FROM reports WHERE status = 'pending'"
                    )
                    pending_reports = cur.fetchone()["count"]

                    cur.execute(
                        "SELECT COUNT(*) as count FROM users WHERE status = 'suspended'"
                    )
                    suspended_users = cur.fetchone()["count"]

                    cur.execute(
                        "SELECT COUNT(*) as count FROM users WHERE created_at::date = %s",
                        (today,),
                    )
                    today_new_users = cur.fetchone()["count"]

                    cur.execute(
                        "SELECT COUNT(*) as count FROM posts WHERE created_at::date = %s AND is_deleted = false",
                        (today,),
                    )
                    today_new_posts = cur.fetchone()["count"]

                    cur.execute(
                        "SELECT COUNT(*) as count FROM comments WHERE created_at::date = %s AND is_deleted = false",
                        (today,),
                    )
                    today_new_comments = cur.fetchone()["count"]

                    return {
                        "totalUsers": total_users,
                        "totalPosts": total_posts,
                        "totalComments": total_comments,
                        "pendingReports": pending_reports,
                        "suspendedUsers": suspended_users,
                        "todayNewUsers": today_new_users,
                        "todayNewPosts": today_new_posts,
                        "todayNewComments": today_new_comments,
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    # ============================================================
    # Posts Management
    # ============================================================

    async def get_posts(
        self,
        page: int = 1,
        limit: int = 20,
        search_type: Optional[str] = None,
        search_keyword: Optional[str] = None,
        category: Optional[str] = None,
        is_public: Optional[bool] = None,
    ) -> Dict[str, Any]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    conditions = ["p.is_deleted = false"]
                    params: list = []

                    if category:
                        conditions.append("p.category = %s")
                        params.append(category)
                    if is_public is not None:
                        conditions.append("p.is_public = %s")
                        params.append(is_public)
                    if search_keyword and search_type:
                        if search_type == "title":
                            conditions.append("p.title ILIKE %s")
                            params.append(f"%{search_keyword}%")
                        elif search_type == "author":
                            conditions.append("u.name ILIKE %s")
                            params.append(f"%{search_keyword}%")
                        elif search_type == "title_author":
                            conditions.append("(p.title ILIKE %s OR u.name ILIKE %s)")
                            params.extend(
                                [f"%{search_keyword}%", f"%{search_keyword}%"]
                            )
                        elif search_type == "keyword":
                            conditions.append(
                                "(p.title ILIKE %s OR p.content ILIKE %s)"
                            )
                            params.extend(
                                [f"%{search_keyword}%", f"%{search_keyword}%"]
                            )

                    where = " AND ".join(conditions)
                    offset = (page - 1) * limit

                    cur.execute(
                        f"""
                        SELECT
                            p.id, p.category, p.title, p.content,
                            u.name AS author, p.user_id AS "authorId",
                            p.created_at AS "createdAt", p.updated_at AS "updatedAt",
                            p.views, p.likes, p.is_public AS "isPublic", p.is_deleted AS "isDeleted",
                            (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.is_deleted = false) AS "commentsCount"
                        FROM posts p
                        LEFT JOIN users u ON p.user_id = u.user_id
                        WHERE {where}
                        ORDER BY p.is_pinned DESC, p.created_at DESC
                        LIMIT %s OFFSET %s
                    """,
                        params + [limit, offset],
                    )
                    data = [dict(row) for row in cur.fetchall()]

                    cur.execute(
                        f"""
                        SELECT COUNT(*) FROM posts p
                        LEFT JOIN users u ON p.user_id = u.user_id
                        WHERE {where}
                    """,
                        params,
                    )
                    total = cur.fetchone()["count"]

                    return {
                        "data": data,
                        "pagination": {
                            "currentPage": page,
                            "totalPages": math.ceil(total / limit) if total > 0 else 0,
                            "totalItems": total,
                            "itemsPerPage": limit,
                        },
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_post_by_id(self, post_id: int) -> Optional[Dict]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT p.*, u.name AS author,
                            (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.is_deleted = false) AS "commentsCount"
                        FROM posts p
                        LEFT JOIN users u ON p.user_id = u.user_id
                        WHERE p.id = %s
                    """,
                        (post_id,),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def update_post_visibility(self, post_id: int, is_public: bool) -> bool:
        def _update():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE posts SET is_public = %s WHERE id = %s",
                        (is_public, post_id),
                    )
                    affected = cur.rowcount
                conn.commit()
                return affected > 0
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_update)

    async def soft_delete_post(self, post_id: int) -> bool:
        def _delete():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE posts SET is_deleted = true WHERE id = %s", (post_id,)
                    )
                    affected = cur.rowcount
                conn.commit()
                return affected > 0
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_delete)

    async def create_notice(
        self, admin_user_id: str, title: str, content: str, is_pinned: bool = False
    ) -> int:
        """공지사항을 작성합니다. admin_user_id는 관리자의 users 테이블 user_id입니다."""

        def _create():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO posts (user_id, category, title, content, is_notice, is_pinned)
                        VALUES (%s, '공지사항', %s, %s, true, %s)
                        RETURNING id
                    """,
                        (admin_user_id, title, content, is_pinned),
                    )
                    post_id = cur.fetchone()[0]
                conn.commit()
                return post_id
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_create)

    # ============================================================
    # Comments Management
    # ============================================================

    async def get_comments(
        self, page: int = 1, limit: int = 20, post_id: Optional[int] = None
    ) -> Dict[str, Any]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    conditions = ["c.is_deleted = false"]
                    params: list = []
                    if post_id is not None:
                        conditions.append("c.post_id = %s")
                        params.append(post_id)

                    where = " AND ".join(conditions)
                    offset = (page - 1) * limit

                    cur.execute(
                        f"""
                        SELECT
                            c.id, c.post_id AS "postId", c.content,
                            u.name AS author, c.user_id AS "authorId",
                            c.created_at AS "createdAt", c.updated_at AS "updatedAt",
                            c.is_public AS "isPublic", c.is_deleted AS "isDeleted"
                        FROM comments c
                        LEFT JOIN users u ON c.user_id = u.user_id
                        WHERE {where}
                        ORDER BY c.created_at DESC
                        LIMIT %s OFFSET %s
                    """,
                        params + [limit, offset],
                    )
                    data = [dict(row) for row in cur.fetchall()]

                    cur.execute(
                        f"SELECT COUNT(*) FROM comments c WHERE {where}", params
                    )
                    total = cur.fetchone()["count"]

                    return {
                        "data": data,
                        "pagination": {
                            "currentPage": page,
                            "totalPages": math.ceil(total / limit) if total > 0 else 0,
                            "totalItems": total,
                            "itemsPerPage": limit,
                        },
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def update_comment_visibility(self, comment_id: int, is_public: bool) -> bool:
        def _update():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE comments SET is_public = %s WHERE id = %s",
                        (is_public, comment_id),
                    )
                    affected = cur.rowcount
                conn.commit()
                return affected > 0
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_update)

    async def soft_delete_comment(self, comment_id: int) -> bool:
        def _delete():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE comments SET is_deleted = true WHERE id = %s",
                        (comment_id,),
                    )
                    affected = cur.rowcount
                conn.commit()
                return affected > 0
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_delete)

    # ============================================================
    # Users Management
    # ============================================================

    async def get_users(
        self,
        page: int = 1,
        limit: int = 20,
        search_keyword: Optional[str] = None,
        status: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    conditions: list = []
                    params: list = []

                    if search_keyword:
                        conditions.append("(u.name ILIKE %s OR u.email ILIKE %s)")
                        params.extend([f"%{search_keyword}%", f"%{search_keyword}%"])
                    if status:
                        conditions.append("u.status = %s")
                        params.append(status)
                    if provider:
                        conditions.append("u.provider = %s")
                        params.append(provider)

                    where = " AND ".join(conditions) if conditions else "TRUE"
                    offset = (page - 1) * limit

                    cur.execute(
                        f"""
                        SELECT
                            u.user_id AS id, u.name, u.email, u.provider,
                            u.created_at AS "createdAt", u.last_login_at AS "lastLoginAt",
                            COALESCE(u.status, 'active') AS status,
                            (SELECT COUNT(*) FROM posts p WHERE p.user_id = u.user_id AND p.is_deleted = false) AS "postCount",
                            (SELECT COUNT(*) FROM comments c WHERE c.user_id = u.user_id AND c.is_deleted = false) AS "commentCount",
                            (SELECT COUNT(*) FROM reports r WHERE r.reporter_id = u.user_id) AS "reportCount"
                        FROM users u
                        WHERE {where}
                        ORDER BY u.created_at DESC
                        LIMIT %s OFFSET %s
                    """,
                        params + [limit, offset],
                    )
                    data = [dict(row) for row in cur.fetchall()]

                    cur.execute(f"SELECT COUNT(*) FROM users u WHERE {where}", params)
                    total = cur.fetchone()["count"]

                    return {
                        "data": data,
                        "pagination": {
                            "currentPage": page,
                            "totalPages": math.ceil(total / limit) if total > 0 else 0,
                            "totalItems": total,
                            "itemsPerPage": limit,
                        },
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            u.user_id AS id, u.name, u.email, u.provider,
                            u.created_at AS "createdAt", u.last_login_at AS "lastLoginAt",
                            COALESCE(u.status, 'active') AS status,
                            (SELECT COUNT(*) FROM posts p WHERE p.user_id = u.user_id AND p.is_deleted = false) AS "postCount",
                            (SELECT COUNT(*) FROM comments c WHERE c.user_id = u.user_id AND c.is_deleted = false) AS "commentCount",
                            (SELECT COUNT(*) FROM reports r WHERE r.reporter_id = u.user_id) AS "reportCount"
                        FROM users u
                        WHERE u.user_id = %s
                    """,
                        (user_id,),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def update_user_status(self, user_id: str, new_status: str) -> bool:
        def _update():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET status = %s WHERE user_id = %s",
                        (new_status, user_id),
                    )
                    affected = cur.rowcount
                conn.commit()
                return affected > 0
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_update)

    # ============================================================
    # Reports Management
    # ============================================================

    async def get_reports(
        self,
        page: int = 1,
        limit: int = 20,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    conditions: list = []
                    params: list = []
                    if report_type:
                        conditions.append("r.type = %s")
                        params.append(report_type)
                    if status:
                        conditions.append("r.status = %s")
                        params.append(status)

                    where = " AND ".join(conditions) if conditions else "TRUE"
                    offset = (page - 1) * limit

                    cur.execute(
                        f"""
                        SELECT
                            r.id, r.type, r.target_id AS "targetId",
                            CASE
                                WHEN r.type = 'post' THEN (SELECT title FROM posts WHERE id = r.target_id)
                                ELSE (SELECT content FROM comments WHERE id = r.target_id)
                            END AS "targetTitle",
                            CASE
                                WHEN r.type = 'post' THEN (SELECT content FROM posts WHERE id = r.target_id)
                                ELSE (SELECT content FROM comments WHERE id = r.target_id)
                            END AS "targetContent",
                            r.reporter_id AS "reporterId",
                            u.name AS "reporterName",
                            r.reason, r.status,
                            r.created_at AS "createdAt",
                            r.admin_note AS "adminNote"
                        FROM reports r
                        LEFT JOIN users u ON r.reporter_id = u.user_id
                        WHERE {where}
                        ORDER BY r.created_at DESC
                        LIMIT %s OFFSET %s
                    """,
                        params + [limit, offset],
                    )
                    data = [dict(row) for row in cur.fetchall()]

                    cur.execute(f"SELECT COUNT(*) FROM reports r WHERE {where}", params)
                    total = cur.fetchone()["count"]

                    return {
                        "data": data,
                        "pagination": {
                            "currentPage": page,
                            "totalPages": math.ceil(total / limit) if total > 0 else 0,
                            "totalItems": total,
                            "itemsPerPage": limit,
                        },
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_report_by_id(self, report_id: int) -> Optional[Dict]:
        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            r.id, r.type, r.target_id AS "targetId",
                            CASE
                                WHEN r.type = 'post' THEN (SELECT title FROM posts WHERE id = r.target_id)
                                ELSE (SELECT content FROM comments WHERE id = r.target_id)
                            END AS "targetTitle",
                            CASE
                                WHEN r.type = 'post' THEN (SELECT content FROM posts WHERE id = r.target_id)
                                ELSE (SELECT content FROM comments WHERE id = r.target_id)
                            END AS "targetContent",
                            r.reporter_id AS "reporterId",
                            u.name AS "reporterName",
                            r.reason, r.status,
                            r.created_at AS "createdAt",
                            r.admin_note AS "adminNote"
                        FROM reports r
                        LEFT JOIN users u ON r.reporter_id = u.user_id
                        WHERE r.id = %s
                    """,
                        (report_id,),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def update_report_status(
        self, report_id: int, new_status: str, admin_note: Optional[str] = None
    ) -> bool:
        def _update():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE reports SET status = %s, admin_note = %s WHERE id = %s",
                        (new_status, admin_note, report_id),
                    )
                    affected = cur.rowcount
                conn.commit()
                return affected > 0
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_update)

    # ============================================================
    # Audit Log
    # ============================================================

    async def log_action(
        self,
        admin_id: str,
        action_type: str,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> None:
        def _log():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO audit_logs (admin_id, action_type, target_type, target_id, reason)
                        VALUES (%s, %s, %s, %s, %s)
                    """,
                        (admin_id, action_type, target_type, target_id, reason),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        await asyncio.to_thread(_log)
