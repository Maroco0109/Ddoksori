"""
똑소리 프로젝트 - 도메인 설정 모듈
작성일: 2026-01-15
S2-4: 도메인 설정 세분화 (FSS, K-Medi 추가)

기관 정보, 키워드 상수, 도메인 분류 로직을 통합 관리합니다.
"""

from .classifier import DomainClassifier, classify_domain
from .config import (
    AGENCY_CODES,
    AGENCY_INFO,
    CONTENT_KEYWORDS,
    CRITERIA_KEYWORDS,
    FINANCE_KEYWORDS,
    INDIVIDUAL_KEYWORDS,
    LAW_KEYWORDS,
    MEDICAL_KEYWORDS,
)

__all__ = [
    "AGENCY_INFO",
    "AGENCY_CODES",
    "CONTENT_KEYWORDS",
    "INDIVIDUAL_KEYWORDS",
    "FINANCE_KEYWORDS",
    "MEDICAL_KEYWORDS",
    "LAW_KEYWORDS",
    "CRITERIA_KEYWORDS",
    "DomainClassifier",
    "classify_domain",
]
