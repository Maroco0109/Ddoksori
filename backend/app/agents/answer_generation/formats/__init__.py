"""
똑소리 프로젝트 - 답변 형식 모듈

작성일: 2026-01-28

유연한 답변 형식을 지원하는 모듈입니다.
쿼리 타입과 검색 결과에 따라 적절한 답변 형식을 선택합니다.
"""

from .config import (
    SectionConfig,
    ResponseFormat,
    RESPONSE_FORMATS,
)
from .selector import FormatSelector
from .prompt_builder import PromptBuilder


__all__ = [
    'SectionConfig',
    'ResponseFormat',
    'RESPONSE_FORMATS',
    'FormatSelector',
    'PromptBuilder',
]
