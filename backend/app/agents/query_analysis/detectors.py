"""
Query Detectors

도메인 감지, 모호함 탐지, 시스템 메타 쿼리 감지 함수들.
"""

import logging
import re
from typing import Dict, Optional

from .constants import (
    AMBIGUOUS_QUERY_PATTERNS,
    COMMON_PRODUCTS,
    CRITERIA_KEYWORDS,
    DISPUTE_INTENT_KEYWORDS,
    ENABLE_AMBIGUOUS_DETECTION,
    ENABLE_FAST_PATH_PROMOTION,
    FAST_PATH_PROMOTION_KEYWORDS,
    LAW_KEYWORDS,
    LLM_AMBIGUITY_CHECK_MAX_LENGTH,
    META_CONVERSATIONAL_KEYWORDS,
    META_CONVERSATIONAL_PATTERNS,
    PROCEDURE_KEYWORDS,
    PROCEDURE_PATTERNS,
    RESTRICTED_DOMAIN_KEYWORDS,
    SYSTEM_META_KEYWORDS,
    SYSTEM_META_PATTERNS,
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
    LLM을 사용해 쿼리가 모호한지 판단

    규칙 기반으로 판단하기 어려운 짧은 쿼리에 대해 LLM의 상식을 활용합니다.
    비용 절감을 위해 모든 쿼리에 사용하지 않고, Layer 1, 2를 통과한 경우에만 호출합니다.

    Fallback 체인:
    1. EXAONE (Primary) - 도메인 특화 모델
    2. gpt-4o-mini IntentClassifier (Fallback) - 구조화된 분류

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
        logger.warning(
            f"[QueryAnalysis] EXAONE ambiguity check failed: {e}, trying fallback..."
        )

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
        logger.warning("[QueryAnalysis] IntentClassifier import failed")
        return False
    except Exception as e:
        logger.warning(f"[QueryAnalysis] IntentClassifier failed: {e}")
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
    law_pattern_match = re.search(r"\S+법", query_lower)
    logger.debug(f"law_pattern_match check: law_pattern_match={law_pattern_match}")
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
        "finance": [
            "금융분쟁",
            "보험분쟁",
            "대출분쟁",
            "대출",
            "보험금",
            "보험료",
            "은행",
            "금융회사",
            "증권",
            "펀드",
        ],
        "medical": [
            "의료사고",
            "의료분쟁",
            "의료과실",
            "진료",
            "수술",
            "병원",
            "의사",
            "오진",
        ],
        "privacy": ["개인정보유출", "개인정보침해", "개인정보", "정보유출", "해킹"],
        "realestate": [
            "임대차분쟁",
            "전세분쟁",
            "보증금분쟁",
            "전세",
            "월세",
            "임대차",
            "보증금반환",
            "집주인",
        ],
        "construction": [
            "건축분쟁",
            "시공분쟁",
            "하자분쟁",
            "시공불량",
            "시공",
            "건축",
            "아파트하자",
        ],
    }

    # 우선순위: 핵심 키워드 먼저 체크
    for domain, keywords in core_keywords.items():
        if any(kw in query_lower for kw in keywords):
            logger.info(
                f"[QueryAnalysis] Restricted domain detected by core keyword: {domain}"
            )
            return domain

    # 일반 키워드 2개 이상 매칭 체크
    for domain, keywords in RESTRICTED_DOMAIN_KEYWORDS.items():
        match_count = sum(1 for kw in keywords if kw in query_lower)
        if match_count >= 2:
            logger.info(
                f"[QueryAnalysis] Restricted domain detected: {domain} (matches: {match_count})"
            )
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
        logger.info(
            f"[QueryAnalysis] Procedure query detected (matches: {procedure_match})"
        )
        return True

    # 절차 질문 패턴
    for pattern in PROCEDURE_PATTERNS:
        if re.search(pattern, query_lower):
            return True

    return False


