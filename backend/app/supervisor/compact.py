"""
똑소리 프로젝트 - Compact 모듈
작성일: 2026-01-20
PR-3: 대화 히스토리에서 구조화 필드 추출

Compact 동작:
1. 대화 히스토리에서 구조화 정보 추출
2. 기존 요약과 병합
3. 슬라이딩 윈도우로 최근 N턴만 유지

추출 필드:
- purchase_item: 구매 품목
- purchase_date: 구매 일자
- purchase_amount: 구매 금액
- purchase_place: 구매처
- dispute_type: 분쟁 유형
- dispute_details: 분쟁 상세 내용
- desired_resolution: 희망 해결 방안
- key_facts: 핵심 사실 목록
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 품목 추출 패턴
PRODUCT_PATTERNS = [
    r"(?:구매|산|샀|주문).*?([가-힣A-Za-z0-9]+(?:\s*[가-힣A-Za-z0-9]+)?)",
    r"([가-힣A-Za-z0-9]+)\s*(?:을|를|이|가)\s*(?:구매|주문|구입)",
]

# 일반 제품 키워드
COMMON_PRODUCTS = [
    "노트북",
    "컴퓨터",
    "PC",
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
    "TV",
    "텔레비전",
    "냉장고",
    "세탁기",
    "에어컨",
    "청소기",
    "전자레인지",
    "오븐",
    "건조기",
    "모니터",
    "키보드",
    "마우스",
    "프린터",
    "카메라",
    "렌즈",
    "드론",
    "로봇청소기",
    "공기청정기",
    "제습기",
    "가습기",
    "전기밥솥",
    "믹서기",
    "커피머신",
    "침대",
    "소파",
    "책상",
    "의자",
    "옷장",
    "매트리스",
    "가구",
    "헬스장",
    "PT",
    "피티",
    "수영장",
    "필라테스",
    "요가",
    "학원",
    "웨딩",
    "결혼",
    "스튜디오",
    "여행",
    "항공권",
    "호텔",
    "숙박",
    "옷",
    "신발",
    "가방",
    "지갑",
    "시계",
    "악세서리",
    "자동차",
    "차량",
    "중고차",
    "오토바이",
    "자전거",
    "킥보드",
    "전동킥보드",
]

# 분쟁 유형 키워드
DISPUTE_TYPE_KEYWORDS = {
    "환불": ["환불", "취소", "청약철회", "반환"],
    "교환": ["교환", "바꿔", "대체"],
    "수리": ["수리", "AS", "A/S", "무상수리", "유상수리", "고장", "불량"],
    "해지": ["해지", "해약", "중도해지", "계약해지"],
    "보상": ["보상", "배상", "피해보상", "손해배상"],
    "환급": ["환급", "위약금 환급"],
}

# 금액 패턴
AMOUNT_PATTERNS = [
    r"(\d{1,3}(?:,\d{3})*)\s*(?:원|만원)",
    r"(\d+)\s*(?:원|만원)",
    r"약?\s*(\d+)\s*만\s*원?",
]

# 날짜 패턴
DATE_PATTERNS = [
    r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?",
    r"(\d{1,2})[-./월]\s*(\d{1,2})일?",
    r"(\d+)\s*(?:개월|달)\s*전",
    r"(\d+)\s*(?:주|일)\s*전",
    r"작년|올해|지난\s*(?:달|주)",
]


def _extract_product(text: str) -> Optional[str]:
    """텍스트에서 품목 추출"""
    text_lower = text.lower()

    # 일반 제품 키워드 매칭
    for product in COMMON_PRODUCTS:
        if product.lower() in text_lower:
            return product

    # 패턴 기반 추출
    for pattern in PRODUCT_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    return None


def _extract_amount(text: str) -> Optional[str]:
    """텍스트에서 금액 추출"""
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, text)
        if match:
            amount = match.group(1).replace(",", "")
            if "만원" in text[match.end() : match.end() + 3] or "만" in match.group(0):
                return f"{int(amount) * 10000}원"
            return f"{amount}원"
    return None


def _extract_date(text: str) -> Optional[str]:
    """텍스트에서 날짜 추출"""
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _extract_dispute_type(text: str) -> Optional[str]:
    """텍스트에서 분쟁 유형 추출"""
    text_lower = text.lower()

    for dispute_type, keywords in DISPUTE_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return dispute_type

    return None


def _extract_key_facts(turns: List[Any]) -> List[str]:
    """대화에서 핵심 사실 추출"""
    facts = []

    # 사용자 메시지에서 핵심 문장 추출
    for turn in turns:
        if turn.role == "user":
            content = turn.content

            # 핵심 사실 패턴
            fact_patterns = [
                r"([가-힣A-Za-z0-9\s]+(?:안|않|못|없|거부|거절)[가-힣\s]*)",
                r"([가-힣A-Za-z0-9\s]+(?:했|됐|받았|보냈)[가-힣\s]*)",
                r"([가-힣A-Za-z0-9\s]+(?:요청|문의|연락)[가-힣\s]*)",
            ]

            for pattern in fact_patterns:
                matches = re.findall(pattern, content)
                for match in matches[:2]:  # 패턴당 최대 2개
                    fact = match.strip()
                    if len(fact) > 10 and fact not in facts:
                        facts.append(fact)

    return facts[:5]  # 최대 5개


def _merge_summaries(
    existing: Optional[Any], new_data: Dict[str, Any]
) -> Dict[str, Any]:
    """기존 요약과 새 데이터 병합"""
    from .memory import CompactSummary

    if existing is None:
        return new_data

    # 기존 요약을 dict로 변환
    if isinstance(existing, CompactSummary):
        existing_dict = existing.to_dict()
    else:
        existing_dict = existing

    # 새 데이터가 있으면 덮어쓰기, 없으면 기존 유지
    merged = {}
    for key in [
        "purchase_item",
        "purchase_date",
        "purchase_amount",
        "purchase_place",
        "dispute_type",
        "dispute_details",
        "desired_resolution",
    ]:
        merged[key] = new_data.get(key) or existing_dict.get(key)

    # key_facts는 병합
    existing_facts = existing_dict.get("key_facts") or []
    new_facts = new_data.get("key_facts") or []
    merged["key_facts"] = list(set(existing_facts + new_facts))[:10]

    # compacted_turn_count 누적
    merged["compacted_turn_count"] = existing_dict.get(
        "compacted_turn_count", 0
    ) + new_data.get("compacted_turn_count", 0)

    return merged


def compact_conversation(
    turns: List[Any],
    existing_summary: Optional[Any] = None,
) -> Any:
    """
    대화 히스토리를 Compact하여 구조화된 요약 생성

    Args:
        turns: 대화 턴 리스트 (ConversationTurn 객체들)
        existing_summary: 기존 CompactSummary (있는 경우)

    Returns:
        CompactSummary: 업데이트된 요약
    """
    from .memory import CompactSummary

    logger.info(f"[Compact] Processing {len(turns)} turns")

    # 모든 텍스트 수집
    all_text = "\n".join([turn.content for turn in turns])
    user_text = "\n".join([turn.content for turn in turns if turn.role == "user"])

    # 각 필드 추출
    new_data: Dict[str, Any] = {
        "purchase_item": _extract_product(all_text),
        "purchase_date": _extract_date(user_text),
        "purchase_amount": _extract_amount(user_text),
        "purchase_place": None,  # 별도 추출 로직 필요 시 추가
        "dispute_type": _extract_dispute_type(all_text),
        "dispute_details": None,  # LLM 기반 추출 필요 시 확장
        "desired_resolution": None,  # LLM 기반 추출 필요 시 확장
        "key_facts": _extract_key_facts(turns),
        "compacted_turn_count": len(turns),
    }

    # 기존 요약과 병합
    merged = _merge_summaries(existing_summary, new_data)

    logger.info(
        f"[Compact] Extracted: item={merged.get('purchase_item')}, "
        f"type={merged.get('dispute_type')}, facts={len(merged.get('key_facts', []))}"
    )

    return CompactSummary.from_dict(merged)


def format_compact_summary_for_prompt(summary: Any) -> str:
    """Compact 요약을 LLM 프롬프트용 문자열로 포맷"""
    if summary is None:
        return ""

    from .memory import CompactSummary

    if isinstance(summary, CompactSummary):
        data = summary.to_dict()
    else:
        data = summary

    lines = ["[이전 대화 요약]"]

    if data.get("purchase_item"):
        lines.append(f"- 품목: {data['purchase_item']}")
    if data.get("purchase_date"):
        lines.append(f"- 구매일: {data['purchase_date']}")
    if data.get("purchase_amount"):
        lines.append(f"- 금액: {data['purchase_amount']}")
    if data.get("purchase_place"):
        lines.append(f"- 구매처: {data['purchase_place']}")
    if data.get("dispute_type"):
        lines.append(f"- 분쟁 유형: {data['dispute_type']}")
    if data.get("key_facts"):
        lines.append("- 핵심 사실:")
        for fact in data["key_facts"][:5]:
            lines.append(f"  * {fact}")

    if data.get("compacted_turn_count", 0) > 0:
        lines.append(f"(이전 {data['compacted_turn_count']}턴 요약)")

    return "\n".join(lines)
