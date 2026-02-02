from .agent import (
    CitationVerifyResult,
    review_node,
    review_node_wrapper,
    verify_citation_accuracy,
)
from .confidence_scorer import (
    ConfidenceScorer,
    ConfidenceScoreResult,
    get_confidence_scorer,
)
from .metrics import (
    PrometheusReviewMetrics,
    ReviewEvalResult,
    ReviewMetrics,
    aggregate_review_results,
    detect_violations,
    get_prometheus_review_metrics,
)
from .relevance_checker import (
    RelevanceChecker,
    RelevanceResult,
    get_relevance_checker,
)
from .reviewer_agent import LegalReviewerAgent, legal_reviewer_agent

__all__ = [
    # Legacy
    "review_node",
    "review_node_wrapper",
    # Metrics
    "ReviewMetrics",
    "ReviewEvalResult",
    "detect_violations",
    "aggregate_review_results",
    # Prometheus Metrics (P3)
    "PrometheusReviewMetrics",
    "get_prometheus_review_metrics",
    # Agent
    "LegalReviewerAgent",
    "legal_reviewer_agent",
    # Relevance Checker (P0)
    "RelevanceChecker",
    "RelevanceResult",
    "get_relevance_checker",
    # Citation Accuracy (P0)
    "verify_citation_accuracy",
    "CitationVerifyResult",
    # Confidence Scorer (P3)
    "ConfidenceScorer",
    "ConfidenceScoreResult",
    "get_confidence_scorer",
]


def get_hybrid_reviewer():
    from .llm_reviewer import HybridLegalReviewer

    return HybridLegalReviewer


def get_hybrid_review_node():
    from .llm_reviewer import hybrid_review_node

    return hybrid_review_node


def get_hybrid_review_node_wrapper():
    from .llm_reviewer import hybrid_review_node_wrapper

    return hybrid_review_node_wrapper
