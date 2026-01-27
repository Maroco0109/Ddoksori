"""
똑소리 프로젝트 - JWT 인증 의존성

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
JWT 토큰 생성 및 검증 의존성을 제공합니다.
- create_access_token(): JWT Access Token 생성
- decode_access_token(): JWT 토큰 디코드 및 검증
- get_current_user(): 현재 인증된 사용자 조회 (필수)
- get_current_user_optional(): 현재 인증된 사용자 조회 (선택)

[사용 예시]
    from fastapi import Depends
    from app.auth.dependencies import get_current_user
    from app.auth.models import User

    @app.get("/me")
    async def get_me(user: User = Depends(get_current_user)):
        return {"user": user}
"""

import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.common.config import get_config
from app.common.logging.rag_logger import get_rag_logger
from app.auth.models import User, TokenPayload
from app.auth.user_db import UserDB

logger = get_rag_logger()
security = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> tuple[str, int]:
    """
    JWT Access Token을 생성합니다.

    Args:
        user: User 모델 인스턴스

    Returns:
        (access_token, expires_in_seconds)
    """
    config = get_config().auth
    expires_delta = timedelta(days=config.jwt_token_expire_days)
    expires_at = datetime.utcnow() + expires_delta

    payload = TokenPayload(
        sub=user.user_id,
        email=user.email,
        name=user.name,
        provider=user.provider,
        exp=int(expires_at.timestamp()),
        iat=int(datetime.utcnow().timestamp())
    )

    token = jwt.encode(
        payload.model_dump(),
        config.jwt_secret_key,
        algorithm=config.jwt_algorithm
    )

    logger.info(f"[JWT] 토큰 생성: user_id={user.user_id}")
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> TokenPayload:
    """
    JWT Access Token을 디코드하고 검증합니다.

    Args:
        token: JWT Access Token

    Returns:
        TokenPayload 인스턴스

    Raises:
        HTTPException: 토큰 검증 실패 시
    """
    config = get_config().auth

    try:
        payload = jwt.decode(
            token,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm]
        )
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        logger.warning("[JWT] 토큰 만료")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[JWT] 토큰 검증 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    현재 인증된 사용자를 조회합니다 (필수).

    FastAPI Depends로 사용하여 인증이 필요한 엔드포인트를 보호합니다.

    Args:
        credentials: HTTP Bearer 인증 정보

    Returns:
        User 모델 인스턴스

    Raises:
        HTTPException: 인증 실패 시 (401 Unauthorized)
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token_payload = decode_access_token(credentials.credentials)

    user_db = UserDB()
    user = await user_db.get_user_by_id(token_payload.sub)

    if not user:
        logger.warning(f"[JWT] 사용자 없음: user_id={token_payload.sub}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """
    현재 인증된 사용자를 조회합니다 (선택).

    인증 정보가 없어도 None을 반환하며 예외를 발생시키지 않습니다.
    게스트와 로그인 사용자 모두 접근 가능한 엔드포인트에서 사용합니다.

    Args:
        credentials: HTTP Bearer 인증 정보 (선택)

    Returns:
        User 모델 인스턴스 또는 None
    """
    if not credentials:
        return None

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_db = UserDB()
        user = await user_db.get_user_by_id(token_payload.sub)
        return user
    except HTTPException:
        # 토큰 검증 실패 시 None 반환 (예외 발생 안 함)
        return None
