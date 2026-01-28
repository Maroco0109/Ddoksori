"""
Query Detectors

도메인 감지, 모호함 탐지, 시스템 메타 쿼리 감지 함수들.
"""

import logging
import os
import re
from typing import Optional

from .constants import (
    ENABLE_AMBIGUOUS_DETECTION,
    ENABLE_FAST_PATH_PROMOTION,
    LLM_AMBIGUITY_CHECK_MAX_LENGTH,
    RESTRICTED_DOMAIN_KEYWORDS,
    PROCEDURE_KEYWORDS,
    SYSTEM_META_KEYWORDS,
    SYSTEM_META_PATTERNS,
    FAST_PATH_PROMOTION_KEYWORDS,
    AMBIGUOUS_QUERY_PATTERNS,
    DISPUTE_INTENT_KEYWORDS,
    COMMON_PRODUCTS,
    LAW_KEYWORDS,
    CRITERIA_KEYWORDS,
    PROCEDURE_PATTERNS,
)

logger = logging.getLogger(__name__)


def should_promote_to_rag(query: str) -> bool:
    """일반 대화(General)로 분류되었지만, RAG 검색이 필요한지 확인합니다."""
    if not ENABLE_FAST_PATH_PROMOTION:
        return False
    query_lower = query.lower()
    return any(kw in query_lower for kw in FAST_PATH_PROMOTION_KEYWORDS)


def check_ambiguity_with_llm(query: str) -> bool:
    """
    LLM을 사용해 쿼리가 모호한지 판단 (Layer 3 fallback)

    규칙 기반으로 판단하기 어려운 짧은 쿼리에 대해 LLM의 상식을 활용합니다.
    비용 절감을 위해 모든 쿼리에 사용하지 않고, Layer 1, 2를 통과한 경우에만 호출합니다.

    Fallback 체인:
    1. EXAONE (Primary) - 도메인 특화 모델
    2. gpt-4o-mini Function Calling (Fallback) - 구조화된 분류

    Args:
        query: 사용자 쿼리

    Returns:
        True if query is ambiguous and needs clarification
    """
    system_prompt = "당신은 소비자 분쟁 상담 시스템의 쿼리 분류기입니다. 사용자 질문이 구체적인지 모호한지 판단하세요."
    user_prompt = f"""사용자 질문: "{query}"
판단 기준:
- 구체적: 제품/서비스 종류, 문제 상황(환불/교환/배송 등)이 명확함
- 모호함: 무엇을 원하는지 불명확, 맥락 없는 단순 요청

응답: "구체적" 또는 "모호함" 중 하나만 출력하세요."""

    # 1. EXAONE 시도 (Primary)
    try:
        from app.llm.exaone_client import ExaoneLLMClient

        client = ExaoneLLMClient()
        if client.is_available():
            response = client.generate(system_prompt, user_prompt)
            is_ambiguous = "모호" in response.lower()
            logger.info(
                f"[QueryAnalysis] EXAONE ambiguity check: '{query[:20]}...' -> {response.strip()} (ambiguous={is_ambiguous})"
            )
            return is_ambiguous
        else:
            logger.info("[QueryAnalysis] EXAONE not available, trying fallback...")
    except Exception as e:
        logger.warning(f"[QueryAnalysis] EXAONE ambiguity check failed: {e}, trying fallback...")

    # 2. gpt-4o-mini Function Calling Fallback (PR-2 IntentClassifier 통합)
    try:
        from .classifier import IntentClassifier

        classifier = IntentClassifier(model="gpt-4o-mini", timeout=3.0)
        result = classifier.classify(query)

        # ambiguous로 분류되었거나 confidence가 낮으면 모호한 것으로 판단
        is_ambiguous = result.query_type == "ambiguous" or result.confidence < 0.8
        logger.info(
            f"[QueryAnalysis] gpt-4o-mini intent check: '{query[:20]}...' -> "
            f"type={result.query_type}, conf={result.confidence:.2f} (ambiguous={is_ambiguous})"
        )
        return is_ambiguous

    except ImportError:
        logger.warning("[QueryAnalysis] IntentClassifier import failed, using legacy fallback")
    except Exception as e:
        logger.warning(f"[QueryAnalysis] IntentClassifier failed: {e}, using legacy fallback...")

    # 3. Legacy fallback (텍스트 기반)
    try:
        from openai import OpenAI

        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("[QueryAnalysis] OpenAI API key not found, skipping LLM check")
            return False

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=20
        )

        result = response.choices[0].message.content.strip()
        is_ambiguous = "모호" in result.lower()
        logger.info(
            f"[QueryAnalysis] gpt-4o-mini ambiguity check: '{query[:20]}...' -> {result} (ambiguous={is_ambiguous})"
        )
        return is_ambiguous

    except Exception as e:
        logger.warning(f"[QueryAnalysis] gpt-4o-mini fallback failed: {e}")
        return False  # 모든 LLM 실패 시 보수적으로 RAG 진행


