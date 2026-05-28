"""M1-9 Redis password wiring tests."""

import os
from unittest.mock import patch

from app.agents.answer_generation.cache import AnswerCache
from app.common.cache.base import get_redis_client, reset_redis_client
from app.common.cache.embedding_cache import (
    EmbeddingCache,
    reset_embedding_redis_client,
)


def _password_env(enable_var: str) -> dict[str, str]:
    return {
        enable_var: "true",
        "REDIS_HOST": "redis",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
        "REDIS_PASSWORD": "test-password",
    }


def test_shared_redis_client_passes_password_when_configured():
    reset_redis_client()
    try:
        with (
            patch.dict(os.environ, _password_env("ENABLE_ANSWER_CACHE"), clear=False),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.return_value.ping.return_value = True
            client = get_redis_client()

        assert client is mock_redis_cls.return_value
        mock_redis_cls.assert_called_once()
        assert mock_redis_cls.call_args.kwargs["password"] == "test-password"
    finally:
        reset_redis_client()


def test_answer_cache_passes_password_when_configured():
    with (
        patch.dict(os.environ, _password_env("ENABLE_ANSWER_CACHE"), clear=False),
        patch("redis.Redis") as mock_redis_cls,
    ):
        mock_redis_cls.return_value.ping.return_value = True
        cache = AnswerCache()

    assert cache.enabled is True
    mock_redis_cls.assert_called_once()
    assert mock_redis_cls.call_args.kwargs["password"] == "test-password"


def test_embedding_cache_passes_password_when_configured():
    reset_embedding_redis_client()
    try:
        with (
            patch.dict(os.environ, _password_env("ENABLE_EMBEDDING_CACHE"), clear=False),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.return_value.ping.return_value = True
            client = EmbeddingCache._get_redis()

        assert client is mock_redis_cls.return_value
        mock_redis_cls.assert_called_once()
        assert mock_redis_cls.call_args.kwargs["password"] == "test-password"
    finally:
        reset_embedding_redis_client()
