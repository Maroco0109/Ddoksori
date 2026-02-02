"""
똑소리 프로젝트 - 인증 시스템 모델

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
인증 시스템에서 사용하는 Pydantic 모델을 정의합니다.
- User: 사용자 정보
- AuthResponse: 인증 응답 (토큰 + 사용자 정보)
- TokenPayload: JWT 토큰 페이로드

[사용 예시]
    from app.auth.models import User, AuthResponse

    user = User(
        user_id="google:123456",
        email="user@example.com",
        name="홍길동",
        provider="google"
    )

    response = AuthResponse(
        access_token="eyJ...",
        token_type="bearer",
        user=user
    )
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class User(BaseModel):
    """
    사용자 정보 모델.

    OAuth 인증을 통해 생성된 사용자 정보를 표현합니다.
    """
    user_id: str = Field(..., description="사용자 고유 ID")
    email: str = Field(..., description="이메일 주소")
    name: str = Field(..., description="사용자 이름")
    avatar_url: Optional[str] = Field(None, description="프로필 이미지 URL")
    provider: Literal["google", "naver"] = Field(..., description="OAuth 제공자")
    provider_user_id: str = Field(..., description="제공자에서의 사용자 ID")
    created_at: Optional[datetime] = Field(None, description="계정 생성 시각")
    updated_at: Optional[datetime] = Field(None, description="계정 갱신 시각")
    last_login_at: Optional[datetime] = Field(None, description="마지막 로그인 시각")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "google:123456789",
                "email": "user@example.com",
                "name": "홍길동",
                "avatar_url": "https://example.com/avatar.jpg",
                "provider": "google",
                "provider_user_id": "123456789",
                "created_at": "2026-01-28T10:00:00",
                "updated_at": "2026-01-28T10:00:00",
                "last_login_at": "2026-01-28T12:00:00"
            }
        }


class AuthResponse(BaseModel):
    """
    인증 응답 모델.

    OAuth 인증 완료 후 반환되는 JWT 토큰 및 사용자 정보입니다.
    """
    access_token: str = Field(..., description="JWT Access Token")
    token_type: str = Field(default="bearer", description="토큰 타입")
    expires_in: int = Field(..., description="토큰 만료 시간 (초)")
    user: User = Field(..., description="사용자 정보")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 2592000,
                "user": {
                    "user_id": "google:123456789",
                    "email": "user@example.com",
                    "name": "홍길동",
                    "avatar_url": "https://example.com/avatar.jpg",
                    "provider": "google",
                    "provider_user_id": "123456789"
                }
            }
        }


class TokenPayload(BaseModel):
    """
    JWT 토큰 페이로드 모델.

    JWT 토큰에 포함되는 클레임(claims) 정보입니다.
    """
    sub: str = Field(..., description="Subject (user_id)")
    email: str = Field(..., description="이메일 주소")
    name: str = Field(..., description="사용자 이름")
    provider: str = Field(..., description="OAuth 제공자")
    exp: int = Field(..., description="만료 시각 (Unix timestamp)")
    iat: int = Field(..., description="발행 시각 (Unix timestamp)")

    class Config:
        json_schema_extra = {
            "example": {
                "sub": "google:123456789",
                "email": "user@example.com",
                "name": "홍길동",
                "provider": "google",
                "exp": 1738051200,
                "iat": 1735459200
            }
        }


class OAuthCallbackRequest(BaseModel):
    """
    OAuth 콜백 요청 모델.

    프론트엔드에서 OAuth 콜백 URL의 쿼리 파라미터를 전달할 때 사용합니다.
    """
    code: str = Field(..., description="OAuth Authorization Code")
    state: str = Field(..., description="OAuth State (CSRF 방지)")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "4/0AY0e-g7...",
                "state": "abc123xyz"
            }
        }
