"""
EmbeddingCache 통합 테스트

실제 retriever를 통한 캐시 동작 검증.
Redis 또는 OpenAI 연결이 필요한 테스트는 마커로 분리.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.common.cache.embedding_cache import EmbeddingCache


@pytest.fixture(autouse=True)
def reset_cache_state():
    """각 테스트 전 캐시 메트릭 리셋."""
    EmbeddingCache.reset_metrics()
    yield


@pytest.mark.unit
class TestPathAIntegration:
    """Path A (unified_retriever) 캐시 통합 테스트."""

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_unified_retriever_uses_cache(self):
        """unified_retriever._create_embedding()이 캐시를 활용하는지 확인."""
        from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        mock_openai_response = MagicMock()
        mock_openai_response.data = [MagicMock(embedding=[0.1] * 1536)]

        mock_openai_client = MagicMock()
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        retriever = UnifiedRetriever.__new__(UnifiedRetriever)
        retriever._openai_client = mock_openai_client
        retriever._openai_api_key = "test-key"

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            # 1회차: 캐시 미스 → API 호출 → 캐시 저장
            result1 = retriever._create_embedding("테스트 쿼리")
            assert len(result1) == 1536
            mock_openai_client.embeddings.create.assert_called_once()
            mock_redis.setex.assert_called_once()

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_unified_retriever_cache_hit_skips_api(self):
        """캐시 히트 시 OpenAI API 호출을 건너뛰는지 확인."""
        import json

        from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever

        cached_embedding = [0.5] * 1536
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(cached_embedding)

        mock_openai_client = MagicMock()

        retriever = UnifiedRetriever.__new__(UnifiedRetriever)
        retriever._openai_client = mock_openai_client
        retriever._openai_api_key = "test-key"

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            result = retriever._create_embedding("캐시된 쿼리")
            assert result == cached_embedding
            mock_openai_client.embeddings.create.assert_not_called()


@pytest.mark.unit
class TestPathBIntegration:
    """Path B (rds_internal_retriever) 캐시 통합 테스트."""

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_rds_retriever_uses_cache(self):
        """rds_internal_retriever.embed_query()가 캐시를 활용하는지 확인."""
        from app.agents.retrieval.tools.rds_internal_retriever import (
            RDSInternalRetriever,
        )

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        mock_openai_response = MagicMock()
        mock_openai_response.data = [MagicMock(embedding=[0.2] * 1536)]

        mock_openai_client = MagicMock()
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        retriever = RDSInternalRetriever.__new__(RDSInternalRetriever)
        retriever._openai_client = mock_openai_client

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            result = retriever.embed_query("테스트 쿼리")
            assert len(result) == 1536
            mock_openai_client.embeddings.create.assert_called_once()
            mock_redis.setex.assert_called_once()

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "true"})
    def test_rds_retriever_cache_hit_skips_api(self):
        """캐시 히트 시 OpenAI API 호출을 건너뛰는지 확인."""
        import json

        from app.agents.retrieval.tools.rds_internal_retriever import (
            RDSInternalRetriever,
        )

        cached_embedding = [0.3] * 1536
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(cached_embedding)

        mock_openai_client = MagicMock()

        retriever = RDSInternalRetriever.__new__(RDSInternalRetriever)
        retriever._openai_client = mock_openai_client

        with patch.object(EmbeddingCache, "_get_redis", return_value=mock_redis):
            result = retriever.embed_query("캐시된 쿼리")
            assert result == cached_embedding
            mock_openai_client.embeddings.create.assert_not_called()


@pytest.mark.unit
class TestCacheDisabledIntegration:
    """캐시 비활성화 시 기존 동작 유지 확인."""

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "false"})
    def test_unified_retriever_works_without_cache(self):
        """캐시 비활성화 시 unified_retriever가 정상 동작."""
        from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever

        mock_openai_response = MagicMock()
        mock_openai_response.data = [MagicMock(embedding=[0.1] * 1536)]

        mock_openai_client = MagicMock()
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        retriever = UnifiedRetriever.__new__(UnifiedRetriever)
        retriever._openai_client = mock_openai_client
        retriever._openai_api_key = "test-key"

        result = retriever._create_embedding("테스트")
        assert len(result) == 1536
        mock_openai_client.embeddings.create.assert_called_once()

    @patch.dict("os.environ", {"ENABLE_EMBEDDING_CACHE": "false"})
    def test_rds_retriever_works_without_cache(self):
        """캐시 비활성화 시 rds_internal_retriever가 정상 동작."""
        from app.agents.retrieval.tools.rds_internal_retriever import (
            RDSInternalRetriever,
        )

        mock_openai_response = MagicMock()
        mock_openai_response.data = [MagicMock(embedding=[0.2] * 1536)]

        mock_openai_client = MagicMock()
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        retriever = RDSInternalRetriever.__new__(RDSInternalRetriever)
        retriever._openai_client = mock_openai_client

        result = retriever.embed_query("테스트")
        assert len(result) == 1536
        mock_openai_client.embeddings.create.assert_called_once()
