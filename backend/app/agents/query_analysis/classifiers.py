"""
Query Classifiers

쿼리 유형 분류 및 라우팅 모드 결정 함수들.

변경 이력:
- Issue #3: Hybrid Intent Classification (규칙 + LLM Fallback)
  - classify_query_type_with_confidence() 추가 (confidence score 반환)
  - 분쟁 의도 패턴 (DISPUTE_COMPOUND_PATTERNS) 추가
  - classify_query_type()는 backward-compatible wrapper로 유지
"""

import logging
import re
from enum import Enum
from typing import Literal, Tuple

from ...supervisor.state import RoutingMode
from .constants import (
    LAW_KEYWORDS,
    CRITERIA_KEYWORDS,
    GENERAL_PATTERNS,
    DEFINITIONAL_PATTERNS,
    COMMON_PRODUCTS,
)
from .detectors import (
    should_promote_to_rag,
    is_ambiguous_query,
    is_system_meta_query,
    detect_restricted_domain,
    is_procedure_query,
    is_meta_conversational,
    is_followup_with_context,
)

logger = logging.getLogger(__name__)

# Query type literal
QueryType = Literal[
    "dispute", "general", "law", "criteria",
    "procedure", "restricted", "system_meta", "ambiguous",
    "meta_conversational",
]

# 쿼리 복잡도 (Adaptive RAG용)
class QueryComplexity(str, Enum):
    """
    쿼리 복잡도 분류 (Adaptive RAG 전략 선택에 사용)

    - SIMPLE: 단순 키워드 질문 → BM25 위주 검색 (HyDE 생략)
    - MODERATE: 일반적 분쟁 상담 → HyDE + RRF 기본 검색
    - COMPLEX: 복잡한 상황 설명 → HyDE + RRF + 확장 검색
    """
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"

# 분쟁 의도 복합 패턴 (Issue #3: dispute-specific compound patterns)
# 규칙 기반 분류 정확도를 높이기 위해 LLM fallback 전에 체크
DISPUTE_COMPOUND_PATTERNS: list[Tuple[str, float]] = [
    (r'.+(?:인데|했는데|됐는데).+(?:가능|해줘|되나|할\s*수)', 0.85),  # "~인데 ~가능해?"
    (r'(?:파손|불량|하자|결함|고장)', 0.85),  # 제품 하자 키워드
    (r'(?:환불|교환|수리|반품|AS|as)', 0.85),  # 분쟁 해결 키워드
    (r'(?:피해|손해|배상|보상)', 0.80),  # 피해/배상 키워드
]


def classify_mode(
    query_type: QueryType,
    needs_clarification: bool,
    query: str,
    previous_followups: list = None,
    previous_available_details: dict = None,
) -> RoutingMode:
    """
    분석된 정보를 바탕으로 오케스트레이터의 라우팅 경로를 결정합니다.

    - NO_RETRIEVAL: 검색 없이 바로 답변 (일반 대화, 시스템 질문)
    - NEED_USER_CLARIFICATION: 정보가 부족하거나 모호해서 사용자에게 되물어야 함
    - NEED_RAG: 정보 검색이 필요함
    - RESTRICTED_DOMAIN: 전문기관 도메인 (유사 사례 검색 + 전문기관 안내)
    - FOLLOWUP_WITH_CONTEXT: 이전 턴 후속 질문 매칭 (캐시 재사용)
    """
    logger.info(
        f"[classify_mode] Input: query_type={query_type}, needs_clarification={needs_clarification}, "
        f"query='{query[:50] if query else 'N/A'}...'"
    )

    # Phase 4: 시스템 관련 질문은 검색 불필요
    if query_type == "system_meta":
        logger.info("[classify_mode] System meta query detected, skipping retrieval")
        return "NO_RETRIEVAL"

    # 메타 대화 쿼리: legacy 모드에서는 기존 동작(NO_RETRIEVAL), 아니면 META_CONVERSATIONAL
    if query_type == "meta_conversational":
        try:
            from ...common.config import get_config
            response_mode = get_config().response.response_mode
        except Exception:
            logger.warning("[QueryAnalysis] Failed to read response_mode, defaulting to legacy")
            response_mode = "legacy"
        if response_mode == "legacy":
            logger.info("[QueryAnalysis] Meta-conversational in legacy mode → NO_RETRIEVAL")
            return "NO_RETRIEVAL"
        logger.info(f"[QueryAnalysis] Meta-conversational query → META_CONVERSATIONAL (mode={response_mode})")
        return "META_CONVERSATIONAL"

    # Phase D: FOLLOWUP_WITH_CONTEXT — 이전 턴 후속 질문 매칭
    if previous_followups:
        try:
            from ...common.config import get_config
            threshold = get_config().response.followup_similarity_threshold
            response_mode = get_config().response.response_mode
        except Exception:
            threshold = 0.8
            response_mode = "legacy"

        if response_mode != "legacy":
            if is_followup_with_context(query, previous_followups, threshold):
                logger.info(f"[QueryAnalysis] Followup matched → FOLLOWUP_WITH_CONTEXT")
                return "FOLLOWUP_WITH_CONTEXT"

    # NEW: 모호한 쿼리는 RAG로 라우팅 (명확화 단계 제거됨)
    if query_type == "ambiguous":
        logger.info(
            "[QueryAnalysis] Ambiguous query detected, routing to RAG"
        )
        return "NEED_RAG"

    if query_type == "general":
        # 일반 대화라도 특정 키워드(소송, 환불기간 등)가 있으면 검색 수행
        if should_promote_to_rag(query):
            logger.info(
                "[classify_mode] Fast Path promotion triggered for general query → NEED_RAG"
            )
            return "NEED_RAG"
        logger.info("[classify_mode] General query → NO_RETRIEVAL")
        return "NO_RETRIEVAL"

    # NEW: Restricted 도메인은 전문기관 안내 + 유사 사례 검색
    if query_type == "restricted":
        logger.info("[QueryAnalysis] Restricted domain detected, routing to specialist agency guidance")
        return "RESTRICTED_DOMAIN"

    # needs_clarification parameter kept for backward compatibility but ignored
    # Phase system removed - all queries now route to RAG

    # procedure, law, criteria, dispute 모두 RAG 필요
    logger.info(f"[classify_mode] query_type={query_type} → NEED_RAG")
    return "NEED_RAG"


