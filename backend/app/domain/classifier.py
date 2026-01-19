"""
똑소리 프로젝트 - 도메인 분류기
S2-4: 키워드 기반 기관 분류 로직

분류 우선순위:
1. Restricted 도메인 (FSS, K_MEDI, KOPICO) - 동등 우선순위, 매칭 점수 기반 결정
2. KCDRC (콘텐츠)
3. ECMC (개인간 거래)
4. KCA (기본값)
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import (
    AgencyCode,
    AGENCY_INFO,
    CONTENT_KEYWORDS,
    INDIVIDUAL_KEYWORDS,
    FINANCE_KEYWORDS,
    MEDICAL_KEYWORDS,
    PRIVACY_KEYWORDS,
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
    RESTRICTED_THRESHOLD = 2
    CONTENT_THRESHOLD = 1
    INDIVIDUAL_THRESHOLD = 1

    RESTRICTED_DOMAINS: List[Tuple[AgencyCode, str, str, List[str]]] = [
        ('FSS', 'finance', '금융', FINANCE_KEYWORDS),
        ('K_MEDI', 'medical', '의료', MEDICAL_KEYWORDS),
        ('KOPICO', 'privacy', '개인정보', PRIVACY_KEYWORDS),
    ]

    def classify(self, query: str) -> ClassificationResult:
        query_lower = query.lower()

        restricted_result = self._classify_restricted_domains(query_lower)
        if restricted_result:
            return restricted_result

        content_matches = self._find_matches_with_boundary(query_lower, CONTENT_KEYWORDS)
        if len(content_matches) >= self.CONTENT_THRESHOLD:
            return ClassificationResult(
                agency='KCDRC',
                dispute_type='contents',
                reason=f"콘텐츠 관련 분쟁으로 판단됩니다 (키워드: {', '.join(content_matches[:3])})",
                confidence=min(0.6 + len(content_matches) * 0.1, 0.95),
                matched_keywords=content_matches,
                is_restricted=False,
            )

        individual_matches = self._find_matches_with_boundary(query_lower, INDIVIDUAL_KEYWORDS)
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

    def _classify_restricted_domains(self, query: str) -> Optional[ClassificationResult]:
        candidates: List[Tuple[AgencyCode, str, str, List[str], float]] = []

        for agency, dispute_type, domain_name, keywords in self.RESTRICTED_DOMAINS:
            matches = self._find_matches_with_boundary(query, keywords)
            if len(matches) >= self.RESTRICTED_THRESHOLD:
                score = len(matches) + sum(len(m) for m in matches) * 0.01
                candidates.append((agency, dispute_type, domain_name, matches, score))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[4], reverse=True)
        agency, dispute_type, domain_name, matches, score = candidates[0]

        return ClassificationResult(
            agency=agency,
            dispute_type=dispute_type,
            reason=f"{domain_name} 관련 분쟁으로 판단됩니다 (키워드: {', '.join(matches[:3])})",
            confidence=min(0.6 + len(matches) * 0.08, 0.95),
            matched_keywords=matches,
            is_restricted=True,
        )

    def _find_matches_with_boundary(self, query: str, keywords: List[str]) -> List[str]:
        matches = []
        for kw in keywords:
            if kw in query:
                matches.append(kw)
        return matches

    def get_agency_info(self, agency: AgencyCode) -> dict:
        return dict(AGENCY_INFO.get(agency, AGENCY_INFO['KCA']))


_classifier = DomainClassifier()


def classify_domain(query: str) -> ClassificationResult:
    return _classifier.classify(query)
