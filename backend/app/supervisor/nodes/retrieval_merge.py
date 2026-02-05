"""
똑소리 프로젝트 - Retrieval 결과 병합 노드 (Phase 5: MAS Supervisor)

작성일: 2026-01-26

[역할]
4개 Retrieval Agent(Law, Criteria, Case, Counsel)의 병렬 실행 결과를
하나의 RetrievalResult로 병합합니다.

[워크플로우]
Supervisor → Fan-out → [Law|Criteria|Case|Counsel] → retrieval_merge → Supervisor

[병합 전략]
1. 각 Agent 결과의 documents를 해당 섹션(laws, criteria, disputes, counsels)으로 분류
2. RRF(Reciprocal Rank Fusion) 기반 점수 재계산 (옵션)
3. 최대/평균 유사도 통계 계산
4. Supervisor 상태 업데이트 (completed_tasks에 'retrieval' 추가)
"""

import logging
import time
from typing import Any, Dict, List, Optional

from ...common.config import get_config
from ..cache import RetrievalResultCache
from ..state import ChatState, IndividualRetrievalResult, RetrievalResult

logger = logging.getLogger(__name__)


# Product category mapping for relevance scoring
# Based on COMMON_PRODUCTS from query_analysis/constants.py
PRODUCT_CATEGORY_MAP = {
    "전자기기": [
        "전자기기",  # 카테고리 이름 자체도 포함
        "전자제품",
        "가전제품",
        "가전",
        "노트북",
        "컴퓨터",
        "pc",
        "스마트폰",
        "휴대폰",
        "핸드폰",
        "아이폰",
        "갤럭시",
        "태블릿",
        "아이패드",
        "에어팟",
        "이어폰",
        "헤드폰",
        "스피커",
        "모니터",
        "키보드",
        "마우스",
        "프린터",
        "카메라",
        "렌즈",
        "드론",
    ],
    "가전제품": [
        "가전제품",  # 카테고리 이름 자체도 포함
        "가전",
        "tv",
        "텔레비전",
        "냉장고",
        "세탁기",
        "에어컨",
        "청소기",
        "전자레인지",
        "오븐",
        "건조기",
        "로봇청소기",
        "공기청정기",
        "제습기",
        "가습기",
        "전기밥솥",
        "믹서기",
        "커피머신",
    ],
    "가구": ["가구", "가구제품", "침대", "소파", "책상", "의자", "옷장", "매트리스"],
    "서비스": [
        "서비스",
        "헬스장",
        "pt",
        "피티",
        "수영장",
        "필라테스",
        "요가",
        "학원",
        "영어",
        "웨딩",
        "결혼",
        "스튜디오",
        "여행",
        "항공권",
        "호텔",
        "숙박",
    ],
    "의류잡화": ["의류", "잡화", "의류잡화", "옷", "신발", "가방", "지갑", "시계", "악세서리"],
    "차량": ["차량", "자동차", "중고차", "오토바이", "자전거", "킥보드", "전동킥보드"],
}


def _compute_product_relevance(
    document: Dict[str, Any],
    purchase_item: Optional[str],
    product_category: Optional[str],
    negated_items: Optional[List[str]] = None,
) -> float:
    """
    검색된 문서의 품목 관련성을 계산합니다.

    Args:
        document: 검색된 문서 dict (content, metadata 등)
        purchase_item: 온보딩 구매 품목
        product_category: 온보딩 품목 카테고리
        negated_items: 제외하려는 품목 리스트 (e.g., ["모니터"])

    Returns:
        관련성 점수 (0.0 ~ 1.0)
    """
    content = (document.get("content") or "").lower()
    title = (document.get("doc_title") or document.get("title") or "").lower()
    text = f"{title} {content}"

    # Negated items 체크 (최우선 - 제외하려는 품목이 있으면 relevance 0)
    if negated_items:
        for negated_item in negated_items:
            if negated_item.lower() in text:
                return 0.0  # 제외 대상!

    # 품목과 카테고리 둘 다 없으면 모든 문서 관련
    if not purchase_item and not product_category:
        return 1.0

    # 직접 품목명 매칭 (purchase_item이 있을 때만)
    if purchase_item:
        item_lower = purchase_item.lower()
        if item_lower in text:
            return 1.0

    # 카테고리 키워드 매칭 (purchase_item 유무와 관계없이 실행)
    if product_category:
        category_keywords = PRODUCT_CATEGORY_MAP.get(product_category, [])
        for keyword in category_keywords:
            if keyword.lower() in text:
                return 0.8

    # 분쟁 유형 매칭 (환불, 교환 등은 범용)
    dispute_keywords = ["환불", "교환", "수리", "취소", "해지", "청약철회"]
    if any(kw in text for kw in dispute_keywords):
        return 0.4  # 분쟁 관련이지만 품목 불일치

    return 0.2  # 무관


