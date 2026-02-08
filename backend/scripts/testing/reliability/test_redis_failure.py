"""
Redis Failure Handling Tests

Tests that Redis failures (ConnectionError, timeout, disabled) are handled
gracefully without crashing the application.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestCacheCheckRedisConnectionError:
    """Redis ConnectionError during cache check should skip cache gracefully."""

    def test_cache_check_redis_connection_error(self):
        """Redis ConnectionError in BaseRedisCache.get → returns None, no exception."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.get.side_effect = ConnectionError("Connection refused")

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.cache import SupervisorResponseCache

            result = SupervisorResponseCache.get("test query", "session-1")

        assert result is None

    def test_cache_check_returns_none_on_redis_error(self):
        """BaseRedisCache.get catches generic Exception and returns None."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Unexpected Redis error")

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.cache import QueryAnalysisCache

            result = QueryAnalysisCache.get("test query")

        assert result is None

    def test_cache_get_timeout(self):
        """Redis timeout during get → returns None (no crash)."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.get.side_effect = TimeoutError("Redis read timed out")

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.cache import IntentClassificationCache

            result = IntentClassificationCache.get("timeout query")

        assert result is None


@pytest.mark.unit
class TestCacheStoreRedisDown:
    """Redis down during cache store should not raise exceptions."""

    def test_cache_store_redis_down(self):
        """Redis down during set → returns False, logs warning, no exception."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = ConnectionError("Connection refused")

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.cache import SupervisorResponseCache

            result = SupervisorResponseCache.set(
                "test query",
                {"final_answer": "test answer"},
                "session-1",
            )

        assert result is False

    def test_cache_store_timeout(self):
        """Redis timeout during set → returns False, no exception."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = TimeoutError("Redis write timed out")

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.cache import QueryAnalysisCache

            result = QueryAnalysisCache.set("test", {"mode": "NEED_RAG"})

        assert result is False


@pytest.mark.unit
class TestCacheDisabled:
    """Cache disabled by config should skip entirely."""

    def test_cache_disabled_returns_none_on_get(self):
        """When Redis client is None (disabled), get returns None."""
        from app.common.cache.base import BaseRedisCache

        with patch.object(BaseRedisCache, "_get_redis", return_value=None):
            from app.supervisor.cache import SupervisorResponseCache

            result = SupervisorResponseCache.get("any query")

        assert result is None

    def test_cache_disabled_returns_false_on_set(self):
        """When Redis client is None (disabled), set returns False."""
        from app.common.cache.base import BaseRedisCache

        with patch.object(BaseRedisCache, "_get_redis", return_value=None):
            from app.supervisor.cache import SupervisorResponseCache

            result = SupervisorResponseCache.set("q", {"data": "val"})

        assert result is False

    def test_cache_disabled_delete_returns_false(self):
        """When Redis client is None (disabled), delete returns False."""
        from app.common.cache.base import BaseRedisCache

        with patch.object(BaseRedisCache, "_get_redis", return_value=None):
            from app.supervisor.cache import SupervisorResponseCache

            result = SupervisorResponseCache.delete("q")

        assert result is False

    def test_cache_disabled_clear_all_returns_zero(self):
        """When Redis client is None (disabled), clear_all returns 0."""
        from app.common.cache.base import BaseRedisCache

        with patch.object(BaseRedisCache, "_get_redis", return_value=None):
            from app.supervisor.cache import SupervisorResponseCache

            result = SupervisorResponseCache.clear_all()

        assert result == 0

    def test_cache_disabled_count_returns_zero(self):
        """When Redis client is None (disabled), count returns 0."""
        from app.common.cache.base import BaseRedisCache

        with patch.object(BaseRedisCache, "_get_redis", return_value=None):
            from app.supervisor.cache import SupervisorResponseCache

            result = SupervisorResponseCache.count()

        assert result == 0


@pytest.mark.unit
class TestCacheCheckNodeRedisFailure:
    """Cache check node in graph_mas handles Redis failures."""

    def test_cache_check_node_redis_error_returns_no_hit(self):
        """_cache_check_node with Redis error → _cache_hit=False."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.get.side_effect = ConnectionError("Redis down")

        state = {
            "user_query": "환불 가능한가요?",
            "session_id": "test-session",
            "total_turn_count": 0,
        }

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.graph_mas import _cache_check_node

            result = _cache_check_node(state)

        assert result["_cache_hit"] is False

    def test_cache_check_node_empty_query(self):
        """_cache_check_node with empty query → _cache_hit=False."""
        from app.supervisor.graph_mas import _cache_check_node

        state = {"user_query": "", "session_id": "test-session"}
        result = _cache_check_node(state)
        assert result["_cache_hit"] is False


@pytest.mark.unit
class TestGetRedisClient:
    """Tests for get_redis_client singleton initialization."""

    def test_redis_client_disabled_by_env(self):
        """ENABLE_ANSWER_CACHE != 'true' → returns None."""
        from app.common.cache.base import reset_redis_client

        reset_redis_client()

        with patch.dict("os.environ", {"ENABLE_ANSWER_CACHE": "false"}, clear=False):
            from app.common.cache.base import get_redis_client

            client = get_redis_client()

        assert client is None
        reset_redis_client()

    def test_redis_client_import_error(self):
        """redis package not installed → returns None."""
        import builtins

        from app.common.cache.base import reset_redis_client

        reset_redis_client()
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "redis":
                raise ImportError("No module named 'redis'")
            return original_import(name, *args, **kwargs)

        with (
            patch.dict("os.environ", {"ENABLE_ANSWER_CACHE": "true"}, clear=False),
            patch("builtins.__import__", side_effect=mock_import),
        ):
            from app.common.cache.base import get_redis_client

            client = get_redis_client()

        assert client is None
        reset_redis_client()
