"""
EmbeddingProviderFactory - 통합 임베딩 프로바이더 팩토리

환경변수 기반으로 적절한 임베딩 프로바이더 자동 선택.

환경변수:
- EMBEDDING_MODEL: 사용할 모델 ('openai', 'kure-v1', 'bge-m3')
- USE_OPENAI_EMBEDDING: OpenAI 임베딩 사용 여부 (true/false)
- EMBEDDING_API_URL: 로컬 임베딩 서버 URL (KURE-v1)
- BGE_M3_API_URL: BGE-M3 서버 URL

Usage:
    from app.common.embedding import get_embedding_provider

    # 환경변수 기반 자동 선택
    provider = get_embedding_provider()
    embedding = provider.embed_query("검색 쿼리")

    # 특정 프로바이더 지정
    provider = get_embedding_provider("openai")
"""

import logging
import os
from typing import Dict, Optional

from .provider import BaseEmbeddingProvider

logger = logging.getLogger(__name__)

# 프로바이더 싱글톤 캐시
_providers: Dict[str, BaseEmbeddingProvider] = {}


class EmbeddingProviderFactory:
    """
    통합 임베딩 프로바이더 팩토리.

    모든 프로바이더는 싱글톤으로 관리되어 연결을 재사용합니다.
    """

    # 지원 프로바이더 목록
    SUPPORTED_PROVIDERS = {
        "openai": {
            "model": "text-embedding-3-large",
            "dimensions": 1536,
        },
        "kure-v1": {
            "model": "nlpai-lab/KURE-v1",
            "dimensions": 1024,
        },
        "bge-m3": {
            "model": "BAAI/bge-m3",
            "dimensions": 1024,
            "supports_sparse": True,
        },
    }

    @classmethod
    def get_provider(
        cls,
        provider_type: Optional[str] = None,
    ) -> Optional[BaseEmbeddingProvider]:
        """
        임베딩 프로바이더 반환.

        Args:
            provider_type: 프로바이더 타입 (openai, kure-v1, bge-m3)
                          미지정 시 환경변수에서 자동 결정

        Returns:
            EmbeddingProvider 인스턴스 또는 None
        """
        global _providers

        # 프로바이더 타입 결정
        if provider_type is None:
            provider_type = cls._detect_provider_type()

        if provider_type is None:
            logger.warning("[EmbeddingFactory] No provider configured")
            return None

        provider_type = provider_type.lower()

        # 캐시 확인
        if provider_type in _providers:
            return _providers[provider_type]

        # 프로바이더 생성
        provider = cls._create_provider(provider_type)
        if provider:
            _providers[provider_type] = provider

        return provider

    @classmethod
    def _detect_provider_type(cls) -> Optional[str]:
        """환경변수에서 프로바이더 타입 감지."""
        # 1. EMBEDDING_MODEL 환경변수 우선
        model = os.getenv("EMBEDDING_MODEL", "").lower()
        if model in cls.SUPPORTED_PROVIDERS:
            return model

        # 2. USE_OPENAI_EMBEDDING=true인 경우 OpenAI
        if os.getenv("USE_OPENAI_EMBEDDING", "false").lower() == "true":
            return "openai"

        # 3. BGE_M3_API_URL 설정된 경우 BGE-M3
        if os.getenv("BGE_M3_API_URL") or os.getenv("BGE_M3_REMOTE_URL"):
            return "bge-m3"

        # 4. EMBEDDING_API_URL 설정된 경우 KURE-v1
        if os.getenv("EMBEDDING_API_URL"):
            return "kure-v1"

        # 5. 기본값: kure-v1 (로컬)
        return "kure-v1"

    @classmethod
    def _create_provider(cls, provider_type: str) -> Optional[BaseEmbeddingProvider]:
        """프로바이더 타입에 따라 인스턴스 생성."""
        try:
            if provider_type == "openai":
                from .openai_provider import OpenAIEmbeddingProvider

                return OpenAIEmbeddingProvider()

            elif provider_type == "kure-v1":
                from .local_provider import LocalEmbeddingProvider

                return LocalEmbeddingProvider()

            elif provider_type == "bge-m3":
                from .local_provider import BGEM3EmbeddingProvider

                return BGEM3EmbeddingProvider()

            else:
                logger.error(
                    f"[EmbeddingFactory] Unknown provider: {provider_type}. "
                    f"Supported: {list(cls.SUPPORTED_PROVIDERS.keys())}"
                )
                return None

        except ImportError as e:
            logger.error(f"[EmbeddingFactory] Import error for {provider_type}: {e}")
            return None
        except Exception as e:
            logger.error(f"[EmbeddingFactory] Failed to create {provider_type}: {e}")
            return None

    @classmethod
    def get_dimensions(cls, provider_type: Optional[str] = None) -> int:
        """
        임베딩 차원 수 반환.

        Args:
            provider_type: 프로바이더 타입 (미지정 시 자동 감지)

        Returns:
            임베딩 차원 수 (기본값: 1024)
        """
        if provider_type is None:
            provider_type = cls._detect_provider_type()

        if provider_type and provider_type in cls.SUPPORTED_PROVIDERS:
            return cls.SUPPORTED_PROVIDERS[provider_type]["dimensions"]

        return 1024  # 기본값

    @classmethod
    def reset_all(cls) -> None:
        """모든 프로바이더 리셋 (테스트용)."""
        global _providers
        _providers = {}
        logger.debug("[EmbeddingFactory] All providers reset")


# 편의 함수
def get_embedding_provider(
    provider_type: Optional[str] = None,
) -> Optional[BaseEmbeddingProvider]:
    """
    임베딩 프로바이더 반환.

    Args:
        provider_type: 프로바이더 타입 (openai, kure-v1, bge-m3)

    Returns:
        EmbeddingProvider 인스턴스 또는 None
    """
    return EmbeddingProviderFactory.get_provider(provider_type)


def get_embedding_dimensions(provider_type: Optional[str] = None) -> int:
    """
    임베딩 차원 수 반환.

    Args:
        provider_type: 프로바이더 타입

    Returns:
        임베딩 차원 수
    """
    return EmbeddingProviderFactory.get_dimensions(provider_type)


def reset_embedding_providers() -> None:
    """모든 프로바이더 리셋 (테스트용)."""
    EmbeddingProviderFactory.reset_all()
