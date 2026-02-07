"""
똑소리 프로젝트 - 게시판 서비스 계층

게시글, 댓글, 좋아요, 신고 관련 비즈니스 로직을 담당합니다.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.board.board_db import BoardDB
from app.board.schemas import (
    CategoryResponse,
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    LikeResponse,
    MyCommentedPostItem,
    MyCommentedPostsResponse,
    MyPostItem,
    MyPostsResponse,
    PostCreate,
    PostDetail,
    PostListItem,
    PostListResponse,
    PostUpdate,
    ReplyResponse,
    ReportCreate,
    ReportResponse,
)

logger = logging.getLogger(__name__)


class BoardService:
    """게시판 서비스 계층."""

    def __init__(self):
        self.db = BoardDB()

    # ============================================================
    # Category
    # ============================================================

    async def get_categories(self) -> List[CategoryResponse]:
        """카테고리 목록을 조회합니다."""
        categories = await self.db.get_categories()
        return [CategoryResponse(**cat) for cat in categories]

    # ============================================================
    # Post
    # ============================================================

    async def create_post(
        self,
        user_id: str,
        data: PostCreate,
    ) -> PostDetail:
        """게시글을 생성합니다."""
        # 카테고리 조회
        category = await self.db.get_category_by_key(data.category.value)
        if not category:
            raise ValueError(f"카테고리를 찾을 수 없습니다: {data.category.value}")

        # 게시글 생성
        result = await self.db.create_post(
            user_id=user_id,
            category_id=UUID(str(category["id"])),
            title=data.title,
            content=data.content,
            sub_category=data.sub_category.value if data.sub_category else None,
        )

        # 생성된 게시글 조회
        post = await self.db.get_post(result["id"], user_id)
        return self._to_post_detail(post)

    async def get_post(
        self,
        post_id: UUID,
        current_user_id: Optional[str] = None,
        increment_view: bool = True,
    ) -> Optional[PostDetail]:
        """게시글 상세를 조회합니다."""
        # 조회수 증가
        if increment_view:
            await self.db.increment_view_count(post_id)

        post = await self.db.get_post(post_id, current_user_id)
        if not post:
            return None
        return self._to_post_detail(post)

    async def get_posts(
        self,
        page: int = 1,
        limit: int = 10,
        category: Optional[str] = None,
        search_query: Optional[str] = None,
        search_type: str = "title",
        current_user_id: Optional[str] = None,
    ) -> PostListResponse:
        """게시글 목록을 조회합니다."""
        result = await self.db.get_posts(
            page=page,
            limit=limit,
            category_key=category,
            search_query=search_query,
            search_type=search_type,
            current_user_id=current_user_id,
        )

        posts = [self._to_post_list_item(p) for p in result["posts"]]

        return PostListResponse(
            posts=posts,
            total=result["total"],
            page=result["page"],
            total_pages=result["total_pages"],
            has_next=result["has_next"],
            has_prev=result["has_prev"],
        )

    async def update_post(
        self,
        post_id: UUID,
        user_id: str,
        data: PostUpdate,
    ) -> bool:
        """게시글을 수정합니다."""
        category_id = None
        if data.category:
            category = await self.db.get_category_by_key(data.category.value)
            if not category:
                raise ValueError(f"카테고리를 찾을 수 없습니다: {data.category.value}")
            category_id = UUID(str(category["id"]))

        return await self.db.update_post(
            post_id=post_id,
            user_id=user_id,
            title=data.title,
            content=data.content,
            category_id=category_id,
            sub_category=data.sub_category.value if data.sub_category else None,
        )

    async def delete_post(self, post_id: UUID, user_id: str) -> bool:
        """게시글을 삭제합니다."""
        return await self.db.delete_post(post_id, user_id)

    async def toggle_post_like(self, post_id: UUID, user_id: str) -> LikeResponse:
        """게시글 좋아요를 토글합니다."""
        result = await self.db.toggle_post_like(post_id, user_id)
        return LikeResponse(**result)

    async def report_post(
        self,
        post_id: UUID,
        reporter_id: str,
        data: ReportCreate,
    ) -> ReportResponse:
        """게시글을 신고합니다."""
        result = await self.db.create_report(
            reporter_id=reporter_id,
            target_type="post",
            target_id=post_id,
            reason=data.reason,
        )
        return ReportResponse(id=result["id"])

    # ============================================================
    # Comment
    # ============================================================

    async def create_comment(
        self,
        post_id: UUID,
        user_id: str,
        data: CommentCreate,
    ) -> Dict[str, Any]:
        """댓글을 생성합니다."""
        return await self.db.create_comment(
            post_id=post_id,
            user_id=user_id,
            content=data.content,
        )

    async def create_reply(
        self,
        comment_id: UUID,
        user_id: str,
        post_id: UUID,
        data: CommentCreate,
    ) -> Dict[str, Any]:
        """대댓글을 생성합니다."""
        return await self.db.create_comment(
            post_id=post_id,
            user_id=user_id,
            content=data.content,
            parent_comment_id=comment_id,
        )

    async def get_comments(
        self,
        post_id: UUID,
        current_user_id: Optional[str] = None,
    ) -> CommentListResponse:
        """게시글의 댓글 목록을 조회합니다."""
        comments = await self.db.get_comments(post_id, current_user_id)

        result = []
        for c in comments:
            replies = [
                ReplyResponse(
                    id=r["id"],
                    content=r["content"],
                    author_id=r["author_id"],
                    author_nickname=r["author_nickname"],
                    is_author_deleted=r["is_author_deleted"],
                    like_count=r["like_count"],
                    is_liked=r["is_liked"],
                    created_at=r["created_at"],
                    edited_at=r["edited_at"],
                )
                for r in c.get("replies", [])
            ]

            result.append(
                CommentResponse(
                    id=c["id"],
                    content=c["content"],
                    author_id=c["author_id"],
                    author_nickname=c["author_nickname"],
                    is_author_deleted=c["is_author_deleted"],
                    like_count=c["like_count"],
                    is_liked=c["is_liked"],
                    created_at=c["created_at"],
                    edited_at=c["edited_at"],
                    replies=replies,
                )
            )

        return CommentListResponse(comments=result, total=len(result))

    async def update_comment(
        self,
        comment_id: UUID,
        user_id: str,
        content: str,
    ) -> bool:
        """댓글을 수정합니다."""
        return await self.db.update_comment(comment_id, user_id, content)

    async def delete_comment(self, comment_id: UUID, user_id: str) -> bool:
        """댓글을 삭제합니다."""
        return await self.db.delete_comment(comment_id, user_id)

    async def toggle_comment_like(self, comment_id: UUID, user_id: str) -> LikeResponse:
        """댓글 좋아요를 토글합니다."""
        result = await self.db.toggle_comment_like(comment_id, user_id)
        return LikeResponse(**result)

    async def report_comment(
        self,
        comment_id: UUID,
        reporter_id: str,
        data: ReportCreate,
    ) -> ReportResponse:
        """댓글을 신고합니다."""
        result = await self.db.create_report(
            reporter_id=reporter_id,
            target_type="comment",
            target_id=comment_id,
            reason=data.reason,
        )
        return ReportResponse(id=result["id"])

    # ============================================================
    # MyPage
    # ============================================================

    async def get_my_posts(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> MyPostsResponse:
        """사용자의 게시글 목록을 조회합니다."""
        result = await self.db.get_user_posts(user_id, page, limit)

        posts = [
            MyPostItem(
                id=p["id"],
                category=p["category"],
                category_key=p["category_key"],
                title=p["title"],
                date=p["date"],
                views=p["views"],
                likes=p["likes"],
                comments=p["comments"],
            )
            for p in result["posts"]
        ]

        return MyPostsResponse(
            posts=posts,
            total=result["total"],
            page=result["page"],
            total_pages=result["total_pages"],
        )

    async def get_my_commented_posts(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> MyCommentedPostsResponse:
        """사용자가 댓글을 단 게시글 목록을 조회합니다."""
        result = await self.db.get_user_commented_posts(user_id, page, limit)

        posts = [
            MyCommentedPostItem(
                id=p["id"],
                category=p["category"],
                category_key=p["category_key"],
                title=p["title"],
                date=p["date"],
                views=p["views"],
                likes=p["likes"],
                comments=p["comments"],
                my_comment_date=p["my_comment_date"],
                my_comment_preview=p.get("my_comment_preview"),
            )
            for p in result["posts"]
        ]

        return MyCommentedPostsResponse(
            posts=posts,
            total=result["total"],
            page=result["page"],
            total_pages=result["total_pages"],
        )

    # ============================================================
    # Helper Methods
    # ============================================================

    def _to_post_list_item(self, post: Dict[str, Any]) -> PostListItem:
        """DB 결과를 PostListItem으로 변환합니다."""
        return PostListItem(
            id=post["id"],
            category=post["category"],
            category_key=post["category_key"],
            sub_category=post.get("sub_category"),
            title=post["title"],
            preview=post.get("preview"),
            author_id=post["author_id"],
            author_nickname=post["author_nickname"],
            is_author_deleted=post.get("is_author_deleted", False),
            view_count=post["view_count"],
            like_count=post["like_count"],
            comment_count=post["comment_count"],
            created_at=post["created_at"],
            edited_at=post.get("edited_at"),
        )

    def _to_post_detail(self, post: Dict[str, Any]) -> PostDetail:
        """DB 결과를 PostDetail으로 변환합니다."""
        return PostDetail(
            id=post["id"],
            category=post["category"],
            category_key=post["category_key"],
            sub_category=post.get("sub_category"),
            title=post["title"],
            content=post["content"],
            preview=post.get("preview"),
            author_id=post["author_id"],
            author_nickname=post["author_nickname"],
            is_author_deleted=post.get("is_author_deleted", False),
            view_count=post["view_count"],
            like_count=post["like_count"],
            comment_count=post["comment_count"],
            is_liked=post.get("is_liked", False),
            created_at=post["created_at"],
            edited_at=post.get("edited_at"),
        )


# 싱글톤 인스턴스
_board_service: Optional[BoardService] = None


def get_board_service() -> BoardService:
    """BoardService 싱글톤 인스턴스를 반환합니다."""
    global _board_service
    if _board_service is None:
        _board_service = BoardService()
    return _board_service
