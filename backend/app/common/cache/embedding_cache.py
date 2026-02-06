"""
EmbeddingCache - 임베딩 벡터 Redis 캐시

OpenAI text-embedding API 호출 결과를 캐싱하여 비용 절감 및 응답 시간 단축.
BaseRedisCache를 상속하며, 모델명을 캐시 키에 포함하여 모델 변경 시 자동 무효화.

사용법:
    from app.common.cache import EmbeddingCache

    cache = EmbeddingCache()
    embedding = cache.get_embedding("검색 쿼리", "text-embedding-3-large")
    if embedding is None:
        embedding = openai_client.embeddings.create(...)
        cache.set_embedding("검색 쿼리", "text-embedding-3-large", embedding)
"""

import json
import logging
import os
from typing import ClassVar, List, Optional

from app.common.cache.base import BaseRedisCache, hash_query, normalize_query

logger = logging.getLogger(__name__)

# Embedding-specific Redis client (singleton, independent of ENABLE_ANSWER_CACHE)
_embedding_redis_client = None
_embedding_redis_init_attempted = False


class EmbeddingCache(BaseRedisCache):
    """
    임베딩 벡터 Redis 캐시.

    - PREFIX: "emb:"
    - TTL: 7일 (604800초)
    - 키: emb:{hash(model_name + normalized_text)}
    - 값: List[float] (JSON 직렬화)
    - 독립적인 Redis 연결: ENABLE_ANSWER_CACHE와 무관하게 ENABLE_EMBEDDING_CACHE로 제어
    """

    PREFIX: ClassVar[str] = "emb"
    TTL_SECONDS: ClassVar[int] = 86400 * 7  # 7일

    @classmethod
    def _is_enabled(cls) -> bool:
        """임베딩 캐시 활성화 여부 확인."""
        return os.getenv("ENABLE_EMBEDDING_CACHE", "false").lower() == "true"

    @classmethod
    def _get_redis(cls):
        """
        임베딩 전용 Redis 클라이언트 조회.

        ENABLE_ANSWER_CACHE와 독립적으로 ENABLE_EMBEDDING_CACHE 환경변수로 제어.
        """
        global _embedding_redis_client, _embedding_redis_init_attempted

        if _embedding_redis_client is not None:
            return _embedding_redis_client

        if _embedding_redis_init_attempted:
            return None

        _embedding_redis_init_attempted = True

        if not cls._is_enabled():
            logger.debug("[EmbeddingCache] Disabled (ENABLE_EMBEDDING_CACHE != true)")
            return None

        try:
            import redis

            _embedding_redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_DB", "0")),
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            _embedding_redis_client.ping()
            logger.info("[EmbeddingCache] Redis connection established")
            return _embedding_redis_client
        except ImportError:
            logger.warning("[EmbeddingCache] redis package not installed")
            return None
        except Exception as e:
            logger.warning(f"[EmbeddingCache] Redis connection failed: {e}")
            _embedding_redis_client = None
            return None

    @classmethod
    def _build_embedding_key(cls, text: str, model: str) -> str:
        """
        임베딩 캐시 키 생성.

        모델명을 포함하여 모델 변경 시 자동 무효화.
        """
        normalized = normalize_query(text)
        combined = f"{model}:{normalized}"
        key_hash = hash_query(combined, length=32)
        return f"{cls.PREFIX}:{key_hash}"

    @classmethod
    def get_embedding(cls, text: str, model: str) -> Optional[List[float]]:
        """
        캐시에서 임베딩 벡터 조회.

        Args:
            text: 임베딩할 텍스트
            model: 임베딩 모델명 (예: "text-embedding-3-large")

        Returns:
            캐시된 임베딩 벡터 또는 None (캐시 미스/비활성화/에러)
        """
        if not cls._is_enabled():
            return None

        redis = cls._get_redis()
        if not redis:
            return None

        try:
            cache_key = cls._build_embedding_key(text, model)
            cached = redis.get(cache_key)

            if cached:
                cls._hit_count += 1
                logger.debug(f"[{cls.PREFIX}] HIT: {cache_key[:30]}...")
                return json.loads(cached)

            cls._miss_count += 1
            logger.debug(f"[{cls.PREFIX}] MISS: {cache_key[:30]}...")
            return None

        except Exception as e:
            cls._error_count += 1
            logger.warning(f"[{cls.PREFIX}] Get error: {e}")
            return None

    @classmethod
    def set_embedding(cls, text: str, model: str, embedding: List[float]) -> bool:
        """
        임베딩 벡터를 캐시에 저장.

        Args:
            text: 임베딩한 텍스트
            model: 임베딩 모델명
            embedding: 임베딩 벡터 (List[float])

        Returns:
            저장 성공 여부
        """
        if not cls._is_enabled():
            return False

        redis = cls._get_redis()
        if not redis:
            return False

        try:
            cache_key = cls._build_embedding_key(text, model)
            serialized = json.dumps(embedding)
            redis.setex(cache_key, cls.TTL_SECONDS, serialized)
            logger.debug(
                f"[{cls.PREFIX}] SET: {cache_key[:30]}... "
                f"(dim={len(embedding)}, TTL={cls.TTL_SECONDS}s)"
            )
            return True

        except Exception as e:
            cls._error_count += 1
            logger.warning(f"[{cls.PREFIX}] Set error: {e}")
            return False
