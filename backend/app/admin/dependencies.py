"""관리자 JWT 인증 의존성"""

import hashlib
import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from app.admin.models import Admin
from app.common.config import get_config

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """비밀번호를 bcrypt로 해싱합니다."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호를 검증합니다. bcrypt 해시와 레거시 SHA-256 모두 지원."""
    try:
        if pwd_context.verify(plain_password, hashed_password):
            return True
    except Exception:
        pass
    # 레거시 SHA-256 fallback (마이그레이션 기간)
    sha256_hash = hashlib.sha256(plain_password.encode()).hexdigest()
    return sha256_hash == hashed_password


def create_admin_token(admin: Admin) -> str:
    """관리자용 JWT 토큰을 생성합니다."""
    config = get_config().auth
    from datetime import datetime, timedelta

    payload = {
        "sub": admin.id,
        "username": admin.username,
        "role": admin.role,
        "type": "admin",
        "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
    }
    return jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Admin:
    """현재 인증된 관리자를 조회합니다."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    config = get_config().auth
    try:
        payload = jwt.decode(
            credentials.credentials,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if payload.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    return Admin(
        id=payload["sub"],
        username=payload["username"],
        role=payload["role"],
    )
