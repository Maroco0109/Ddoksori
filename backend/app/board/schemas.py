"""
똑소리 프로젝트 - 게시판 Pydantic 스키마

게시글, 댓글, 좋아요, 신고 관련 요청/응답 스키마를 정의합니다.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ============================================================
# Enums
# ============================================================


class PostCategory(str, Enum):
    """게시글 카테고리"""

    CASE_SHARING = "case-sharing"
    QNA = "qna"
    TIPS = "tips"


class SubCategory(str, Enum):
    """분쟁해결사례 서브 카테고리"""

    PRE_MEDIATION = "pre-mediation"  # 조정 이전 단계에서 해결
    MEDIATION = "mediation"  # 조정을 통한 해결


class ContentStatus(str, Enum):
    """게시글/댓글 상태"""

    NORMAL = "normal"
    HIDDEN = "hidden"
    DELETED = "deleted"


class ReportTargetType(str, Enum):
    """신고 대상 유형"""

    POST = "post"
    COMMENT = "comment"


# ============================================================
# Category Schemas
# ============================================================


class CategoryResponse(BaseModel):
    """카테고리 응답"""

    id: UUID
    category_key: str
    category_name: str
    display_name: str
    sort_order: Optional[int] = None


# ============================================================
# Post Schemas
# ============================================================


class PostCreate(BaseModel):
    """게시글 작성 요청"""

    category: PostCategory
    sub_category: Optional[SubCategory] = None
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=5000)


class PostUpdate(BaseModel):
    """게시글 수정 요청"""

    category: Optional[PostCategory] = None
    sub_category: Optional[SubCategory] = None
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    content: Optional[str] = Field(None, min_length=1, max_length=5000)


class PostListItem(BaseModel):
    """게시글 목록 아이템"""

    id: UUID
    category: str  # display_name
    category_key: str
    sub_category: Optional[str] = None
    title: str
    preview: Optional[str] = None
    author_id: str
    author_nickname: str
    is_author_deleted: bool = False
    view_count: int
    like_count: int
    comment_count: int
    created_at: datetime
    edited_at: Optional[datetime] = None


class PostDetail(BaseModel):
    """게시글 상세"""

    id: UUID
    category: str  # display_name
    category_key: str
    sub_category: Optional[str] = None
    title: str
    content: str
    preview: Optional[str] = None
    author_id: str
    author_nickname: str
    is_author_deleted: bool = False
    view_count: int
    like_count: int
    comment_count: int
    is_liked: bool = False  # 현재 사용자가 좋아요 했는지
    created_at: datetime
    edited_at: Optional[datetime] = None


class PostListResponse(BaseModel):
    """게시글 목록 응답"""

    posts: List[PostListItem]
    total: int
    page: int
    total_pages: int
    has_next: bool
    has_prev: bool


# ============================================================
# Comment Schemas
# ============================================================


class CommentCreate(BaseModel):
    """댓글 작성 요청"""

    content: str = Field(..., min_length=1, max_length=1000)


class CommentUpdate(BaseModel):
    """댓글 수정 요청"""

    content: str = Field(..., min_length=1, max_length=1000)


class ReplyResponse(BaseModel):
    """대댓글 응답"""

    id: UUID
    content: str
    author_id: str
    author_nickname: str
    is_author_deleted: bool = False
    like_count: int
    is_liked: bool = False
    created_at: datetime
    edited_at: Optional[datetime] = None


class CommentResponse(BaseModel):
    """댓글 응답"""

    id: UUID
    content: str
    author_id: str
    author_nickname: str
    is_author_deleted: bool = False
    like_count: int
    is_liked: bool = False
    created_at: datetime
    edited_at: Optional[datetime] = None
    replies: List[ReplyResponse] = []


class CommentListResponse(BaseModel):
    """댓글 목록 응답"""

    comments: List[CommentResponse]
    total: int


# ============================================================
# Like Schemas
# ============================================================


class LikeResponse(BaseModel):
    """좋아요 토글 응답"""

    liked: bool
    like_count: int


# ============================================================
# Report Schemas
# ============================================================


class ReportCreate(BaseModel):
    """신고 요청"""

    reason: str = Field(..., min_length=1, max_length=1000)


class ReportResponse(BaseModel):
    """신고 응답"""

    id: UUID
    message: str = "신고가 접수되었습니다."


# ============================================================
# MyPage Schemas
# ============================================================


class MyPostItem(BaseModel):
    """마이페이지 내 게시글 아이템"""

    id: UUID
    category: str  # display_name
    category_key: str
    title: str
    date: str  # YYYY.MM.DD 형식
    views: int
    likes: int
    comments: int


class MyCommentedPostItem(BaseModel):
    """마이페이지 내가 댓글 단 게시글 아이템"""

    id: UUID
    category: str  # display_name
    category_key: str
    title: str
    date: str  # YYYY.MM.DD 형식
    views: int
    likes: int
    comments: int
    my_comment_date: str  # YYYY.MM.DD 형식
    my_comment_preview: Optional[str] = None


class MyPostsResponse(BaseModel):
    """마이페이지 내 게시글 목록 응답"""

    posts: List[MyPostItem]
    total: int
    page: int
    total_pages: int


class MyCommentedPostsResponse(BaseModel):
    """마이페이지 내가 댓글 단 게시글 목록 응답"""

    posts: List[MyCommentedPostItem]
    total: int
    page: int
    total_pages: int
