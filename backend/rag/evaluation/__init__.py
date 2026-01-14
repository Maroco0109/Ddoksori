"""
똑소리 RAG 평가 모듈

검색(Retrieval) 품질 평가를 위한 메트릭 및 도구 제공
- LLM 호출 없이 빠르고 저렴하게 실행
- 섹션별 검색 품질 측정 (nDCG, MRR, Precision, Recall)
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

__all__ = [
    'RetrievalMetrics',
    'EvaluationResult',
    'SectionMetrics',
    'calculate_ndcg',
    'calculate_mrr',
    'calculate_precision_at_k',
    'calculate_recall',
    'calculate_domain_accuracy',
    'calculate_hit_rate',
    'aggregate_results'
]
