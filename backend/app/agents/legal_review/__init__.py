from .agent import review_node, review_node_wrapper
from .metrics import ReviewMetrics, ReviewEvalResult, detect_violations, aggregate_review_results
from .reviewer_agent import LegalReviewerAgent, legal_reviewer_agent

__all__ = [
    'review_node',
    'review_node_wrapper',
    'ReviewMetrics',
    'ReviewEvalResult',
    'detect_violations',
    'aggregate_review_results',
    'LegalReviewerAgent',
    'legal_reviewer_agent',
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
