"""
Query Expanders

쿼리 확장 및 다중 검색 쿼리 생성 함수들.
"""

import logging
from typing import Dict, List, Optional, Tuple, Literal

from ...supervisor.state import OnboardingInfo
from .constants import (
    DISPUTE_VERBS,
    VERB_SYNONYMS,
    RESTRICTED_DOMAIN_KEYWORDS,
)
from .detectors import detect_restricted_domain

logger = logging.getLogger(__name__)

# Query type literal
QueryType = Literal[
    "dispute", "general", "law", "criteria",
    "procedure", "restricted", "system_meta", "ambiguous"
]


def expand_query_by_type(
    query: str,
    query_type: QueryType,
    onboarding: Optional[OnboardingInfo],
    extracted_info: Dict[str, str],
    keywords: List[str],
    use_llm: bool = True,
) -> Tuple[str, str]:
    """
    질의 유형별 쿼리 확장 (Query Expansion)

    [전략]
    1. LLM Rewrite (S2-10): 복잡한 법률 용어가 포함된 쿼리는 EXAONE으로 일상어 변환
       - 100ms 타임아웃으로 지연시간 제약 보장
       - 타임아웃/에러 시 기존 규칙 기반 확장으로 폴백
    2. Rule-based Expansion (Phase 1):
       - dispute: {품목} {동사} 분쟁조정 피해구제 소비자
       - law: {쿼리} 관련 조항 조문
       - criteria: {품목} 분쟁해결기준 기간
       - procedure: {쿼리} 분쟁조정 신청 절차 서류
       - restricted: {쿼리} 분쟁 사례 (유사 사례 검색용)

    Returns:
        (확장된 쿼리, 적용된 확장 방식)
    """
    # Phase 4: 시스템 관련 질문은 확장 불필요
    if query_type == "system_meta":
        return query, "system_meta_no_expansion"

    if query_type == "general":
        return query, "general_no_expansion"

    # 모호한 쿼리는 확장 불필요 (clarification 먼저)
    if query_type == "ambiguous":
        return query, "ambiguous_no_expansion"

    # 기존 규칙 기반 확장 (Phase 1)
    item = extracted_info.get("purchase_item", "")
    if not item and onboarding:
        item = onboarding.get("purchase_item", "")

    found_verbs = [v for v in DISPUTE_VERBS if v in query]
    verb = found_verbs[0] if found_verbs else ""

    expanded_verbs = []
    if verb and verb in VERB_SYNONYMS:
        expanded_verbs = VERB_SYNONYMS[verb][:2]

    if query_type == "dispute":
        if item and verb:
            verb_str = " ".join(expanded_verbs) if expanded_verbs else verb
            expanded = f"{item} {verb_str} 분쟁조정 피해구제 소비자"
            return expanded, f"dispute_item_verb: {item}+{verb}"
        elif item:
            expanded = f"{item} 분쟁 환불 교환 수리 피해구제"
            return expanded, f"dispute_item_only: {item}"
        elif verb:
            expanded = f"{verb} 분쟁조정 피해구제 소비자 사례"
            return expanded, f"dispute_verb_only: {verb}"
        else:
            return query, "dispute_no_context"

    elif query_type == "law":
        law_names = [kw for kw in keywords if "법" in kw]
        if law_names:
            expanded = f"{query} {' '.join(law_names)} 관련 조항 조문"
            return expanded, f"law_expansion: {','.join(law_names)}"
        return f"{query} 소비자보호법 전자상거래법 조항", "law_default"

    elif query_type == "criteria":
        if item:
            expanded = f"{item} 분쟁해결기준 교환 환불 수리 보상 기간"
            return expanded, f"criteria_item: {item}"
        return f"{query} 분쟁해결기준 품목 기준", "criteria_default"

    # NEW: procedure (절차 안내)
    elif query_type == "procedure":
        expanded = f"{query} 분쟁조정 신청 절차 서류 기간 방법"
        return expanded, "procedure_expansion"

    # NEW: restricted (전문기관 도메인 - 유사 사례 검색용)
    elif query_type == "restricted":
        # 도메인 키워드를 추출하여 유사 사례 검색에 활용
        domain = detect_restricted_domain(query)
        if domain:
            domain_keywords = RESTRICTED_DOMAIN_KEYWORDS.get(domain, [])[:3]
            expanded = f"{query} {' '.join(domain_keywords)} 분쟁 사례"
            return expanded, f"restricted_expansion: {domain}"
        return f"{query} 분쟁 사례", "restricted_default"

    return query, "unknown_type"


def generate_search_queries(
    original: str, expanded: str, keywords: List[str]
) -> List[str]:
    """
    Multi-Query Expansion (PR 2)

    다양한 검색 전략으로 Recall(재현율)을 높입니다.
    하나의 질문이라도 여러 가지 방식으로 표현하여 검색엔진에 질의합니다.

    전략:
    1. 원본 쿼리: 사용자의 날 것 그대로의 질문
    2. 확장 쿼리: 규칙/LLM으로 보강된 쿼리 (법률 용어 등 추가)
    3. 키워드 조합 쿼리: 불필요한 조사 등을 제거한 순수 키워드 나열
    4. 동의어 변형 쿼리: "환불" -> "반환/청약철회" 등으로 치환
    """
    queries = [original]

    if expanded and expanded != original:
        queries.append(expanded)

    if len(keywords) >= 3:
        keyword_query = " ".join(keywords[:5])
        if keyword_query not in queries:
            queries.append(keyword_query)

    synonym_query = create_synonym_variant_query(original, keywords)
    if synonym_query and synonym_query not in queries:
        queries.append(synonym_query)

    return queries[:4]


def create_synonym_variant_query(original: str, keywords: List[str]) -> Optional[str]:
    """
    동의어 변형 쿼리 생성
    예: "노트북 환불" -> "노트북 반환 청약철회"
    """
    variant_parts = []
    for kw in keywords[:3]:
        if kw in VERB_SYNONYMS:
            synonyms = VERB_SYNONYMS[kw][:2]
            variant_parts.append(" ".join(synonyms))
        else:
            variant_parts.append(kw)

    variant = " ".join(variant_parts)
    return variant if variant != original else None


__all__ = [
    "expand_query_by_type",
    "generate_search_queries",
    "create_synonym_variant_query",
]
