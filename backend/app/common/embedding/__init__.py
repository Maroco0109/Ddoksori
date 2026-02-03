"""
임베딩 프로바이더 모듈 (OpenAI text-embedding-3-large).

Usage:
    from app.common.embedding import get_embedding_provider

    provider = get_embedding_provider()
    embedding = provider.embed_query("검색 쿼리")
"""

from app.common.embedding.factory import (
    get_embedding_dimensions,
    get_embedding_provider,
    reset_embedding_providers,
)
from app.common.embedding.provider import (
    BaseEmbeddingProvider,
    BatchEmbeddingResult,
    EmbeddingProvider,
    EmbeddingResult,
)

__all__ = [
    # Protocol & Base
    "EmbeddingProvider",
    "BaseEmbeddingProvider",
    # Result types
    "EmbeddingResult",
    "BatchEmbeddingResult",
    # Factory
    "get_embedding_provider",
    "get_embedding_dimensions",
    "reset_embedding_providers",
]
