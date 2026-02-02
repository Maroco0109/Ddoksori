"""
똑소리 프로젝트 - 답변 형식 설정

작성일: 2026-02-01

[역할 및 책임]
답변 형식(ResponseFormat)을 정의하고 관리합니다.
각 형식은 쿼리 타입에 따라 다른 섹션 구성과 톤을 가집니다.

[형식 종류]
1. law_response: 법령 질문 - 법적 근거 + 면책 (형식적)
2. law_onboarding: 법령+온보딩 - 온보딩 요약 + 적용 법령 + 근거 (형식적)
3. criteria_response: 기준 질문 - 품질보증기간 + 하자기준 + 주의사항 (형식적)
4. case_response: 사례 질문 - 조정사례 + 상담사례 + 분석 (형식적)
5. comprehensive_dispute: 종합 분쟁 - 법령 + 기준 + 절차 (형식적)
6. general_greeting: 일반/인사 - 섹션 없는 자연스러운 대화 (친근함)
7. info_only: 제한 영역 - 기관 안내 + 참고 사례 (정보제공)
"""

from typing import List, Dict, Literal, Optional
from dataclasses import dataclass


@dataclass
class SectionConfig:
    """
    답변 섹션 설정

    Attributes:
        section_id: 섹션 식별자 (similar_cases, legal_basis, agency_info, etc.)
        required: 필수 섹션 여부
        conditions: 섹션 표시 조건 (예: {'has_cases': True})
    """
    section_id: str
    required: bool = True
    conditions: Optional[Dict[str, bool]] = None

    def should_include(self, context: Dict) -> bool:
        """
        컨텍스트를 기반으로 섹션 포함 여부를 판단합니다.

        Args:
            context: 검색 결과 컨텍스트 (has_cases, has_laws 등)

        Returns:
            섹션 포함 여부
        """
        if not self.conditions:
            return self.required

        # 모든 조건을 만족해야 함
        for key, expected_value in self.conditions.items():
            if context.get(key) != expected_value:
                return False

        return True


@dataclass
class ResponseFormat:
    """
    답변 형식

    Attributes:
        format_id: 형식 식별자
        query_types: 적용 가능한 쿼리 타입 목록
        sections: 포함할 섹션 목록
        include_disclaimer: 면책 문구 포함 여부
        tone: 답변 톤 (formal, friendly, informative)
        closing_prompt: 마무리 멘트 (Optional)
    """
    format_id: str
    query_types: List[str]
    sections: List[SectionConfig]
    include_disclaimer: bool
    tone: Literal['formal', 'friendly', 'informative']
    closing_prompt: Optional[str] = None


# ============================================================
# 답변 형식 정의
# ============================================================

RESPONSE_FORMATS: Dict[str, ResponseFormat] = {
    'law_response': ResponseFormat(
        format_id='law_response',
        query_types=['law'],
        sections=[
            SectionConfig(
                section_id='legal_basis',
                required=True,
                conditions={'has_laws': True}
            ),
        ],
        include_disclaimer=True,
        tone='formal',
        closing_prompt="더 자세한 정보를 원하시나요?"
    ),

    'law_onboarding': ResponseFormat(
        format_id='law_onboarding',
        query_types=['law', 'dispute'],  # selected via onboarding context, not just query_type
        sections=[
            SectionConfig(
                section_id='onboarding_summary',
                required=True,
                conditions=None
            ),
            SectionConfig(
                section_id='applicable_laws',
                required=True,
                conditions={'has_laws': True}
            ),
            SectionConfig(
                section_id='rationale',
                required=True,
                conditions=None
            ),
        ],
        include_disclaimer=True,
        tone='formal',
        closing_prompt=None
    ),

    'criteria_response': ResponseFormat(
        format_id='criteria_response',
        query_types=['criteria'],
        sections=[
            SectionConfig(
                section_id='warranty_period',
                required=True,
                conditions=None
            ),
            SectionConfig(
                section_id='defect_criteria',
                required=True,
                conditions={'has_criteria': True}
            ),
            SectionConfig(
                section_id='caution_procedure',
                required=True,
                conditions=None
            ),
        ],
        include_disclaimer=True,
        tone='formal',
        closing_prompt=None
    ),

    'case_response': ResponseFormat(
        format_id='case_response',
        query_types=['dispute'],  # selected via context, not just query_type
        sections=[
            SectionConfig(
                section_id='mediation_cases',
                required=True,
                conditions={'has_cases': True}
            ),
            SectionConfig(
                section_id='counsel_cases',
                required=False,
                conditions={'has_cases': True}
            ),
            SectionConfig(
                section_id='case_analysis',
                required=True,
                conditions=None
            ),
        ],
        include_disclaimer=True,
        tone='formal',
        closing_prompt=None
    ),

    'comprehensive_dispute': ResponseFormat(
        format_id='comprehensive_dispute',
        query_types=['dispute', 'procedure', 'ambiguous'],
        sections=[
            SectionConfig(
                section_id='applicable_laws',
                required=True,
                conditions={'has_laws': True}
            ),
            SectionConfig(
                section_id='criteria_detail',
                required=True,
                conditions={'has_criteria': True}
            ),
            SectionConfig(
                section_id='next_steps',
                required=False,
                conditions=None
            ),
        ],
        include_disclaimer=True,
        tone='formal',
        closing_prompt="유사한 사례에 대해 궁금하신가요?"
    ),

    'general_greeting': ResponseFormat(
        format_id='general_greeting',
        query_types=['general', 'greeting', 'thanks', 'system_meta', 'meta_conversational', 'ambiguous'],
        sections=[],
        include_disclaimer=False,
        tone='friendly',
        closing_prompt=None  # handled in prompt
    ),

    'info_only': ResponseFormat(
        format_id='info_only',
        query_types=['restricted'],
        sections=[
            SectionConfig(
                section_id='agency_referral',
                required=True,
                conditions=None
            ),
            SectionConfig(
                section_id='related_cases',
                required=False,
                conditions={'has_cases': True}
            ),
        ],
        include_disclaimer=True,
        tone='informative',
        closing_prompt=None
    ),
}


def get_format_by_id(format_id: str) -> Optional[ResponseFormat]:
    """
    형식 ID로 ResponseFormat을 조회합니다.

    Args:
        format_id: 형식 식별자

    Returns:
        ResponseFormat 또는 None
    """
    return RESPONSE_FORMATS.get(format_id)


def get_format_by_query_type(query_type: str) -> Optional[ResponseFormat]:
    """
    쿼리 타입으로 ResponseFormat을 조회합니다.

    Args:
        query_type: 쿼리 타입 (dispute, general, restricted 등)

    Returns:
        ResponseFormat 또는 None (매칭되는 형식이 없으면 None)
    """
    for response_format in RESPONSE_FORMATS.values():
        if query_type in response_format.query_types:
            return response_format
    return None


__all__ = [
    'SectionConfig',
    'ResponseFormat',
    'RESPONSE_FORMATS',
    'get_format_by_id',
    'get_format_by_query_type',
]
