"""
OpenAI text-embedding-3-large 클라이언트

- 차원: 1536 고정 (Matryoshka embedding)
- 94.8% Recall@10 성능
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 1536


class EmbeddingClient:
    """
    OpenAI text-embedding-3-large 클라이언트

    Matryoshka 임베딩을 사용하여 1536차원으로 고정.
    - 94.8% Recall@10 (512의 91.2%보다 높음)
    - 쿼리 속도 2배 빠름 (3072 대비)
    - 저장 공간 50% 절감 (3072 대비)

    Usage:
        client = EmbeddingClient()
        embedding = client.embed_query("검색 쿼리")
        embeddings = client.embed(["텍스트1", "텍스트2"])
    """

    def __init__(self):
        """OpenAI 클라이언트 초기화"""
        try:
            from openai import OpenAI

            self.client = OpenAI()
        except ImportError:
            raise ImportError(
                "openai 패키지가 필요합니다. pip install openai 명령어로 설치하세요."
            )

        self.model = "text-embedding-3-large"
        self.dimensions = EMBEDDING_DIMENSIONS

        logger.info(
            f"[EmbeddingClient] Initialized with model={self.model}, "
            f"dimensions={self.dimensions}"
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        텍스트 리스트를 임베딩 벡터로 변환

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            임베딩 벡터 리스트 (각 벡터는 1536차원)

        Raises:
            ValueError: 빈 텍스트 리스트가 입력된 경우
            Exception: OpenAI API 호출 실패 시
        """
        if not texts:
            raise ValueError("texts 리스트가 비어있습니다.")

        cleaned_texts = [t.strip() if t else "" for t in texts]
        processed_texts = [t if t else " " for t in cleaned_texts]

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=processed_texts,
                dimensions=self.dimensions,
            )

            embeddings = [r.embedding for r in response.data]

            logger.debug(
                f"[EmbeddingClient] Generated {len(embeddings)} embeddings, "
                f"tokens_used={response.usage.total_tokens}"
            )

            return embeddings

        except Exception as e:
            logger.error(f"[EmbeddingClient] API 호출 실패: {e}")
            raise

    def embed_query(self, query: str) -> List[float]:
        """
        단일 쿼리를 임베딩 벡터로 변환

        Args:
            query: 임베딩할 쿼리 문자열

        Returns:
            임베딩 벡터 (1536차원)
        """
        if not query or not query.strip():
            raise ValueError("query가 비어있습니다.")

        return self.embed([query])[0]

    def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        대량 텍스트를 배치 처리하여 임베딩

        OpenAI API는 한 번에 최대 2048개 텍스트를 처리할 수 있지만,
        메모리 및 속도 최적화를 위해 배치 크기를 조절합니다.

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 배치 크기 (기본: 100)

        Returns:
            임베딩 벡터 리스트
        """
        if not texts:
            return []

        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_num = i // batch_size + 1

            logger.info(
                f"[EmbeddingClient] Processing batch {batch_num}/{total_batches} "
                f"({len(batch)} texts)"
            )

            embeddings = self.embed(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings


class EmbeddingAdapter:
    """
    임베딩 모델 어댑터 (OpenAI text-embedding-3-large)

    Usage:
        adapter = EmbeddingAdapter()
        embedding = adapter.embed_query("검색 쿼리")
    """

    def __init__(self):
        """어댑터 초기화"""
        self.dimensions = EMBEDDING_DIMENSIONS
        self.client = EmbeddingClient()
        logger.info(
            f"[EmbeddingAdapter] Using OpenAI embeddings "
            f"(dimensions={self.dimensions})"
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        텍스트 리스트를 임베딩 벡터로 변환

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            임베딩 벡터 리스트 (각 벡터는 1536차원)
        """
        return self.client.embed(texts)

    def embed_query(self, query: str) -> List[float]:
        """
        단일 쿼리를 임베딩 벡터로 변환

        Args:
            query: 임베딩할 쿼리 문자열

        Returns:
            임베딩 벡터 (1536차원)
        """
        return self.client.embed_query(query)

    def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        대량 텍스트를 배치 처리하여 임베딩

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 배치 크기 (기본: 100)

        Returns:
            임베딩 벡터 리스트
        """
        return self.client.embed_batch(texts, batch_size)


def get_embedding_dimensions() -> int:
    """
    현재 설정된 임베딩 차원 반환

    Returns:
        1536 (고정값)
    """
    return EMBEDDING_DIMENSIONS
