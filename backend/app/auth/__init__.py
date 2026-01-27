"""
똑소리 프로젝트 - 인증 시스템

작성일: 2026-01-28
설명: JWT 기반 인증 및 OAuth 2.0 소셜 로그인 (Google, Kakao, Naver)

Modules:
    models: User, AuthResponse Pydantic 모델
    oauth: OAuth 제공자 (GoogleOAuth, KakaoOAuth, NaverOAuth)
    user_db: UserDB - 사용자 데이터베이스 접근 계층
    service: AuthService - 인증 비즈니스 로직
    dependencies: JWT 토큰 생성/검증 의존성
"""

from .models import User, AuthResponse, TokenPayload
from .oauth import GoogleOAuth, KakaoOAuth, NaverOAuth, OAuthProvider
from .user_db import UserDB
from .service import AuthService
from .dependencies import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_current_user_optional,
)

__all__ = [
    # Models
    "User",
    "AuthResponse",
    "TokenPayload",
    # OAuth
    "GoogleOAuth",
    "KakaoOAuth",
    "NaverOAuth",
    "OAuthProvider",
    # Database
    "UserDB",
    # Service
    "AuthService",
    # Dependencies
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "get_current_user_optional",
]
