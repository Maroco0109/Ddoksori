"""
EmbeddingProviderFactory - OpenAI 임베딩 프로바이더 팩토리

Usage:
    from app.common.embedding import get_embedding_provider

    provider = get_embedding_provider()
    embedding = provider.embed_query("검색 쿼리")
"""

import logging
from typing import Optional

from .provider import BaseEmbeddingProvider

logger = logging.getLogger(__name__)

# 프로바이더 싱글톤 캐시
_provider: Optional[BaseEmbeddingProvider] = None

EMBEDDING_DIMENSIONS = 1536


def get_embedding_provider() -> BaseEmbeddingProvider:
    """
    OpenAI 임베딩 프로바이더 반환 (싱글톤).

    Returns:
        OpenAIEmbeddingProvider 인스턴스
    """
    global _provider

    if _provider is None:
        from .openai_provider import OpenAIEmbeddingProvider

        _provider = OpenAIEmbeddingProvider()
        logger.info("[EmbeddingFactory] OpenAI provider initialized")

    return _provider


def get_embedding_dimensions() -> int:
    """
    임베딩 차원 수 반환.

    Returns:
        1536 (text-embedding-3-large)
    """
    return EMBEDDING_DIMENSIONS


def reset_embedding_providers() -> None:
    """프로바이더 리셋 (테스트용)."""
    global _provider
    _provider = None
    logger.debug("[EmbeddingFactory] Provider reset")