def classify_query_type_with_confidence(query: str) -> Tuple[QueryType, float]:
    """
    사용자의 질문을 9가지 유형 중 하나로 분류하고 confidence score를 반환합니다.
    우선순위(Priority) 기반의 Rule-based 로직을 사용합니다.

    Issue #3: Hybrid Intent Classification을 위해 confidence score를 추가하여
    LLM Fallback이 필요한 경우(confidence < 0.7)를 식별합니다.

    Priority:
    1. System Meta (시스템 질문) -> 검색 Skip (0.95)
    1.5. Meta-Conversational (대화형 안내) -> 가이드 응답 (0.90)
    2. General (인사/잡담) -> 검색 Skip (0.9)
    3. Definitional (정의 질문) -> General로 분류 (0.85)
    4. Restricted (전문기관 도메인) -> 전문기관 안내 (0.9)
    5. Procedure (절차 안내) -> 절차 템플릿 + RAG 보강 (0.85)
    6. Law (법령 질문) -> 관련 법령 검색 (0.8-0.9)
    7. Criteria (기준 질문) -> 고시/기준 검색 (0.85)
    7.5. Dispute compound patterns (분쟁 복합 패턴) -> (0.80-0.85)
    8. Ambiguous (모호함) -> 사용자 확인 요청 (0.6)
    9. Dispute (분쟁 상담) -> Default (0.5)

    Returns:
        (query_type, confidence) 튜플
    """
    query_lower = query.lower()

    logger.info(f"[classify_query_type_with_confidence] Input query: '{query[:50]}'...")

    # Phase 4: 시스템/봇 관련 질문 (검색 불필요)
    if is_system_meta_query(query):
        return "system_meta", 0.95

    # 일반 대화 패턴 (인사, 감사 등) - meta_conversational 전에 체크
    for pattern in GENERAL_PATTERNS:
        if re.search(pattern, query_lower):
            return "general", 0.9

    # 법률명 패턴 우선 (예: "소비자보호법이 뭐야?" → law, not general)
    # DEFINITIONAL 패턴보다 먼저 체크하여 법률명 포함 질문을 law로 분류
    law_pattern_match = re.search(r'\S+법', query_lower)
    if law_pattern_match:
        return "law", 0.9

    # "환불이 뭐예요?" 같은 정의형 질문은 일반 대화로 처리
    # (법률명이 포함되지 않은 정의형만 해당)
    for pattern in DEFINITIONAL_PATTERNS:
        if re.search(pattern, query_lower):
            return "general", 0.85

    # NEW: Restricted 도메인 체크 (전문기관 안내 필요)
    # 금융, 의료, 개인정보, 부동산, 건설 분야는 전문기관 안내
    restricted_domain = detect_restricted_domain(query)
    if restricted_domain:
        return "restricted", 0.9

    # NEW: Procedure 체크 (절차 안내 질문)
    if is_procedure_query(query):
        return "procedure", 0.85

    # Pattern 2: 키워드 카운트 (2개 이상) 또는 특정 패턴
    law_count = sum(1 for kw in LAW_KEYWORDS if kw in query_lower)
    if law_count >= 2 or any(
        kw in query_lower for kw in ["몇조", "법 조항", "법령 조회"]
    ):
        return "law", 0.8

    # 분쟁조정기준 문의 - meta_conversational 전에 체크 (우선순위 높임)
    criteria_count = sum(1 for kw in CRITERIA_KEYWORDS if kw in query_lower)
    # "분쟁조정기준" 명시적 언급 또는 "기준" + 제품명 조합이면 높은 confidence
    if "분쟁조정기준" in query_lower:
        return "criteria", 0.90
    # "기준" 키워드가 있고 제품명도 있으면 criteria로 분류
    has_criteria_keyword = "기준" in query_lower
    has_product = any(p.lower() in query_lower for p in COMMON_PRODUCTS)
    if has_criteria_keyword and has_product:
        return "criteria", 0.85
    # 기준 관련 키워드 2개 이상
    if criteria_count >= 2:
        return "criteria", 0.80

    # 메타 대화 쿼리 ("뭘 물어봐야 할까?", "도와줘") - 도메인 키워드 체크 후
    # 주의: "냉장고 환불 기준 알려줘" 같은 구체적 질문이 meta로 잘못 분류되지 않도록
    # 도메인 특화 키워드 체크를 먼저 수행한 후 meta_conversational 체크
    if is_meta_conversational(query):
        return "meta_conversational", 0.90

    # Issue #3: 분쟁 의도 복합 패턴 (ambiguous/default 전에 체크)
    for pattern, conf in DISPUTE_COMPOUND_PATTERNS:
        if re.search(pattern, query_lower):
            return "dispute", conf

    # NEW: 하이브리드 ambiguous 체크 (dispute default 전에)
    if is_ambiguous_query(query):
        return "ambiguous", 0.6

    # 기본값: 분쟁 상담 (confidence 낮음 → LLM fallback 대상)
    result = ("dispute", 0.5)
    logger.info(f"[classify_query_type_with_confidence] Result: type={result[0]}, confidence={result[1]}")
    return result


