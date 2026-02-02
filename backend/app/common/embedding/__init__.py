"""
임베딩 프로바이더 모듈.

OpenAI, KURE-v1, BGE-M3 임베딩을 통합 관리하는 팩토리 패턴 제공.
각 프로바이더는 싱글톤으로 관리되어 연결 재사용.

Usage:
    from app.common.embedding import get_embedding_provider

    # 환경변수 기반 자동 선택
    provider = get_embedding_provider()
    embedding = provider.embed_query("검색 쿼리")

    # Dense + Sparse (BGE-M3)
    result = provider.embed("텍스트")
    dense = result.dense
    sparse = result.sparse  # BGE-M3만 지원
"""

from app.common.embedding.factory import (
    EmbeddingProviderFactory,
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
    "EmbeddingProviderFactory",
    "get_embedding_provider",
    "get_embedding_dimensions",
    "reset_embedding_providers",
]
