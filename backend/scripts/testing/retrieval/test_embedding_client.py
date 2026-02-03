"""
S3-PR1: OpenAI EmbeddingClient 단위 테스트

테스트 실행:
    pytest backend/scripts/testing/retrieval/test_embedding_client.py -v
"""

import os
from unittest.mock import Mock, patch

import pytest


class TestEmbeddingClient:
    """EmbeddingClient 테스트"""

    @pytest.fixture
    def mock_openai_response(self):
        """OpenAI API 응답 mock"""
        mock_response = Mock()
        mock_response.data = [
            Mock(embedding=[0.1] * 1536),
            Mock(embedding=[0.2] * 1536),
        ]
        mock_response.usage = Mock(total_tokens=100)
        return mock_response

    @pytest.fixture
    def mock_openai_client(self, mock_openai_response):
        """OpenAI 클라이언트 mock"""
        with patch("openai.OpenAI") as mock_cls:
            mock_instance = Mock()
            mock_instance.embeddings.create.return_value = mock_openai_response
            mock_cls.return_value = mock_instance
            yield mock_instance

    def test_init(self, mock_openai_client):
        """클라이언트 초기화 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        client = EmbeddingClient()

        assert client.model == "text-embedding-3-large"
        assert client.dimensions == 1536

    def test_embed_single_text(self, mock_openai_client, mock_openai_response):
        """단일 텍스트 임베딩 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        mock_openai_response.data = [Mock(embedding=[0.1] * 1536)]
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        client = EmbeddingClient()
        embeddings = client.embed(["테스트 텍스트"])

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 1536

        mock_openai_client.embeddings.create.assert_called_once()
        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-large"
        assert call_kwargs["dimensions"] == 1536

    def test_embed_multiple_texts(self, mock_openai_client, mock_openai_response):
        """복수 텍스트 임베딩 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        client = EmbeddingClient()
        embeddings = client.embed(["텍스트1", "텍스트2"])

        assert len(embeddings) == 2
        for emb in embeddings:
            assert len(emb) == 1536

    def test_embed_query(self, mock_openai_client, mock_openai_response):
        """embed_query 메서드 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        mock_openai_response.data = [Mock(embedding=[0.5] * 1536)]
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        client = EmbeddingClient()
        embedding = client.embed_query("검색 쿼리")

        assert len(embedding) == 1536

    def test_embed_empty_list_raises(self, mock_openai_client):
        """빈 리스트 입력 시 ValueError 발생 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        client = EmbeddingClient()

        with pytest.raises(ValueError, match="texts 리스트가 비어있습니다"):
            client.embed([])

    def test_embed_query_empty_raises(self, mock_openai_client):
        """빈 쿼리 입력 시 ValueError 발생 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        client = EmbeddingClient()

        with pytest.raises(ValueError, match="query가 비어있습니다"):
            client.embed_query("")

        with pytest.raises(ValueError, match="query가 비어있습니다"):
            client.embed_query("   ")

    def test_embed_handles_empty_strings(
        self, mock_openai_client, mock_openai_response
    ):
        """빈 문자열이 포함된 리스트 처리 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        mock_openai_response.data = [
            Mock(embedding=[0.1] * 1536),
            Mock(embedding=[0.2] * 1536),
        ]
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        client = EmbeddingClient()
        embeddings = client.embed(["텍스트", ""])

        assert len(embeddings) == 2
        call_args = mock_openai_client.embeddings.create.call_args.kwargs["input"]
        assert call_args[1] == " "

    def test_embed_batch(self, mock_openai_client, mock_openai_response):
        """배치 임베딩 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        mock_openai_response.data = [Mock(embedding=[0.1] * 1536)]
        mock_openai_client.embeddings.create.return_value = mock_openai_response

        client = EmbeddingClient()
        texts = [f"텍스트{i}" for i in range(150)]
        client.embed_batch(texts, batch_size=100)

        assert mock_openai_client.embeddings.create.call_count == 2

    def test_embed_batch_empty(self, mock_openai_client):
        """빈 리스트 배치 처리 테스트"""
        from app.agents.retrieval.tools.embedding_client import EmbeddingClient

        client = EmbeddingClient()
        embeddings = client.embed_batch([])

        assert embeddings == []


class TestEmbeddingAdapter:
    """EmbeddingAdapter 테스트 (OpenAI only)"""

    def test_adapter_init(self):
        """어댑터 초기화 테스트"""
        with patch("openai.OpenAI") as mock_cls:
            mock_instance = Mock()
            mock_cls.return_value = mock_instance

            from app.agents.retrieval.tools.embedding_client import EmbeddingAdapter

            adapter = EmbeddingAdapter()

            assert adapter.dimensions == 1536

    def test_adapter_embed_delegates_to_client(self):
        """embed 메서드가 클라이언트로 위임되는지 테스트"""
        with patch("openai.OpenAI") as mock_cls:
            mock_instance = Mock()
            mock_response = Mock()
            mock_response.data = [Mock(embedding=[0.1] * 1536)]
            mock_response.usage = Mock(total_tokens=50)
            mock_instance.embeddings.create.return_value = mock_response
            mock_cls.return_value = mock_instance

            from app.agents.retrieval.tools.embedding_client import EmbeddingAdapter

            adapter = EmbeddingAdapter()
            result = adapter.embed(["테스트"])

            assert len(result) == 1
            assert len(result[0]) == 1536


class TestGetEmbeddingDimensions:
    """get_embedding_dimensions 함수 테스트"""

    def test_returns_1536(self):
        """항상 1536을 반환하는지 테스트"""
        from app.agents.retrieval.tools.embedding_client import get_embedding_dimensions

        assert get_embedding_dimensions() == 1536


class TestEmbeddingDimensionsConstant:
    """EMBEDDING_DIMENSIONS 상수 테스트"""

    def test_constant_is_1536(self):
        """상수가 1536인지 테스트"""
        from app.agents.retrieval.tools.embedding_client import EMBEDDING_DIMENSIONS

        assert EMBEDDING_DIMENSIONS == 1536
