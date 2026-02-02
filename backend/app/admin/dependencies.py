"""관리자 JWT 인증 의존성"""

import jwt
import hashlib
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.common.config import get_config
from app.admin.models import Admin

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """비밀번호를 SHA-256으로 해싱합니다."""
    return hashlib.sha256(password.encode()).hexdigest()


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