def is_meta_conversational(query: str) -> bool:
    """
    대화형 안내 쿼리 감지.

    사용자가 "뭘 물어봐야 할까?", "도와줘" 같은 메타 수준의 질문을 했을 때,
    RAG 검색 없이 가이드 응답을 생성하기 위한 감지 함수입니다.

    system_meta (시스템/봇 관련)과 구분:
    - system_meta: "네가 뭐야?", "어떤 AI야?" → 봇 자체에 대한 질문
    - meta_conversational: "뭘 물어봐야 할까?" → 서비스 이용 가이드 요청

    Args:
        query: 사용자 쿼리

    Returns:
        True if query is a meta-conversational guide request
    """
    query_lower = query.lower().strip()

    # [분쟁 정보] 형식의 질문은 실제 분쟁 상담이므로 meta_conversational이 아님
    if "[분쟁 정보]" in query or "분쟁 정보" in query_lower:
        return False

    # 분쟁 의도 키워드가 있으면 meta_conversational이 아님
    from .constants import DISPUTE_INTENT_KEYWORDS
    if any(kw in query_lower for kw in DISPUTE_INTENT_KEYWORDS):
        return False

    # 키워드 매칭 (우선)
    if any(kw in query_lower for kw in META_CONVERSATIONAL_KEYWORDS):
        logger.info(f"[QueryAnalysis] Meta-conversational by keyword: '{query[:30]}'")
        return True

    # 패턴 매칭
    for pattern in META_CONVERSATIONAL_PATTERNS:
        if re.search(pattern, query_lower):
            logger.info(
                f"[QueryAnalysis] Meta-conversational by pattern: '{query[:30]}'"
            )
            return True

    return False


def _extract_product_keywords(query: str) -> set:
    """
    쿼리에서 품목 키워드를 추출합니다 (화제 전환 감지용).

    Args:
        query: 사용자 쿼리

    Returns:
        추출된 품목 키워드 집합
    """
    from .constants import COMMON_PRODUCTS

    query_lower = query.lower()
    found_items = set()

    # COMMON_PRODUCTS에서 키워드 추출
    for category, items in COMMON_PRODUCTS.items():
        for item in items:
            if item.lower() in query_lower:
                found_items.add(item.lower())

    return found_items


def is_followup_with_context(
    query: str,
    previous_followups: list,
    threshold: float = 0.8,
    previous_query: str = None,
) -> bool:
    """
    현재 쿼리가 이전 턴의 후속 질문 중 하나와 매칭되는지 확인합니다.

    Args:
        query: 현재 사용자 쿼리
        previous_followups: 이전 턴의 followup_questions 리스트
        threshold: SequenceMatcher 유사도 임계값 (기본 0.8)
        previous_query: 이전 턴의 사용자 쿼리 (품목 변경 감지용)

    Returns:
        True if 매칭됨
    """
    if not previous_followups:
        return False

    import difflib
    import logging
    import re

    logger = logging.getLogger(__name__)

    query_normalized = query.strip()

    # 조문 번호 패턴 감지 (법률 제XX조)
    article_pattern = r'([\w가-힣]+법?)\s*제?(\d+)조'
    current_article_match = re.search(article_pattern, query_normalized)

    # 품목 변경 감지 (화제 전환)
    if previous_query:
        current_items = _extract_product_keywords(query)
        previous_items = _extract_product_keywords(previous_query)

        # 둘 다 구체적 품목을 언급한 경우
        if current_items and previous_items:
            # 완전히 다른 품목 → 화제 전환
            overlap = current_items & previous_items
            if not overlap:
                logger.info(
                    f"[Followup] Product changed detected: {previous_items} → {current_items}, "
                    f"not a followup (topic shift)"
                )
                return False  # 화제 전환!
            else:
                logger.info(
                    f"[Followup] Same/related products: {overlap}, checking text similarity"
                )

    for followup in previous_followups:
        if not followup:
            continue

        # 이전 followup에서도 조문 번호 추출
        followup_article_match = re.search(article_pattern, followup.strip())

        # 둘 다 조문 번호 쿼리인 경우: 조문 번호가 다르면 follow-up이 아님
        if current_article_match and followup_article_match:
            current_law = current_article_match.group(1)
            current_num = current_article_match.group(2)
            followup_law = followup_article_match.group(1)
            followup_num = followup_article_match.group(2)

            # 같은 법률의 다른 조문 → follow-up이 아님
            if current_law == followup_law and current_num != followup_num:
                continue  # 다음 followup 검사

            # 다른 법률 → follow-up이 아님
            if current_law != followup_law:
                continue

        # 텍스트 유사도 체크
        ratio = difflib.SequenceMatcher(
            None, query_normalized, followup.strip()
        ).ratio()
        if ratio >= threshold:
            return True

    return False


