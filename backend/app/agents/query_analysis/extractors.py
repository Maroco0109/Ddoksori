"""
Query Extractors

정보 추출, 키워드 추출, 정규화 함수들.
"""

import logging
import re
from typing import Dict, List, Optional, Literal

from ...supervisor.state import OnboardingInfo
from ...supervisor.conversation_manager import extract_dispute_type
from .constants import (
    COMMON_PRODUCTS,
    DISPUTE_VERBS,
    VERB_SYNONYMS,
    REQUIRED_DISPUTE_FIELDS,
    FIELD_KOREAN_NAMES,
)

logger = logging.getLogger(__name__)


def extract_info_from_message(query: str) -> Dict[str, str]:
    """
    메시지 내용에서 정규식(Regex)을 사용하여 온보딩 정보를 추출합니다.
    사용자가 "아이폰15 환불 관련 문의입니다"라고 했을 때 'purchase_item': '아이폰15'를 추출하기 위함입니다.
    """
    info: Dict[str, str] = {}

    patterns = {
        "purchase_item": [
            r"구매\s*품목[:\s]+([^\n,]+)",
            r"품목[:\s]+([^\n,]+)",
            r"제품[:\s]+([^\n,]+)",
        ],
        "dispute_details": [
            r"분쟁\s*상세[:\s]+([^\n]+)",
            r"문제[:\s]+([^\n]+)",
            r"상황[:\s]+([^\n]+)",
        ],
        "purchase_date": [
            r"구매\s*일자[:\s]+([^\n,]+)",
            r"구매일[:\s]+([^\n,]+)",
        ],
        "purchase_place": [
            r"구매처[:\s]+([^\n,]+)",
            r"판매처[:\s]+([^\n,]+)",
        ],
        "purchase_platform": [
            r"플랫폼[:\s]+([^\n,]+)",
        ],
        "purchase_amount": [
            r"구매\s*금액[:\s]+([^\n,]+)",
            r"금액[:\s]+([^\n,]+)",
            r"(\d{1,}(?:만\s*)?원(?:에|에서|을|를)?)",
        ],
    }

    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and value not in ["없음", "모름", "-"]:
                    info[field] = value
                break

    # 패턴 매칭에 실패했다면, 일반 명사 리스트(COMMON_PRODUCTS)에서 검색
    if "purchase_item" not in info:
        query_lower = query.lower()
        for product in COMMON_PRODUCTS:
            if product.lower() in query_lower:
                info["purchase_item"] = product
                break

    # 분쟁 동사가 있고 품목이 식별되었다면, 분쟁 상세 내용을 자동으로 구성
    if "dispute_details" not in info:
        found_verbs = [v for v in DISPUTE_VERBS if v in query]
        if found_verbs and "purchase_item" in info:
            verb = found_verbs[0]
            item = info["purchase_item"]
            info["dispute_details"] = f"{item} {verb} 관련 문의"

    # 금액 정규화: "150만원" → "1500000"
    if "purchase_amount" in info:
        amount_str = info["purchase_amount"]
        if "만" in amount_str:
            base_match = re.search(r'(\d+(?:\.\d+)?)', amount_str)
            if base_match:
                amount = int(float(base_match.group(1)) * 10000)
                info["purchase_amount"] = str(amount)

    if "dispute_type" not in info:
        dispute_type = extract_dispute_type(query)
        if dispute_type:
            info["dispute_type"] = dispute_type

    return info


def get_missing_fields_description(
    missing_fields: List[str], extracted_info: Dict[str, str]
) -> str:
    """
    부족한 정보에 대한 구체적인 설명 문자열을 생성합니다.
    LLM이 사용자에게 되물을 때 Context로 제공됩니다.
    """
    lines = []

    if extracted_info:
        lines.append("**입력하신 정보:**")
        for field, value in extracted_info.items():
            korean_name = FIELD_KOREAN_NAMES.get(field, field)
            lines.append(f"  • {korean_name}: {value}")
        lines.append("")

    if missing_fields:
        lines.append("**추가로 필요한 정보:**")
        for field in missing_fields:
            korean_name = FIELD_KOREAN_NAMES.get(field, field)
            lines.append(f"  • {korean_name}")

    return "\n".join(lines)


