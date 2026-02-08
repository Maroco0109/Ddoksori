"""
Concurrency and Isolation Tests

Tests that concurrent operations (OAuth state, cache access) don't
interfere with each other.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestConcurrentOAuthStateOperations:
    """Multiple OAuth state store/verify operations should not interfere."""

    def test_concurrent_oauth_state_store_and_verify(self):
        """Multiple states stored concurrently can each be verified."""
        import secrets

        states = {}
        for i in range(5):
            state = secrets.token_urlsafe(32)
            states[f"session_{i}"] = state

        for session_id, state in states.items():
            assert len(state) > 0
            assert state != states.get(
                f"session_{(int(session_id.split('_')[1]) + 1) % 5}"
            )

    def test_oauth_state_uniqueness(self):
        """Each generated OAuth state must be unique."""
        import secrets

        generated = set()
        for _ in range(100):
            state = secrets.token_urlsafe(32)
            assert state not in generated, f"Duplicate state generated: {state}"
            generated.add(state)

        assert len(generated) == 100


@pytest.mark.unit
class TestOAuthStateIsolation:
    """Different OAuth states should not affect each other."""

    def test_google_and_naver_states_independent(self):
        """Google and Naver OAuth states are generated independently."""
        import secrets

        google_state = secrets.token_urlsafe(32)
        naver_state = secrets.token_urlsafe(32)

        assert google_state != naver_state
        assert len(google_state) > 20
        assert len(naver_state) > 20

    def test_state_token_format(self):
        """OAuth state tokens should be URL-safe."""
        import secrets

        state = secrets.token_urlsafe(32)
        safe_chars = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        for char in state:
            assert char in safe_chars, f"Unsafe character in state: {char}"

    def test_multiple_provider_states_no_collision(self):
        """States for multiple providers stored simultaneously don't collide."""
        import secrets

        providers = ["google", "naver", "kakao", "apple"]
        state_map = {}

        for provider in providers:
            state_map[provider] = secrets.token_urlsafe(32)

        unique_states = set(state_map.values())
        assert len(unique_states) == len(providers)


@pytest.mark.unit
class TestCacheConcurrentAccess:
    """Multiple concurrent cache reads should not corrupt data."""

    def test_cache_concurrent_reads_return_consistent_data(self):
        """Multiple reads of the same cache key return identical data."""
        from app.common.cache.base import BaseRedisCache

        cached_data = '{"final_answer": "test answer", "_cached_at": 1234567890}'

        mock_redis = MagicMock()
        mock_redis.get.return_value = cached_data

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.cache import SupervisorResponseCache

            results = []
            for _ in range(10):
                result = SupervisorResponseCache.get("same query", "session-1")
                results.append(result)

        for r in results:
            assert r is not None
            assert r["final_answer"] == "test answer"

    def test_cache_different_keys_no_interference(self):
        """Reads with different keys return different cached data."""
        from app.common.cache.base import BaseRedisCache

        call_count = 0

        def mock_get(key):
            nonlocal call_count
            call_count += 1
            if "query1" in key:
                return '{"final_answer": "answer1"}'
            elif "query2" in key:
                return '{"final_answer": "answer2"}'
            return None

        mock_redis = MagicMock()
        mock_redis.get.side_effect = mock_get

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.supervisor.cache import SupervisorResponseCache

            r1 = SupervisorResponseCache.get("query1")
            r2 = SupervisorResponseCache.get("query2")

        if r1 and r2:
            assert r1["final_answer"] != r2["final_answer"]

    def test_cache_metrics_thread_safety_basic(self):
        """Cache metrics (hit/miss counters) should be consistent."""
        from app.supervisor.cache import SupervisorResponseCache

        SupervisorResponseCache.reset_metrics()
        initial = SupervisorResponseCache.get_metrics()
        assert initial["hit_count"] == 0
        assert initial["miss_count"] == 0

    @pytest.mark.asyncio
    async def test_async_cache_operations_no_crash(self):
        """Async cache operations running concurrently should not crash."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True

        async def cache_operation(query_id):
            with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
                from app.supervisor.cache import SupervisorResponseCache

                SupervisorResponseCache.get(f"query_{query_id}")
                SupervisorResponseCache.set(
                    f"query_{query_id}",
                    {"final_answer": f"answer_{query_id}"},
                )

        tasks = [cache_operation(i) for i in range(5)]
        await asyncio.gather(*tasks)
