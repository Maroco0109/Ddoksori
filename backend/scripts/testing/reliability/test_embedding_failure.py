"""
Embedding Service Failure Tests

Tests that embedding API timeouts, errors, empty inputs, and malformed
responses are handled gracefully.
"""

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestEmbeddingAPITimeout:
    """OpenAI Embedding API timeout should be handled."""

    def test_embedding_api_timeout_raises(self):
        """OpenAI API timeout during embedding → raises exception."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = TimeoutError("Request timed out")

        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = mock_client
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises(TimeoutError, match="Request timed out"):
            provider.embed_batch(["test text"])

    def test_embedding_api_timeout_single_text(self):
        """Single text embedding timeout → raises."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = TimeoutError("Connection timeout")

        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = mock_client
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises(TimeoutError):
            provider.embed("test text")


@pytest.mark.unit
class TestEmbeddingAPIError:
    """OpenAI Embedding API errors should be handled."""

    def test_embedding_api_error_500(self):
        """API returns HTTP 500 → exception raised."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception(
            "Error code: 500 - Internal Server Error"
        )

        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = mock_client
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises(Exception, match="500"):
            provider.embed_batch(["test text"])

    def test_embedding_api_auth_error(self):
        """API returns auth error → exception raised."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception(
            "Error code: 401 - Invalid API key"
        )

        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = mock_client
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises(Exception, match="401"):
            provider.embed_batch(["test text"])


@pytest.mark.unit
class TestEmbeddingEmptyInput:
    """Empty input to embedding should be handled."""

    def test_embedding_empty_string_raises(self):
        """Empty string input to embed → raises ValueError."""
        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = MagicMock()
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises(ValueError, match="비어있습니다"):
            provider.embed("")

    def test_embedding_whitespace_only_raises(self):
        """Whitespace-only input to embed → raises ValueError."""
        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = MagicMock()
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises(ValueError, match="비어있습니다"):
            provider.embed("   ")

    def test_embedding_empty_list_returns_empty(self):
        """Empty list input to embed_batch → returns empty result."""
        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = MagicMock()
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        result = provider.embed_batch([])
        assert result.dense == []
        assert result.tokens_used == 0

    def test_embed_query_empty_raises(self):
        """Empty query to embed_query → raises ValueError."""
        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = MagicMock()
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises(ValueError, match="비어있습니다"):
            provider.embed_query("")


@pytest.mark.unit
class TestEmbeddingInvalidResponse:
    """Malformed API response should be handled."""

    def test_embedding_response_missing_data(self):
        """API response with missing 'data' attribute → raises."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = None
        mock_client.embeddings.create.return_value = mock_response

        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = mock_client
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        with pytest.raises((TypeError, AttributeError)):
            provider.embed_batch(["test text"])

    def test_embedding_response_empty_embeddings(self):
        """API response with empty data list → returns empty embeddings."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_response.usage.total_tokens = 0
        mock_client.embeddings.create.return_value = mock_response

        from app.common.embedding.openai_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider._client = mock_client
        provider._model = "text-embedding-3-large"
        provider._target_dimensions = 1536
        provider._model_name = "text-embedding-3-large"
        provider._dimensions = 1536

        result = provider.embed_batch(["test text"])
        assert result.dense == []
