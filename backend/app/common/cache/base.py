"""
BaseRedisCache - 통합 Redis 캐시 기본 클래스

모든 Redis 기반 캐시 구현이 상속하는 base class.
공통 기능: Redis 연결, 쿼리 정규화, 해시 생성, get/set/delete/clear.
"""

import hashlib
import json
import logging
import os
import re
import time
from abc import ABC
from typing import Any, ClassVar, Dict, Optional

logger = logging.getLogger(__name__)

# Global Redis client (singleton)
_redis_client = None
_redis_init_attempted = False


def get_redis_client():
    """
    Redis 클라이언트 lazy initialization (singleton).

    환경변수:
    - ENABLE_ANSWER_CACHE: 'true'로 설정 시 캐싱 활성화
    - REDIS_HOST: Redis 호스트 (기본: localhost)
    - REDIS_PORT: Redis 포트 (기본: 6379)
    - REDIS_DB: Redis DB 번호 (기본: 0)
    """
    global _redis_client, _redis_init_attempted

    if _redis_client is not None:
        return _redis_client

    if _redis_init_attempted:
        return None

    _redis_init_attempted = True

    if os.getenv("ENABLE_ANSWER_CACHE", "false").lower() != "true":
        logger.debug("[Redis] Caching disabled (ENABLE_ANSWER_CACHE != true)")
        return None

    try:
        import redis

        _redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        logger.info("[Redis] Connection established")
        return _redis_client
    except ImportError:
        logger.warning("[Redis] redis package not installed")
        return None
    except Exception as e:
        logger.warning(f"[Redis] Connection failed: {e}")
        _redis_client = None
        return None


def reset_redis_client() -> None:
    """Redis 클라이언트 리셋 (테스트용)."""
    global _redis_client, _redis_init_attempted
    _redis_client = None
    _redis_init_attempted = False


def normalize_query(query: str) -> str:
    """
    쿼리 정규화.

    - 소문자 변환
    - 앞뒤 공백 제거
    - 연속 공백을 단일 공백으로
    - 끝 문장부호 제거
    """
    normalized = query.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[?!.,。？！，．]$", "", normalized)
    return normalized


def hash_query(query: str, length: int = 16) -> str:
    """쿼리 해시 생성 (SHA256, 지정 길이로 truncate)."""
    return hashlib.sha256(query.encode()).hexdigest()[:length]


