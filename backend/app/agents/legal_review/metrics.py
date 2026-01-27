"""
똑소리 RAG - 검토 에이전트 평가 메트릭 + Prometheus 모니터링

평가 지표:
- Violation Detection Precision: 위반 탐지 정밀도 (목표: ≥0.85)
- Violation Detection Recall: 위반 탐지 재현율 (목표: ≥0.90)
- False Positive Rate: 오탐률 (목표: ≤0.10)
- Filter Effectiveness: 필터링 효과 (목표: ≥0.80)

Prometheus 메트릭:
- legal_review_violations_total: 위반 탐지 총 건수
- legal_review_hallucination_detected_total: Hallucination 탐지 건수
- legal_review_confidence_score: 신뢰도 점수 분포
- legal_review_llm_calls_total: LLM 리뷰 호출 건수
- legal_review_processing_seconds: 리뷰 처리 시간
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Prometheus 메트릭 (지연 초기화)
_prometheus_metrics = None


def _get_prometheus_metrics():
    """Prometheus 메트릭 객체 지연 초기화"""
    global _prometheus_metrics
    if _prometheus_metrics is None:
        try:
            from prometheus_client import Counter, Histogram, Gauge

            _prometheus_metrics = {
                'violations_total': Counter(
                    'legal_review_violations_total',
                    'Total number of violations detected',
                    ['violation_type']
                ),
                'hallucination_detected': Counter(
                    'legal_review_hallucination_detected_total',
                    'Total number of hallucinations detected'
                ),
                'legal_judgment_detected': Counter(
                    'legal_review_legal_judgment_detected_total',
                    'Total number of legal judgments detected'
                ),
                'confidence_score': Histogram(
                    'legal_review_confidence_score',
                    'Confidence score distribution',
                    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
                ),
                'llm_calls': Counter(
                    'legal_review_llm_calls_total',
                    'Total number of LLM review calls',
                    ['status']  # success, failure, skipped
                ),
                'processing_seconds': Histogram(
                    'legal_review_processing_seconds',
                    'Review processing time in seconds',
                    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
                ),
                'reviews_total': Counter(
                    'legal_review_reviews_total',
                    'Total number of reviews processed',
                    ['result']  # passed, failed, filtered
                ),
                'relevance_score': Histogram(
                    'legal_review_relevance_score',
                    'Query-Answer relevance score distribution',
                    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
                ),
            }
            logger.info("[LegalReviewMetrics] Prometheus metrics initialized")
        except ImportError:
            logger.warning("[LegalReviewMetrics] prometheus_client not installed, metrics disabled")
            _prometheus_metrics = {}

    return _prometheus_metrics


class PrometheusReviewMetrics:
    """
    Prometheus 기반 리뷰 메트릭 수집기

    Usage:
        metrics = PrometheusReviewMetrics()
        metrics.record_violation('legal_judgment')
        metrics.record_confidence_score(0.75)
        metrics.record_review_result('passed')
    """

    def record_violation(self, violation_type: str) -> None:
        """위반 탐지 기록"""
        metrics = _get_prometheus_metrics()
        if metrics and 'violations_total' in metrics:
            metrics['violations_total'].labels(violation_type=violation_type).inc()

    def record_hallucination(self) -> None:
        """Hallucination 탐지 기록"""
        metrics = _get_prometheus_metrics()
        if metrics and 'hallucination_detected' in metrics:
            metrics['hallucination_detected'].inc()

    def record_legal_judgment(self) -> None:
        """법적 판단 탐지 기록"""
        metrics = _get_prometheus_metrics()
        if metrics and 'legal_judgment_detected' in metrics:
            metrics['legal_judgment_detected'].inc()

    def record_confidence_score(self, score: float) -> None:
        """신뢰도 점수 기록"""
        metrics = _get_prometheus_metrics()
        if metrics and 'confidence_score' in metrics:
            metrics['confidence_score'].observe(score)

    def record_relevance_score(self, score: float) -> None:
        """관련성 점수 기록"""
        metrics = _get_prometheus_metrics()
        if metrics and 'relevance_score' in metrics:
            metrics['relevance_score'].observe(score)

    def record_llm_call(self, status: str) -> None:
        """LLM 호출 기록 (status: success, failure, skipped)"""
        metrics = _get_prometheus_metrics()
        if metrics and 'llm_calls' in metrics:
            metrics['llm_calls'].labels(status=status).inc()

    def record_processing_time(self, seconds: float) -> None:
        """리뷰 처리 시간 기록"""
        metrics = _get_prometheus_metrics()
        if metrics and 'processing_seconds' in metrics:
            metrics['processing_seconds'].observe(seconds)

    def record_review_result(self, result: str) -> None:
        """리뷰 결과 기록 (result: passed, failed, filtered)"""
        metrics = _get_prometheus_metrics()
        if metrics and 'reviews_total' in metrics:
            metrics['reviews_total'].labels(result=result).inc()


# 싱글톤 인스턴스
_prometheus_review_metrics: Optional[PrometheusReviewMetrics] = None


def get_prometheus_review_metrics() -> PrometheusReviewMetrics:
    """PrometheusReviewMetrics 싱글톤 인스턴스 반환"""
    global _prometheus_review_metrics
    if _prometheus_review_metrics is None:
        _prometheus_review_metrics = PrometheusReviewMetrics()
    return _prometheus_review_metrics


PROHIBITED_PATTERNS = [
    (r'반드시\s+\S+해야\s*합니다', 'absolute_expression'),
    (r'법적으로\s+\S+입니다', 'legal_assertion'),
    (r'위법입니다', 'legal_judgment'),
    (r'불법입니다', 'legal_judgment'),
    (r'불법', 'legal_judgment'),
    (r'위법', 'legal_judgment'),
    (r'소송\s*(을|에서)\s*이길\s*(수\s*있|것)', 'litigation_prediction'),
    (r'승소\s*할\s*(수\s*있|것)', 'litigation_prediction'),
    (r'패소\s*할\s*(수\s*있|것)', 'litigation_prediction'),
    (r'이길\s*수\s*있', 'litigation_prediction'),
    (r'이깁니다', 'litigation_prediction'),
    (r'승소', 'litigation_prediction'),
    (r'패소', 'litigation_prediction'),
    (r'확실히\s+\S+받을\s*수\s*있', 'certainty_expression'),
    (r'100%\s*\S+', 'certainty_expression'),
    (r'100%', 'certainty_expression'),
    (r'당연히\s+\S+해야', 'absolute_expression'),
    (r'무조건\s+\S+', 'absolute_expression'),
    (r'틀림없이\s+\S+', 'certainty_expression'),
    (r'분명히\s+\S+할\s*것입니다', 'certainty_expression'),
    (r'확실히', 'certainty_expression'),
    (r'당연히', 'absolute_expression'),
    (r'무조건', 'absolute_expression'),
    (r'틀림없이', 'certainty_expression'),
    (r'분명히', 'certainty_expression'),
    (r'분명한', 'certainty_expression'),
    (r'반드시', 'absolute_expression'),
    (r'법적으로', 'legal_assertion'),
    (r'법률\s*전문가로서', 'expert_impersonation'),
    (r'변호사\s*입장에서', 'expert_impersonation'),
    (r'법적\s*조언을\s*드리', 'expert_impersonation'),
]


@dataclass
class ReviewEvalResult:
    """단일 검토 평가 결과"""
    item_id: str
    answer_text: str

    is_violation_predicted: bool
    is_violation_expected: bool

    predicted_violations: List[Dict]
    expected_violations: List[Dict]

    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    precision: float
    recall: float
    f1: float

    def to_dict(self) -> Dict:
        return {
            'id': self.item_id,
            'is_violation_predicted': self.is_violation_predicted,
            'is_violation_expected': self.is_violation_expected,
            'predicted_violation_count': len(self.predicted_violations),
            'expected_violation_count': len(self.expected_violations),
            'true_positive': self.true_positive,
            'false_positive': self.false_positive,
            'false_negative': self.false_negative,
            'precision': self.precision,
            'recall': self.recall,
            'f1': self.f1,
        }


def detect_violations(text: str) -> List[Dict]:
    """
    텍스트에서 금지 표현 탐지

    Returns:
        [{'pattern': str, 'type': str, 'match': str}, ...]
    """
    violations = []
    seen_types = set()

    for pattern, violation_type in PROHIBITED_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches and violation_type not in seen_types:
            match_str = matches[0] if isinstance(matches[0], str) else str(matches[0])
            violations.append({
                'pattern': pattern,
                'type': violation_type,
                'match': match_str
            })
            seen_types.add(violation_type)

    return violations


class ReviewMetrics:
    """
    검토 에이전트 평가기

    Usage:
        metrics = ReviewMetrics()
        
        result = metrics.evaluate_item(
            item_id="rev_001",
            answer_text="반드시 환불받으실 수 있습니다.",
            expected_violations=[{"pattern": "반드시", "type": "absolute_expression"}],
            expected_is_violation=True
        )
    """

    def evaluate_item(
        self,
        item_id: str,
        answer_text: str,
        expected_violations: List[Dict],
        expected_is_violation: bool
    ) -> ReviewEvalResult:
        """단일 항목 평가"""

        predicted_violations = detect_violations(answer_text)
        is_violation_predicted = len(predicted_violations) > 0
        is_violation_expected = expected_is_violation

        predicted_types = set(v['type'] for v in predicted_violations)
        expected_types = set(v['type'] for v in expected_violations)

        tp = len(predicted_types & expected_types)
        fp = len(predicted_types - expected_types)
        fn = len(expected_types - predicted_types)
        tn = 1 if (not predicted_types and not expected_types) else 0

        precision = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if not expected_types else 0.0)
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return ReviewEvalResult(
            item_id=item_id,
            answer_text=answer_text,
            is_violation_predicted=is_violation_predicted,
            is_violation_expected=is_violation_expected,
            predicted_violations=predicted_violations,
            expected_violations=expected_violations,
            true_positive=tp,
            false_positive=fp,
            false_negative=fn,
            true_negative=tn,
            precision=precision,
            recall=recall,
            f1=f1,
        )


def aggregate_review_results(results: List[ReviewEvalResult]) -> Dict[str, float]:
    """
    여러 평가 결과를 집계하여 평균 메트릭 계산

    Returns:
        {
            'violation_detection_precision': float,
            'violation_detection_recall': float,
            'violation_detection_f1': float,
            'false_positive_rate': float,
            'binary_accuracy': float,
            'sample_count': int,
        }
    """
    if not results:
        return {}

    n = len(results)

    total_tp = sum(r.true_positive for r in results)
    total_fp = sum(r.false_positive for r in results)
    total_fn = sum(r.false_negative for r in results)
    total_tn = sum(r.true_negative for r in results)

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = 2 * overall_precision * overall_recall / (overall_precision + overall_recall) if (overall_precision + overall_recall) > 0 else 0.0

    fpr = total_fp / (total_fp + total_tn) if (total_fp + total_tn) > 0 else 0.0

    binary_correct = sum(
        1 for r in results
        if r.is_violation_predicted == r.is_violation_expected
    )
    binary_accuracy = binary_correct / n

    return {
        'violation_detection_precision': round(overall_precision, 4),
        'violation_detection_recall': round(overall_recall, 4),
        'violation_detection_f1': round(overall_f1, 4),
        'false_positive_rate': round(fpr, 4),
        'binary_accuracy': round(binary_accuracy, 4),
        'sample_count': n,
    }
