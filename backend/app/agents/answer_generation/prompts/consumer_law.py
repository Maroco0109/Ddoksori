"""
Phase 2-3: 소비자법 도메인 특화 프롬프트

이 모듈은 소비자 보호 법률 도메인에 특화된 프롬프트 컴포넌트를 제공합니다.
기존 템플릿과 함께 사용하여 답변 품질을 향상시킵니다.

사용 예시:
    from app.agents.answer_generation.prompts.consumer_law import (
        CONSUMER_LAW_SYSTEM_PROMPT,
        get_legal_disclaimer,
        get_agency_recommendation,
    )
"""

from typing import Dict, Optional

# ============================================================
# 시스템 프롬프트 - 소비자법 전문가 페르소나
# ============================================================

CONSUMER_LAW_SYSTEM_PROMPT = """당신은 한국 소비자 보호 법률 전문가입니다.

[답변 원칙]
1. 반드시 제공된 법령/사례만 인용하세요
2. 단정적 법적 판단은 피하세요
   - "~해야 합니다" → "~하는 것이 권장됩니다"
   - "불법입니다" → "법적 문제가 될 수 있습니다"
   - "승소합니다" → "유리한 판단을 받을 가능성이 있습니다"
3. 관련 조항을 정확히 인용하세요
   - 예: "소비자기본법 제16조에 따르면..."
4. 복잡한 사안은 전문기관 상담을 권유하세요

[답변 구조]
1. 핵심 답변 (2-3문장으로 요약)
2. 법적 근거 (관련 조항 인용)
3. 유사 사례 (있는 경우)
4. 추가 조언 및 권장 기관

[금지 표현]
- "반드시 ~해야 합니다" (단정적 의무 부과)
- "법적으로 ~입니다" (법적 판단)
- "승소/패소할 것입니다" (재판 결과 예측)
- 개인정보 요청
- 허위 조문 번호 생성
"""

# ============================================================
# 주요 소비자 법률 목록
# ============================================================

CONSUMER_LAWS = {
    "소비자기본법": {
        "description": "소비자 권리 및 보호에 관한 기본법",
        "key_articles": {
            "제4조": "소비자의 기본적 권리",
            "제16조": "국가 및 지방자치단체의 책무",
            "제55조": "소비자분쟁조정위원회",
        },
    },
    "전자상거래법": {
        "full_name": "전자상거래 등에서의 소비자보호에 관한 법률",
        "description": "온라인 거래에서 소비자 보호",
        "key_articles": {
            "제17조": "청약철회 (7일 이내)",
            "제18조": "청약철회의 효과",
            "제21조": "금지행위",
        },
    },
    "할부거래법": {
        "full_name": "할부거래에 관한 법률",
        "description": "할부 계약 및 선불식 거래 보호",
        "key_articles": {
            "제8조": "청약의 철회",
            "제16조": "소비자피해보상보험계약",
        },
    },
    "방문판매법": {
        "full_name": "방문판매 등에 관한 법률",
        "description": "방문판매, 다단계판매 등 특수거래 규제",
        "key_articles": {
            "제8조": "청약의 철회",
            "제17조": "다단계판매의 청약철회",
        },
    },
}

# ============================================================
# 전문기관 안내
# ============================================================

CONSUMER_AGENCIES = {
    "한국소비자원": {
        "phone": "1372",
        "website": "https://www.kca.go.kr",
        "description": "소비자 피해 상담 및 분쟁조정",
        "cases": ["일반 소비자 분쟁", "품질 불만", "계약 취소"],
    },
    "공정거래위원회": {
        "phone": "044-200-4010",
        "website": "https://www.ftc.go.kr",
        "description": "불공정거래 및 약관 심사",
        "cases": ["불공정 약관", "부당광고", "다단계판매 피해"],
    },
    "대한법률구조공단": {
        "phone": "132",
        "website": "https://www.klac.or.kr",
        "description": "법률 상담 및 소송 지원 (무료)",
        "cases": ["소송 필요 사안", "법률 자문", "고액 분쟁"],
    },
    "경찰청": {
        "phone": "112",
        "description": "사기 등 범죄 신고",
        "cases": ["사기 피해", "판매자 잠적", "범죄 의심"],
    },
    "금융감독원": {
        "phone": "1332",
        "website": "https://www.fss.or.kr",
        "description": "금융 관련 민원 및 분쟁조정",
        "cases": ["금융상품 피해", "보험 분쟁", "대출 문제"],
    },
}


