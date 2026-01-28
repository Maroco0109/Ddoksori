"""
Query Classifiers

쿼리 유형 분류 및 라우팅 모드 결정 함수들.
"""

import logging
import re
from typing import Literal

from ...supervisor.state import RoutingMode
from .constants import (
    LAW_KEYWORDS,
    CRITERIA_KEYWORDS,
    GENERAL_PATTERNS,
    DEFINITIONAL_PATTERNS,
)
from .detectors import (
    should_promote_to_rag,
    is_ambiguous_query,
    is_system_meta_query,
    detect_restricted_domain,
    is_procedure_query,
)

logger = logging.getLogger(__name__)

# Query type literal
QueryType = Literal[
    "dispute", "general", "law", "criteria",
    "procedure", "restricted", "system_meta", "ambiguous"
]


def classify_mode(
    query_type: QueryType,
    needs_clarification: bool,
    query: str,
) -> RoutingMode:
    """
    분석된 정보를 바탕으로 오케스트레이터의 라우팅 경로를 결정합니다.

    - NO_RETRIEVAL: 검색 없이 바로 답변 (일반 대화, 시스템 질문)
    - NEED_USER_CLARIFICATION: 정보가 부족하거나 모호해서 사용자에게 되물어야 함
    - NEED_RAG: 정보 검색이 필요함
    - RESTRICTED_DOMAIN: 전문기관 도메인 (유사 사례 검색 + 전문기관 안내)
    """
    # Phase 4: 시스템 관련 질문은 검색 불필요
    if query_type == "system_meta":
        logger.info("[QueryAnalysis] System meta query detected, skipping retrieval")
        return "NO_RETRIEVAL"

    # NEW: 모호한 쿼리는 사전 명확화 필요
    if query_type == "ambiguous":
        logger.info(
            "[QueryAnalysis] Ambiguous query detected, requesting pre-clarification"
        )
        return "NEED_USER_CLARIFICATION"

    if query_type == "general":
        # 일반 대화라도 특정 키워드(소송, 환불기간 등)가 있으면 검색 수행
        if should_promote_to_rag(query):
            logger.info(
                "[QueryAnalysis] Fast Path promotion triggered for general query"
            )
            return "NEED_RAG"
        return "NO_RETRIEVAL"

    # NEW: Restricted 도메인은 전문기관 안내 + 유사 사례 검색
    if query_type == "restricted":
        logger.info("[QueryAnalysis] Restricted domain detected, routing to specialist agency guidance")
        return "RESTRICTED_DOMAIN"

    if needs_clarification:
        return "NEED_USER_CLARIFICATION"

    # procedure, law, criteria, dispute 모두 RAG 필요
    return "NEED_RAG"


def classify_query_type(query: str) -> QueryType:
    """
    사용자의 질문을 8가지 유형 중 하나로 분류합니다.
    우선순위(Priority) 기반의 Rule-based 로직을 사용합니다.

    Priority:
    1. System Meta (시스템 질문) -> 검색 Skip
    2. General (인사/잡담) -> 검색 Skip
    3. Definitional (정의 질문) -> General로 분류
    4. Restricted (전문기관 도메인) -> 전문기관 안내 + 유사 사례 검색
    5. Procedure (절차 안내) -> 절차 템플릿 + RAG 보강
    6. Law (법령 질문) -> 관련 법령 검색
    7. Criteria (기준 질문) -> 고시/기준 검색
    8. Ambiguous (모호함) -> 사용자 확인 요청
    9. Dispute (분쟁 상담) -> Default (유사 사례 검색)

    Returns:
        분류된 질의 유형 문자열
    """
    query_lower = query.lower()

    # Phase 4: 시스템/봇 관련 질문 (검색 불필요)
    if is_system_meta_query(query):
        return "system_meta"

    # 일반 대화 패턴 (인사, 감사 등)
    for pattern in GENERAL_PATTERNS:
        if re.search(pattern, query_lower):
            return "general"

    # "환불이 뭐예요?" 같은 정의형 질문은 일반 대화로 처리
    for pattern in DEFINITIONAL_PATTERNS:
        if re.search(pattern, query_lower):
            return "general"

    # NEW: Restricted 도메인 체크 (전문기관 안내 필요)
    # 금융, 의료, 개인정보, 부동산, 건설 분야는 전문기관 안내
    restricted_domain = detect_restricted_domain(query)
    if restricted_domain:
        return "restricted"

    # NEW: Procedure 체크 (절차 안내 질문)
    if is_procedure_query(query):
        return "procedure"

    # 법령 문의 (법령 키워드가 명시적으로 포함)
    # Pattern 1: 법률명 패턴 (예: "소비자기본법", "전자상거래법")
    law_pattern_match = re.search(r'\S+법', query_lower)
    if law_pattern_match:
        return "law"

    # Pattern 2: 키워드 카운트 (2개 이상) 또는 특정 패턴
    law_count = sum(1 for kw in LAW_KEYWORDS if kw in query_lower)
    if law_count >= 2 or any(
        kw in query_lower for kw in ["몇조", "법 조항", "법령 조회"]
    ):
        return "law"

    # 분쟁조정기준 문의
    criteria_count = sum(1 for kw in CRITERIA_KEYWORDS if kw in query_lower)
    if criteria_count >= 2 or "분쟁조정기준" in query_lower:
        return "criteria"

    # NEW: 하이브리드 ambiguous 체크 (dispute default 전에)
    if is_ambiguous_query(query):
        return "ambiguous"

    # 기본값: 분쟁 상담
    return "dispute"


__all__ = [
    "QueryType",
    "classify_mode",
    "classify_query_type",
]
