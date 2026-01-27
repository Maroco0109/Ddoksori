"""
똑소리 프로젝트 - 답변 형식 설정

작성일: 2026-01-28

[역할 및 책임]
답변 형식(ResponseFormat)을 정의하고 관리합니다.
각 형식은 쿼리 타입에 따라 다른 섹션 구성과 톤을 가집니다.

[형식 종류]
1. full_dispute: 분쟁/법률 조회 - 유사사례 + 법령 + 기관정보 (형식적)
2. simple_general: 일반 대화 - 섹션 없는 자연스러운 대화 (친근함)
3. info_only: 제한 영역 - 기관 안내 + 참고 사례 (정보제공)
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
    """
    format_id: str
    query_types: List[str]
    sections: List[SectionConfig]
    include_disclaimer: bool
    tone: Literal['formal', 'friendly', 'informative']


# ============================================================
# 답변 형식 정의
# ============================================================

RESPONSE_FORMATS: Dict[str, ResponseFormat] = {
    'full_dispute': ResponseFormat(
        format_id='full_dispute',
        query_types=['dispute', 'law_inquiry'],
        sections=[
            SectionConfig(
                section_id='similar_cases',
                required=True,
                conditions={'has_cases': True}
            ),
            SectionConfig(
                section_id='legal_basis',
                required=True,
                conditions={'has_laws': True}
            ),
            SectionConfig(
                section_id='agency_info',
                required=False,
                conditions=None
            ),
        ],
        include_disclaimer=True,
        tone='formal'
    ),

    'simple_general': ResponseFormat(
        format_id='simple_general',
        query_types=['general', 'greeting', 'thanks', 'system_meta'],
        sections=[],
        include_disclaimer=False,
        tone='friendly'
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
        tone='informative'
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
