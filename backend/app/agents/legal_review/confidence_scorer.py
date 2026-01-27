"""
똑소리 프로젝트 - 신뢰도 점수 계산 모듈 (Confidence Scorer)

작성일: 2026-01-27

[역할 및 책임]
생성된 답변의 종합 신뢰도 점수를 계산합니다.
출처 커버리지, 관련성, 인용 정확도를 종합하여 0.0 ~ 1.0 점수를 산출합니다.

[가중치 구성]
- 출처 커버리지 (Source Coverage): 40%
- Query-Answer 관련성 (Relevance): 30%
- 인용 정확도 (Citation Accuracy): 30%
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceScoreResult:
    """
    신뢰도 점수 계산 결과

    Attributes:
        total_score: 종합 신뢰도 점수 (0.0 ~ 1.0)
        source_coverage_score: 출처 커버리지 점수
        relevance_score: 관련성 점수
        citation_accuracy_score: 인용 정확도 점수
        grade: 등급 (A/B/C/D/F)
        is_reliable: 신뢰 가능 여부 (0.6 이상)
    """
    total_score: float
    source_coverage_score: float
    relevance_score: float
    citation_accuracy_score: float
    grade: str
    is_reliable: bool


class ConfidenceScorer:
    """
    종합 신뢰도 점수 계산기

    Usage:
        scorer = ConfidenceScorer()
        result = scorer.calculate(
            answer="답변 텍스트",
            sources=[{"content": "..."}],
            relevance_score=0.75,
            citation_accuracy=0.9
        )
        print(f"신뢰도: {result.total_score:.2f} ({result.grade})")
    """

    # 가중치 설정
    WEIGHT_SOURCE_COVERAGE = 0.4
    WEIGHT_RELEVANCE = 0.3
    WEIGHT_CITATION_ACCURACY = 0.3

    # 등급 기준
    GRADE_THRESHOLDS = {
        'A': 0.85,
        'B': 0.70,
        'C': 0.55,
        'D': 0.40,
        'F': 0.0,
    }

    # 신뢰 가능 임계값
    RELIABILITY_THRESHOLD = 0.6

    def calculate(
        self,
        answer: str,
        sources: List[Dict],
        relevance_score: float = 0.5,
        citation_accuracy: float = 0.5
    ) -> ConfidenceScoreResult:
        """
        종합 신뢰도 점수 계산

        Args:
            answer: 생성된 답변 텍스트
            sources: 검색된 출처 문서 리스트
            relevance_score: Query-Answer 관련성 점수 (0.0 ~ 1.0)
            citation_accuracy: 인용 정확도 (0.0 ~ 1.0)

        Returns:
            ConfidenceScoreResult: 신뢰도 점수 결과
        """
        # 출처 커버리지 계산
        source_coverage = self._calculate_source_coverage(answer, sources)

        # 종합 점수 계산
        total_score = (
            source_coverage * self.WEIGHT_SOURCE_COVERAGE +
            relevance_score * self.WEIGHT_RELEVANCE +
            citation_accuracy * self.WEIGHT_CITATION_ACCURACY
        )

        # 범위 제한
        total_score = min(1.0, max(0.0, total_score))

        # 등급 산정
        grade = self._get_grade(total_score)

        # 신뢰 가능 여부
        is_reliable = total_score >= self.RELIABILITY_THRESHOLD

        logger.debug(
            f"[ConfidenceScorer] score={total_score:.3f}, grade={grade}, "
            f"coverage={source_coverage:.3f}, relevance={relevance_score:.3f}, "
            f"citation={citation_accuracy:.3f}"
        )

        return ConfidenceScoreResult(
            total_score=total_score,
            source_coverage_score=source_coverage,
            relevance_score=relevance_score,
            citation_accuracy_score=citation_accuracy,
            grade=grade,
            is_reliable=is_reliable,
        )

    def _calculate_source_coverage(
        self,
        answer: str,
        sources: List[Dict]
    ) -> float:
        """
        출처 커버리지 점수 계산

        답변이 검색된 출처에 얼마나 기반하는지 측정합니다.
        - 출처가 없으면 0.0
        - 출처가 있고 답변이 짧으면 부분 점수
        - 출처와 답변 길이의 비율로 커버리지 추정

        Args:
            answer: 생성된 답변
            sources: 검색된 출처 문서 리스트

        Returns:
            커버리지 점수 (0.0 ~ 1.0)
        """
        if not answer or not sources:
            return 0.0

        # 출처 총 길이
        source_total_length = 0
        for source in sources:
            content = source.get('content', '') or source.get('text', '')
            source_total_length += len(content)

        if source_total_length == 0:
            return 0.0

        # 답변 길이 대비 출처 길이 비율
        answer_length = len(answer)

        # 출처가 답변보다 충분히 길면 좋은 커버리지
        # 이상적으로 출처는 답변의 2~5배 정도가 적당
        coverage_ratio = source_total_length / (answer_length + 1)

        if coverage_ratio >= 3.0:
            score = 1.0
        elif coverage_ratio >= 1.5:
            score = 0.8
        elif coverage_ratio >= 0.5:
            score = 0.6
        else:
            score = 0.3

        # 출처 개수 보너스 (최대 5개까지)
        source_count_bonus = min(len(sources) * 0.05, 0.25)
        score = min(1.0, score + source_count_bonus)

        return score

    def _get_grade(self, score: float) -> str:
        """점수를 등급으로 변환"""
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return 'F'


# 싱글톤 인스턴스
_confidence_scorer: Optional[ConfidenceScorer] = None


def get_confidence_scorer() -> ConfidenceScorer:
    """
    ConfidenceScorer 싱글톤 인스턴스 반환

    Returns:
        ConfidenceScorer: 신뢰도 점수 계산기 인스턴스
    """
    global _confidence_scorer
    if _confidence_scorer is None:
        _confidence_scorer = ConfidenceScorer()
    return _confidence_scorer


__all__ = [
    'ConfidenceScoreResult',
    'ConfidenceScorer',
    'get_confidence_scorer',
]
