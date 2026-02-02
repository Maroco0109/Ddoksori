"""
S2-PR3: AnswerCache 테스트
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.agents.answer_generation.cache import (
    AnswerCache,
    get_answer_cache,
    reset_cache_instance,
)


class TestAnswerCacheInit:
    def test_init_disabled_by_default(self):
        with patch.dict(os.environ, {"ENABLE_ANSWER_CACHE": "false"}):
            cache = AnswerCache()
            assert cache.enabled is False
            assert cache._redis is None

    def test_init_enabled_without_redis_disables_cache(self):
        with patch.dict(os.environ, {"ENABLE_ANSWER_CACHE": "true"}):
            with patch("redis.Redis") as mock_redis_cls:
                mock_redis_cls.return_value.ping.side_effect = ConnectionError(
                    "mock: Redis unavailable"
                )
                cache = AnswerCache()
                assert cache.enabled is False


class TestCacheKey:
    def test_generate_cache_key_consistency(self):
        cache = AnswerCache()

        key1 = cache._generate_cache_key("환불 가능한가요?", "dispute")
        key2 = cache._generate_cache_key("환불 가능한가요?", "dispute")

        assert key1 == key2
        assert key1.startswith("answer_cache:")

    def test_generate_cache_key_normalization(self):
        cache = AnswerCache()

        key1 = cache._generate_cache_key("환불 가능한가요?", "dispute")
        key2 = cache._generate_cache_key("  환불 가능한가요?  ", "dispute")
        key3 = cache._generate_cache_key("환불 가능한가요?", "dispute")

        assert key1 == key2 == key3

    def test_generate_cache_key_different_for_different_types(self):
        cache = AnswerCache()

        key1 = cache._generate_cache_key("환불 가능한가요?", "dispute")
        key2 = cache._generate_cache_key("환불 가능한가요?", "law")

        assert key1 != key2


class TestCacheOperationsDisabled:
    def test_get_returns_none_when_disabled(self):
        cache = AnswerCache()
        cache.enabled = False

        result = cache.get("query", "type")

        assert result is None

    def test_set_returns_false_when_disabled(self):
        cache = AnswerCache()
        cache.enabled = False

        result = cache.set("query", "type", {"answer": "test"})

        assert result is False

    def test_invalidate_returns_false_when_disabled(self):
        cache = AnswerCache()
        cache.enabled = False

        result = cache.invalidate("query", "type")

        assert result is False


class TestCacheOperationsWithMockRedis:
    @pytest.fixture
    def cache_with_mock_redis(self):
        cache = AnswerCache()
        mock_redis = MagicMock()
        cache._redis = mock_redis
        cache.enabled = True
        return cache, mock_redis

    def test_get_returns_cached_value(self, cache_with_mock_redis):
        cache, mock_redis = cache_with_mock_redis
        mock_redis.get.return_value = (
            '{"answer": "cached answer", "has_evidence": true}'
        )

        result = cache.get("환불 가능한가요?", "dispute")

        assert result == {"answer": "cached answer", "has_evidence": True}
        assert cache._hit_count == 1

    def test_get_returns_none_on_miss(self, cache_with_mock_redis):
        cache, mock_redis = cache_with_mock_redis
        mock_redis.get.return_value = None

        result = cache.get("환불 가능한가요?", "dispute")

        assert result is None
        assert cache._miss_count == 1

    def test_get_handles_redis_error(self, cache_with_mock_redis):
        cache, mock_redis = cache_with_mock_redis
        mock_redis.get.side_effect = Exception("Redis error")

        result = cache.get("환불 가능한가요?", "dispute")

        assert result is None
        assert cache._error_count == 1

    def test_set_stores_value(self, cache_with_mock_redis):
        cache, mock_redis = cache_with_mock_redis

        result = cache.set("환불 가능한가요?", "dispute", {"answer": "test"})

        assert result is True
        mock_redis.setex.assert_called_once()

    def test_set_handles_redis_error(self, cache_with_mock_redis):
        cache, mock_redis = cache_with_mock_redis
        mock_redis.setex.side_effect = Exception("Redis error")

        result = cache.set("query", "type", {"answer": "test"})

        assert result is False
        assert cache._error_count == 1

    def test_invalidate_deletes_key(self, cache_with_mock_redis):
        cache, mock_redis = cache_with_mock_redis
        mock_redis.delete.return_value = 1

        result = cache.invalidate("환불 가능한가요?", "dispute")

        assert result is True
        mock_redis.delete.assert_called_once()

    def test_clear_all_deletes_all_keys(self, cache_with_mock_redis):
        cache, mock_redis = cache_with_mock_redis
        mock_redis.scan_iter.return_value = iter(
            ["answer_cache:abc", "answer_cache:def"]
        )
        mock_redis.delete.return_value = 2

        result = cache.clear_all()

        assert result == 2


class TestMetrics:
    def test_get_metrics_returns_stats(self):
        cache = AnswerCache()
        cache._hit_count = 10
        cache._miss_count = 5
        cache._error_count = 1

        metrics = cache.get_metrics()

        assert metrics["hit_count"] == 10
        assert metrics["miss_count"] == 5
        assert metrics["error_count"] == 1
        assert metrics["hit_rate"] == round(10 / 15, 4)

    def test_get_metrics_zero_division(self):
        cache = AnswerCache()

        metrics = cache.get_metrics()

        assert metrics["hit_rate"] == 0.0

    def test_reset_metrics(self):
        cache = AnswerCache()
        cache._hit_count = 10
        cache._miss_count = 5
        cache._error_count = 1

        cache.reset_metrics()

        assert cache._hit_count == 0
        assert cache._miss_count == 0
        assert cache._error_count == 0


class TestSingleton:
    def test_get_answer_cache_returns_singleton(self):
        reset_cache_instance()

        cache1 = get_answer_cache()
        cache2 = get_answer_cache()

        assert cache1 is cache2

        reset_cache_instance()

    def test_reset_cache_instance(self):
        reset_cache_instance()
        cache1 = get_answer_cache()

        reset_cache_instance()
        cache2 = get_answer_cache()

        assert cache1 is not cache2

        reset_cache_instance()
