"""
똑소리 프로젝트 - 관리자 API 라우터

관리자 인증, 대시보드, 게시글/댓글/회원/신고 관리 엔드포인트를 제공합니다.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.admin.models import Admin, AdminLoginRequest, AdminLoginResponse
from app.admin.admin_db import AdminDB
from app.admin.dependencies import get_current_admin, hash_password, create_admin_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================
# Admin Auth
# ============================================================

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(request: AdminLoginRequest):
    """관리자 로그인"""
    admin_db = AdminDB()
    admin_row = await admin_db.get_admin_by_username(request.username)

    if not admin_row:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if admin_row["password_hash"] != hash_password(request.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    admin = Admin(
        id=str(admin_row["id"]),
        username=admin_row["username"],
        email=admin_row.get("email"),
        role=admin_row["role"],
    )

    await admin_db.update_admin_last_login(str(admin_row["id"]))
    token = create_admin_token(admin)

    return AdminLoginResponse(admin=admin, token=token)


# ============================================================
# Dashboard
# ============================================================

@router.get("/stats")
async def get_stats(admin: Admin = Depends(get_current_admin)):
    """대시보드 통계 데이터"""
    admin_db = AdminDB()
    return await admin_db.get_stats()


# ============================================================
# Posts Management
# ============================================================

@router.get("/posts")
async def get_posts(
    searchType: Optional[str] = Query(None),
    searchKeyword: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    isPublic: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: Admin = Depends(get_current_admin),
):
    """게시글 목록 조회 (관리자)"""
    admin_db = AdminDB()
    return await admin_db.get_posts(page, limit, searchType, searchKeyword, category, isPublic)


@router.get("/posts/{post_id}")
async def get_post(post_id: int, admin: Admin = Depends(get_current_admin)):
    """게시글 상세 조회"""
    admin_db = AdminDB()
    post = await admin_db.get_post_by_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


class VisibilityRequest(BaseModel):
    isPublic: bool


@router.put("/posts/{post_id}/visibility")
async def update_post_visibility(
    post_id: int, request: VisibilityRequest, admin: Admin = Depends(get_current_admin)
):
    """게시글 공개/비공개 전환"""
    admin_db = AdminDB()
    success = await admin_db.update_post_visibility(post_id, request.isPublic)
    if not success:
        raise HTTPException(status_code=404, detail="Post not found")
    await admin_db.log_action(admin.id, "toggle_post_visibility", "post", post_id)
    msg = "게시글이 공개 처리되었습니다." if request.isPublic else "게시글이 비공개 처리되었습니다."
    return {"success": True, "message": msg}


@router.delete("/posts/{post_id}")
async def delete_post(post_id: int, admin: Admin = Depends(get_current_admin)):
    """게시글 삭제 (soft delete)"""
    admin_db = AdminDB()
    success = await admin_db.soft_delete_post(post_id)
    if not success:
        raise HTTPException(status_code=404, detail="Post not found")
    await admin_db.log_action(admin.id, "delete_post", "post", post_id)
    return {"success": True, "message": "게시글이 삭제되었습니다."}


class NoticeRequest(BaseModel):
    title: str
    content: str
    isPinned: bool = False


@router.post("/posts/notice")
async def create_notice(request: NoticeRequest, admin: Admin = Depends(get_current_admin)):
    """공지사항 작성"""
    admin_db = AdminDB()
    post_id = await admin_db.create_notice(admin.id, request.title, request.content, request.isPinned)
    await admin_db.log_action(admin.id, "create_notice", "post", post_id)
    return {"success": True, "postId": post_id, "message": "공지사항이 작성되었습니다."}


# ============================================================
# Comments Management
# ============================================================

@router.get("/comments")
async def get_comments(
    postId: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: Admin = Depends(get_current_admin),
):
    """댓글 목록 조회"""
    admin_db = AdminDB()
    return await admin_db.get_comments(page, limit, postId)


@router.put("/comments/{comment_id}/visibility")
async def update_comment_visibility(
    comment_id: int, request: VisibilityRequest, admin: Admin = Depends(get_current_admin)
):
    """댓글 공개/비공개 전환"""
    admin_db = AdminDB()
    success = await admin_db.update_comment_visibility(comment_id, request.isPublic)
    if not success:
        raise HTTPException(status_code=404, detail="Comment not found")
    await admin_db.log_action(admin.id, "toggle_comment_visibility", "comment", comment_id)
    return {"success": True, "message": "댓글 공개 상태가 변경되었습니다."}


@router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: int, admin: Admin = Depends(get_current_admin)):
    """댓글 삭제 (soft delete)"""
    admin_db = AdminDB()
    success = await admin_db.soft_delete_comment(comment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Comment not found")
    await admin_db.log_action(admin.id, "delete_comment", "comment", comment_id)
    return {"success": True, "message": "댓글이 삭제되었습니다."}


# ============================================================
# Users Management
# ============================================================

@router.get("/users")
async def get_users(
    searchKeyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: Admin = Depends(get_current_admin),
):
    """회원 목록 조회"""
    admin_db = AdminDB()
    return await admin_db.get_users(page, limit, searchKeyword, status, provider)


@router.get("/users/{user_id}")
async def get_user(user_id: str, admin: Admin = Depends(get_current_admin)):
    """회원 상세 조회"""
    admin_db = AdminDB()
    user = await admin_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


class UserStatusRequest(BaseModel):
    status: str


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: str, request: UserStatusRequest, admin: Admin = Depends(get_current_admin)
):
    """회원 상태 변경"""
    if request.status not in ("active", "suspended", "banned"):
        raise HTTPException(status_code=400, detail="Invalid status")
    admin_db = AdminDB()
    success = await admin_db.update_user_status(user_id, request.status)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    await admin_db.log_action(admin.id, f"change_user_status_{request.status}", "user", reason=user_id)
    return {"success": True, "message": "사용자 상태가 변경되었습니다."}


# ============================================================
# Reports Management
# ============================================================

@router.get("/reports")
async def get_reports(
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: Admin = Depends(get_current_admin),
):
    """신고 목록 조회"""
    admin_db = AdminDB()
    return await admin_db.get_reports(page, limit, type, status)


@router.get("/reports/{report_id}")
async def get_report(report_id: int, admin: Admin = Depends(get_current_admin)):
    """신고 상세 조회"""
    admin_db = AdminDB()
    report = await admin_db.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


class ReportStatusRequest(BaseModel):
    status: str
    adminNote: Optional[str] = None


@router.put("/reports/{report_id}/status")
async def update_report_status(
    report_id: int, request: ReportStatusRequest, admin: Admin = Depends(get_current_admin)
):
    """신고 처리 상태 변경"""
    if request.status not in ("reviewed", "resolved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid status")
    admin_db = AdminDB()
    success = await admin_db.update_report_status(report_id, request.status, request.adminNote)
    if not success:
        raise HTTPException(status_code=404, detail="Report not found")
    await admin_db.log_action(admin.id, f"update_report_{request.status}", "report", report_id, request.adminNote)
    return {"success": True, "message": "신고 처리 상태가 변경되었습니다."}
