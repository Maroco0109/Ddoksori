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

# LLM-based Intent Classifier
from .classifier import (
    HybridIntentClassifier,
    IntentClassificationResult,
    IntentClassifier,
    classify_intent,
    get_intent_classifier,
)

# Classifiers
from .classifiers import (
    QueryType,
    classify_mode,
    classify_query_type,
    classify_query_type_with_confidence,
)

# Constants (commonly used)
from .constants import AMBIGUOUS_QUERY_PATTERNS  # backward compat for tests
from .constants import (
    COMMON_PRODUCTS,
    CRITERIA_KEYWORDS,
    DISPUTE_INTENT_KEYWORDS,
    DISPUTE_VERBS,
    INDIVIDUAL_KEYWORDS,
    LAW_KEYWORDS,
    META_CONVERSATIONAL_KEYWORDS,
    META_CONVERSATIONAL_PATTERNS,
    PROCEDURE_KEYWORDS,
    QUERY_TYPE_TO_RETRIEVERS,
    RESTRICTED_DOMAIN_AGENCIES,
    RESTRICTED_DOMAIN_KEYWORDS,
    SYSTEM_META_KEYWORDS,
    VERB_SYNONYMS,
)

# Detectors
from .detectors import (
    detect_restricted_domain,
    is_ambiguous_query,
    is_meta_conversational,
    is_procedure_query,
    is_system_meta_query,
    should_promote_to_rag,
)

# Expanders
from .expanders import (
    create_synonym_variant_query,
    expand_query_by_type,
    generate_search_queries,
)

# Extractors
from .extractors import (
    check_missing_onboarding_fields,
    determine_agency_hint,
    extract_info_from_message,
    extract_keywords,
    get_missing_fields_description,
    normalize_query,
)

# LLM Fallback Classifier (Issue #3: Hybrid Intent Classification)
from .llm_classifier import llm_classify

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
    "META_CONVERSATIONAL_PATTERNS",
    "META_CONVERSATIONAL_KEYWORDS",
    # Detectors
    "is_ambiguous_query",
    "is_system_meta_query",
    "detect_restricted_domain",
    "is_procedure_query",
    "should_promote_to_rag",
    "is_meta_conversational",
    # Classifiers
    "classify_query_type",
    "classify_query_type_with_confidence",
    "classify_mode",
    "QueryType",
    "_classify_query_type",  # backward compat
    # LLM Fallback Classifier
    "llm_classify",
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
