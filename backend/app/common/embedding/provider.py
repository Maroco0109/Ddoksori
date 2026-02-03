"""
EmbeddingProvider Protocol - 통합 임베딩 프로바이더 인터페이스

모든 임베딩 클라이언트가 구현해야 하는 공통 인터페이스.

지원 프로바이더:
- OpenAI (text-embedding-3-large): 1536차원
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """임베딩 결과 데이터 클래스."""

    dense: List[float]
    """Dense 임베딩 벡터."""

    sparse: Optional[Dict[str, float]] = None
    """Sparse 임베딩 벡터 (BGE-M3 전용). {token_id: weight}"""

    model: str = ""
    """사용된 모델 이름."""

    dimensions: int = 0
    """Dense 벡터 차원 수."""


@dataclass
class BatchEmbeddingResult:
    """배치 임베딩 결과 데이터 클래스."""

    dense: List[List[float]]
    """Dense 임베딩 벡터 리스트."""

    sparse: Optional[List[Dict[str, float]]] = None
    """Sparse 임베딩 벡터 리스트 (BGE-M3 전용)."""

    model: str = ""
    """사용된 모델 이름."""

    dimensions: int = 0
    """Dense 벡터 차원 수."""

    tokens_used: int = 0
    """사용된 토큰 수 (OpenAI 전용)."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    임베딩 프로바이더 프로토콜.

    모든 임베딩 클라이언트가 구현해야 하는 인터페이스.
    """

    @property
    def model_name(self) -> str:
        """모델 이름 반환."""
        ...

    @property
    def dimensions(self) -> int:
        """임베딩 차원 수 반환."""
        ...

    @property
    def supports_sparse(self) -> bool:
        """Sparse 임베딩 지원 여부."""
        ...

    def embed(self, text: str) -> EmbeddingResult:
        """
        단일 텍스트 임베딩.

        Args:
            text: 임베딩할 텍스트

        Returns:
            EmbeddingResult: 임베딩 결과
        """
        ...

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> BatchEmbeddingResult:
        """
        배치 텍스트 임베딩.

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 배치 크기

        Returns:
            BatchEmbeddingResult: 배치 임베딩 결과
        """
        ...

    def embed_query(self, query: str) -> List[float]:
        """
        쿼리 임베딩 (검색용).

        embed()와 동일하지만 dense 벡터만 반환.

        Args:
            query: 검색 쿼리

        Returns:
            Dense 임베딩 벡터
        """
        ...


class BaseEmbeddingProvider(ABC):
    """
    임베딩 프로바이더 기본 클래스.

    공통 로직을 구현하고 구체적인 임베딩 로직은 서브클래스에 위임.
    """

    def __init__(self, model_name: str, dimensions: int):
        self._model_name = model_name
        self._dimensions = dimensions
        logger.info(f"[EmbeddingProvider] Initialized: {model_name} ({dimensions}D)")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def supports_sparse(self) -> bool:
        """기본값: Sparse 미지원."""
        return False

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 (기본 구현: embed() 호출)."""
        if not query or not query.strip():
            raise ValueError("query가 비어있습니다.")
        result = self.embed(query)
        return result.dense

    @abstractmethod
    def embed(self, text: str) -> EmbeddingResult:
        """단일 텍스트 임베딩 (서브클래스 구현 필수)."""
        ...

    @abstractmethod
    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> BatchEmbeddingResult:
        """배치 텍스트 임베딩 (서브클래스 구현 필수)."""
        ...
