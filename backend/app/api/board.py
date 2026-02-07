"""
똑소리 프로젝트 - 게시판 API 라우터

게시글, 댓글, 좋아요, 신고 관련 엔드포인트를 제공합니다.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.auth.models import User
from app.board.schemas import (
    CategoryResponse,
    CommentCreate,
    CommentListResponse,
    CommentUpdate,
    LikeResponse,
    PostCreate,
    PostDetail,
    PostListResponse,
    PostUpdate,
    ReportCreate,
    ReportResponse,
)
from app.board.service import get_board_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/board", tags=["board"])


# ============================================================
# Category Endpoints
# ============================================================


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories():
    """카테고리 목록을 조회합니다."""
    service = get_board_service()
    return await service.get_categories()


# ============================================================
# Post Endpoints
# ============================================================


@router.get("/posts", response_model=PostListResponse)
async def get_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(
        None, description="카테고리 키 (case-sharing, qna, tips, all)"
    ),
    search: Optional[str] = Query(None, description="검색어"),
    search_type: str = Query(
        "title", description="검색 유형 (title, author, content, title_content)"
    ),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """게시글 목록을 조회합니다."""
    service = get_board_service()
    return await service.get_posts(
        page=page,
        limit=limit,
        category=category,
        search_query=search,
        search_type=search_type,
        current_user_id=current_user.user_id if current_user else None,
    )


@router.get("/posts/{post_id}", response_model=PostDetail)
async def get_post(
    post_id: UUID,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """게시글 상세를 조회합니다."""
    service = get_board_service()
    post = await service.get_post(
        post_id=post_id,
        current_user_id=current_user.user_id if current_user else None,
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="게시글을 찾을 수 없습니다.",
        )
    return post


@router.post("/posts", response_model=PostDetail, status_code=status.HTTP_201_CREATED)
async def create_post(
    data: PostCreate,
    current_user: User = Depends(get_current_user),
):
    """게시글을 작성합니다."""
    service = get_board_service()
    try:
        return await service.create_post(
            user_id=current_user.user_id,
            data=data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/posts/{post_id}", response_model=dict)
async def update_post(
    post_id: UUID,
    data: PostUpdate,
    current_user: User = Depends(get_current_user),
):
    """게시글을 수정합니다."""
    service = get_board_service()
    try:
        success = await service.update_post(
            post_id=post_id,
            user_id=current_user.user_id,
            data=data,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="수정 권한이 없거나 게시글을 찾을 수 없습니다.",
            )
        return {"success": True, "message": "게시글이 수정되었습니다."}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/posts/{post_id}", response_model=dict)
async def delete_post(
    post_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """게시글을 삭제합니다."""
    service = get_board_service()
    success = await service.delete_post(
        post_id=post_id,
        user_id=current_user.user_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="삭제 권한이 없거나 게시글을 찾을 수 없습니다.",
        )
    return {"success": True, "message": "게시글이 삭제되었습니다."}


@router.post("/posts/{post_id}/like", response_model=LikeResponse)
async def toggle_post_like(
    post_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """게시글 좋아요를 토글합니다."""
    service = get_board_service()
    return await service.toggle_post_like(
        post_id=post_id,
        user_id=current_user.user_id,
    )


@router.post("/posts/{post_id}/report", response_model=ReportResponse)
async def report_post(
    post_id: UUID,
    data: ReportCreate,
    current_user: User = Depends(get_current_user),
):
    """게시글을 신고합니다."""
    service = get_board_service()
    return await service.report_post(
        post_id=post_id,
        reporter_id=current_user.user_id,
        data=data,
    )


# ============================================================
# Comment Endpoints
# ============================================================


@router.get("/posts/{post_id}/comments", response_model=CommentListResponse)
async def get_comments(
    post_id: UUID,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """게시글의 댓글 목록을 조회합니다."""
    service = get_board_service()
    return await service.get_comments(
        post_id=post_id,
        current_user_id=current_user.user_id if current_user else None,
    )


@router.post(
    "/posts/{post_id}/comments",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    post_id: UUID,
    data: CommentCreate,
    current_user: User = Depends(get_current_user),
):
    """댓글을 작성합니다."""
    service = get_board_service()
    result = await service.create_comment(
        post_id=post_id,
        user_id=current_user.user_id,
        data=data,
    )
    return {"success": True, "comment_id": str(result["id"])}


@router.put("/comments/{comment_id}", response_model=dict)
async def update_comment(
    comment_id: UUID,
    data: CommentUpdate,
    current_user: User = Depends(get_current_user),
):
    """댓글을 수정합니다."""
    service = get_board_service()
    success = await service.update_comment(
        comment_id=comment_id,
        user_id=current_user.user_id,
        content=data.content,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="수정 권한이 없거나 댓글을 찾을 수 없습니다.",
        )
    return {"success": True, "message": "댓글이 수정되었습니다."}


@router.delete("/comments/{comment_id}", response_model=dict)
async def delete_comment(
    comment_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """댓글을 삭제합니다."""
    service = get_board_service()
    success = await service.delete_comment(
        comment_id=comment_id,
        user_id=current_user.user_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="삭제 권한이 없거나 댓글을 찾을 수 없습니다.",
        )
    return {"success": True, "message": "댓글이 삭제되었습니다."}


@router.post("/comments/{comment_id}/like", response_model=LikeResponse)
async def toggle_comment_like(
    comment_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """댓글 좋아요를 토글합니다."""
    service = get_board_service()
    return await service.toggle_comment_like(
        comment_id=comment_id,
        user_id=current_user.user_id,
    )


@router.post("/comments/{comment_id}/report", response_model=ReportResponse)
async def report_comment(
    comment_id: UUID,
    data: ReportCreate,
    current_user: User = Depends(get_current_user),
):
    """댓글을 신고합니다."""
    service = get_board_service()
    return await service.report_comment(
        comment_id=comment_id,
        reporter_id=current_user.user_id,
        data=data,
    )


@router.post(
    "/comments/{comment_id}/replies",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_reply(
    comment_id: UUID,
    data: CommentCreate,
    current_user: User = Depends(get_current_user),
):
    """대댓글을 작성합니다."""
    service = get_board_service()

    # 부모 댓글의 post_id를 찾아야 함
    # 여기서는 DB에서 직접 조회
    from app.board.board_db import BoardDB

    db = BoardDB()

    # 부모 댓글 조회를 위한 쿼리
    import psycopg2
    import psycopg2.extras

    def _get_parent_post_id():
        conn = db._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT post_id FROM community_comment
                    WHERE id = %s AND status = 'normal'
                """,
                    (str(comment_id),),
                )
                row = cur.fetchone()
                return row["post_id"] if row else None
        finally:
            conn.close()

    import asyncio

    post_id = await asyncio.to_thread(_get_parent_post_id)

    if not post_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부모 댓글을 찾을 수 없습니다.",
        )

    try:
        result = await service.create_reply(
            comment_id=comment_id,
            user_id=current_user.user_id,
            post_id=post_id,
            data=data,
        )
        return {"success": True, "comment_id": str(result["id"])}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
