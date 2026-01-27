"""
Unit tests for JWT dependencies

작성일: 2026-01-28
설명: JWT 토큰 생성 및 검증 테스트 (Unit - 모킹 사용)
"""

import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.auth.dependencies import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_current_user_optional
)
from app.auth.models import User
from fastapi import HTTPException


@pytest.mark.unit
def test_create_access_token():
    """JWT 토큰 생성 테스트"""
    user = User(
        user_id="google:123456",
        email="test@example.com",
        name="Test User",
        provider="google",
        provider_user_id="123456"
    )

    token, expires_in = create_access_token(user)

    assert isinstance(token, str)
    assert len(token) > 0
    assert expires_in > 0

    # 토큰 디코드 검증
    from app.common.config import get_config
    config = get_config().auth
    payload = jwt.decode(token, config.jwt_secret_key, algorithms=[config.jwt_algorithm])

    assert payload["sub"] == user.user_id
    assert payload["email"] == user.email
    assert payload["name"] == user.name
    assert payload["provider"] == user.provider


@pytest.mark.unit
def test_decode_access_token_valid():
    """유효한 JWT 토큰 디코드 테스트"""
    user = User(
        user_id="google:123456",
        email="test@example.com",
        name="Test User",
        provider="google",
        provider_user_id="123456"
    )

    token, _ = create_access_token(user)
    payload = decode_access_token(token)

    assert payload.sub == user.user_id
    assert payload.email == user.email
    assert payload.name == user.name
    assert payload.provider == user.provider


@pytest.mark.unit
def test_decode_access_token_expired():
    """만료된 JWT 토큰 디코드 테스트"""
    from app.common.config import get_config
    config = get_config().auth

    # 이미 만료된 토큰 생성
    payload = {
        "sub": "google:123456",
        "email": "test@example.com",
        "name": "Test User",
        "provider": "google",
        "exp": int((datetime.utcnow() - timedelta(days=1)).timestamp()),
        "iat": int(datetime.utcnow().timestamp())
    }
    expired_token = jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(expired_token)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.unit
def test_decode_access_token_invalid():
    """잘못된 JWT 토큰 디코드 테스트"""
    invalid_token = "invalid.jwt.token"

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(invalid_token)

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_valid():
    """유효한 토큰으로 현재 사용자 조회 테스트"""
    user = User(
        user_id="google:123456",
        email="test@example.com",
        name="Test User",
        provider="google",
        provider_user_id="123456"
    )

    token, _ = create_access_token(user)

    # HTTPAuthorizationCredentials 모킹
    credentials = MagicMock()
    credentials.credentials = token

    # UserDB 모킹
    with patch('app.auth.dependencies.UserDB') as MockUserDB:
        mock_db_instance = MockUserDB.return_value
        mock_db_instance.get_user_by_id = AsyncMock(return_value=user)

        result = await get_current_user(credentials)

        assert result.user_id == user.user_id
        assert result.email == user.email


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_no_credentials():
    """인증 정보 없이 현재 사용자 조회 테스트"""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(None)

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_optional_valid():
    """유효한 토큰으로 선택적 사용자 조회 테스트"""
    user = User(
        user_id="google:123456",
        email="test@example.com",
        name="Test User",
        provider="google",
        provider_user_id="123456"
    )

    token, _ = create_access_token(user)

    credentials = MagicMock()
    credentials.credentials = token

    with patch('app.auth.dependencies.UserDB') as MockUserDB:
        mock_db_instance = MockUserDB.return_value
        mock_db_instance.get_user_by_id = AsyncMock(return_value=user)

        result = await get_current_user_optional(credentials)

        assert result is not None
        assert result.user_id == user.user_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_optional_no_credentials():
    """인증 정보 없이 선택적 사용자 조회 테스트 (None 반환)"""
    result = await get_current_user_optional(None)
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_optional_invalid_token():
    """잘못된 토큰으로 선택적 사용자 조회 테스트 (None 반환)"""
    credentials = MagicMock()
    credentials.credentials = "invalid.token"

    result = await get_current_user_optional(credentials)
    assert result is None
