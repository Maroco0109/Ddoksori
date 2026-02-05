"""
로컬 임베딩 프로바이더 (HTTP API 호출).

KURE-v1 및 BGE-M3 서버를 지원.
"""

import logging
import os
from typing import Dict, List, Optional

import requests

from .provider import (
    BaseEmbeddingProvider,
    BatchEmbeddingResult,
    EmbeddingResult,
)

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """
    로컬 임베딩 서버 프로바이더 (KURE-v1).

    HTTP API를 통해 로컬 임베딩 서버와 통신.
    기본 포트: 9001

    Usage:
        provider = LocalEmbeddingProvider()
        result = provider.embed("검색 쿼리")
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        model_name: str = "kure-v1",
        dimensions: int = 1024,
        timeout: float = 30.0,
    ):
        """
        로컬 임베딩 프로바이더 초기화.

        Args:
            api_url: 임베딩 서버 URL (기본: http://localhost:9001/embed)
            model_name: 모델 이름 (로깅용)
            dimensions: 임베딩 차원
            timeout: 요청 타임아웃 (초)
        """
        super().__init__(model_name, dimensions)

        self._api_url = api_url or os.getenv(
            "EMBEDDING_API_URL", "http://localhost:9001/embed"
        )
        self._timeout = timeout

    def embed(self, text: str) -> EmbeddingResult:
        """
        단일 텍스트 임베딩.

        Args:
            text: 임베딩할 텍스트

        Returns:
            EmbeddingResult: 임베딩 결과
        """
        if not text or not text.strip():
            raise ValueError("text가 비어있습니다.")

        try:
            response = requests.post(
                self._api_url,
                json={"text": text},
                timeout=self._timeout,
            )
            response.raise_for_status()

            data = response.json()
            embedding = data.get("embedding", [])

            return EmbeddingResult(
                dense=embedding,
                model=self._model_name,
                dimensions=len(embedding),
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"[LocalEmbedding] API 호출 실패: {e}")
            raise

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
        if not texts:
            return BatchEmbeddingResult(
                dense=[],
                model=self._model_name,
                dimensions=self._dimensions,
            )

        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_num = i // batch_size + 1

            try:
                response = requests.post(
                    self._api_url,
                    json={"texts": batch},
                    timeout=self._timeout,
                )
                response.raise_for_status()

                data = response.json()
                embeddings = data.get("embeddings", [])
                all_embeddings.extend(embeddings)

                logger.debug(
                    f"[LocalEmbedding] Batch {batch_num}/{total_batches}: "
                    f"{len(batch)} texts"
                )

            except requests.exceptions.RequestException as e:
                logger.error(f"[LocalEmbedding] Batch {batch_num} 실패: {e}")
                raise

        return BatchEmbeddingResult(
            dense=all_embeddings,
            model=self._model_name,
            dimensions=self._dimensions if all_embeddings else 0,
        )


class BGEM3EmbeddingProvider(BaseEmbeddingProvider):
    """
    BGE-M3 임베딩 프로바이더.

    Dense (1024D) + Sparse 임베딩 지원.
    기본 포트: 9003

    Usage:
        provider = BGEM3EmbeddingProvider()
        result = provider.embed("검색 쿼리")  # dense + sparse
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        BGE-M3 임베딩 프로바이더 초기화.

        Args:
            api_url: 임베딩 서버 URL (기본: http://localhost:9003/embed)
            timeout: 요청 타임아웃 (초)
        """
        super().__init__("bge-m3", 1024)

        self._api_url = api_url or os.getenv(
            "BGE_M3_API_URL", "http://localhost:9003/embed"
        )
        self._timeout = timeout

    @property
    def supports_sparse(self) -> bool:
        """BGE-M3는 Sparse 임베딩 지원."""
        return True

    def embed(
        self,
        text: str,
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> EmbeddingResult:
        """
        단일 텍스트 임베딩 (Dense + Sparse).

        Args:
            text: 임베딩할 텍스트
            return_dense: Dense 임베딩 반환 여부
            return_sparse: Sparse 임베딩 반환 여부

        Returns:
            EmbeddingResult: 임베딩 결과
        """
        if not text or not text.strip():
            raise ValueError("text가 비어있습니다.")

        try:
            response = requests.post(
                self._api_url,
                json={
                    "text": text,
                    "return_dense": return_dense,
                    "return_sparse": return_sparse,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()

            data = response.json()
            dense = data.get("dense_embedding", [])
            sparse = data.get("sparse_embedding")

            return EmbeddingResult(
                dense=dense,
                sparse=sparse,
                model=self._model_name,
                dimensions=len(dense) if dense else self._dimensions,
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"[BGEM3Embedding] API 호출 실패: {e}")
            raise

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> BatchEmbeddingResult:
        """
        배치 텍스트 임베딩 (Dense + Sparse).

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 배치 크기
            return_dense: Dense 임베딩 반환 여부
            return_sparse: Sparse 임베딩 반환 여부

        Returns:
            BatchEmbeddingResult: 배치 임베딩 결과
        """
        if not texts:
            return BatchEmbeddingResult(
                dense=[],
                sparse=[],
                model=self._model_name,
                dimensions=self._dimensions,
            )

        all_dense = []
        all_sparse = [] if return_sparse else None
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_num = i // batch_size + 1

            try:
                response = requests.post(
                    self._api_url,
                    json={
                        "texts": batch,
                        "return_dense": return_dense,
                        "return_sparse": return_sparse,
                    },
                    timeout=self._timeout,
                )
                response.raise_for_status()

                data = response.json()

                if return_dense:
                    dense = data.get("dense_embeddings", [])
                    all_dense.extend(dense)

                if return_sparse:
                    sparse = data.get("sparse_embeddings", [])
                    all_sparse.extend(sparse)

                logger.debug(
                    f"[BGEM3Embedding] Batch {batch_num}/{total_batches}: "
                    f"{len(batch)} texts"
                )

            except requests.exceptions.RequestException as e:
                logger.error(f"[BGEM3Embedding] Batch {batch_num} 실패: {e}")
                raise

        return BatchEmbeddingResult(
            dense=all_dense,
            sparse=all_sparse,
            model=self._model_name,
            dimensions=self._dimensions,
        )

    def embed_dense_only(self, text: str) -> List[float]:
        """Dense 임베딩만 반환 (검색용)."""
        result = self.embed(text, return_dense=True, return_sparse=False)
        return result.dense

    def embed_sparse_only(self, text: str) -> Dict[str, float]:
        """Sparse 임베딩만 반환."""
        result = self.embed(text, return_dense=False, return_sparse=True)
        return result.sparse or {}
