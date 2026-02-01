"""
Query Extractors

정보 추출, 키워드 추출, 정규화 함수들.
"""

import logging
import re
from datetime import datetime, date
from typing import Dict, List, Optional, Literal

from ...supervisor.state import OnboardingInfo

# Local implementation of extract_dispute_type (moved from conversation_manager)
DISPUTE_TYPE_MAPPING = {
    '환불': 'refund',
    '반품': 'refund',
    '교환': 'exchange',
    '수리': 'repair',
    '취소': 'cancellation',
    '해지': 'cancellation',
    '청약철회': 'withdrawal',
}


def extract_dispute_type(text: str) -> Optional[str]:
    """Extract dispute type from user message using keyword matching."""
    for korean_keyword, dispute_type in DISPUTE_TYPE_MAPPING.items():
        if korean_keyword in text:
            return dispute_type
    return None
from .constants import (
    COMMON_PRODUCTS,
    DISPUTE_VERBS,
    VERB_SYNONYMS,
    REQUIRED_DISPUTE_FIELDS,
    FIELD_KOREAN_NAMES,
)

logger = logging.getLogger(__name__)


PRODUCT_CATEGORY_MAP = {
    '전자제품': ['노트북', '컴퓨터', 'PC', '태블릿', '갤럭시', '아이폰', '아이패드', '맥북',
                '스마트폰', '핸드폰', '휴대폰', 'TV', '텔레비전', '모니터', '냉장고', '세탁기',
                '에어컨', '건조기', '청소기', '전자레인지', '이어폰', '헤드폰', '스피커'],
    '의류/패션': ['옷', '의류', '신발', '가방', '지갑', '모자', '자켓', '코트', '원피스'],
    '가구/인테리어': ['소파', '침대', '매트리스', '책상', '의자', '테이블', '가구'],
    '건강/미용': ['화장품', '헬스장', '피트니스', '필라테스', '요가', 'PT', '퍼스널트레이닝',
                  '피부관리', '에스테틱', '마사지'],
    '교육/학원': ['학원', '교육', '인강', '온라인강의', '수강', '과외'],
    '여행/숙박': ['항공', '호텔', '숙박', '여행', '펜션', '리조트'],
    '식품': ['식품', '건강식품', '음식', '배달'],
    '자동차': ['자동차', '차량', '중고차', '렌트카'],
}


def compute_days_since_purchase(purchase_date_str: Optional[str]) -> Optional[int]:
    """
    구매일로부터 경과 일수를 계산합니다.

    Args:
        purchase_date_str: 구매일 문자열 (YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD 등)

    Returns:
        경과 일수 (int) 또는 None (파싱 실패 시)
    """
    if not purchase_date_str:
        return None

    # 다양한 날짜 포맷 지원
    date_formats = ['%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d', '%Y년%m월%d일']
    purchase_date_clean = purchase_date_str.strip().replace(' ', '')

    for fmt in date_formats:
        try:
            purchase_date = datetime.strptime(purchase_date_clean, fmt).date()
            days = (date.today() - purchase_date).days
            return max(0, days)  # 미래 날짜인 경우 0
        except ValueError:
            continue

    logger.warning(f"[extractors] Failed to parse purchase_date: {purchase_date_str}")
    return None


def determine_product_category(purchase_item: Optional[str]) -> Optional[str]:
    """
    구매 품목에서 카테고리를 결정합니다.

    Args:
        purchase_item: 구매 품목 문자열

    Returns:
        카테고리 문자열 또는 None
    """
    if not purchase_item:
        return None

    item_lower = purchase_item.lower().replace(' ', '')

    for category, keywords in PRODUCT_CATEGORY_MAP.items():
        for keyword in keywords:
            if keyword.lower().replace(' ', '') in item_lower:
                return category

    return None


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
    "compute_days_since_purchase",
    "determine_product_category",
]
