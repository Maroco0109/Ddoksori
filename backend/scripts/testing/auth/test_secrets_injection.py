"""
Tests for AWS Secrets Manager injection logic (secrets.py)

Covers the fix for empty string environment variable override bug:
- Docker Compose sets env vars to "" when host var is missing
- os.environ treats "" as "exists" → AWS Secrets Manager values not injected
- Fix: use `not os.environ.get(env_key)` to treat "" as missing
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.common.secrets import inject_aws_secrets


@pytest.fixture(autouse=True)
def reset_injected_flag():
    """Reset the _injected flag before each test."""
    import app.common.secrets as secrets_mod

    secrets_mod._injected = False
    yield
    secrets_mod._injected = False


def _make_mock_client(secret_data: dict):
    """Create a mock boto3 client returning given secret data for all categories."""
    client = MagicMock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps(secret_data)
    }
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = client
    return mock_boto3, client


class TestSecretsInjectionEmptyString:
    """빈 문자열 환경변수 덮어쓰기 테스트 (OAuth client_id 버그 수정)."""

    @pytest.mark.unit
    def test_empty_string_env_overridden_by_secret(self):
        """빈 문자열('') env var는 AWS Secrets Manager 값으로 덮어써야 한다."""
        mock_boto3, _ = _make_mock_client({"GOOGLE_CLIENT_ID": "real-client-id"})

        env_patch = {
            "USE_AWS_SECRETS": "true",
            "GOOGLE_CLIENT_ID": "",  # Docker Compose가 빈 문자열로 설정
        }
        with patch.dict(os.environ, env_patch, clear=False), \
             patch.dict("sys.modules", {"boto3": mock_boto3}):
            count = inject_aws_secrets()
            assert os.environ["GOOGLE_CLIENT_ID"] == "real-client-id"
            assert count >= 1

    @pytest.mark.unit
    def test_existing_nonempty_env_not_overridden(self):
        """실질적 값이 있는 env var는 AWS Secrets Manager 값으로 덮어쓰지 않는다."""
        mock_boto3, _ = _make_mock_client({"GOOGLE_CLIENT_ID": "secret-value"})

        env_patch = {
            "USE_AWS_SECRETS": "true",
            "GOOGLE_CLIENT_ID": "already-set-value",
        }
        with patch.dict(os.environ, env_patch, clear=False), \
             patch.dict("sys.modules", {"boto3": mock_boto3}):
            inject_aws_secrets()
            assert os.environ["GOOGLE_CLIENT_ID"] == "already-set-value"

    @pytest.mark.unit
    def test_missing_env_filled_by_secret(self):
        """env var가 아예 없으면 AWS Secrets Manager 값이 주입된다."""
        mock_boto3, _ = _make_mock_client({"NAVER_CLIENT_ID": "naver-id"})

        os.environ.pop("NAVER_CLIENT_ID", None)
        env_patch = {"USE_AWS_SECRETS": "true"}
        with patch.dict(os.environ, env_patch, clear=False), \
             patch.dict("sys.modules", {"boto3": mock_boto3}):
            inject_aws_secrets()
            assert os.environ.get("NAVER_CLIENT_ID") == "naver-id"


class TestSecretsInjectionGuards:
    """inject_aws_secrets 가드 조건 테스트."""

    @pytest.mark.unit
    def test_skips_when_aws_secrets_disabled(self):
        """USE_AWS_SECRETS가 false면 아무것도 하지 않는다."""
        with patch.dict(os.environ, {"USE_AWS_SECRETS": "false"}, clear=False):
            assert inject_aws_secrets() == 0

    @pytest.mark.unit
    def test_skips_when_aws_secrets_not_set(self):
        """USE_AWS_SECRETS가 없으면 아무것도 하지 않는다."""
        os.environ.pop("USE_AWS_SECRETS", None)
        with patch.dict(os.environ, {}, clear=False):
            assert inject_aws_secrets() == 0

    @pytest.mark.unit
    def test_idempotent_second_call_returns_zero(self):
        """두 번째 호출은 0을 반환한다 (중복 방지)."""
        mock_boto3, _ = _make_mock_client({"KEY": "val"})

        with patch.dict(os.environ, {"USE_AWS_SECRETS": "true"}, clear=False), \
             patch.dict("sys.modules", {"boto3": mock_boto3}):
            inject_aws_secrets()

            import app.common.secrets as secrets_mod
            # _injected is now True, second call should return 0
            assert secrets_mod._injected is True
            second = inject_aws_secrets()
            assert second == 0

    @pytest.mark.unit
    def test_handles_missing_secret_gracefully(self):
        """Secret이 없어도 에러 없이 처리한다."""
        mock_boto3 = MagicMock()
        client = MagicMock()

        class FakeResourceNotFound(Exception):
            pass

        FakeResourceNotFound.__name__ = "ResourceNotFoundException"
        client.get_secret_value.side_effect = FakeResourceNotFound("not found")
        mock_boto3.client.return_value = client

        with patch.dict(os.environ, {"USE_AWS_SECRETS": "true"}, clear=False), \
             patch.dict("sys.modules", {"boto3": mock_boto3}):
            count = inject_aws_secrets()
            assert count == 0
