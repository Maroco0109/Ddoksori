"""
EmbeddingCache 단위 테스트

테스트 항목:
1. 캐시 히트/미스
2. TTL 만료
3. 모델별 키 분리
4. 환경변수 비활성화
5. Redis 연결 실패 시 graceful fallback
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.common.cache.embedding_cache import EmbeddingCache


@pytest.fixture(autouse=True)
def reset_cache_state():
    """각 테스트 전 캐시 메트릭 리셋."""
    EmbeddingCache.reset_metrics()
    yield


class TestEmbeddingCacheKey:
    """캐시 키 생성 테스트."""

    def test_build_embedding_key_includes_model(self):
        """모델명이 캐시 키에 포함되는지 확인."""
        key1 = EmbeddingCache._build_embedding_key("hello", "model-a")
        key2 = EmbeddingCache._build_embedding_key("hello", "model-b")
        assert key1 != key2

    def test_build_embedding_key_normalizes_text(self):
        """텍스트 정규화 확인 (대소문자, 공백, 문장부호)."""
        key1 = EmbeddingCache._build_embedding_key("Hello World!", "model-a")
        key2 = EmbeddingCache._build_embedding_key("hello  world", "model-a")
        assert key1 == key2

    def test_build_embedding_key_same_input_same_key(self):
        """동일 입력은 동일 키 생성."""
        key1 = EmbeddingCache._build_embedding_key(
            "test query", "text-embedding-3-large"
        )
        key2 = EmbeddingCache._build_embedding_key(
            "test query", "text-embedding-3-large"
        )
        assert key1 == key2

    def test_build_embedding_key_prefix(self):
        """키가 emb: prefix로 시작하는지 확인."""
        key = EmbeddingCache._build_embedding_key("test", "model")
        assert key.startswith("emb:")


class TestEmbeddingCacheDisabled:
    """캐시 비활성화 테스트."""

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "false"})
    def test_get_returns_none_when_disabled(self):
        """비활성화 시 get_embedding은 None 반환."""
        result = EmbeddingCache.get_embedding("test", "model")
        assert result is None

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "false"})
    def test_set_returns_false_when_disabled(self):
        """비활성화 시 set_embedding은 False 반환."""
        result = EmbeddingCache.set_embedding("test", "model", [0.1, 0.2])
        assert result is False

    @patch.dict("os.environ", {}, clear=False)
    def test_disabled_by_default(self):
        """ENABLE_EMBEDDING_CACHE 미설정 시 기본 비활성화."""
        with patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": ""}, clear=False):
            result = EmbeddingCache.get_embedding("test", "model")
            assert result is None


class TestEmbeddingCacheEnabled:
    """캐시 활성화 시 히트/미스 테스트."""

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_cache_miss_returns_none(self):
        """캐시 미스 시 None 반환."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            result = EmbeddingCache.get_embedding("new query", "text-embedding-3-large")
            assert result is None
            assert EmbeddingCache._miss_count == 1

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_cache_hit_returns_embedding(self):
        """캐시 히트 시 임베딩 벡터 반환."""
        expected = [0.1, 0.2, 0.3]
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(expected)

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            result = EmbeddingCache.get_embedding(
                "cached query", "text-embedding-3-large"
            )
            assert result == expected
            assert EmbeddingCache._hit_count == 1

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_set_and_get_roundtrip(self):
        """저장 후 조회 라운드트립."""
        storage = {}
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        mock_redis = MagicMock()

        def mock_setex(key, ttl, value):
            storage[key] = value

        def mock_get(key):
            return storage.get(key)

        mock_redis.setex.side_effect = mock_setex
        mock_redis.get.side_effect = mock_get

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            # set
            success = EmbeddingCache.set_embedding(
                "test query", "text-embedding-3-large", embedding
            )
            assert success is True

            # get
            result = EmbeddingCache.get_embedding(
                "test query", "text-embedding-3-large"
            )
            assert result == embedding

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_set_uses_correct_ttl(self):
        """TTL이 7일(604800초)으로 설정되는지 확인."""
        mock_redis = MagicMock()

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            EmbeddingCache.set_embedding("test", "model", [0.1])
            mock_redis.setex.assert_called_once()
            args = mock_redis.setex.call_args[0]
            assert args[1] == 86400 * 7  # 7일


class TestEmbeddingCacheModelSeparation:
    """모델별 캐시 키 분리 테스트."""

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_different_models_different_cache(self):
        """다른 모델은 다른 캐시 키 사용."""
        storage = {}
        embedding_a = [0.1, 0.2]
        embedding_b = [0.3, 0.4]

        mock_redis = MagicMock()

        def mock_setex(key, ttl, value):
            storage[key] = value

        def mock_get(key):
            return storage.get(key)

        mock_redis.setex.side_effect = mock_setex
        mock_redis.get.side_effect = mock_get

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            EmbeddingCache.set_embedding("same query", "model-a", embedding_a)
            EmbeddingCache.set_embedding("same query", "model-b", embedding_b)

            result_a = EmbeddingCache.get_embedding("same query", "model-a")
            result_b = EmbeddingCache.get_embedding("same query", "model-b")

            assert result_a == embedding_a
            assert result_b == embedding_b


class TestEmbeddingCacheGracefulFallback:
    """Redis 연결 실패 시 graceful fallback 테스트."""

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_get_returns_none_when_redis_unavailable(self):
        """Redis 연결 불가 시 get은 None 반환."""
        with patch.object(EmbeddingCache, "_get_redis", return_value=None):
            result = EmbeddingCache.get_embedding("test", "model")
            assert result is None

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_set_returns_false_when_redis_unavailable(self):
        """Redis 연결 불가 시 set은 False 반환."""
        with patch.object(EmbeddingCache, "_get_redis", return_value=None):
            result = EmbeddingCache.set_embedding("test", "model", [0.1])
            assert result is False

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_get_handles_redis_exception(self):
        """Redis 예외 발생 시 None 반환 (에러 카운트 증가)."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection lost")

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            result = EmbeddingCache.get_embedding("test", "model")
            assert result is None
            assert EmbeddingCache._error_count == 1

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_set_handles_redis_exception(self):
        """Redis 예외 발생 시 False 반환 (에러 카운트 증가)."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Connection lost")

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            result = EmbeddingCache.set_embedding("test", "model", [0.1])
            assert result is False
            assert EmbeddingCache._error_count == 1