def is_ambiguous_query(query: str) -> bool:
    """
    하이브리드 방식으로 모호한 쿼리 탐지

    사용자가 "그냥 도와줘" 처럼 맥락 없는 질문을 했을 때,
    무리하게 검색하지 않고 "어떤 도움이 필요하신가요?"라고 되물어보기 위함입니다.

    Layer 0: Intent 키워드/제품명 체크 (있으면 즉시 NOT ambiguous)
    Layer 1: Pattern 매칭 (명시적 모호 패턴)
    Layer 2: LLM fallback (짧은 쿼리, 의도 불명확)

    Args:
        query: 사용자 쿼리

    Returns:
        True if query is ambiguous and needs pre-clarification
    """
    if not ENABLE_AMBIGUOUS_DETECTION:
        return False

    query_stripped = query.strip()
    query_lower = query_stripped.lower()

    # Layer 0: 의도 키워드 있으면 → 즉시 NOT ambiguous (최우선 체크)
    has_intent = any(kw in query_lower for kw in DISPUTE_INTENT_KEYWORDS)
    if has_intent:
        return False

    # Layer 0.5: 제품명 있으면 → NOT ambiguous (제품 + 문제없음도 일단 RAG 시도)
    has_product = any(p.lower() in query_lower for p in COMMON_PRODUCTS)
    if has_product:
        return False

    # Layer 0.6: 법령명 패턴 있으면 → NOT ambiguous (예: "소비자기본법", "전자상거래법")
    law_pattern_match = re.search(r'\S+법', query_lower)
    logger.info(f"[DEBUG] query_lower='{query_lower}', law_pattern_match={law_pattern_match}")
    if law_pattern_match:
        return False

    # Layer 0.7: 법령/기준 관련 키워드 있으면 → NOT ambiguous
    has_law_keywords = any(kw in query_lower for kw in LAW_KEYWORDS)
    has_criteria_keywords = any(kw in query_lower for kw in CRITERIA_KEYWORDS)
    if has_law_keywords or has_criteria_keywords:
        return False

    # Layer 1: 명시적 패턴 매칭 (의도/제품 없는 경우에만)
    for pattern in AMBIGUOUS_QUERY_PATTERNS:
        if re.search(pattern, query_stripped, re.IGNORECASE):
            logger.info(f"[QueryAnalysis] Ambiguous by pattern: '{query[:20]}'")
            return True

    # Layer 2: 짧은 쿼리인데 의도 불명확 → LLM 판단
    if len(query_stripped) <= LLM_AMBIGUITY_CHECK_MAX_LENGTH:
        is_ambiguous = check_ambiguity_with_llm(query)
        if is_ambiguous:
            logger.info(f"[QueryAnalysis] Ambiguous by LLM: '{query[:20]}'")
        return is_ambiguous

    return False


def is_system_meta_query(query: str) -> bool:
    """
    시스템/봇 관련 질문인지 확인 (Phase 4)
    예: "네 모델명이 뭐야?", "니가 뭔데?", "어떤 AI야?"

    이런 질문은 RAG 검색 없이 미리 정의된 시스템 프롬프트로 답변하는 것이 효율적입니다.
    """
    query_lower = query.lower()

    # 키워드 기반 체크
    meta_keyword_count = sum(1 for kw in SYSTEM_META_KEYWORDS if kw in query_lower)
    if meta_keyword_count >= 1:
        return True

    # 패턴 기반 체크
    for pattern in SYSTEM_META_PATTERNS:
        if re.search(pattern, query_lower):
            return True

    return False


def detect_restricted_domain(query: str) -> Optional[str]:
    """
    전문기관 도메인 감지

    KCA/ECMC 관할 외 전문분쟁조정기관으로 안내해야 하는 도메인인지 확인합니다.

    Returns:
        도메인 키 (finance, medical, privacy, realestate, construction) 또는 None
    """
    query_lower = query.lower()

    # 핵심 키워드 (1개만 있어도 해당 도메인으로 판단)
    core_keywords = {
        "finance": ["금융분쟁", "보험분쟁", "대출분쟁", "대출", "보험금", "보험료", "은행", "금융회사", "증권", "펀드"],
        "medical": ["의료사고", "의료분쟁", "의료과실", "진료", "수술", "병원", "의사", "오진"],
        "privacy": ["개인정보유출", "개인정보침해", "개인정보", "정보유출", "해킹"],
        "realestate": ["임대차분쟁", "전세분쟁", "보증금분쟁", "전세", "월세", "임대차", "보증금반환", "집주인"],
        "construction": ["건축분쟁", "시공분쟁", "하자분쟁", "시공불량", "시공", "건축", "아파트하자"],
    }

    # 우선순위: 핵심 키워드 먼저 체크
    for domain, keywords in core_keywords.items():
        if any(kw in query_lower for kw in keywords):
            logger.info(f"[QueryAnalysis] Restricted domain detected by core keyword: {domain}")
            return domain

    # 일반 키워드 2개 이상 매칭 체크
    for domain, keywords in RESTRICTED_DOMAIN_KEYWORDS.items():
        match_count = sum(1 for kw in keywords if kw in query_lower)
        if match_count >= 2:
            logger.info(f"[QueryAnalysis] Restricted domain detected: {domain} (matches: {match_count})")
            return domain

    return None


def is_procedure_query(query: str) -> bool:
    """
    절차 안내 질문인지 확인

    분쟁조정 신청 절차, 서류, 기간 등에 대한 질문인지 판단합니다.
    """
    query_lower = query.lower()

    # 절차 키워드 매칭
    procedure_match = sum(1 for kw in PROCEDURE_KEYWORDS if kw in query_lower)
    if procedure_match >= 1:
        logger.info(f"[QueryAnalysis] Procedure query detected (matches: {procedure_match})")
        return True

    # 절차 질문 패턴
    for pattern in PROCEDURE_PATTERNS:
        if re.search(pattern, query_lower):
            return True

    return False


__all__ = [
    "should_promote_to_rag",
    "check_ambiguity_with_llm",
    "is_ambiguous_query",
    "is_system_meta_query",
    "detect_restricted_domain",
    "is_procedure_query",
]