class BaseRedisCache(ABC):
    """
    Redis 캐시 기본 클래스.

    서브클래스에서 반드시 정의해야 하는 클래스 변수:
    - PREFIX: 캐시 키 prefix (예: "supervisor_response")
    - TTL_SECONDS: TTL 초 단위 (예: 3600)

    선택적으로 오버라이드 가능한 메서드:
    - _build_cache_key(): 캐시 키 생성 로직
    - _serialize(): 저장 전 직렬화
    - _deserialize(): 조회 후 역직렬화
    - _select_cacheable_fields(): 캐싱할 필드 선택
    """

    PREFIX: ClassVar[str] = ""
    TTL_SECONDS: ClassVar[int] = 3600

    # 메트릭 (클래스별 독립)
    _hit_count: ClassVar[int] = 0
    _miss_count: ClassVar[int] = 0
    _error_count: ClassVar[int] = 0

    @classmethod
    def _get_redis(cls):
        """Redis 클라이언트 조회."""
        return get_redis_client()

    @classmethod
    def _build_cache_key(cls, key: str, session_id: Optional[str] = None) -> str:
        """
        캐시 키 생성.

        기본 형식: {PREFIX}:{key_hash}
        세션 있을 경우: {PREFIX}:{key_hash}:{session_hash}
        """
        normalized = normalize_query(key)
        key_hash = hash_query(normalized)

        if session_id:
            session_hash = hash_query(session_id, length=8)
            return f"{cls.PREFIX}:{key_hash}:{session_hash}"

        return f"{cls.PREFIX}:{key_hash}"

    @classmethod
    def _serialize(cls, data: Dict[str, Any]) -> str:
        """데이터 직렬화 (JSON)."""
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def _deserialize(cls, data: str) -> Dict[str, Any]:
        """데이터 역직렬화 (JSON)."""
        return json.loads(data)

    @classmethod
    def _select_cacheable_fields(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        캐싱할 필드 선택.

        서브클래스에서 오버라이드하여 특정 필드만 캐싱.
        기본값: 전체 데이터 + 캐싱 타임스탬프.
        """
        result = dict(data)
        result["_cached_at"] = time.time()
        return result

    @classmethod
    def get(
        cls, key: str, session_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        캐시 조회.

        Args:
            key: 캐시 키 (일반적으로 쿼리 문자열)
            session_id: 세션 ID (세션별 분리 캐싱 시)

        Returns:
            캐시된 데이터 또는 None
        """
        redis = cls._get_redis()
        if not redis:
            return None

        try:
            cache_key = cls._build_cache_key(key, session_id)
            cached = redis.get(cache_key)

            if cached:
                cls._hit_count += 1
                logger.debug(f"[{cls.PREFIX}] HIT: {cache_key}")
                result = cls._deserialize(cached)
                result["_from_cache"] = True
                return result

            cls._miss_count += 1
            logger.debug(f"[{cls.PREFIX}] MISS: {cache_key}")
            return None

        except Exception as e:
            cls._error_count += 1
            logger.warning(f"[{cls.PREFIX}] Get error: {e}")
            return None

    @classmethod
    def set(
        cls,
        key: str,
        data: Dict[str, Any],
        session_id: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        캐시 저장.

        Args:
            key: 캐시 키
            data: 저장할 데이터
            session_id: 세션 ID
            ttl: TTL 초 (None이면 클래스 기본값 사용)

        Returns:
            성공 여부
        """
        redis = cls._get_redis()
        if not redis:
            return False

        try:
            cache_key = cls._build_cache_key(key, session_id)
            cacheable = cls._select_cacheable_fields(data)
            serialized = cls._serialize(cacheable)

            effective_ttl = ttl if ttl is not None else cls.TTL_SECONDS
            redis.setex(cache_key, effective_ttl, serialized)

            logger.debug(f"[{cls.PREFIX}] SET: {cache_key}, TTL={effective_ttl}s")
            return True

        except Exception as e:
            cls._error_count += 1
            logger.warning(f"[{cls.PREFIX}] Set error: {e}")
            return False

    @classmethod
    def delete(cls, key: str, session_id: Optional[str] = None) -> bool:
        """
        캐시 삭제.

        Args:
            key: 캐시 키
            session_id: 세션 ID

        Returns:
            삭제 성공 여부 (키가 존재했는지)
        """
        redis = cls._get_redis()
        if not redis:
            return False

        try:
            cache_key = cls._build_cache_key(key, session_id)
            deleted = redis.delete(cache_key)
            logger.debug(f"[{cls.PREFIX}] DELETE: {cache_key}, deleted={deleted}")
            return deleted > 0

        except Exception as e:
            cls._error_count += 1
            logger.warning(f"[{cls.PREFIX}] Delete error: {e}")
            return False

    @classmethod
    def clear_all(cls) -> int:
        """
        해당 PREFIX의 모든 캐시 삭제.

        Returns:
            삭제된 키 개수
        """
        redis = cls._get_redis()
        if not redis:
            return 0

        try:
            pattern = f"{cls.PREFIX}:*"
            keys = list(redis.scan_iter(match=pattern))

            if keys:
                deleted = redis.delete(*keys)
                logger.info(f"[{cls.PREFIX}] Cleared {deleted} entries")
                return deleted

            return 0

        except Exception as e:
            cls._error_count += 1
            logger.warning(f"[{cls.PREFIX}] Clear error: {e}")
            return 0

    @classmethod
    def count(cls) -> int:
        """해당 PREFIX의 캐시 개수 조회."""
        redis = cls._get_redis()
        if not redis:
            return 0

        try:
            pattern = f"{cls.PREFIX}:*"
            return sum(1 for _ in redis.scan_iter(match=pattern))
        except Exception as e:
            logger.warning(f"[{cls.PREFIX}] Count error: {e}")
            return 0

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """캐시 메트릭 조회."""
        total = cls._hit_count + cls._miss_count
        hit_rate = cls._hit_count / total if total > 0 else 0.0

        return {
            "prefix": cls.PREFIX,
            "ttl_seconds": cls.TTL_SECONDS,
            "hit_count": cls._hit_count,
            "miss_count": cls._miss_count,
            "error_count": cls._error_count,
            "hit_rate": round(hit_rate, 4),
            "entry_count": cls.count(),
        }

    @classmethod
    def reset_metrics(cls) -> None:
        """메트릭 리셋."""
        cls._hit_count = 0
        cls._miss_count = 0
        cls._error_count = 0
