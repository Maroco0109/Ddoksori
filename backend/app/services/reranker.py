"""
Cross-Encoder 기반 재랭킹 서비스

Phase 2-2: 검색 결과를 Cross-Encoder 모델로 재랭킹하여 정확도 향상

의존성: pip install sentence-transformers

환경 변수:
- RERANKER_ENABLED: "true"로 설정 시 활성화
- RERANKER_MODEL: 사용할 모델 (기본: cross-encoder/ms-marco-MiniLM-L-6-v2)

사용 예시:
    from app.services.reranker import rerank_results

    reranked = await rerank_results(query, search_results, top_n=10)
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# 환경 변수
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "false").lower() == "true"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# 전역 인스턴스 (지연 로딩)
_reranker = None
_reranker_loading = False


def get_reranker():
    """
    싱글톤 재랭커 인스턴스 반환 (지연 로딩)

    Returns:
        CrossEncoder 인스턴스 또는 None (비활성화/오류 시)
    """
    global _reranker, _reranker_loading

    if not RERANKER_ENABLED:
        return None

    if _reranker is not None:
        return _reranker

    if _reranker_loading:
        return None

    _reranker_loading = True
    try:
        from sentence_transformers import CrossEncoder

        logger.info(f"[Reranker] Loading model: {RERANKER_MODEL}")
        _reranker = CrossEncoder(RERANKER_MODEL)
        logger.info("[Reranker] Model loaded successfully")
        return _reranker

    except ImportError:
        logger.warning(
            "[Reranker] sentence-transformers not installed. "
            "Run: pip install sentence-transformers"
        )
        return None

    except Exception as e:
        logger.error(f"[Reranker] Failed to load model: {e}")
        return None

    finally:
        _reranker_loading = False


async def rerank_results(
    query: str,
    results: List[Union[Dict[str, Any], Any]],
    top_n: int = 10,
    text_field: str = "content",
    min_score: Optional[float] = None,
) -> List[Union[Dict[str, Any], Any]]:
    """
    Cross-Encoder 기반 재랭킹

    검색 결과를 쿼리와의 관련성으로 재정렬합니다.

    Args:
        query: 사용자 쿼리
        results: 검색 결과 리스트 (dict 또는 SearchResult 객체)
        top_n: 반환할 최대 결과 수
        text_field: 텍스트 필드명 (dict인 경우)
        min_score: 최소 점수 임계값 (None이면 적용 안 함)

    Returns:
        재랭킹된 결과 리스트 (top_n개)
    """
    if not results:
        return results

    # 결과가 top_n 이하면 재랭킹 불필요
    if len(results) <= top_n and min_score is None:
        return results

    # 재랭커 비활성화 시 원본 반환
    if not RERANKER_ENABLED:
        logger.debug("[Reranker] Disabled, returning original results")
        return results[:top_n]

    reranker = get_reranker()
    if reranker is None:
        logger.debug("[Reranker] Not available, returning original results")
        return results[:top_n]

    try:
        # 텍스트 추출
        texts = []
        for r in results:
            if hasattr(r, "content"):
                text = r.content
            elif isinstance(r, dict):
                text = r.get(text_field, r.get("text", ""))
            else:
                text = str(r)
            # 텍스트 길이 제한 (512 토큰 ~= 2000자)
            texts.append(text[:2000] if text else "")

        # 쿼리-문서 쌍 생성
        pairs = [(query, text) for text in texts]

        # 동기 함수를 비동기로 실행
        scores = await asyncio.to_thread(reranker.predict, pairs)

        # 점수 할당
        scored_results = []
        for i, r in enumerate(results):
            score = float(scores[i])

            # 점수 저장
            if hasattr(r, "__dict__"):
                r.rerank_score = score
            elif isinstance(r, dict):
                r["rerank_score"] = score

            scored_results.append((score, i, r))

        # 점수 기준 정렬 (내림차순)
        scored_results.sort(key=lambda x: x[0], reverse=True)

        # 필터링 및 반환
        reranked = []
        for score, _, r in scored_results:
            if min_score is not None and score < min_score:
                continue
            reranked.append(r)
            if len(reranked) >= top_n:
                break

        logger.info(
            f"[Reranker] Reranked {len(results)} → {len(reranked)} results "
            f"(top_score={scored_results[0][0]:.3f})"
        )

        return reranked

    except Exception as e:
        logger.error(f"[Reranker] Error during reranking: {e}")
        return results[:top_n]


def rerank_results_sync(
    query: str,
    results: List[Union[Dict[str, Any], Any]],
    top_n: int = 10,
    text_field: str = "content",
    min_score: Optional[float] = None,
) -> List[Union[Dict[str, Any], Any]]:
    """
    재랭킹 동기 버전

    asyncio 이벤트 루프 외부에서 사용할 때 유용합니다.
    """
    return asyncio.run(
        rerank_results(query, results, top_n, text_field, min_score)
    )


__all__ = [
    "rerank_results",
    "rerank_results_sync",
    "get_reranker",
    "RERANKER_ENABLED",
    "RERANKER_MODEL",
]