def _calculate_merged_statistics(
    individual_results: List[IndividualRetrievalResult],
) -> Dict[str, float]:
    """
    개별 결과들의 통계 계산

    Args:
        individual_results: 4개 Agent의 결과 리스트

    Returns:
        max_similarity, avg_similarity 딕셔너리
    """
    all_similarities = []
    for result in individual_results:
        if result.get("max_similarity"):
            all_similarities.append(result["max_similarity"])
        if result.get("avg_similarity"):
            all_similarities.append(result["avg_similarity"])

    if not all_similarities:
        return {"max_similarity": 0.0, "avg_similarity": 0.0}

    return {
        "max_similarity": max(all_similarities),
        "avg_similarity": sum(all_similarities) / len(all_similarities),
    }


def _merge_to_retrieval_result(
    individual_results: List[IndividualRetrievalResult],
) -> RetrievalResult:
    """
    개별 결과를 RetrievalResult 4섹션 구조로 병합

    Args:
        individual_results: 4개 Agent의 결과 리스트

    Returns:
        병합된 RetrievalResult
    """
    # 4섹션 초기화
    merged: RetrievalResult = {
        "agency": {},
        "disputes": [],
        "counsels": [],
        "laws": [],
        "criteria": [],
        "max_similarity": 0.0,
        "avg_similarity": 0.0,
    }

    # 소스별 매핑
    source_to_section = {
        "law": "laws",
        "criteria": "criteria",
        "case": "disputes",  # case → disputes 섹션
        "counsel": "counsels",
    }

    for result in individual_results:
        source = result.get("source", "")
        section_key = source_to_section.get(source)

        if section_key and result.get("documents"):
            # 해당 섹션에 문서 추가
            merged[section_key].extend(result["documents"])

        # 에러 로깅
        if result.get("error"):
            logger.warning(f"[RetrievalMerge] {source} agent error: {result['error']}")

    # 통계 계산
    stats = _calculate_merged_statistics(individual_results)
    merged["max_similarity"] = stats["max_similarity"]
    merged["avg_similarity"] = stats["avg_similarity"]

    return merged


