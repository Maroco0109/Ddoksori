"""
통합 캐시 프레임워크

모든 Redis 기반 캐시 구현을 위한 공통 base class와 유틸리티 제공.
"""

from app.common.cache.base import (
    BaseRedisCache,
    get_redis_client,
    normalize_query,
    hash_query,
)

__all__ = [
    "BaseRedisCache",
    "get_redis_client",
    "normalize_query",
    "hash_query",
]
