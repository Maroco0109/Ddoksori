"""
똑소리 프로젝트 - 인증 API 라우터

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
OAuth 2.0 소셜 로그인 API 엔드포인트를 제공합니다.
- Google, Kakao, Naver 로그인
- JWT 토큰 발행
- 현재 사용자 정보 조회

[API 엔드포인트]
    GET  /auth/google/login    - Google 로그인 시작
    GET  /auth/google/callback - Google 콜백 처리
    GET  /auth/kakao/login     - Kakao 로그인 시작
    GET  /auth/kakao/callback  - Kakao 콜백 처리
    GET  /auth/naver/login     - Naver 로그인 시작
    GET  /auth/naver/callback  - Naver 콜백 처리
    GET  /auth/me              - 현재 사용자 정보 조회

[사용 예시]
    # 1. 프론트엔드에서 /auth/google/login 호출
    # 2. Google 로그인 페이지로 리다이렉트
    # 3. 사용자 인증 후 /auth/google/callback으로 돌아옴
    # 4. JWT 토큰 발행 후 프론트엔드로 리다이렉트
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException, Query, Depends, status
from fastapi.responses import RedirectResponse

from app.common.config import get_config
from app.common.logging.rag_logger import get_rag_logger
from app.auth.models import User, AuthResponse
from app.auth.service import AuthService
from app.auth.dependencies import get_current_user

logger = get_rag_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

# 인메모리 OAuth state 저장소 (TTL 관리)
# 프로덕션에서는 Redis 사용 권장, 단일 인스턴스에서는 충분
_oauth_states: Dict[str, datetime] = {}
STATE_TTL_MINUTES = 10


def _store_state(state: str) -> None:
    """OAuth state를 저장합니다."""
    _oauth_states[state] = datetime.now() + timedelta(minutes=STATE_TTL_MINUTES)


def _verify_and_remove_state(state: str) -> bool:
    """OAuth state를 검증하고 삭제합니다."""
    if state not in _oauth_states:
        return False

    # 만료 확인
    if datetime.now() > _oauth_states[state]:
        del _oauth_states[state]
        return False

    # 사용 후 삭제 (일회용)
    del _oauth_states[state]
    return True


def _cleanup_expired_states() -> None:
    """만료된 state를 정리합니다."""
    now = datetime.now()
    expired_keys = [k for k, v in _oauth_states.items() if now > v]
    for key in expired_keys:
        del _oauth_states[key]


# 백그라운드 정리 태스크 (5분마다)
async def _periodic_state_cleanup():
    """주기적으로 만료된 state를 정리합니다."""
    while True:
        await asyncio.sleep(300)  # 5분
        _cleanup_expired_states()
        logger.debug(f"[Auth] OAuth state 정리 완료: {len(_oauth_states)}개 남음")


# ============================================================
# Google OAuth
# ============================================================

@router.get("/google/login")
async def google_login():
    """
    Google 로그인을 시작합니다.

    Google OAuth 인증 페이지로 리다이렉트합니다.

    Returns:
        RedirectResponse: Google 인증 URL로 리다이렉트
    """
    auth_service = AuthService()
    auth_url, state = auth_service.get_google_auth_url()

    # State 저장 (CSRF 방지)
    _store_state(state)

    logger.info(f"[Auth] Google 로그인 시작: state={state[:8]}...")
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization Code"),
    state: str = Query(..., description="OAuth State")
):
    """
    Google OAuth 콜백을 처리합니다.

    Authorization Code를 받아 JWT 토큰을 발행하고 프론트엔드로 리다이렉트합니다.

    Args:
        code: Authorization Code
        state: OAuth State (CSRF 방지)

    Returns:
        RedirectResponse: 프론트엔드 URL로 리다이렉트 (토큰 포함)

    Raises:
        HTTPException: State 검증 실패 또는 OAuth 에러
    """
    # State 검증
    if not _verify_and_remove_state(state):
        logger.warning(f"[Auth] Google 콜백: 잘못된 state={state[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state"
        )

    try:
        auth_service = AuthService()
        auth_response = await auth_service.handle_google_callback(code)

        # 프론트엔드로 리다이렉트 (토큰을 URL fragment로 전달)
        config = get_config().auth
        redirect_params = {
            "access_token": auth_response.access_token,
            "token_type": auth_response.token_type,
            "expires_in": auth_response.expires_in
        }
        redirect_url = f"{config.frontend_url}/auth/callback?{urlencode(redirect_params)}"

        logger.info(f"[Auth] Google 콜백 성공: user_id={auth_response.user.user_id}")
        return RedirectResponse(redirect_url)

    except Exception as e:
        logger.error(f"[Auth] Google 콜백 실패: {e}", exc_info=True)
        error_url = f"{get_config().auth.frontend_url}/auth/error?error={str(e)}"
        return RedirectResponse(error_url)


# ============================================================
# Kakao OAuth
# ============================================================

@router.get("/kakao/login")
async def kakao_login():
    """
    Kakao 로그인을 시작합니다.

    Kakao OAuth 인증 페이지로 리다이렉트합니다.

    Returns:
        RedirectResponse: Kakao 인증 URL로 리다이렉트
    """
    auth_service = AuthService()
    auth_url, state = auth_service.get_kakao_auth_url()

    # State 저장 (CSRF 방지)
    _store_state(state)

    logger.info(f"[Auth] Kakao 로그인 시작: state={state[:8]}...")
    return RedirectResponse(auth_url)


@router.get("/kakao/callback")
async def kakao_callback(
    code: str = Query(..., description="Authorization Code"),
    state: str = Query(..., description="OAuth State")
):
    """
    Kakao OAuth 콜백을 처리합니다.

    Authorization Code를 받아 JWT 토큰을 발행하고 프론트엔드로 리다이렉트합니다.

    Args:
        code: Authorization Code
        state: OAuth State (CSRF 방지)

    Returns:
        RedirectResponse: 프론트엔드 URL로 리다이렉트 (토큰 포함)

    Raises:
        HTTPException: State 검증 실패 또는 OAuth 에러
    """
    # State 검증
    if not _verify_and_remove_state(state):
        logger.warning(f"[Auth] Kakao 콜백: 잘못된 state={state[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state"
        )

    try:
        auth_service = AuthService()
        auth_response = await auth_service.handle_kakao_callback(code)

        # 프론트엔드로 리다이렉트 (토큰을 URL fragment로 전달)
        config = get_config().auth
        redirect_params = {
            "access_token": auth_response.access_token,
            "token_type": auth_response.token_type,
            "expires_in": auth_response.expires_in
        }
        redirect_url = f"{config.frontend_url}/auth/callback?{urlencode(redirect_params)}"

        logger.info(f"[Auth] Kakao 콜백 성공: user_id={auth_response.user.user_id}")
        return RedirectResponse(redirect_url)

    except Exception as e:
        logger.error(f"[Auth] Kakao 콜백 실패: {e}", exc_info=True)
        error_url = f"{get_config().auth.frontend_url}/auth/error?error={str(e)}"
        return RedirectResponse(error_url)


# ============================================================
# Naver OAuth
# ============================================================

@router.get("/naver/login")
async def naver_login():
    """
    Naver 로그인을 시작합니다.

    Naver OAuth 인증 페이지로 리다이렉트합니다.

    Returns:
        RedirectResponse: Naver 인증 URL로 리다이렉트
    """
    auth_service = AuthService()
    auth_url, state = auth_service.get_naver_auth_url()

    # State 저장 (CSRF 방지)
    _store_state(state)

    logger.info(f"[Auth] Naver 로그인 시작: state={state[:8]}...")
    return RedirectResponse(auth_url)


@router.get("/naver/callback")
async def naver_callback(
    code: str = Query(..., description="Authorization Code"),
    state: str = Query(..., description="OAuth State")
):
    """
    Naver OAuth 콜백을 처리합니다.

    Authorization Code를 받아 JWT 토큰을 발행하고 프론트엔드로 리다이렉트합니다.

    Args:
        code: Authorization Code
        state: OAuth State (CSRF 방지)

    Returns:
        RedirectResponse: 프론트엔드 URL로 리다이렉트 (토큰 포함)

    Raises:
        HTTPException: State 검증 실패 또는 OAuth 에러
    """
    # State 검증
    if not _verify_and_remove_state(state):
        logger.warning(f"[Auth] Naver 콜백: 잘못된 state={state[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state"
        )

    try:
        auth_service = AuthService()
        auth_response = await auth_service.handle_naver_callback(code)

        # 프론트엔드로 리다이렉트 (토큰을 URL fragment로 전달)
        config = get_config().auth
        redirect_params = {
            "access_token": auth_response.access_token,
            "token_type": auth_response.token_type,
            "expires_in": auth_response.expires_in
        }
        redirect_url = f"{config.frontend_url}/auth/callback?{urlencode(redirect_params)}"

        logger.info(f"[Auth] Naver 콜백 성공: user_id={auth_response.user.user_id}")
        return RedirectResponse(redirect_url)

    except Exception as e:
        logger.error(f"[Auth] Naver 콜백 실패: {e}", exc_info=True)
        error_url = f"{get_config().auth.frontend_url}/auth/error?error={str(e)}"
        return RedirectResponse(error_url)


# ============================================================
# User Info
# ============================================================

@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    현재 인증된 사용자 정보를 조회합니다.

    Args:
        current_user: 현재 사용자 (JWT 토큰에서 추출)

    Returns:
        User 모델

    Raises:
        HTTPException: 인증 실패 (401 Unauthorized)
    """
    return current_user


# ============================================================
# Startup/Shutdown
# ============================================================

@router.on_event("startup")
async def start_state_cleanup():
    """OAuth state 정리 태스크를 시작합니다."""
    asyncio.create_task(_periodic_state_cleanup())
    logger.info("[Auth] OAuth state 정리 태스크 시작")