def _update_supervisor_state(
    current_supervisor: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Supervisor 상태 업데이트: completed_tasks에 'retrieval' 추가

    Args:
        current_supervisor: 현재 supervisor 상태

    Returns:
        업데이트된 supervisor 상태
    """
    if current_supervisor is None:
        # 초기 상태 생성
        return {
            "current_phase": "drafting",
            "agent_messages": [],
            "pending_tasks": [],
            "completed_tasks": ["retrieval"],
            "supervisor_reasoning": "Retrieval completed",
            "next_agent": None,
            "iteration_count": 0,
        }

    completed = list(current_supervisor.get("completed_tasks", []))
    if "retrieval" not in completed:
        completed.append("retrieval")

    return {
        **current_supervisor,
        "current_phase": "drafting",
        "completed_tasks": completed,
    }


def _apply_display_limits(
    merged: RetrievalResult,
    session_id: Optional[str],
) -> RetrievalResult:
    """
    도메인별 노출 수 제한을 적용하고 오버플로 결과를 캐시합니다.

    Args:
        merged: 병합된 전체 결과
        session_id: 세션 ID (캐시 키)

    Returns:
        노출 수 제한이 적용된 RetrievalResult
    """
    config = get_config().retrieval
    limits = {
        "laws": config.display_law,
        "criteria": config.display_criteria,
        "disputes": config.display_case,
        "counsels": config.display_counsel,
    }

    overflow: Dict[str, list] = {}

    for section_key, limit in limits.items():
        docs = merged.get(section_key, [])
        if len(docs) > limit:
            # 상위 N개만 노출, 나머지는 오버플로
            merged[section_key] = docs[:limit]
            overflow[section_key] = docs[limit:]

    # 오버플로 캐시 저장
    if overflow and session_id and config.cache_overflow:
        try:
            from ..cache import RetrievalOverflowCache

            RetrievalOverflowCache.set_by_session(session_id, overflow)
            overflow_counts = {k: len(v) for k, v in overflow.items()}
            logger.info(f"[RetrievalMerge] Overflow cached: {overflow_counts}")
        except Exception as e:
            logger.warning(f"[RetrievalMerge] Overflow cache save failed: {e}")

    return merged


async def retrieval_merge_node(state: ChatState) -> Dict[str, Any]:
    """
    Retrieval 결과 병합 노드 (async)

    4개 Retrieval Agent의 결과를 하나의 RetrievalResult로 병합합니다.

    Args:
        state: ChatState (individual_retrieval_results 포함)

    Returns:
        Dict with:
            - retrieval: 병합된 RetrievalResult
            - sources: 인용 출처 리스트 (추가)
            - supervisor: 업데이트된 SupervisorState
    """
    start_time = time.time()

    # 개별 결과 가져오기
    individual_results = state.get("individual_retrieval_results", [])

    logger.info(f"[RetrievalMerge] Merging {len(individual_results)} agent results")

    # 결과 병합
    merged = _merge_to_retrieval_result(individual_results)

    # Agency 정보 병합 (query_analysis에서 도메인 라우팅 결과)
    query_analysis = state.get("query_analysis") or {}
    restricted_domain = query_analysis.get("restricted_domain")
    restricted_agency_info = query_analysis.get("restricted_agency_info")

    if restricted_domain and restricted_agency_info:
        merged["agency"] = {
            "domain": restricted_domain,
            "name": restricted_agency_info.get("name", ""),
            "organization": restricted_agency_info.get("organization", ""),
            "url": restricted_agency_info.get("url", ""),
            "phone": restricted_agency_info.get("phone", ""),
            "is_restricted": True,
        }
        logger.info(
            f"[RetrievalMerge] Agency info populated: domain={restricted_domain}"
        )

    # Post-retrieval product relevance filtering
    # Check if user changed product scope in follow-up question
    product_scope_change = query_analysis.get("product_scope_change") or {}
    should_ignore_filter = product_scope_change.get("should_ignore_product_filter", False)
    negated_items = product_scope_change.get("negated_items", [])

    logger.info(
        f"[RetrievalMerge] product_scope_change={product_scope_change}, "
        f"should_ignore={should_ignore_filter}"
    )

    onboarding = state.get("onboarding") or {}
    purchase_item = onboarding.get("purchase_item")
    product_category = onboarding.get("product_category")

    logger.info(
        f"[RetrievalMerge] Initial: purchase_item={purchase_item}, category={product_category}"
    )

    # Override product category if expanded
    if product_scope_change.get("expanded_category"):
        product_category = product_scope_change["expanded_category"]
        purchase_item = None  # Clear specific item filter when expanding
        logger.info(
            f"[RetrievalMerge] Product scope expanded to category='{product_category}'"
        )

    # Apply product filter only if not explicitly ignored
    if purchase_item and not should_ignore_filter:
        logger.info(
            f"[RetrievalMerge] Applying product relevance filter for item='{purchase_item}'"
        )
        # Score and filter case results (disputes/counsels) only
        # Laws and criteria are not product-specific
        for section_key in ["disputes", "counsels"]:
            docs = merged.get(section_key, [])
            if docs:
                # Calculate product relevance for each document
                for doc in docs:
                    doc["product_relevance"] = _compute_product_relevance(
                        doc, purchase_item, product_category, negated_items
                    )

                # Sort by (product_relevance * similarity) descending
                docs.sort(
                    key=lambda d: (
                        d.get("product_relevance", 1.0) * d.get("similarity", 0.0)
                    ),
                    reverse=True,
                )

                # Filter out very low relevance (< 0.3) only if we have enough high-relevance results
                high_relevance = [
                    d for d in docs if d.get("product_relevance", 1.0) >= 0.3
                ]
                if len(high_relevance) >= 2:
                    filtered_count = len(docs) - len(high_relevance)
                    merged[section_key] = high_relevance
                    if filtered_count > 0:
                        logger.info(
                            f"[RetrievalMerge] Filtered {filtered_count} low-relevance "
                            f"{section_key} (kept {len(high_relevance)})"
                        )
                # else: keep all results to maintain minimum coverage
    elif should_ignore_filter:
        logger.info(
            f"[RetrievalMerge] Product filter ignored (scope change detected)"
        )
        # Apply category-level filtering if expanded category is specified
        if product_category:
            logger.info(
                f"[RetrievalMerge] Applying category filter for '{product_category}'"
            )
            if negated_items:
                logger.info(
                    f"[RetrievalMerge] Excluding negated items: {negated_items}"
                )
            for section_key in ["disputes", "counsels"]:
                docs = merged.get(section_key, [])
                if docs:
                    # Score by category relevance (more lenient than item matching)
                    for doc in docs:
                        doc["product_relevance"] = _compute_product_relevance(
                            doc, None, product_category, negated_items
                        )

                    # Sort by category relevance
                    docs.sort(
                        key=lambda d: (
                            d.get("product_relevance", 1.0) * d.get("similarity", 0.0)
                        ),
                        reverse=True,
                    )

                    # Filter out negated items (relevance = 0.0) and low relevance
                    # If negated_items exist, filter out 0.0 relevance (negated)
                    # Otherwise, use threshold 0.5 for category matching
                    if negated_items:
                        # Exclude negated items (relevance = 0.0)
                        high_relevance = [
                            d for d in docs if d.get("product_relevance", 1.0) > 0.0
                        ]
                    else:
                        # Normal category filter (threshold 0.5)
                        high_relevance = [
                            d for d in docs if d.get("product_relevance", 1.0) >= 0.5
                        ]

                    if len(high_relevance) >= 2:
                        filtered_count = len(docs) - len(high_relevance)
                        merged[section_key] = high_relevance
                        if filtered_count > 0:
                            logger.info(
                                f"[RetrievalMerge] Category filter: removed {filtered_count} "
                                f"low-relevance {section_key} (kept {len(high_relevance)})"
                            )
                    # else: keep all results to maintain minimum coverage

    # 도메인별 노출 수 제한 적용
    session_id = state.get("session_id")
    merged = _apply_display_limits(merged, session_id)

    # 출처 목록 생성 (sources 필드용)
    sources = []
    for section_key in ["laws", "criteria", "disputes", "counsels"]:
        for doc in merged.get(section_key, []):
            if doc.get("chunk_id") or doc.get("doc_id"):
                sources.append(
                    {
                        "type": section_key,
                        "id": doc.get("chunk_id") or doc.get("doc_id"),
                        "title": doc.get("title", ""),
                        "similarity": doc.get("similarity", 0.0),
                    }
                )

    # Supervisor 상태 업데이트
    updated_supervisor = _update_supervisor_state(state.get("supervisor"))

    elapsed = time.time() - start_time
    logger.info(
        f"[RetrievalMerge] Completed in {elapsed * 1000:.1f}ms: "
        f"laws={len(merged['laws'])}, criteria={len(merged['criteria'])}, "
        f"disputes={len(merged['disputes'])}, counsels={len(merged['counsels'])}"
    )

    # L4 캐시: 세션별 Retrieval 결과 저장 (Progressive Disclosure용)
    if session_id:
        try:
            RetrievalResultCache.set_by_session(session_id, merged)
            logger.info(
                f"[RetrievalMerge] L4 cache saved for session={session_id[:8]}..."
            )
        except Exception as e:
            logger.warning(f"[RetrievalMerge] L4 cache save failed: {e}")

    return {
        "retrieval": merged,
        "sources": sources,
        "supervisor": updated_supervisor,
    }


__all__ = ["retrieval_merge_node"]
