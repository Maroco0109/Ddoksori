"""
S2-PR3: Redis 기반 답변 캐싱
"""

import hashlib
import json
import logging
import os
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AnswerCache:
    """
    Redis 기반 답변 캐시
    
    유사한 질문에 대해 캐시된 답변을 반환하여 LLM API 비용 절감.
    Redis 연결 실패 시 graceful degradation (캐시 없이 동작).
    """
    
    def __init__(self):
        self.enabled = os.getenv('ENABLE_ANSWER_CACHE', 'false').lower() == 'true'
        self.ttl = int(os.getenv('ANSWER_CACHE_TTL_HOURS', '24')) * 3600
        self._redis = None
        self._hit_count = 0
        self._miss_count = 0
        self._error_count = 0
        
        if self.enabled:
            self._init_redis()
    
    def _init_redis(self) -> None:
        try:
            import redis
            self._redis = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                db=int(os.getenv('REDIS_DB', '0')),
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            logger.info("[AnswerCache] Redis connection established")
        except ImportError:
            logger.warning("[AnswerCache] redis package not installed, caching disabled")
            self.enabled = False
            self._redis = None
        except Exception as e:
            logger.warning(f"[AnswerCache] Redis connection failed: {e}, caching disabled")
            self.enabled = False
            self._redis = None
    
    def _generate_cache_key(self, query: str, query_type: str) -> str:
        normalized = query.lower().strip()
        hash_input = f"{query_type}:{normalized}"
        return f"answer_cache:{hashlib.sha256(hash_input.encode()).hexdigest()[:16]}"
    
    def get(self, query: str, query_type: str) -> Optional[Dict]:
        if not self.enabled or not self._redis:
            return None
        
        try:
            key = self._generate_cache_key(query, query_type)
            cached = self._redis.get(key)
            
            if cached:
                self._hit_count += 1
                logger.debug(f"[AnswerCache] Cache HIT: {key}")
                return json.loads(cached)
            
            self._miss_count += 1
            logger.debug(f"[AnswerCache] Cache MISS: {key}")
            return None
            
        except Exception as e:
            self._error_count += 1
            logger.warning(f"[AnswerCache] Redis get error: {e}")
            return None
    
    def set(self, query: str, query_type: str, answer_data: Dict) -> bool:
        if not self.enabled or not self._redis:
            return False
        
        try:
            key = self._generate_cache_key(query, query_type)
            serialized = json.dumps(answer_data, ensure_ascii=False)
            self._redis.setex(key, self.ttl, serialized)
            logger.debug(f"[AnswerCache] Cache SET: {key}, TTL={self.ttl}s")
            return True
            
        except Exception as e:
            self._error_count += 1
            logger.warning(f"[AnswerCache] Redis set error: {e}")
            return False
    
    def invalidate(self, query: str, query_type: str) -> bool:
        if not self.enabled or not self._redis:
            return False
        
        try:
            key = self._generate_cache_key(query, query_type)
            deleted = self._redis.delete(key)
            logger.debug(f"[AnswerCache] Cache INVALIDATE: {key}, deleted={deleted}")
            return deleted > 0
        except Exception as e:
            self._error_count += 1
            logger.warning(f"[AnswerCache] Redis delete error: {e}")
            return False
    
    def clear_all(self) -> int:
        if not self.enabled or not self._redis:
            return 0
        
        try:
            pattern = "answer_cache:*"
            keys = list(self._redis.scan_iter(match=pattern))
            if keys:
                deleted = self._redis.delete(*keys)
                logger.info(f"[AnswerCache] Cleared {deleted} cache entries")
                return deleted
            return 0
        except Exception as e:
            self._error_count += 1
            logger.warning(f"[AnswerCache] Redis clear error: {e}")
            return 0
    
    def get_metrics(self) -> Dict[str, Any]:
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0.0
        
        return {
            'enabled': self.enabled,
            'connected': self._redis is not None,
            'hit_count': self._hit_count,
            'miss_count': self._miss_count,
            'error_count': self._error_count,
            'hit_rate': round(hit_rate, 4),
            'ttl_hours': self.ttl // 3600,
        }
    
    def reset_metrics(self) -> None:
        self._hit_count = 0
        self._miss_count = 0
        self._error_count = 0


_cache_instance: Optional[AnswerCache] = None


def get_answer_cache() -> AnswerCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = AnswerCache()
    return _cache_instance


def reset_cache_instance() -> None:
    global _cache_instance
    _cache_instance = None
