"""
똑소리 프로젝트 - 게시판 데이터베이스 접근 계층

게시글, 댓글, 좋아요, 신고 관련 DB 작업을 담당합니다.
"""

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2
import psycopg2.extras

from app.common.config import DatabaseConfig, get_config

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

    # ============================================================
    # Category
    # ============================================================

    async def get_categories(self) -> List[Dict[str, Any]]:
        """카테고리 목록을 조회합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, category_key, category_name, display_name, sort_order
                        FROM community_category
                        ORDER BY sort_order
                    """)
                    return [dict(row) for row in cur.fetchall()]
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_category_by_key(self, category_key: str) -> Optional[Dict[str, Any]]:
        """카테고리 키로 카테고리를 조회합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, category_key, category_name, display_name, sort_order
                        FROM community_category
                        WHERE category_key = %s
                    """, (category_key,))
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    # ============================================================
    # Post - CRUD
    # ============================================================

    async def create_post(
        self,
        user_id: str,
        category_id: UUID,
        title: str,
        content: str,
        sub_category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """게시글을 생성합니다."""

        # preview 생성 (최대 200자)
        preview = content[:200] if len(content) > 200 else content

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        INSERT INTO community_post
                            (user_id, category_id, sub_category, title, content, preview)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, created_at
                    """, (user_id, str(category_id), sub_category, title, content, preview))
                    row = cur.fetchone()
                    conn.commit()
                    return dict(row)
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 게시글 생성 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_post(self, post_id: UUID, current_user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """게시글 상세를 조회합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            p.id,
                            p.user_id AS author_id,
                            u.name AS author_nickname,
                            CASE WHEN u.user_id IS NULL THEN true ELSE false END AS is_author_deleted,
                            c.category_key,
                            c.display_name AS category,
                            p.sub_category,
                            p.title,
                            p.content,
                            p.preview,
                            p.view_count,
                            p.like_count,
                            p.comment_count,
                            p.status,
                            p.created_at,
                            p.edited_at,
                            CASE
                                WHEN %s IS NOT NULL AND EXISTS (
                                    SELECT 1 FROM community_post_like
                                    WHERE post_id = p.id AND user_id = %s
                                ) THEN true
                                ELSE false
                            END AS is_liked
                        FROM community_post p
                        JOIN community_category c ON p.category_id = c.id
                        LEFT JOIN users u ON p.user_id = u.user_id
                        WHERE p.id = %s AND p.status = 'normal'
                    """, (current_user_id, current_user_id, str(post_id)))
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_posts(
        self,
        page: int = 1,
        limit: int = 10,
        category_key: Optional[str] = None,
        search_query: Optional[str] = None,
        search_type: str = "title",
        current_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """게시글 목록을 조회합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    offset = (page - 1) * limit
                    where_clauses = ["p.status = 'normal'"]
                    params: List[Any] = []

                    # 카테고리 필터
                    if category_key and category_key != "all":
                        where_clauses.append("c.category_key = %s")
                        params.append(category_key)

                    # 검색 필터
                    if search_query:
                        if search_type == "title":
                            where_clauses.append("p.title ILIKE %s")
                            params.append(f"%{search_query}%")
                        elif search_type == "author":
                            where_clauses.append("u.name ILIKE %s")
                            params.append(f"%{search_query}%")
                        elif search_type == "content":
                            where_clauses.append("p.content ILIKE %s")
                            params.append(f"%{search_query}%")
                        elif search_type == "title_content":
                            where_clauses.append("(p.title ILIKE %s OR p.content ILIKE %s)")
                            params.append(f"%{search_query}%")
                            params.append(f"%{search_query}%")

                    where_sql = " AND ".join(where_clauses)

                    # 게시글 목록 조회
                    cur.execute(f"""
                        SELECT
                            p.id,
                            p.user_id AS author_id,
                            COALESCE(u.name, '탈퇴한 사용자') AS author_nickname,
                            CASE WHEN u.user_id IS NULL THEN true ELSE false END AS is_author_deleted,
                            c.category_key,
                            c.display_name AS category,
                            p.sub_category,
                            p.title,
                            p.preview,
                            p.view_count,
                            p.like_count,
                            p.comment_count,
                            p.created_at,
                            p.edited_at
                        FROM community_post p
                        JOIN community_category c ON p.category_id = c.id
                        LEFT JOIN users u ON p.user_id = u.user_id
                        WHERE {where_sql}
                        ORDER BY p.created_at DESC
                        LIMIT %s OFFSET %s
                    """, params + [limit, offset])
                    posts = [dict(row) for row in cur.fetchall()]

                    # 총 개수 조회
                    cur.execute(f"""
                        SELECT COUNT(*)
                        FROM community_post p
                        JOIN community_category c ON p.category_id = c.id
                        LEFT JOIN users u ON p.user_id = u.user_id
                        WHERE {where_sql}
                    """, params)
                    total = cur.fetchone()["count"]

                    total_pages = math.ceil(total / limit) if total > 0 else 0

                    return {
                        "posts": posts,
                        "total": total,
                        "page": page,
                        "total_pages": total_pages,
                        "has_next": page < total_pages,
                        "has_prev": page > 1,
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def update_post(
        self,
        post_id: UUID,
        user_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        category_id: Optional[UUID] = None,
        sub_category: Optional[str] = None,
    ) -> bool:
        """게시글을 수정합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    # 작성자 확인
                    cur.execute("""
                        SELECT user_id FROM community_post
                        WHERE id = %s AND status = 'normal'
                    """, (str(post_id),))
                    row = cur.fetchone()
                    if not row or row[0] != user_id:
                        return False

                    # 동적 업데이트 쿼리 생성
                    updates = ["edited_at = NOW()"]
                    params: List[Any] = []

                    if title:
                        updates.append("title = %s")
                        params.append(title)
                    if content:
                        updates.append("content = %s")
                        params.append(content)
                        updates.append("preview = %s")
                        params.append(content[:200] if len(content) > 200 else content)
                    if category_id:
                        updates.append("category_id = %s")
                        params.append(str(category_id))
                    if sub_category is not None:
                        updates.append("sub_category = %s")
                        params.append(sub_category if sub_category else None)

                    params.append(str(post_id))

                    cur.execute(f"""
                        UPDATE community_post
                        SET {', '.join(updates)}
                        WHERE id = %s
                    """, params)
                    conn.commit()
                    return True
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 게시글 수정 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def delete_post(self, post_id: UUID, user_id: str) -> bool:
        """게시글을 삭제합니다 (소프트 삭제)."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    # 작성자 확인 후 삭제
                    cur.execute("""
                        UPDATE community_post
                        SET status = 'deleted', deleted_at = NOW()
                        WHERE id = %s AND user_id = %s AND status = 'normal'
                    """, (str(post_id), user_id))
                    affected = cur.rowcount
                    conn.commit()
                    return affected > 0
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 게시글 삭제 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def increment_view_count(self, post_id: UUID) -> None:
        """게시글 조회수를 증가시킵니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE community_post
                        SET view_count = view_count + 1
                        WHERE id = %s
                    """, (str(post_id),))
                    conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 조회수 증가 실패: {e}")
            finally:
                conn.close()

        await asyncio.to_thread(_query)

    # ============================================================
    # Comment - CRUD
    # ============================================================

    async def create_comment(
        self,
        post_id: UUID,
        user_id: str,
        content: str,
        parent_comment_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """댓글/대댓글을 생성합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # 대댓글인 경우, 부모 댓글이 1단 댓글인지 확인
                    if parent_comment_id:
                        cur.execute("""
                            SELECT parent_comment_id FROM community_comment
                            WHERE id = %s AND status = 'normal'
                        """, (str(parent_comment_id),))
                        parent = cur.fetchone()
                        if not parent:
                            raise ValueError("부모 댓글을 찾을 수 없습니다.")
                        if parent["parent_comment_id"] is not None:
                            raise ValueError("대댓글의 대댓글은 작성할 수 없습니다.")

                    cur.execute("""
                        INSERT INTO community_comment
                            (post_id, user_id, parent_comment_id, content)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, created_at
                    """, (str(post_id), user_id, str(parent_comment_id) if parent_comment_id else None, content))
                    row = cur.fetchone()
                    conn.commit()
                    return dict(row)
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 댓글 생성 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_comments(
        self,
        post_id: UUID,
        current_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """게시글의 댓글 목록을 조회합니다 (대댓글 포함)."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # 1단 댓글 조회
                    cur.execute("""
                        SELECT
                            c.id,
                            c.user_id AS author_id,
                            COALESCE(u.name, '탈퇴한 사용자') AS author_nickname,
                            CASE WHEN u.user_id IS NULL THEN true ELSE false END AS is_author_deleted,
                            c.content,
                            c.like_count,
                            c.created_at,
                            c.edited_at,
                            CASE
                                WHEN %s IS NOT NULL AND EXISTS (
                                    SELECT 1 FROM community_comment_like
                                    WHERE comment_id = c.id AND user_id = %s
                                ) THEN true
                                ELSE false
                            END AS is_liked
                        FROM community_comment c
                        LEFT JOIN users u ON c.user_id = u.user_id
                        WHERE c.post_id = %s AND c.parent_comment_id IS NULL AND c.status = 'normal'
                        ORDER BY c.created_at ASC
                    """, (current_user_id, current_user_id, str(post_id)))
                    comments = [dict(row) for row in cur.fetchall()]

                    # 각 댓글의 대댓글 조회
                    for comment in comments:
                        cur.execute("""
                            SELECT
                                r.id,
                                r.user_id AS author_id,
                                COALESCE(u.name, '탈퇴한 사용자') AS author_nickname,
                                CASE WHEN u.user_id IS NULL THEN true ELSE false END AS is_author_deleted,
                                r.content,
                                r.like_count,
                                r.created_at,
                                r.edited_at,
                                CASE
                                    WHEN %s IS NOT NULL AND EXISTS (
                                        SELECT 1 FROM community_comment_like
                                        WHERE comment_id = r.id AND user_id = %s
                                    ) THEN true
                                    ELSE false
                                END AS is_liked
                            FROM community_comment r
                            LEFT JOIN users u ON r.user_id = u.user_id
                            WHERE r.parent_comment_id = %s AND r.status = 'normal'
                            ORDER BY r.created_at ASC
                        """, (current_user_id, current_user_id, str(comment["id"])))
                        comment["replies"] = [dict(row) for row in cur.fetchall()]

                    return comments
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def update_comment(self, comment_id: UUID, user_id: str, content: str) -> bool:
        """댓글을 수정합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE community_comment
                        SET content = %s, edited_at = NOW()
                        WHERE id = %s AND user_id = %s AND status = 'normal'
                    """, (content, str(comment_id), user_id))
                    affected = cur.rowcount
                    conn.commit()
                    return affected > 0
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 댓글 수정 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def delete_comment(self, comment_id: UUID, user_id: str) -> bool:
        """댓글을 삭제합니다 (소프트 삭제)."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE community_comment
                        SET status = 'deleted', deleted_at = NOW()
                        WHERE id = %s AND user_id = %s AND status = 'normal'
                    """, (str(comment_id), user_id))
                    affected = cur.rowcount
                    conn.commit()
                    return affected > 0
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 댓글 삭제 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    # ============================================================
    # Like
    # ============================================================

    async def toggle_post_like(self, post_id: UUID, user_id: str) -> Dict[str, Any]:
        """게시글 좋아요를 토글합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # 이미 좋아요했는지 확인
                    cur.execute("""
                        SELECT id FROM community_post_like
                        WHERE post_id = %s AND user_id = %s
                    """, (str(post_id), user_id))
                    existing = cur.fetchone()

                    if existing:
                        # 좋아요 취소
                        cur.execute("""
                            DELETE FROM community_post_like
                            WHERE post_id = %s AND user_id = %s
                        """, (str(post_id), user_id))
                        liked = False
                    else:
                        # 좋아요 추가
                        cur.execute("""
                            INSERT INTO community_post_like (post_id, user_id)
                            VALUES (%s, %s)
                        """, (str(post_id), user_id))
                        liked = True

                    # 현재 좋아요 수 조회
                    cur.execute("""
                        SELECT like_count FROM community_post WHERE id = %s
                    """, (str(post_id),))
                    like_count = cur.fetchone()["like_count"]

                    conn.commit()
                    return {"liked": liked, "like_count": like_count}
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 게시글 좋아요 토글 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def toggle_comment_like(self, comment_id: UUID, user_id: str) -> Dict[str, Any]:
        """댓글 좋아요를 토글합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # 이미 좋아요했는지 확인
                    cur.execute("""
                        SELECT id FROM community_comment_like
                        WHERE comment_id = %s AND user_id = %s
                    """, (str(comment_id), user_id))
                    existing = cur.fetchone()

                    if existing:
                        # 좋아요 취소
                        cur.execute("""
                            DELETE FROM community_comment_like
                            WHERE comment_id = %s AND user_id = %s
                        """, (str(comment_id), user_id))
                        liked = False
                    else:
                        # 좋아요 추가
                        cur.execute("""
                            INSERT INTO community_comment_like (comment_id, user_id)
                            VALUES (%s, %s)
                        """, (str(comment_id), user_id))
                        liked = True

                    # 현재 좋아요 수 조회
                    cur.execute("""
                        SELECT like_count FROM community_comment WHERE id = %s
                    """, (str(comment_id),))
                    like_count = cur.fetchone()["like_count"]

                    conn.commit()
                    return {"liked": liked, "like_count": like_count}
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 댓글 좋아요 토글 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    # ============================================================
    # Report
    # ============================================================

    async def create_report(
        self,
        reporter_id: str,
        target_type: str,
        target_id: UUID,
        reason: str,
    ) -> Dict[str, Any]:
        """신고를 생성합니다."""

        def _query():
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        INSERT INTO community_report
                            (reporter_id, target_type, target_id, reason)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, created_at
                    """, (reporter_id, target_type, str(target_id), reason))
                    row = cur.fetchone()
                    conn.commit()
                    return dict(row)
            except Exception as e:
                conn.rollback()
                logger.error(f"[BoardDB] 신고 생성 실패: {e}")
                raise
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    # ============================================================
    # MyPage
    # ============================================================

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
                    cur.execute("""
                        SELECT
                            p.id,
                            c.category_key,
                            c.display_name AS category,
                            p.title,
                            TO_CHAR(p.created_at, 'YYYY.MM.DD') AS date,
                            p.view_count AS views,
                            p.like_count AS likes,
                            p.comment_count AS comments
                        FROM community_post p
                        JOIN community_category c ON p.category_id = c.id
                        WHERE p.user_id = %s AND p.status = 'normal'
                        ORDER BY p.created_at DESC
                        LIMIT %s OFFSET %s
                    """, (user_id, limit, offset))
                    posts = [dict(row) for row in cur.fetchall()]

                    # 총 개수
                    cur.execute("""
                        SELECT COUNT(*) FROM community_post
                        WHERE user_id = %s AND status = 'normal'
                    """, (user_id,))
                    total = cur.fetchone()["count"]

                    return {
                        "posts": posts,
                        "total": total,
                        "page": page,
                        "total_pages": math.ceil(total / limit) if total > 0 else 0,
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

                    cur.execute("""
                        SELECT DISTINCT ON (p.id)
                            p.id,
                            cat.category_key,
                            cat.display_name AS category,
                            p.title,
                            TO_CHAR(p.created_at, 'YYYY.MM.DD') AS date,
                            p.view_count AS views,
                            p.like_count AS likes,
                            p.comment_count AS comments,
                            TO_CHAR(c.created_at, 'YYYY.MM.DD') AS my_comment_date,
                            SUBSTRING(c.content, 1, 50) AS my_comment_preview
                        FROM community_post p
                        JOIN community_category cat ON p.category_id = cat.id
                        INNER JOIN community_comment c ON p.id = c.post_id
                            AND c.user_id = %s AND c.status = 'normal'
                        WHERE p.status = 'normal'
                        ORDER BY p.id, c.created_at DESC
                        LIMIT %s OFFSET %s
                    """, (user_id, limit, offset))
                    posts = [dict(row) for row in cur.fetchall()]

                    cur.execute("""
                        SELECT COUNT(DISTINCT p.id)
                        FROM community_post p
                        INNER JOIN community_comment c ON p.id = c.post_id
                        WHERE c.user_id = %s AND p.status = 'normal' AND c.status = 'normal'
                    """, (user_id,))
                    total = cur.fetchone()["count"]

                    return {
                        "posts": posts,
                        "total": total,
                        "page": page,
                        "total_pages": math.ceil(total / limit) if total > 0 else 0,
                    }
            finally:
                conn.close()

        return await asyncio.to_thread(_query)
