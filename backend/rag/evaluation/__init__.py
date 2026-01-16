"""
똑소리 RAG 평가 모듈

에이전트별 품질 평가를 위한 메트릭 및 도구 제공
- LLM 호출 없이 빠르고 저렴하게 실행
- Retrieval: nDCG, MRR, Precision, Recall
- Query Analysis: Query Type Accuracy, Keyword P/R, Agency Hint Accuracy
- Review: Violation Detection Precision/Recall, FPR
"""

from .retrieval_metrics import (
    RetrievalMetrics,
    EvaluationResult,
    SectionMetrics,
    calculate_ndcg,
    calculate_mrr,
    calculate_precision_at_k,
    calculate_recall,
    calculate_domain_accuracy,
    calculate_hit_rate,
    aggregate_results
)

from .query_analysis_metrics import (
    QueryAnalysisMetrics,
    QueryAnalysisEvalResult,
    aggregate_query_analysis_results,
)

from .review_metrics import (
    ReviewMetrics,
    ReviewEvalResult,
    aggregate_review_results,
    detect_violations,
)

__all__ = [
    # Retrieval
    'RetrievalMetrics',
    'EvaluationResult',
    'SectionMetrics',
    'calculate_ndcg',
    'calculate_mrr',
    'calculate_precision_at_k',
    'calculate_recall',
    'calculate_domain_accuracy',
    'calculate_hit_rate',
    'aggregate_results',
    # Query Analysis
    'QueryAnalysisMetrics',
    'QueryAnalysisEvalResult',
    'aggregate_query_analysis_results',
    # Review
    'ReviewMetrics',
    'ReviewEvalResult',
    'aggregate_review_results',
    'detect_violations',
]
