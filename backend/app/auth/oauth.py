"""
똑소리 프로젝트 - OAuth 2.0 제공자

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
OAuth 2.0 소셜 로그인을 위한 제공자 클래스를 정의합니다.
- GoogleOAuth: Google OAuth 2.0
- NaverOAuth: Naver OAuth 2.0

각 제공자는 다음 메서드를 제공합니다:
- get_authorization_url(): 인증 URL 생성
- exchange_code_for_token(): Authorization Code를 Access Token으로 교환
- get_user_info(): Access Token으로 사용자 정보 조회

[사용 예시]
    from app.auth.oauth import GoogleOAuth
    from app.common.config import get_config

    config = get_config()
    google = GoogleOAuth(config.auth)

    # 1. 인증 URL 생성
    auth_url, state = google.get_authorization_url()

    # 2. Authorization Code 교환
    token_data = await google.exchange_code_for_token(code)

    # 3. 사용자 정보 조회
    user_info = await google.get_user_info(token_data["access_token"])
"""

import logging
import secrets
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx

from app.common.config import AuthConfig

logger = logging.getLogger(__name__)


class OAuthProvider(ABC):
    """
    OAuth 2.0 제공자 추상 클래스.

    모든 OAuth 제공자가 구현해야 하는 인터페이스를 정의합니다.
    """

    def __init__(self, auth_config: AuthConfig):
        """
        OAuth 제공자를 초기화합니다.

        Args:
            auth_config: 인증 설정
        """
        self.auth_config = auth_config
        self.client = httpx.AsyncClient(timeout=10.0)

    @abstractmethod
    def get_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        OAuth 인증 URL을 생성합니다.

        Args:
            state: CSRF 방지용 state 값 (None이면 자동 생성)

        Returns:
            (authorization_url, state)
        """
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> Dict:
        """
        Authorization Code를 Access Token으로 교환합니다.

        Args:
            code: Authorization Code

        Returns:
            Token 정보 딕셔너리
            {
                "access_token": str,
                "token_type": str,
                "expires_in": int,
                "refresh_token": str (optional)
            }

        Raises:
            httpx.HTTPError: API 호출 실패
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> Dict:
        """
        Access Token으로 사용자 정보를 조회합니다.

        Args:
            access_token: Access Token

        Returns:
            사용자 정보 딕셔너리
            {
                "provider_user_id": str,
                "email": str,
                "name": str,
                "avatar_url": str (optional)
            }

        Raises:
            httpx.HTTPError: API 호출 실패
        """
        pass

    async def close(self) -> None:
        """
        HTTP 클라이언트를 닫습니다.
        """
        await self.client.aclose()


class GoogleOAuth(OAuthProvider):
    """
    Google OAuth 2.0 제공자.

    Google 계정을 사용한 소셜 로그인을 지원합니다.
    """

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    SCOPES = "openid email profile"

    def get_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Google OAuth 인증 URL을 생성합니다.

        Args:
            state: CSRF 방지용 state 값 (None이면 자동 생성)

        Returns:
            (authorization_url, state)
        """
        if state is None:
            state = secrets.token_urlsafe(32)

        redirect_uri = f"{self.auth_config.backend_url}/auth/google/callback"

        params = {
            "client_id": self.auth_config.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }

        auth_url = f"{self.AUTH_URL}?{urlencode(params)}"
        logger.info(
            f"[GoogleOAuth] 인증 URL 생성: redirect_uri={redirect_uri}, state={state[:8]}..."
        )
        return auth_url, state

    async def exchange_code_for_token(self, code: str) -> Dict:
        """
        Google Authorization Code를 Access Token으로 교환합니다.

        Args:
            code: Authorization Code

        Returns:
            Token 정보 딕셔너리

        Raises:
            httpx.HTTPError: API 호출 실패
        """
        redirect_uri = f"{self.auth_config.backend_url}/auth/google/callback"

        data = {
            "code": code,
            "client_id": self.auth_config.google_client_id,
            "client_secret": self.auth_config.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        logger.info(f"[GoogleOAuth] 토큰 교환 시도: redirect_uri={redirect_uri}")
        try:
            response = await self.client.post(self.TOKEN_URL, data=data)
            response.raise_for_status()
            token_data = response.json()
            logger.info("[GoogleOAuth] 토큰 교환 성공")
            return token_data
        except httpx.HTTPError as e:
            logger.error(f"[GoogleOAuth] 토큰 교환 실패: {e}")
            raise

    async def get_user_info(self, access_token: str) -> Dict:
        """
        Google Access Token으로 사용자 정보를 조회합니다.

        Args:
            access_token: Access Token

        Returns:
            사용자 정보 딕셔너리

        Raises:
            httpx.HTTPError: API 호출 실패
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self.client.get(self.USER_INFO_URL, headers=headers)
            response.raise_for_status()
            user_data = response.json()

            user_info = {
                "provider_user_id": user_data["id"],
                "email": user_data["email"],
                "name": user_data.get("name", user_data["email"]),
                "avatar_url": user_data.get("picture"),
            }

            logger.info(f"[GoogleOAuth] 사용자 정보 조회 성공: {user_info['email']}")
            return user_info
        except httpx.HTTPError as e:
            logger.error(f"[GoogleOAuth] 사용자 정보 조회 실패: {e}")
            raise


