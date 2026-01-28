"""
PR-6: Supervisor 레벨 캐싱

BaseRedisCache를 상속하여 구현.

L1: 전체 응답 캐싱 (session-aware)
L2: Query Analysis 캐싱 (session-agnostic)
L3: Intent Classification 캐싱 (session-agnostic)
"""

import logging
from typing import Any, ClassVar, Dict, Optional

from app.common.cache import BaseRedisCache, get_redis_client, normalize_query, hash_query

# 하위호환: 기존 테스트에서 _normalize_query 사용
_normalize_query = normalize_query
_hash_query = hash_query

logger = logging.getLogger(__name__)


# ============================================================
# L1: Supervisor 전체 응답 캐시
# ============================================================


class SupervisorResponseCache(BaseRedisCache):
    """
    L1 캐시: 전체 Supervisor 응답.

    동일한 쿼리에 대해 전체 파이프라인을 건너뛰고 즉시 응답.
    세션별로 분리하여 컨텍스트 무결성 유지.
    """

    PREFIX: ClassVar[str] = "supervisor_response"
    TTL_SECONDS: ClassVar[int] = 3600  # 1시간

    @classmethod
    def _select_cacheable_fields(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """캐싱할 필드만 선택 (messages 제외 - 너무 큼)."""
        import time
        return {
            'final_answer': data.get('final_answer'),
            'mode': data.get('mode'),
            'query_type': data.get('query_analysis', {}).get('query_type'),
            'citations': data.get('citations', []),
            '_cached_at': time.time(),
        }


# ============================================================
# L2: Query Analysis 캐시
# ============================================================


class QueryAnalysisCache(BaseRedisCache):
    """
    L2 캐시: Query Analysis 결과.

    동일한 쿼리에 대한 의도 분류, 키워드, retriever_types를 재사용.
    세션 무관하게 캐싱 (쿼리 자체의 특성이므로).
    """

    PREFIX: ClassVar[str] = "query_analysis"
    TTL_SECONDS: ClassVar[int] = 86400  # 24시간

    @classmethod
    def _select_cacheable_fields(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Query Analysis 캐싱 필드."""
        import time
        return {
            'mode': data.get('mode'),
            'query_type': data.get('query_type'),
            'domain': data.get('domain'),
            'keywords': data.get('keywords', []),
            'retriever_types': data.get('retriever_types', []),
            'search_priority': data.get('search_priority'),
            '_cached_at': time.time(),
        }


# ============================================================
# L3: Intent Classification 캐시
# ============================================================


class IntentClassificationCache(BaseRedisCache):
    """
    L3 캐시: Intent Classification 결과.

    gpt-4o-mini 호출 결과를 캐싱하여 LLM 비용/지연 절감.
    세션 무관하게 캐싱 (쿼리 자체의 특성이므로).
    """

    PREFIX: ClassVar[str] = "intent_classification"
    TTL_SECONDS: ClassVar[int] = 86400 * 7  # 7일 (분류 결과는 오래 유효)

    @classmethod
    def _select_cacheable_fields(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Intent Classification 캐싱 필드."""
        import time
        return {
            'query_type': data.get('query_type'),
            'domain': data.get('domain'),
            'agency': data.get('agency'),
            'confidence': data.get('confidence'),
            'reasoning': data.get('reasoning'),
            'model_used': data.get('model_used'),
            '_cached_at': time.time(),
        }


# ============================================================
# 캐시 관리 유틸리티
# ============================================================


def clear_all_supervisor_caches() -> Dict[str, int]:
    """모든 Supervisor 캐시 삭제 (관리용)."""
    results = {
        'l1_deleted': SupervisorResponseCache.clear_all(),
        'l2_deleted': QueryAnalysisCache.clear_all(),
        'l3_deleted': IntentClassificationCache.clear_all(),
    }
    logger.info(f"[SupervisorCache] Cleared: {results}")
    return results


def get_cache_stats() -> Dict[str, Any]:
    """캐시 통계 조회 (모니터링용)."""
    redis = get_redis_client()
    if not redis:
        return {'enabled': False, 'error': 'Redis unavailable'}

    try:
        l1_count = SupervisorResponseCache.count()
        l2_count = QueryAnalysisCache.count()
        l3_count = IntentClassificationCache.count()
        answer_count = sum(1 for _ in redis.scan_iter(match="answer_cache:*"))

        return {
            'enabled': True,
            'l1_supervisor_count': l1_count,
            'l2_query_analysis_count': l2_count,
            'l3_intent_classification_count': l3_count,
            'answer_count': answer_count,
            'total': l1_count + l2_count + l3_count + answer_count,
        }
    except Exception as e:
        return {'enabled': True, 'error': str(e)}
