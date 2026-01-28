"""
query_analysis agent module

모듈 구조 (Refactored 2026-01-28):
- constants.py: 키워드, 패턴, 매핑 상수
- detectors.py: 도메인/모호함/시스템메타 쿼리 감지
- classifiers.py: 쿼리 유형 분류, 모드 결정
- extractors.py: 정보/키워드 추출, 정규화
- expanders.py: 쿼리 확장, 다중 검색 쿼리 생성
- agent.py: query_analysis_node (메인 진입점)
- classifier.py: gpt-4o-mini Intent Classifier (LLM 기반)
- tools.py: search tool schemas
- metrics.py: metric collection
"""

# Main entry point
from .agent import query_analysis_node

# Constants (commonly used)
from .constants import (
    QUERY_TYPE_TO_RETRIEVERS,
    RESTRICTED_DOMAIN_KEYWORDS,
    RESTRICTED_DOMAIN_AGENCIES,
    PROCEDURE_KEYWORDS,
    INDIVIDUAL_KEYWORDS,
    LAW_KEYWORDS,
    CRITERIA_KEYWORDS,
    SYSTEM_META_KEYWORDS,
    COMMON_PRODUCTS,
    DISPUTE_VERBS,
    VERB_SYNONYMS,
    DISPUTE_INTENT_KEYWORDS,
    AMBIGUOUS_QUERY_PATTERNS,  # backward compat for tests
)

# Detectors
from .detectors import (
    is_ambiguous_query,
    is_system_meta_query,
    detect_restricted_domain,
    is_procedure_query,
    should_promote_to_rag,
)

# Classifiers
from .classifiers import (
    classify_query_type,
    classify_mode,
    QueryType,
)

# Extractors
from .extractors import (
    extract_info_from_message,
    extract_keywords,
    normalize_query,
    check_missing_onboarding_fields,
    determine_agency_hint,
    get_missing_fields_description,
)

# Expanders
from .expanders import (
    expand_query_by_type,
    generate_search_queries,
    create_synonym_variant_query,
)

# LLM-based Intent Classifier
from .classifier import (
    IntentClassifier,
    HybridIntentClassifier,
    IntentClassificationResult,
    classify_intent,
    get_intent_classifier,
)

# Backward compatibility alias
_classify_query_type = classify_query_type

__all__ = [
    # Main entry point
    "query_analysis_node",
    # Constants
    "QUERY_TYPE_TO_RETRIEVERS",
    "RESTRICTED_DOMAIN_KEYWORDS",
    "RESTRICTED_DOMAIN_AGENCIES",
    "PROCEDURE_KEYWORDS",
    "INDIVIDUAL_KEYWORDS",
    "LAW_KEYWORDS",
    "CRITERIA_KEYWORDS",
    "SYSTEM_META_KEYWORDS",
    "COMMON_PRODUCTS",
    "DISPUTE_VERBS",
    "VERB_SYNONYMS",
    "DISPUTE_INTENT_KEYWORDS",
    "AMBIGUOUS_QUERY_PATTERNS",
    # Detectors
    "is_ambiguous_query",
    "is_system_meta_query",
    "detect_restricted_domain",
    "is_procedure_query",
    "should_promote_to_rag",
    # Classifiers
    "classify_query_type",
    "classify_mode",
    "QueryType",
    "_classify_query_type",  # backward compat
    # Extractors
    "extract_info_from_message",
    "extract_keywords",
    "normalize_query",
    "check_missing_onboarding_fields",
    "determine_agency_hint",
    "get_missing_fields_description",
    # Expanders
    "expand_query_by_type",
    "generate_search_queries",
    "create_synonym_variant_query",
    # LLM Classifier
    "IntentClassifier",
    "HybridIntentClassifier",
    "IntentClassificationResult",
    "classify_intent",
    "get_intent_classifier",
]
