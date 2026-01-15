"""
똑소리 프로젝트 - 도메인 분류기
S2-4: 키워드 기반 기관 분류 로직

우선순위:
1. FSS (금융) - 전문가 상담 권유
2. K_MEDI (의료) - 전문가 상담 권유
3. KCDRC (콘텐츠)
4. ECMC (개인간 거래)
5. KCA (기본값)
"""

from dataclasses import dataclass
from typing import List, Optional

from .config import (
    AgencyCode,
    AGENCY_INFO,
    CONTENT_KEYWORDS,
    INDIVIDUAL_KEYWORDS,
    FINANCE_KEYWORDS,
    MEDICAL_KEYWORDS,
)


@dataclass
class ClassificationResult:
    agency: AgencyCode
    dispute_type: str
    reason: str
    confidence: float
    matched_keywords: List[str]
    is_restricted: bool


class DomainClassifier:
    FINANCE_THRESHOLD = 2
    MEDICAL_THRESHOLD = 2
    CONTENT_THRESHOLD = 1
    INDIVIDUAL_THRESHOLD = 1

    def classify(self, query: str) -> ClassificationResult:
        query_lower = query.lower()

        finance_matches = self._find_matches(query_lower, FINANCE_KEYWORDS)
        if len(finance_matches) >= self.FINANCE_THRESHOLD:
            return ClassificationResult(
                agency='FSS',
                dispute_type='finance',
                reason=f"금융 관련 분쟁으로 판단됩니다 (키워드: {', '.join(finance_matches[:3])})",
                confidence=min(0.6 + len(finance_matches) * 0.08, 0.95),
                matched_keywords=finance_matches,
                is_restricted=True,
            )

        medical_matches = self._find_matches(query_lower, MEDICAL_KEYWORDS)
        if len(medical_matches) >= self.MEDICAL_THRESHOLD:
            return ClassificationResult(
                agency='K_MEDI',
                dispute_type='medical',
                reason=f"의료 관련 분쟁으로 판단됩니다 (키워드: {', '.join(medical_matches[:3])})",
                confidence=min(0.6 + len(medical_matches) * 0.08, 0.95),
                matched_keywords=medical_matches,
                is_restricted=True,
            )

        content_matches = self._find_matches(query_lower, CONTENT_KEYWORDS)
        if len(content_matches) >= self.CONTENT_THRESHOLD:
            return ClassificationResult(
                agency='KCDRC',
                dispute_type='contents',
                reason=f"콘텐츠 관련 분쟁으로 판단됩니다 (키워드: {', '.join(content_matches[:3])})",
                confidence=min(0.6 + len(content_matches) * 0.1, 0.95),
                matched_keywords=content_matches,
                is_restricted=False,
            )

        individual_matches = self._find_matches(query_lower, INDIVIDUAL_KEYWORDS)
        if len(individual_matches) >= self.INDIVIDUAL_THRESHOLD:
            return ClassificationResult(
                agency='ECMC',
                dispute_type='1:1',
                reason=f"개인간 거래 분쟁으로 판단됩니다 (키워드: {', '.join(individual_matches[:3])})",
                confidence=min(0.6 + len(individual_matches) * 0.1, 0.95),
                matched_keywords=individual_matches,
                is_restricted=False,
            )

        return ClassificationResult(
            agency='KCA',
            dispute_type='1:N',
            reason='일반 소비자 분쟁으로 판단됩니다 (사업자 대 소비자)',
            confidence=0.7,
            matched_keywords=[],
            is_restricted=False,
        )

    def _find_matches(self, query: str, keywords: List[str]) -> List[str]:
        return [kw for kw in keywords if kw in query]

    def get_agency_info(self, agency: AgencyCode) -> dict:
        return dict(AGENCY_INFO.get(agency, AGENCY_INFO['KCA']))


_classifier = DomainClassifier()


def classify_domain(query: str) -> ClassificationResult:
    return _classifier.classify(query)
