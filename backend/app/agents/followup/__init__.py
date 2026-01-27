"""
똑소리 프로젝트 - 후속 질문 생성 모듈

작성일: 2026-01-28

후속 질문(Followup Questions)과 명확화 질문(Clarifying Questions)을 생성합니다.
사용자가 추가 정보를 얻거나 불명확한 정보를 명확히 할 수 있도록 돕습니다.
"""

from .templates import QUESTION_TEMPLATES, QuestionTemplate
from .generator import FollowupQuestionGenerator


__all__ = [
    'QUESTION_TEMPLATES',
    'QuestionTemplate',
    'FollowupQuestionGenerator',
]