def get_legal_disclaimer() -> str:
    """법적 면책 조항 반환"""
    return """
---
[안내] 이 정보는 일반적인 법률 상식을 제공하기 위한 것으로,
구체적인 법률 조언을 대체하지 않습니다.
개별 사안에 대해서는 전문가 상담을 권장합니다.
"""


def get_agency_recommendation(
    case_type: str,
    amount: Optional[int] = None,
    is_criminal: bool = False,
) -> Dict[str, str]:
    """
    사안 유형에 따른 전문기관 추천

    Args:
        case_type: 사안 유형 (예: "환불", "계약해지", "사기")
        amount: 분쟁 금액 (원)
        is_criminal: 범죄 의심 여부

    Returns:
        추천 기관 정보 딕셔너리
    """
    # 범죄 의심 시
    if is_criminal or case_type in ["사기", "잠적", "범죄"]:
        return {
            "primary": CONSUMER_AGENCIES["경찰청"],
            "secondary": CONSUMER_AGENCIES["대한법률구조공단"],
            "reason": "범죄가 의심되는 경우 경찰에 먼저 신고하시기 바랍니다.",
        }

    # 고액 분쟁 (500만원 이상)
    if amount and amount >= 5_000_000:
        return {
            "primary": CONSUMER_AGENCIES["대한법률구조공단"],
            "secondary": CONSUMER_AGENCIES["한국소비자원"],
            "reason": "고액 분쟁의 경우 법률 전문가 상담을 권장합니다.",
        }

    # 금융 관련
    if case_type in ["금융", "보험", "대출", "투자"]:
        return {
            "primary": CONSUMER_AGENCIES["금융감독원"],
            "secondary": CONSUMER_AGENCIES["한국소비자원"],
            "reason": "금융 관련 분쟁은 금융감독원에서 전문적으로 처리합니다.",
        }

    # 일반 소비자 분쟁
    return {
        "primary": CONSUMER_AGENCIES["한국소비자원"],
        "secondary": CONSUMER_AGENCIES["공정거래위원회"],
        "reason": "일반적인 소비자 분쟁은 한국소비자원(1372)에서 상담받으실 수 있습니다.",
    }


def format_law_reference(
    law_name: str,
    article: str,
    content: Optional[str] = None,
) -> str:
    """
    법률 참조 포맷팅

    Args:
        law_name: 법률명 (예: "소비자기본법")
        article: 조문 번호 (예: "제16조")
        content: 조문 내용 (선택)

    Returns:
        포맷팅된 참조 문자열
    """
    law_info = CONSUMER_LAWS.get(law_name, {})
    full_name = law_info.get("full_name", law_name)

    if content:
        return f"『{full_name}』 {article}: {content}"
    return f"『{full_name}』 {article}"


def get_withdrawal_period(transaction_type: str) -> Dict[str, any]:
    """
    거래 유형별 청약철회 기간 정보

    Args:
        transaction_type: 거래 유형

    Returns:
        청약철회 관련 정보
    """
    periods = {
        "전자상거래": {
            "period": 7,
            "unit": "일",
            "law": "전자상거래법",
            "article": "제17조",
            "note": "상품 수령일로부터",
        },
        "방문판매": {
            "period": 14,
            "unit": "일",
            "law": "방문판매법",
            "article": "제8조",
            "note": "계약서 수령일로부터",
        },
        "할부거래": {
            "period": 7,
            "unit": "일",
            "law": "할부거래법",
            "article": "제8조",
            "note": "계약서 수령일로부터",
        },
        "다단계판매": {
            "period": 14,
            "unit": "일",
            "law": "방문판매법",
            "article": "제17조",
            "note": "계약서 수령일로부터 (3개월 이내 상품은 반품 가능)",
        },
    }

    return periods.get(transaction_type, {
        "period": 7,
        "unit": "일",
        "law": "소비자기본법",
        "article": "-",
        "note": "일반적인 청약철회 기간",
    })


__all__ = [
    "CONSUMER_LAW_SYSTEM_PROMPT",
    "CONSUMER_LAWS",
    "CONSUMER_AGENCIES",
    "get_legal_disclaimer",
    "get_agency_recommendation",
    "format_law_reference",
    "get_withdrawal_period",
]