def classify_query_type(query: str) -> QueryType:
    """
    사용자의 질문을 8가지 유형 중 하나로 분류합니다.
    우선순위(Priority) 기반의 Rule-based 로직을 사용합니다.

    Backward-compatible wrapper: confidence score 없이 QueryType만 반환합니다.
    confidence score가 필요한 경우 classify_query_type_with_confidence()를 사용하세요.

    Returns:
        분류된 질의 유형 문자열
    """
    query_type, _ = classify_query_type_with_confidence(query)
    return query_type


def classify_query_complexity(query: str) -> QueryComplexity:
    """
    쿼리의 복잡도를 분류합니다 (Adaptive RAG 전략 선택용).

    분류 기준:
    - SIMPLE: 단어 수 ≤ 5, 단순 키워드/정의형 질문
    - COMPLEX: 단어 수 ≥ 15 또는 복합 문장 구조 (인데/했는데/됐는데 + 요구)
    - MODERATE: 나머지

    Args:
        query: 사용자 쿼리

    Returns:
        QueryComplexity 열거형 값
    """
    import re

    query_stripped = query.strip()
    # 공백 기준 단어 수 (한국어는 어절 기준)
    word_count = len(query_stripped.split())

    # COMPLEX 패턴: 복합 문장 구조 (단어 수보다 우선)
    complex_patterns = [
        r'.+(?:인데|했는데|됐는데|거든요|는데요).+(?:가능|해줘|되나|할\s*수|어떻게)',
        r'(?:구매|주문|결제).+(?:후|지난).+(?:불량|하자|파손|고장)',
        r'.+(?:거부|무시|연락).+(?:어떻게|방법|도움)',
    ]
    for pattern in complex_patterns:
        if re.search(pattern, query_stripped):
            return QueryComplexity.COMPLEX

    # COMPLEX: 긴 문장 (상황 설명이 포함됨)
    if word_count >= 15:
        return QueryComplexity.COMPLEX

    # SIMPLE: 짧은 키워드 질문
    if word_count <= 5:
        return QueryComplexity.SIMPLE

    # 나머지: MODERATE
    return QueryComplexity.MODERATE


__all__ = [
    "QueryType",
    "QueryComplexity",
    "classify_mode",
    "classify_query_type",
    "classify_query_type_with_confidence",
    "classify_query_complexity",
    "DISPUTE_COMPOUND_PATTERNS",
]
