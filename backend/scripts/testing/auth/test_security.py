"""
Security tests for OAuth CSRF defense and JWT attack scenarios

Tests:
  S1: OAuth CSRF Defense (api/auth.py)
  S2: JWT Attack Scenarios (auth/dependencies.py)
  S3: API Auth Protection
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.auth.dependencies import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_current_user_optional,
)
from app.auth.models import User

# ============================================================
# S1: OAuth CSRF Defense
# ============================================================


class TestOAuthCSRFDefense:
    """OAuth state 검증 테스트 (CSRF 방어)"""

    @staticmethod
    def _get_auth_module():
        """app.api.auth 모듈을 __init__.py 부작용 없이 직접 로드"""
        import importlib.util
        import os

        module_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "app", "api", "auth.py"
        )
        module_path = os.path.abspath(module_path)
        spec = importlib.util.spec_from_file_location("app_api_auth", module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def setup_method(self):
        """각 테스트 전 state 저장소 초기화"""
        auth_mod = self._get_auth_module()
        auth_mod._oauth_states.clear()

    @pytest.mark.unit
    def test_valid_state_verification(self):
        """유효한 state 검증 성공"""
        auth_mod = self._get_auth_module()
        auth_mod._store_state("test-state-123")
        assert auth_mod._verify_and_remove_state("test-state-123") is True

    @pytest.mark.unit
    def test_unknown_state_rejected(self):
        """알 수 없는 state 거부"""
        auth_mod = self._get_auth_module()
        assert auth_mod._verify_and_remove_state("unknown-state") is False

    @pytest.mark.unit
    def test_state_single_use(self):
        """state는 일회용 - 재사용 불가"""
        auth_mod = self._get_auth_module()
        auth_mod._store_state("single-use-state")
        assert auth_mod._verify_and_remove_state("single-use-state") is True
        assert auth_mod._verify_and_remove_state("single-use-state") is False

    @pytest.mark.unit
    def test_expired_state_rejected(self):
        """만료된 state 거부"""
        auth_mod = self._get_auth_module()
        auth_mod._oauth_states["expired-state"] = datetime.now() - timedelta(minutes=1)
        assert auth_mod._verify_and_remove_state("expired-state") is False

    @pytest.mark.unit
    def test_cleanup_expired_states(self):
        """만료된 state 정리"""
        auth_mod = self._get_auth_module()
        auth_mod._store_state("valid-state")
        auth_mod._oauth_states["expired-1"] = datetime.now() - timedelta(minutes=15)
        auth_mod._oauth_states["expired-2"] = datetime.now() - timedelta(minutes=30)

        auth_mod._cleanup_expired_states()

        assert "valid-state" in auth_mod._oauth_states
        assert "expired-1" not in auth_mod._oauth_states
        assert "expired-2" not in auth_mod._oauth_states

    @pytest.mark.unit
    def test_empty_state_rejected(self):
        """빈 문자열 state 거부"""
        auth_mod = self._get_auth_module()
        assert auth_mod._verify_and_remove_state("") is False

    @pytest.mark.unit
    def test_store_state_sets_ttl(self):
        """state 저장 시 TTL 설정 확인"""
        auth_mod = self._get_auth_module()
        auth_mod._store_state("ttl-state")
        expiry = auth_mod._oauth_states["ttl-state"]
        expected = datetime.now() + timedelta(minutes=auth_mod.STATE_TTL_MINUTES)
        assert abs((expiry - expected).total_seconds()) < 1


# ============================================================
# S2: JWT Attack Scenarios
# ============================================================


class TestJWTAttackScenarios:
    """JWT 공격 시나리오 테스트"""

    @pytest.mark.unit
    def test_expired_token_rejected(self):
        """만료된 토큰 거부"""
        from app.common.config import get_config

        config = get_config().auth
        payload = {
            "sub": "google:123",
            "email": "test@test.com",
            "name": "Test",
            "provider": "google",
            "exp": int((datetime.utcnow() - timedelta(hours=1)).timestamp()),
            "iat": int(datetime.utcnow().timestamp()),
        }
        token = jwt.encode(
            payload, config.jwt_secret_key, algorithm=config.jwt_algorithm
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_wrong_secret_key_rejected(self):
        """잘못된 서명(다른 시크릿 키) 토큰 거부"""
        payload = {
            "sub": "google:123",
            "email": "test@test.com",
            "name": "Test",
            "provider": "google",
            "exp": int((datetime.utcnow() + timedelta(days=1)).timestamp()),
            "iat": int(datetime.utcnow().timestamp()),
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_none_algorithm_rejected(self):
        """알고리즘 혼동 공격 (none) 거부"""
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(
                "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJnb29nbGU6MTIzIn0."
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_tampered_payload_rejected(self):
        """변조된 페이로드 토큰 거부"""
        user = User(
            user_id="google:123",
            email="test@test.com",
            name="Test",
            provider="google",
            provider_user_id="123",
        )
        token, _ = create_access_token(user)
        # 토큰 페이로드 부분 변조
        parts = token.split(".")
        parts[1] = parts[1] + "tampered"
        tampered_token = ".".join(parts)
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered_token)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_empty_token_rejected(self):
        """빈 문자열 토큰 거부"""
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("")
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    def test_malformed_token_rejected(self):
        """형식이 잘못된 토큰 거부"""
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("not-a-jwt-at-all")
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_token_for_nonexistent_user(self):
        """존재하지 않는 사용자 토큰 → 401"""
        user = User(
            user_id="google:nonexistent",
            email="ghost@test.com",
            name="Ghost",
            provider="google",
            provider_user_id="nonexistent",
        )
        token, _ = create_access_token(user)
        credentials = MagicMock()
        credentials.credentials = token

        with patch("app.auth.dependencies.UserDB") as MockUserDB:
            mock_db = MockUserDB.return_value
            mock_db.get_user_by_id = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)
            assert exc_info.value.status_code == 401


# ============================================================
# S3: API Auth Protection
# ============================================================


class TestAPIAuthProtection:
    """API 엔드포인트 인증 보호 검증"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_me_without_token(self):
        """인증 없이 /auth/me 접근 시 401"""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_me_with_invalid_token(self):
        """잘못된 토큰으로 /auth/me → 401"""
        credentials = MagicMock()
        credentials.credentials = "invalid.token.here"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)
        assert exc_info.value.status_code == 401

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_returns_none_for_invalid(self):
        """선택적 인증에서 잘못된 토큰 → None (예외 없음)"""
        credentials = MagicMock()
        credentials.credentials = "bad-token"
        result = await get_current_user_optional(credentials)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_returns_none_for_no_credentials(self):
        """선택적 인증에서 인증 정보 없음 → None"""
        result = await get_current_user_optional(None)
        assert result is None
