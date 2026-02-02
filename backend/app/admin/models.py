"""관리자 시스템 Pydantic 모델"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Admin(BaseModel):
    id: str = Field(..., description="관리자 UUID")
    username: str
    email: Optional[str] = None
    role: Literal["admin", "super_admin"] = "admin"
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    admin: Admin
    token: str


class AdminStats(BaseModel):
    totalUsers: int = 0
    totalPosts: int = 0
    totalComments: int = 0
    pendingReports: int = 0
    suspendedUsers: int = 0
    todayNewUsers: int = 0
    todayNewPosts: int = 0
    todayNewComments: int = 0


class PaginationMeta(BaseModel):
    currentPage: int
    totalPages: int
    totalItems: int
    itemsPerPage: int


class PaginatedResponse(BaseModel):
    data: List[dict]
    pagination: PaginationMeta
