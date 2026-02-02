"""
OpenAI 임베딩 프로바이더.

text-embedding-3-large 모델 사용.
Matryoshka 임베딩으로 1536차원 고정.
"""

import logging
import os
from typing import List, Optional

from .provider import (
    BaseEmbeddingProvider,
    BatchEmbeddingResult,
    EmbeddingResult,
)

logger = logging.getLogger(__name__)

# 기본 차원 (Matryoshka 임베딩)
DEFAULT_DIMENSIONS = 1536


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """
    OpenAI text-embedding-3-large 임베딩 프로바이더.

    특징:
    - Matryoshka 임베딩으로 1536차원 고정
    - 94.8% Recall@10 (512차원의 91.2%보다 높음)
    - 쿼리 속도 2배 빠름 (3072차원 대비)
    - 저장 공간 50% 절감 (3072차원 대비)

    Usage:
        provider = OpenAIEmbeddingProvider()
        result = provider.embed("검색 쿼리")
        embeddings = provider.embed_batch(["텍스트1", "텍스트2"])
    """

    def __init__(
        self,
        model: str = "text-embedding-3-large",
        dimensions: int = DEFAULT_DIMENSIONS,
        api_key: Optional[str] = None,
    ):
        """
        OpenAI 임베딩 프로바이더 초기화.

        Args:
            model: 모델 이름 (기본: text-embedding-3-large)
            dimensions: 임베딩 차원 (기본: 1536)
            api_key: OpenAI API 키 (미설정 시 OPENAI_API_KEY 환경변수 사용)
        """
        super().__init__(model, dimensions)

        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=api_key or os.getenv("OPENAI_API_KEY"),
            )
        except ImportError:
            raise ImportError(
                "openai 패키지가 필요합니다. pip install openai 명령어로 설치하세요."
            )

        self._model = model
        self._target_dimensions = dimensions

    def embed(self, text: str) -> EmbeddingResult:
        """
        단일 텍스트 임베딩.

        Args:
            text: 임베딩할 텍스트

        Returns:
            EmbeddingResult: 임베딩 결과

        Raises:
            ValueError: 텍스트가 비어있는 경우
        """
        if not text or not text.strip():
            raise ValueError("text가 비어있습니다.")

        result = self.embed_batch([text], batch_size=1)
        return EmbeddingResult(
            dense=result.dense[0],
            model=result.model,
            dimensions=result.dimensions,
        )

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> BatchEmbeddingResult:
        """
        배치 텍스트 임베딩.

        OpenAI API는 한 번에 최대 2048개 텍스트를 처리할 수 있지만,
        메모리 및 속도 최적화를 위해 배치 크기를 조절합니다.

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 배치 크기 (기본: 100)

        Returns:
            BatchEmbeddingResult: 배치 임베딩 결과
        """
        if not texts:
            return BatchEmbeddingResult(
                dense=[],
                model=self._model,
                dimensions=self._target_dimensions,
                tokens_used=0,
            )

        # 빈 텍스트 처리
        cleaned_texts = [t.strip() if t else "" for t in texts]
        processed_texts = [t if t else " " for t in cleaned_texts]

        all_embeddings = []
        total_tokens = 0
        total_batches = (len(processed_texts) + batch_size - 1) // batch_size

        for i in range(0, len(processed_texts), batch_size):
            batch = processed_texts[i : i + batch_size]
            batch_num = i // batch_size + 1

            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                    dimensions=self._target_dimensions,
                )

                embeddings = [r.embedding for r in response.data]
                all_embeddings.extend(embeddings)
                total_tokens += response.usage.total_tokens

                logger.debug(
                    f"[OpenAIEmbedding] Batch {batch_num}/{total_batches}: "
                    f"{len(batch)} texts, {response.usage.total_tokens} tokens"
                )

            except Exception as e:
                logger.error(f"[OpenAIEmbedding] API 호출 실패: {e}")
                raise

        return BatchEmbeddingResult(
            dense=all_embeddings,
            model=self._model,
            dimensions=self._target_dimensions,
            tokens_used=total_tokens,
        )