def extract_keywords(query: str) -> List[str]:
    """
    검색 정확도 향상을 위해 핵심 키워드를 추출합니다.

    [로직]
    1. 불용어(Stopwords) 제거: 조사, 접속사 등 검색에 방해되는 단어 제외
    2. 동의어 정규화: "돈 돌려받고" -> "환불"과 같이 표준 용어로 변환 (PR 2 강화)
    3. 구어체 처리: 어간 추출 및 부분 매칭으로 다양한 표현 대응
    """
    stopwords = {
        "저", "제", "것", "수", "등", "더", "좀", "잘", "못", "안",
        "이", "그", "저", "때", "경우", "어떻게", "무엇", "어디", "왜",
        "알려", "주세요", "해주세요", "싶어요", "있나요", "있어요",
        "하고", "그리고", "그래서", "하지만", "그런데", "근데",
    }

    query_normalized = query.replace(" ", "")

    # 동의어 사전 기반 어간 매칭
    matched_base_verbs = set()
    for base_verb, synonyms in VERB_SYNONYMS.items():
        for synonym in synonyms:
            synonym_stem = synonym.replace(" ", "").rstrip("기").rstrip("줘")
            if len(synonym_stem) >= 3 and synonym_stem in query_normalized:
                matched_base_verbs.add(base_verb)
                break

    words = re.sub(r"[^\w\s]", " ", query).split()
    keywords = [w for w in words if len(w) >= 2 and w not in stopwords]

    normalized_keywords = list(matched_base_verbs)

    # 키워드별 동의어 매칭 확인
    for kw in keywords:
        matched = False
        for base_verb, synonyms in VERB_SYNONYMS.items():
            if kw in synonyms:
                normalized_keywords.append(base_verb)
                matched = True
                break
            for synonym in synonyms:
                if synonym in kw and len(synonym) >= 2:
                    normalized_keywords.append(base_verb)
                    matched = True
                    break
            if matched:
                break

        if not matched:
            normalized_keywords.append(kw)

    # 중복 제거
    seen = set()
    unique_keywords = []
    for kw in normalized_keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    return unique_keywords[:10]


def normalize_query(query: str) -> str:
    """
    쿼리의 불필요한 접미사나 문장 부호를 제거합니다.
    "환불해주세요ㅠㅠ" -> "환불" 형태로 만들어 분석 정확도를 높입니다.
    """
    normalized = query.strip()

    suffix_patterns = [
        r"[~해주세요|알려주세요|싶어요|인가요|할까요|있나요|있어요|될까요]$",
        r"[?？!！。\.]+$",
    ]
    for pattern in suffix_patterns:
        normalized = re.sub(pattern, "", normalized)

    return normalized.strip()


def check_missing_onboarding_fields(
    chat_type: Literal["dispute", "general"],
    onboarding: Optional[OnboardingInfo],
    extracted_info: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    온보딩 필수 정보 누락 확인

    분쟁 상담(dispute)일 때만 체크합니다.
    onboarding 정보와 이번 턴에 추출된 정보를 합쳐서 필수 필드가 있는지 확인합니다.

    Returns:
        누락된 필드명 리스트
    """
    if chat_type == "general":
        return []

    combined: Dict[str, str] = {}
    if onboarding:
        for k, v in dict(onboarding).items():
            if v and isinstance(v, str):
                combined[k] = v
    if extracted_info:
        combined.update(extracted_info)

    if not combined:
        return REQUIRED_DISPUTE_FIELDS.copy()

    missing = []
    for field in REQUIRED_DISPUTE_FIELDS:
        value = combined.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    return missing


def determine_agency_hint(query: str) -> Optional[str]:
    """
    질의 내용을 바탕으로 적절한 분쟁조정 기관을 추측합니다.
    - ECMC: 전자거래/개인간 거래 키워드
    - KCA: 그 외 일반 소비자 분쟁 (Default)
    - None: restricted 도메인 (전문기관 안내 필요)

    Note: KCDRC(콘텐츠분쟁조정위원회) 분류는 Phase 9에서 제거됨.
          콘텐츠 분쟁도 KCA로 통합 처리.
    """
    from .constants import INDIVIDUAL_KEYWORDS
    from .detectors import detect_restricted_domain

    query_lower = query.lower()

    # Restricted 도메인인 경우 agency_hint는 None
    restricted_domain = detect_restricted_domain(query)
    if restricted_domain:
        return None

    # 전자거래/개인간 거래 → ECMC
    individual_matches = [kw for kw in INDIVIDUAL_KEYWORDS if kw in query_lower]
    if individual_matches:
        return "ECMC"

    # 기본값: KCA (한국소비자원)
    return "KCA"


__all__ = [
    "extract_info_from_message",
    "get_missing_fields_description",
    "extract_keywords",
    "normalize_query",
    "check_missing_onboarding_fields",
    "determine_agency_hint",
]
