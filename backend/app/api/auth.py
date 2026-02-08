"""
똑소리 프로젝트 - 인증 API 라우터

작성일: 2026-01-28
최종 수정: 2026-02-01

[역할 및 책임]
OAuth 2.0 소셜 로그인 API 엔드포인트를 제공합니다.
- Google, Naver 로그인
- JWT 토큰 발행
- 현재 사용자 정보 조회

[API 엔드포인트]
    GET    /auth/google          - Google 로그인 시작
    GET    /auth/google/callback - Google 콜백 처리
    GET    /auth/naver           - Naver 로그인 시작
    GET    /auth/naver/callback  - Naver 콜백 처리
    GET    /auth/me              - 현재 사용자 정보 조회
    GET    /auth/verify          - JWT 토큰 검증
    DELETE /auth/delete-account  - 회원탈퇴

[사용 예시]
    # 1. 프론트엔드에서 /auth/google 호출
    # 2. Google 로그인 페이지로 리다이렉트
    # 3. 사용자 인증 후 /auth/google/callback으로 돌아옴
    # 4. JWT 토큰 발행 후 프론트엔드로 리다이렉트
"""

import logging
import os
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from app.auth.dependencies import decode_access_token, get_current_user
from app.auth.models import User
from app.auth.service import AuthService
from app.auth.user_db import UserDB
from app.common.config import get_config
from app.middleware.rate_limiter import RateLimits, limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth state 저장소 (Redis 기반 - 멀티 워커 환경 지원)
STATE_TTL_SECONDS = 600  # 10분
_REDIS_CONNECT_TIMEOUT = 3

_redis_client = None
_redis_init_attempted = False


def _get_redis():
    """OAuth state용 Redis 클라이언트 (싱글톤, 재시도 방지)."""
    global _redis_client, _redis_init_attempted
    if _redis_client is not None:
        return _redis_client
    if _redis_init_attempted:
        return None
    _redis_init_attempted = True
    try:
        import redis as redis_lib

        _redis_client = redis_lib.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD") or None,
            decode_responses=True,
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
        )
        _redis_client.ping()
        logger.info("[Auth] OAuth state Redis 연결 성공")
        return _redis_client
    except ImportError:
        logger.error("[Auth] redis 패키지 미설치")
        return None
    except Exception as e:
        logger.error(f"[Auth] OAuth state Redis 연결 실패: {e}")
        _redis_client = None
        return None


def _store_state(state: str) -> None:
    """OAuth state를 Redis에 저장합니다. 실패 시 HTTPException(503)."""
    r = _get_redis()
    if not r:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth 서비스를 일시적으로 사용할 수 없습니다 (Redis 연결 실패)",
        )
    try:
        r.setex(f"oauth_state:{state}", STATE_TTL_SECONDS, "1")
    except Exception as e:
        logger.error(f"[Auth] OAuth state 저장 중 Redis 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth 서비스를 일시적으로 사용할 수 없습니다",
        )


def _verify_and_remove_state(state: str) -> bool:
    """OAuth state를 검증하고 삭제합니다. Redis 장애 시 503."""
    r = _get_redis()
    if not r:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth 서비스를 일시적으로 사용할 수 없습니다 (Redis 연결 실패)",
        )
    key = f"oauth_state:{state}"
    try:
        result = r.get(key)
        if result is None:
            return False
        r.delete(key)
        return True
    except Exception as e:
        logger.error(f"[Auth] OAuth state 검증 중 Redis 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth 서비스를 일시적으로 사용할 수 없습니다",
        )


# ============================================================
# Google OAuth
# ============================================================


@router.get("/google")
@limiter.limit(RateLimits.AUTH)
async def google_login(request: Request):
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
@limiter.limit(RateLimits.AUTH_CALLBACK)
async def google_callback(
    request: Request,
    code: str = Query(..., description="Authorization Code"),
    state: str = Query(..., description="OAuth State"),
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
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state"
        )

    try:
        auth_service = AuthService()
        auth_response = await auth_service.handle_google_callback(code)

        # 프론트엔드로 리다이렉트 (토큰을 URL fragment로 전달)
        config = get_config().auth
        redirect_params = {
            "access_token": auth_response.access_token,
            "token_type": auth_response.token_type,
            "expires_in": auth_response.expires_in,
        }
        redirect_url = (
            f"{config.frontend_url}/auth/callback#{urlencode(redirect_params)}"
        )

        logger.info(f"[Auth] Google 콜백 성공: user_id={auth_response.user.user_id}")
        return RedirectResponse(redirect_url)

    except Exception as e:
        logger.error(f"[Auth] Google 콜백 실패: {e}", exc_info=True)
        error_url = f"{get_config().auth.frontend_url}/auth/error?error=login_failed"
        return RedirectResponse(error_url)


# ============================================================
# Naver OAuth
# ============================================================


@router.get("/naver")
@limiter.limit(RateLimits.AUTH)
async def naver_login(request: Request):
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
@limiter.limit(RateLimits.AUTH_CALLBACK)
async def naver_callback(
    request: Request,
    code: str = Query(..., description="Authorization Code"),
    state: str = Query(..., description="OAuth State"),
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
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state"
        )

    try:
        auth_service = AuthService()
        auth_response = await auth_service.handle_naver_callback(code)

        # 프론트엔드로 리다이렉트 (토큰을 URL fragment로 전달)
        config = get_config().auth
        redirect_params = {
            "access_token": auth_response.access_token,
            "token_type": auth_response.token_type,
            "expires_in": auth_response.expires_in,
        }
        redirect_url = (
            f"{config.frontend_url}/auth/callback#{urlencode(redirect_params)}"
        )

        logger.info(f"[Auth] Naver 콜백 성공: user_id={auth_response.user.user_id}")
        return RedirectResponse(redirect_url)

    except Exception as e:
        logger.error(f"[Auth] Naver 콜백 실패: {e}", exc_info=True)
        error_url = f"{get_config().auth.frontend_url}/auth/error?error=login_failed"
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


@router.get("/verify")
async def verify_token(token: str = Query(..., description="JWT Token")):
    """JWT 토큰을 검증합니다."""
    payload = decode_access_token(token)
    user_db = UserDB()
    user = await user_db.get_user_by_id(payload.sub)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "valid": True,
        "user": {
            "id": user.user_id,
            "email": user.email,
            "name": user.name,
            "provider": user.provider,
        },
    }


@router.delete("/delete-account")
async def delete_account(current_user: User = Depends(get_current_user)):
    """
    회원탈퇴 API.
    사용자 계정 및 관련 데이터를 삭제합니다.
    """
    try:
        user_db = UserDB()
        await user_db.delete_user(current_user.user_id)

        logger.info(f"[Auth] 회원탈퇴 완료: user_id={current_user.user_id}")
        return {"success": True, "message": "회원탈퇴가 완료되었습니다."}
    except Exception as e:
        logger.error(f"[Auth] 회원탈퇴 실패: user_id={current_user.user_id}, error={e}")
        raise HTTPException(
            status_code=500, detail="회원탈퇴 처리 중 오류가 발생했습니다."
        )


# ============================================================
# Startup/Shutdown
# ============================================================


@router.on_event("startup")
async def init_oauth_redis():
    """OAuth state Redis 연결을 초기화합니다."""
    _get_redis()
    logger.info("[Auth] OAuth state 저장소 초기화 완료 (Redis 기반)")
