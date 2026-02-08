"""
똑소리 프로젝트 - 사용자 API 라우터

마이페이지 관련 엔드포인트를 제공합니다.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.user_db import UserDB
from app.board.schemas import MyCommentedPostsResponse, MyPostsResponse
from app.board.service import get_board_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])


class UpdateProfileRequest(BaseModel):
    """프로필 업데이트 요청 모델"""

    name: str = Field(
        ..., min_length=1, max_length=50, description="사용자 이름(닉네임)"
    )


@router.get("/me/posts", response_model=MyPostsResponse)
async def get_my_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """내가 작성한 게시글 목록을 조회합니다."""
    service = get_board_service()
    return await service.get_my_posts(current_user.user_id, page, limit)


@router.get("/me/commented-posts", response_model=MyCommentedPostsResponse)
async def get_my_commented_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """내가 댓글을 단 게시글 목록을 조회합니다."""
    service = get_board_service()
    return await service.get_my_commented_posts(current_user.user_id, page, limit)


@router.patch("/me/profile")
async def update_my_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
):
    """
    사용자 프로필(닉네임)을 업데이트합니다.

    Args:
        request: 프로필 업데이트 요청 (name)
        current_user: 현재 인증된 사용자

    Returns:
        업데이트된 사용자 정보

    Raises:
        HTTPException: 업데이트 실패 시
    """
    try:
        user_db = UserDB()
        updated_user = await user_db.update_name(current_user.user_id, request.name)

        logger.info(
            f"[Users] 프로필 업데이트 성공: user_id={current_user.user_id}, name={request.name}"
        )

        return {
            "success": True,
            "user": {
                "user_id": updated_user.user_id,
                "email": updated_user.email,
                "name": updated_user.name,
                "avatar_url": updated_user.avatar_url,
                "provider": updated_user.provider,
            },
        }
    except Exception as e:
        logger.error(
            f"[Users] 프로필 업데이트 실패: user_id={current_user.user_id}, error={e}"
        )
        raise HTTPException(status_code=500, detail="프로필 업데이트에 실패했습니다.")
