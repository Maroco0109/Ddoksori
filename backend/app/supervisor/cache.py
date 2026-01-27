"""
PR-6: Supervisor 레벨 캐싱

L1: 전체 응답 캐싱 (session-aware)
L2: Query Analysis 캐싱 (session-agnostic)
"""

import hashlib
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Redis 연결은 기존 cache.py의 패턴 재사용
_redis_client = None


def _get_redis():
    """Redis 클라이언트 lazy initialization"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    import os
    if os.getenv('ENABLE_ANSWER_CACHE', 'false').lower() != 'true':
        return None

    try:
        import redis
        _redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', '6379')),
            db=int(os.getenv('REDIS_DB', '0')),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        logger.info("[SupervisorCache] Redis connection established")
        return _redis_client
    except Exception as e:
        logger.warning(f"[SupervisorCache] Redis unavailable: {e}")
        _redis_client = None
        return None


def _normalize_query(query: str) -> str:
    """쿼리 정규화 (대소문자, 공백, 문장부호)"""
    import re
    normalized = query.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'[?!.,。？！，．]$', '', normalized)
    return normalized


def _hash_query(query: str) -> str:
    """쿼리 해시 생성"""
    return hashlib.sha256(query.encode()).hexdigest()[:16]


# ============================================================
# L1: Supervisor 전체 응답 캐시
# ============================================================

class SupervisorResponseCache:
    """
    L1 캐시: 전체 Supervisor 응답

    동일한 쿼리에 대해 전체 파이프라인을 건너뛰고 즉시 응답.
    세션별로 분리하여 컨텍스트 무결성 유지.
    """

    PREFIX = "supervisor_response"
    TTL_SECONDS = 3600  # 1시간

    @classmethod
    def get(cls, query: str, session_id: Optional[str] = None) -> Optional[Dict]:
        """캐시된 전체 응답 조회"""
        redis = _get_redis()
        if not redis:
            return None

        try:
            normalized = _normalize_query(query)
            session_part = _hash_query(session_id)[:8] if session_id else "default"
            key = f"{cls.PREFIX}:{_hash_query(normalized)}:{session_part}"

            cached = redis.get(key)
            if cached:
                logger.debug(f"[L1 Cache] HIT: {key}")
                return json.loads(cached)

            logger.debug(f"[L1 Cache] MISS: {key}")
            return None

        except Exception as e:
            logger.warning(f"[L1 Cache] Get error: {e}")
            return None

    @classmethod
    def set(cls, query: str, response: Dict, session_id: Optional[str] = None) -> bool:
        """전체 응답 캐싱"""
        redis = _get_redis()
        if not redis:
            return False

        try:
            normalized = _normalize_query(query)
            session_part = _hash_query(session_id)[:8] if session_id else "default"
            key = f"{cls.PREFIX}:{_hash_query(normalized)}:{session_part}"

            # 캐싱할 필드만 선택 (messages 제외 - 너무 큼)
            cacheable = {
                'final_answer': response.get('final_answer'),
                'mode': response.get('mode'),
                'query_type': response.get('query_analysis', {}).get('query_type'),
                'citations': response.get('citations', []),
                '_cached_at': __import__('time').time(),
            }

            redis.setex(key, cls.TTL_SECONDS, json.dumps(cacheable, ensure_ascii=False))
            logger.debug(f"[L1 Cache] SET: {key}")
            return True

        except Exception as e:
            logger.warning(f"[L1 Cache] Set error: {e}")
            return False


# ============================================================
# L2: Query Analysis 캐시
# ============================================================

class QueryAnalysisCache:
    """
    L2 캐시: Query Analysis 결과

    동일한 쿼리에 대한 의도 분류, 키워드, retriever_types를 재사용.
    세션 무관하게 캐싱 (쿼리 자체의 특성이므로).
    """

    PREFIX = "query_analysis"
    TTL_SECONDS = 86400  # 24시간

    @classmethod
    def get(cls, query: str) -> Optional[Dict]:
        """캐시된 Query Analysis 조회"""
        redis = _get_redis()
        if not redis:
            return None

        try:
            normalized = _normalize_query(query)
            key = f"{cls.PREFIX}:{_hash_query(normalized)}"

            cached = redis.get(key)
            if cached:
                logger.debug(f"[L2 Cache] HIT: {key}")
                return json.loads(cached)

            logger.debug(f"[L2 Cache] MISS: {key}")
            return None

        except Exception as e:
            logger.warning(f"[L2 Cache] Get error: {e}")
            return None

    @classmethod
    def set(cls, query: str, analysis: Dict) -> bool:
        """Query Analysis 캐싱"""
        redis = _get_redis()
        if not redis:
            return False

        try:
            normalized = _normalize_query(query)
            key = f"{cls.PREFIX}:{_hash_query(normalized)}"

            # 캐싱할 필드
            cacheable = {
                'mode': analysis.get('mode'),
                'query_type': analysis.get('query_type'),
                'domain': analysis.get('domain'),
                'keywords': analysis.get('keywords', []),
                'retriever_types': analysis.get('retriever_types', []),
                'search_priority': analysis.get('search_priority'),
                '_cached_at': __import__('time').time(),
            }

            redis.setex(key, cls.TTL_SECONDS, json.dumps(cacheable, ensure_ascii=False))
            logger.debug(f"[L2 Cache] SET: {key}")
            return True

        except Exception as e:
            logger.warning(f"[L2 Cache] Set error: {e}")
            return False


# ============================================================
# 캐시 관리 유틸리티
# ============================================================

def clear_all_supervisor_caches() -> Dict[str, int]:
    """모든 Supervisor 캐시 삭제 (관리용)"""
    redis = _get_redis()
    if not redis:
        return {'error': 'Redis unavailable'}

    results = {}

    try:
        # L1 삭제
        l1_keys = list(redis.scan_iter(match=f"{SupervisorResponseCache.PREFIX}:*"))
        if l1_keys:
            results['l1_deleted'] = redis.delete(*l1_keys)
        else:
            results['l1_deleted'] = 0

        # L2 삭제
        l2_keys = list(redis.scan_iter(match=f"{QueryAnalysisCache.PREFIX}:*"))
        if l2_keys:
            results['l2_deleted'] = redis.delete(*l2_keys)
        else:
            results['l2_deleted'] = 0

        logger.info(f"[SupervisorCache] Cleared: {results}")
        return results

    except Exception as e:
        logger.warning(f"[SupervisorCache] Clear error: {e}")
        return {'error': str(e)}


def get_cache_stats() -> Dict[str, Any]:
    """캐시 통계 조회 (모니터링용)"""
    redis = _get_redis()
    if not redis:
        return {'enabled': False, 'error': 'Redis unavailable'}

    try:
        l1_count = sum(1 for _ in redis.scan_iter(match=f"{SupervisorResponseCache.PREFIX}:*"))
        l2_count = sum(1 for _ in redis.scan_iter(match=f"{QueryAnalysisCache.PREFIX}:*"))
        l3_count = sum(1 for _ in redis.scan_iter(match="answer_cache:*"))

        return {
            'enabled': True,
            'l1_supervisor_count': l1_count,
            'l2_query_analysis_count': l2_count,
            'l3_answer_count': l3_count,
            'total': l1_count + l2_count + l3_count,
        }
    except Exception as e:
        return {'enabled': True, 'error': str(e)}