class NaverOAuth(OAuthProvider):
    """
    Naver OAuth 2.0 제공자.

    Naver 계정을 사용한 소셜 로그인을 지원합니다.
    """

    AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
    TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
    USER_INFO_URL = "https://openapi.naver.com/v1/nid/me"

    def get_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Naver OAuth 인증 URL을 생성합니다.

        Args:
            state: CSRF 방지용 state 값 (None이면 자동 생성)

        Returns:
            (authorization_url, state)
        """
        if state is None:
            state = secrets.token_urlsafe(32)

        redirect_uri = f"{self.auth_config.backend_url}/auth/naver/callback"

        params = {
            "client_id": self.auth_config.naver_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }

        auth_url = f"{self.AUTH_URL}?{urlencode(params)}"
        logger.info(
            f"[NaverOAuth] 인증 URL 생성: redirect_uri={redirect_uri}, state={state[:8]}..."
        )
        return auth_url, state

    async def exchange_code_for_token(self, code: str) -> Dict:
        """
        Naver Authorization Code를 Access Token으로 교환합니다.

        Args:
            code: Authorization Code

        Returns:
            Token 정보 딕셔너리

        Raises:
            httpx.HTTPError: API 호출 실패
        """
        # Note: Naver doesn't require redirect_uri in token exchange
        # but log for consistency
        redirect_uri = f"{self.auth_config.backend_url}/auth/naver/callback"
        logger.info(
            f"[NaverOAuth] 토큰 교환 시도: redirect_uri={redirect_uri} (not sent to Naver)"
        )

        params = {
            "code": code,
            "client_id": self.auth_config.naver_client_id,
            "client_secret": self.auth_config.naver_client_secret,
            "grant_type": "authorization_code",
        }

        try:
            response = await self.client.get(self.TOKEN_URL, params=params)
            response.raise_for_status()
            token_data = response.json()
            logger.info("[NaverOAuth] 토큰 교환 성공")
            return token_data
        except httpx.HTTPError as e:
            logger.error(f"[NaverOAuth] 토큰 교환 실패: {e}")
            raise

    async def get_user_info(self, access_token: str) -> Dict:
        """
        Naver Access Token으로 사용자 정보를 조회합니다.

        Args:
            access_token: Access Token

        Returns:
            사용자 정보 딕셔너리

        Raises:
            httpx.HTTPError: API 호출 실패
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self.client.get(self.USER_INFO_URL, headers=headers)
            response.raise_for_status()
            user_data = response.json()

            response_data = user_data.get("response", {})

            user_info = {
                "provider_user_id": response_data["id"],
                "email": response_data.get(
                    "email", f"naver_{response_data['id']}@naver.local"
                ),
                "name": response_data.get(
                    "name", response_data.get("nickname", "Naver User")
                ),
                "avatar_url": response_data.get("profile_image"),
            }

            logger.info(f"[NaverOAuth] 사용자 정보 조회 성공: {user_info['email']}")
            return user_info
        except httpx.HTTPError as e:
            logger.error(f"[NaverOAuth] 사용자 정보 조회 실패: {e}")
            raise
