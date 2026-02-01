"""
똑소리 프로젝트 - 인증 서비스

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
OAuth 인증 흐름을 관리하고 JWT 토큰을 발행합니다.
- OAuth 인증 URL 생성
- Authorization Code를 JWT 토큰으로 교환
- 사용자 생성/갱신

[사용 예시]
    from app.auth.service import AuthService

    auth_service = AuthService()

    # Google 로그인 URL 생성
    auth_url, state = auth_service.get_google_auth_url()

    # Authorization Code 처리
    auth_response = await auth_service.handle_google_callback(code, state)
"""

from typing import Tuple, Optional

from app.common.config import get_config
import logging
from app.auth.models import User, AuthResponse
from app.auth.oauth import GoogleOAuth, KakaoOAuth, NaverOAuth
from app.auth.user_db import UserDB
from app.auth.dependencies import create_access_token

logger = logging.getLogger(__name__)


class AuthService:
    """
    인증 서비스.

    OAuth 2.0 소셜 로그인 및 JWT 토큰 발행을 담당합니다.
    """

    def __init__(self):
        """
        AuthService를 초기화합니다.
        """
        self.config = get_config().auth
        self.user_db = UserDB()

        # OAuth 제공자 초기화
        self.google = GoogleOAuth(self.config)
        self.kakao = KakaoOAuth(self.config)
        self.naver = NaverOAuth(self.config)

    def get_google_auth_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Google OAuth 인증 URL을 생성합니다.

        Args:
            state: CSRF 방지용 state 값 (None이면 자동 생성)

        Returns:
            (authorization_url, state)
        """
        return self.google.get_authorization_url(state)

    def get_kakao_auth_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Kakao OAuth 인증 URL을 생성합니다.

        Args:
            state: CSRF 방지용 state 값 (None이면 자동 생성)

        Returns:
            (authorization_url, state)
        """
        return self.kakao.get_authorization_url(state)

    def get_naver_auth_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Naver OAuth 인증 URL을 생성합니다.

        Args:
            state: CSRF 방지용 state 값 (None이면 자동 생성)

        Returns:
            (authorization_url, state)
        """
        return self.naver.get_authorization_url(state)

    async def handle_google_callback(self, code: str) -> AuthResponse:
        """
        Google OAuth 콜백을 처리하고 JWT 토큰을 발행합니다.

        Args:
            code: Authorization Code

        Returns:
            AuthResponse (JWT 토큰 + 사용자 정보)

        Raises:
            httpx.HTTPError: OAuth API 호출 실패
        """
        # 1. Authorization Code를 Access Token으로 교환
        token_data = await self.google.exchange_code_for_token(code)

        # 2. Access Token으로 사용자 정보 조회
        user_info = await self.google.get_user_info(token_data["access_token"])

        # 3. 사용자 생성 또는 갱신
        user = await self.user_db.upsert_user(
            provider="google",
            provider_user_id=user_info["provider_user_id"],
            email=user_info["email"],
            name=user_info["name"],
            avatar_url=user_info.get("avatar_url")
        )

        # 4. JWT 토큰 생성
        access_token, expires_in = create_access_token(user)

        logger.info(f"[AuthService] Google 로그인 성공: user_id={user.user_id}")

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=user
        )

    async def handle_kakao_callback(self, code: str) -> AuthResponse:
        """
        Kakao OAuth 콜백을 처리하고 JWT 토큰을 발행합니다.

        Args:
            code: Authorization Code

        Returns:
            AuthResponse (JWT 토큰 + 사용자 정보)

        Raises:
            httpx.HTTPError: OAuth API 호출 실패
        """
        # 1. Authorization Code를 Access Token으로 교환
        token_data = await self.kakao.exchange_code_for_token(code)

        # 2. Access Token으로 사용자 정보 조회
        user_info = await self.kakao.get_user_info(token_data["access_token"])

        # 3. 사용자 생성 또는 갱신
        user = await self.user_db.upsert_user(
            provider="kakao",
            provider_user_id=user_info["provider_user_id"],
            email=user_info["email"],
            name=user_info["name"],
            avatar_url=user_info.get("avatar_url")
        )

        # 4. JWT 토큰 생성
        access_token, expires_in = create_access_token(user)

        logger.info(f"[AuthService] Kakao 로그인 성공: user_id={user.user_id}")

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=user
        )

    async def handle_naver_callback(self, code: str) -> AuthResponse:
        """
        Naver OAuth 콜백을 처리하고 JWT 토큰을 발행합니다.

        Args:
            code: Authorization Code

        Returns:
            AuthResponse (JWT 토큰 + 사용자 정보)

        Raises:
            httpx.HTTPError: OAuth API 호출 실패
        """
        # 1. Authorization Code를 Access Token으로 교환
        token_data = await self.naver.exchange_code_for_token(code)

        # 2. Access Token으로 사용자 정보 조회
        user_info = await self.naver.get_user_info(token_data["access_token"])

        # 3. 사용자 생성 또는 갱신
        user = await self.user_db.upsert_user(
            provider="naver",
            provider_user_id=user_info["provider_user_id"],
            email=user_info["email"],
            name=user_info["name"],
            avatar_url=user_info.get("avatar_url")
        )

        # 4. JWT 토큰 생성
        access_token, expires_in = create_access_token(user)

        logger.info(f"[AuthService] Naver 로그인 성공: user_id={user.user_id}")

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=user
        )

    async def close(self) -> None:
        """
        OAuth 제공자의 HTTP 클라이언트를 닫습니다.
        """
        await self.google.close()
        await self.kakao.close()
        await self.naver.close()
