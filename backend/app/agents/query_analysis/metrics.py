"""
똑소리 RAG - 질의분석 에이전트 평가 메트릭

평가 지표:
- Query Type Accuracy: 질의 유형 분류 정확도 (목표: ≥0.90)
- Keyword Precision: 추출 키워드 정밀도 (목표: ≥0.80)
- Keyword Recall: 추출 키워드 재현율 (목표: ≥0.70)
- Agency Hint Accuracy: 기관 추천 힌트 정확도 (목표: ≥0.85)
- Missing Field Detection F1: 누락 필드 탐지 F1 (목표: ≥0.85)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


@dataclass
class QueryAnalysisEvalResult:
    """단일 질의분석 평가 결과"""

    item_id: str
    query: str
    category: str

    query_type_correct: bool
    predicted_query_type: str
    expected_query_type: str

    keyword_precision: float
    keyword_recall: float
    keyword_f1: float
    predicted_keywords: List[str]
    expected_keywords: List[str]

    agency_hint_correct: bool
    predicted_agency_hint: Optional[str]
    expected_agency_hint: Optional[str]

    missing_field_precision: float
    missing_field_recall: float
    missing_field_f1: float
    predicted_missing_fields: List[str]
    expected_missing_fields: List[str]

    def to_dict(self) -> Dict:
        return {
            "id": self.item_id,
            "query": self.query,
            "category": self.category,
            "query_type_correct": self.query_type_correct,
            "predicted_query_type": self.predicted_query_type,
            "expected_query_type": self.expected_query_type,
            "keyword_precision": self.keyword_precision,
            "keyword_recall": self.keyword_recall,
            "keyword_f1": self.keyword_f1,
            "agency_hint_correct": self.agency_hint_correct,
            "predicted_agency_hint": self.predicted_agency_hint,
            "expected_agency_hint": self.expected_agency_hint,
            "missing_field_precision": self.missing_field_precision,
            "missing_field_recall": self.missing_field_recall,
            "missing_field_f1": self.missing_field_f1,
        }


def calculate_set_precision(predicted: Set[str], expected: Set[str]) -> float:
    """정밀도 계산: predicted 중 expected에 포함된 비율"""
    if not predicted:
        return 1.0 if not expected else 0.0
    return len(predicted & expected) / len(predicted)


def calculate_set_recall(predicted: Set[str], expected: Set[str]) -> float:
    """재현율 계산: expected 중 predicted에 포함된 비율"""
    if not expected:
        return 1.0
    return len(predicted & expected) / len(expected)


def calculate_f1(precision: float, recall: float) -> float:
    """F1 스코어 계산"""
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


class QueryAnalysisMetrics:
    """
    질의분석 에이전트 평가기

    Usage:
        metrics = QueryAnalysisMetrics()

        result = metrics.evaluate_item(
            item_id="qa_001",
            query="소비자보호법 제17조 환불 규정",
            category="법령조회",
            predicted_query_type="law",
            expected_query_type="law",
            predicted_keywords=["소비자보호법", "17조", "환불"],
            expected_keywords=["소비자보호법", "17조", "환불", "규정"],
            predicted_agency_hint="KCA",
            expected_agency_hint="KCA",
            predicted_missing_fields=[],
            expected_missing_fields=[]
        )
    """

    def evaluate_item(
        self,
        item_id: str,
        query: str,
        category: str,
        predicted_query_type: str,
        expected_query_type: str,
        predicted_keywords: List[str],
        expected_keywords: List[str],
        predicted_agency_hint: Optional[str],
        expected_agency_hint: Optional[str],
        predicted_missing_fields: List[str],
        expected_missing_fields: List[str],
    ) -> QueryAnalysisEvalResult:
        """단일 항목 평가"""

        query_type_correct = predicted_query_type == expected_query_type

        pred_kw_set = set(predicted_keywords)
        exp_kw_set = set(expected_keywords)
        keyword_precision = calculate_set_precision(pred_kw_set, exp_kw_set)
        keyword_recall = calculate_set_recall(pred_kw_set, exp_kw_set)
        keyword_f1 = calculate_f1(keyword_precision, keyword_recall)

        agency_hint_correct = predicted_agency_hint == expected_agency_hint

        pred_mf_set = set(predicted_missing_fields)
        exp_mf_set = set(expected_missing_fields)
        missing_field_precision = calculate_set_precision(pred_mf_set, exp_mf_set)
        missing_field_recall = calculate_set_recall(pred_mf_set, exp_mf_set)
        missing_field_f1 = calculate_f1(missing_field_precision, missing_field_recall)

        return QueryAnalysisEvalResult(
            item_id=item_id,
            query=query,
            category=category,
            query_type_correct=query_type_correct,
            predicted_query_type=predicted_query_type,
            expected_query_type=expected_query_type,
            keyword_precision=keyword_precision,
            keyword_recall=keyword_recall,
            keyword_f1=keyword_f1,
            predicted_keywords=predicted_keywords,
            expected_keywords=expected_keywords,
            agency_hint_correct=agency_hint_correct,
            predicted_agency_hint=predicted_agency_hint,
            expected_agency_hint=expected_agency_hint,
            missing_field_precision=missing_field_precision,
            missing_field_recall=missing_field_recall,
            missing_field_f1=missing_field_f1,
            predicted_missing_fields=predicted_missing_fields,
            expected_missing_fields=expected_missing_fields,
        )


def aggregate_query_analysis_results(
    results: List[QueryAnalysisEvalResult],
) -> Dict[str, float]:
    """
    여러 평가 결과를 집계하여 평균 메트릭 계산

    Returns:
        {
            'query_type_accuracy': float,
            'keyword_precision_mean': float,
            'keyword_recall_mean': float,
            'keyword_f1_mean': float,
            'agency_hint_accuracy': float,
            'missing_field_f1_mean': float,
            'sample_count': int,
        }
    """
    if not results:
        return {}

    n = len(results)

    query_type_correct_count = sum(1 for r in results if r.query_type_correct)
    agency_hint_correct_count = sum(1 for r in results if r.agency_hint_correct)

    keyword_precision_sum = sum(r.keyword_precision for r in results)
    keyword_recall_sum = sum(r.keyword_recall for r in results)
    keyword_f1_sum = sum(r.keyword_f1 for r in results)

    missing_field_f1_sum = sum(r.missing_field_f1 for r in results)

    return {
        "query_type_accuracy": round(query_type_correct_count / n, 4),
        "keyword_precision_mean": round(keyword_precision_sum / n, 4),
        "keyword_recall_mean": round(keyword_recall_sum / n, 4),
        "keyword_f1_mean": round(keyword_f1_sum / n, 4),
        "agency_hint_accuracy": round(agency_hint_correct_count / n, 4),
        "missing_field_f1_mean": round(missing_field_f1_sum / n, 4),
        "sample_count": n,
    }
