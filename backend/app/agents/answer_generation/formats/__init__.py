"""
똑소리 프로젝트 - 답변 형식 모듈

작성일: 2026-01-28
수정일: 2026-02-01

유연한 답변 형식을 지원하는 모듈입니다.
쿼리 타입, 검색 결과, 온보딩 컨텍스트에 따라 적절한 답변 형식을 선택합니다.

[형식 종류] (7개)
1. law_response: 법령 질문 - 계층적 법령 안내
2. law_onboarding: 법령+온보딩 - 상황별 법령 적용 설명
3. criteria_response: 기준 질문 - 분쟁해결기준 구조화 안내
4. case_response: 사례 질문 - 유사 사례 분석
5. comprehensive_dispute: 종합 분쟁 - 법령+기준+절차 종합 안내
6. general_greeting: 일반/인사 - 자연스러운 대화 + 분쟁 상담 유도
7. info_only: 제한 영역 - 전문 기관 안내
"""

from .config import (
    RESPONSE_FORMATS,
    ResponseFormat,
    SectionConfig,
    get_format_by_id,
    get_format_by_query_type,
)
from .prompt_builder import DISCLAIMER, PromptBuilder
from .selector import FormatSelector

__all__ = [
    "SectionConfig",
    "ResponseFormat",
    "RESPONSE_FORMATS",
    "get_format_by_id",
    "get_format_by_query_type",
    "FormatSelector",
    "PromptBuilder",
    "DISCLAIMER",
]
