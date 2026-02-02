"""
똑소리 프로젝트 - 사용자 API 라우터

마이페이지 관련 엔드포인트를 제공합니다.
"""

import logging
from fastapi import APIRouter, Depends, Query

from app.auth.models import User
from app.auth.dependencies import get_current_user
from app.board.board_db import BoardDB

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me/posts")
async def get_my_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """내가 작성한 게시글 목록을 조회합니다."""
    board_db = BoardDB()
    result = await board_db.get_user_posts(current_user.user_id, page, limit)
    return result


@router.get("/me/commented-posts")
async def get_my_commented_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """내가 댓글을 단 게시글 목록을 조회합니다."""
    board_db = BoardDB()
    result = await board_db.get_user_commented_posts(current_user.user_id, page, limit)
    return result
