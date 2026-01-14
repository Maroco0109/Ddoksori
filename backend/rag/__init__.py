"""
똑소리 RAG 모듈
"""

from .retriever import RAGRetriever, SearchResult
from .generator import RAGGenerator
from .hybrid_retriever import HybridRetriever
from .logger import RAGLogger, get_rag_logger
from .specialized_retrievers import (
    LawRetriever,
    CriteriaRetriever,
    CaseRetriever,
    AgencyClassifier,
    StructuredRetriever,
    LawSearchResult,
    CriteriaSearchResult
)

# Evaluation module
from .evaluation import (
    RetrievalMetrics,
    calculate_ndcg,
    calculate_mrr,
    calculate_precision_at_k,
    calculate_recall,
    calculate_domain_accuracy,
    calculate_hit_rate
)

__all__ = [
    'RAGRetriever',
    'SearchResult',
    'RAGGenerator',
    'HybridRetriever',
    'RAGLogger',
    'get_rag_logger',
    # Specialized Retrievers
    'LawRetriever',
    'CriteriaRetriever',
    'CaseRetriever',
    'AgencyClassifier',
    'StructuredRetriever',
    'LawSearchResult',
    'CriteriaSearchResult',
    # Evaluation
    'RetrievalMetrics',
    'calculate_ndcg',
    'calculate_mrr',
    'calculate_precision_at_k',
    'calculate_recall',
    'calculate_domain_accuracy',
    'calculate_hit_rate'
]