def detect_requested_detail_type(
    query: str, available_details: Optional[Dict] = None
) -> str:
    """
    후속 질문에서 요청된 상세 정보 유형을 감지합니다.

    Returns:
        'laws' | 'cases' | 'criteria' | 'procedure' | 'full'
    """
    query_lower = query.strip().lower()

    # 법령 관련 키워드
    law_patterns = [
        "법령",
        "법률",
        "법적",
        "법",
        "조항",
        "조문",
        "규정",
        "전자상거래법",
        "소비자기본법",
        "소비자보호법",
        "약관규제법",
        "시행령",
        "법적 근거",
        "법에",
        "법으로",
        "법상",
    ]

    # 절차 관련 키워드 (procedure는 case보다 먼저 체크 - '조정신청'이 '조정'에 선행)
    procedure_patterns = [
        "절차",
        "방법",
        "어떻게",
        "신청",
        "접수",
        "소비자원",
        "분쟁조정",
        "조정신청",
        "어디에",
        "어디로",
        "과정",
    ]

    # 사례 관련 키워드 ('조정'은 '조정사례'로 구체화 - '조정신청'과 구분)
    case_patterns = [
        "사례",
        "케이스",
        "판례",
        "조정사례",
        "비슷한",
        "유사한",
        "다른 사람",
        "남들은",
        "보통",
        "일반적",
        "건도",
    ]

    # 기준 관련 키워드
    criteria_patterns = [
        "기준",
        "해결기준",
        "분쟁해결",
        "배상",
        "보상",
        "환불 기준",
        "교환 기준",
        "수리 기준",
    ]

    # Yes/No 패턴 (이전 후속 질문에 대한 긍정 응답)
    yes_patterns = [
        "네",
        "예",
        "응",
        "어",
        "그래",
        "좋아",
        "알려",
        "보여",
        "궁금",
        "보고 싶",
    ]

    # 긍정 응답인 경우 available_details에서 첫 번째 항목 반환
    is_yes = any(p in query_lower for p in yes_patterns) and len(query_lower) < 20

    # 키워드 매칭 (순서 중요: laws → procedure → cases → criteria)
    for pattern in law_patterns:
        if pattern in query_lower:
            return "laws"

    for pattern in procedure_patterns:
        if pattern in query_lower:
            return "procedure"

    for pattern in case_patterns:
        if pattern in query_lower:
            return "cases"

    for pattern in criteria_patterns:
        if pattern in query_lower:
            return "criteria"

    # 긍정 응답 + available_details 기반 추론
    if is_yes and available_details:
        # 첫 번째 available detail type 반환
        for detail_type in ["laws", "cases", "criteria"]:
            if detail_type in available_details:
                return detail_type
        return "procedure"

    return "full"


__all__ = [
    "should_promote_to_rag",
    "check_ambiguity_with_llm",
    "is_ambiguous_query",
    "is_system_meta_query",
    "detect_restricted_domain",
    "is_procedure_query",
    "is_meta_conversational",
    "is_followup_with_context",
    "detect_requested_detail_type",
]
