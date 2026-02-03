"""
DDOKSORI Rate Limiter - SEC-04 보안 수정

slowapi 기반 Rate Limiting 구현으로 API 남용 및 DoS 공격을 방지합니다.

Rate Limits:
    - /chat, /chat/stream: 게스트 10/분, 인증 30/분
    - /auth/*: IP당 5/분 (브루트포스 방지)
    - /search: 20/분
    - /health/*: 60/분
    - 기본: 30/분

Feature Flag:
    ENABLE_RATE_LIMITING=true (기본값)

Usage:
    from app.middleware.rate_limiter import limiter

    @router.post("/chat")
    @limiter.limit("10/minute")
    async def chat(request: Request, ...):
        ...
"""

import logging
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Feature flag for rate limiting
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"


def _get_client_ip(request: Request) -> str:
    """
    클라이언트 IP 주소 추출

    X-Forwarded-For 헤더를 우선 확인 (프록시/로드밸런서 뒤에서 실행 시)
    """
    # X-Forwarded-For 헤더 확인 (Nginx, ALB 등 프록시 뒤에서)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # 첫 번째 IP가 실제 클라이언트 IP
        return forwarded_for.split(",")[0].strip()

    # X-Real-IP 헤더 확인 (Nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # 기본: 직접 연결 IP
    return get_remote_address(request)


def _get_rate_limit_key(request: Request) -> str:
    """
    Rate limit 키 생성

    인증된 사용자는 user_id 기반, 게스트는 IP 기반
    """
    # state에서 user 정보 확인 (의존성 주입 후 설정됨)
    user = getattr(request.state, "current_user", None)
    if user and hasattr(user, "user_id"):
        return f"user:{user.user_id}"

    return f"ip:{_get_client_ip(request)}"


def _rate_limit_key_func(request: Request) -> str:
    """slowapi key_func 래퍼"""
    if not ENABLE_RATE_LIMITING:
        # Rate limiting 비활성화 시 모든 요청에 동일 키 (제한 없음)
        return "disabled"
    return _get_rate_limit_key(request)


# Limiter 인스턴스 생성
limiter = Limiter(
    key_func=_rate_limit_key_func,
    default_limits=["30/minute"],  # 기본 제한
    enabled=ENABLE_RATE_LIMITING,
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """
    Rate limit 초과 시 응답 핸들러

    Returns:
        JSONResponse: 429 Too Many Requests with Korean message
    """
    client_ip = _get_client_ip(request)
    logger.warning(
        f"[RateLimit] Exceeded for {client_ip} on {request.url.path}: {exc.detail}"
    )

    return JSONResponse(
        status_code=429,
        content={
            "detail": "요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
            "error_code": "RATE_LIMIT_EXCEEDED",
            "retry_after": _extract_retry_after(exc.detail),
        },
        headers={"Retry-After": str(_extract_retry_after(exc.detail))},
    )


def _extract_retry_after(detail: str) -> int:
    """
    Rate limit 메시지에서 재시도 시간 추출

    Args:
        detail: slowapi의 rate limit 메시지 (예: "10 per 1 minute")

    Returns:
        int: 재시도까지 대기 시간 (초)
    """
    # 기본값: 60초
    try:
        if "minute" in detail:
            return 60
        elif "hour" in detail:
            return 3600
        elif "second" in detail:
            return 1
        elif "day" in detail:
            return 86400
    except Exception:
        pass
    return 60


# Rate limit 프리셋 (엔드포인트별 제한)
class RateLimits:
    """엔드포인트별 Rate Limit 프리셋"""

    # Chat endpoints - LLM 호출 비용이 높으므로 엄격한 제한
    CHAT_GUEST = "10/minute"  # 게스트: 분당 10회
    CHAT_AUTH = "30/minute"  # 인증 사용자: 분당 30회

    # Auth endpoints - 브루트포스 방지
    AUTH = "5/minute"  # 로그인 시도: 분당 5회
    AUTH_CALLBACK = "10/minute"  # OAuth 콜백: 분당 10회

    # Search endpoints
    SEARCH = "20/minute"  # 검색: 분당 20회

    # Health/Metrics - 모니터링용이므로 관대
    HEALTH = "60/minute"  # 헬스체크: 분당 60회
    METRICS = "30/minute"  # 메트릭스: 분당 30회

    # Admin endpoints
    ADMIN = "20/minute"  # 관리자: 분당 20회

    # Default
    DEFAULT = "30/minute"  # 기본: 분당 30회


def get_chat_rate_limit(request: Request) -> str:
    """
    Chat 엔드포인트용 동적 rate limit

    인증 여부에 따라 다른 제한 적용
    """
    user = getattr(request.state, "current_user", None)
    if user:
        return RateLimits.CHAT_AUTH
    return RateLimits.CHAT_GUEST


# Export
__all__ = [
    "limiter",
    "rate_limit_exceeded_handler",
    "RateLimits",
    "get_chat_rate_limit",
    "ENABLE_RATE_LIMITING",
]
