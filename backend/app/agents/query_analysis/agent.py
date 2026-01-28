"""
똑소리 프로젝트 - 질의분석 노드 (Query Analysis Node)

작성일: 2026-01-14
최종 수정: 2026-01-28 (PR#2 Intent Classifier 고도화)
리팩토링: 2026-01-28 (모듈 분할)

[역할 및 책임]
사용자의 자연어 질문을 분석하여 시스템이 처리 가능한 구조화된 데이터로 변환합니다.
RAG 검색이 필요한지, 어떤 정보를 검색해야 하는지, 혹은 사용자에게 되물어야 하는지를 결정합니다.

[State Flow]
Input State:
    - user_query (str): 사용자의 최신 발화
    - chat_type (str): 이전 턴까지의 대화 유형 (default: general)
    - onboarding (OnboardingInfo): 사용자 초기 입력 정보 (선택)

Output State:
    - query_analysis (QueryAnalysisResult): 분석 결과 (v1 호환)
    - mode (RoutingMode): 라우팅 모드
    - mode (RoutingMode): 다음 단계 라우팅 결정 (NEED_RAG, NO_RETRIEVAL, NEED_USER_CLARIFICATION, RESTRICTED_DOMAIN)

[모듈 구조]
- constants.py: 키워드, 패턴, 매핑 상수
- detectors.py: 도메인/모호함/시스템메타 쿼리 감지
- classifiers.py: 쿼리 유형 분류, 모드 결정
- extractors.py: 정보/키워드 추출, 정규화
- expanders.py: 쿼리 확장, 다중 검색 쿼리 생성
"""

import logging
from typing import Dict

from ...supervisor.state import (
    ChatState,
    QueryAnalysisResult,
)
from ...supervisor.conversation_manager import (
    update_slots_and_phase,
    should_trigger_clarification,
    get_retriever_types_for_phase,
)

# 분할된 모듈에서 import
from .constants import (
    QUERY_TYPE_TO_RETRIEVERS,
    RESTRICTED_DOMAIN_AGENCIES,
    DISPUTE_INTENT_KEYWORDS,
)
from .detectors import detect_restricted_domain
from .classifiers import classify_query_type, classify_mode
from .extractors import (
    extract_info_from_message,
    get_missing_fields_description,
    extract_keywords,
    normalize_query,
    check_missing_onboarding_fields,
    determine_agency_hint,
)
from .expanders import (
    expand_query_by_type,
    generate_search_queries,
)

logger = logging.getLogger(__name__)


def query_analysis_node(state: ChatState) -> Dict:
    """
    [질의분석 노드 진입점]
    LangGraph에서 호출되는 메인 함수입니다.

    ChatState에서 user_query, chat_type, onboarding을 입력받아
    분석 프로세스를 수행하고 결과를 반환합니다.

    [프로세스]
    1. 쿼리 정규화
    2. 유형 분류 (Rule + Hybrid)
    3. 키워드 추출
    4. 정보 추출 (엔티티)
    5. 쿼리 확장 & 다중 검색 쿼리 생성
    6. 필수 정보 누락 확인
    7. 라우팅 모드 결정
    """
    user_query = state.get("user_query", "")
    chat_type = state.get("chat_type", "general")
    onboarding = state.get("onboarding")

    # === PR-6: L2 캐시 체크 ===
    from ...supervisor.cache import QueryAnalysisCache

    cached = QueryAnalysisCache.get(user_query)
    if cached:
        logger.info(f"[QueryAnalysis] Cache HIT for: {user_query[:30]}...")
        return {
            'query_analysis': cached,
            'mode': cached.get('mode', 'NEED_RAG'),
            '_qa_cache_hit': True,
        }
    # === PR-6 끝 ===

    # Step 1: 쿼리 정규화
    normalized_query = normalize_query(user_query)

    # Step 2: 질의 유형 분류
    query_type = classify_query_type(normalized_query)

    # PR-7: 일반 채팅에서도 분쟁 의도 키워드가 있으면 dispute로 처리 (Safety Net)
    if chat_type == "general":
        # 법령/기준 쿼리는 유지 (더 구체적인 분류이므로 우선순위 높음)
        if query_type in ("law", "criteria"):
            pass  # Keep the specific classification
        else:
            has_dispute_intent = any(
                kw in normalized_query for kw in DISPUTE_INTENT_KEYWORDS
            )
            if has_dispute_intent:
                query_type = "dispute"
                logger.info(
                    f"[QueryAnalysis] General chat with dispute intent: '{normalized_query[:30]}'"
                )
            else:
                # 나머지는 general
                query_type = "general"

    # Step 3: 키워드 추출
    keywords = extract_keywords(normalized_query)

    # Step 4: 기관 추천 힌트 및 Restricted 도메인 감지
    restricted_domain = detect_restricted_domain(normalized_query) if query_type == "restricted" else None
    agency_hint = (
        determine_agency_hint(normalized_query)
        if query_type in ("dispute", "procedure", "criteria")
        else None
    )

    # Step 5: 메시지에서 정보 추출
    extracted_info = extract_info_from_message(user_query)

    # Step 6: 쿼리 확장 (Query Expansion)
    rewritten_query, expansion_applied = expand_query_by_type(
        query=normalized_query,
        query_type=query_type,
        onboarding=onboarding,
        extracted_info=extracted_info,
        keywords=keywords,
    )

    # Step 7: 다중 검색 쿼리 생성
    search_queries = generate_search_queries(
        original=normalized_query, expanded=rewritten_query, keywords=keywords
    )

    # Step 8: 누락 필드 확인
    missing_fields = check_missing_onboarding_fields(
        chat_type, onboarding, extracted_info
    )
    missing_fields_description = get_missing_fields_description(
        missing_fields, extracted_info
    )

    # 최소 정보가 있는지 확인 (품목이나 상세 내용 중 하나라도 있으면 진행)
    has_minimal_info = bool(
        extracted_info.get("purchase_item")
        or extracted_info.get("dispute_details")
        or (
            onboarding
            and (onboarding.get("purchase_item") or onboarding.get("dispute_details"))
        )
    )
    needs_clarification = not has_minimal_info and query_type == "dispute"

    # 라우팅 모드 결정
    mode = classify_mode(query_type, needs_clarification, user_query)

    logger.info(
        f"[QueryAnalysis] mode={mode}, query_type={query_type}, needs_clarification={needs_clarification}"
    )

    # v1 호환 결과 구조
    analysis_result: QueryAnalysisResult = {
        "query_type": query_type,
        "keywords": keywords,
        "agency_hint": agency_hint,
        "needs_clarification": needs_clarification,
        "missing_fields": missing_fields,
        "extracted_info": extracted_info,
        "missing_fields_description": missing_fields_description,
        "rewritten_query": rewritten_query,
        "search_queries": search_queries,
        "expansion_applied": expansion_applied,

        # === PR-2: Selective Retrieval 시작 ===
        "retriever_types": QUERY_TYPE_TO_RETRIEVERS.get(query_type, ["law", "criteria"]),
        # === PR-2: Selective Retrieval 끝 ===

        # === Phase 9: Restricted Domain 정보 ===
        "restricted_domain": restricted_domain,
        "restricted_agency_info": RESTRICTED_DOMAIN_AGENCIES.get(restricted_domain) if restricted_domain else None,
    }

    # === PR-6: L2 캐시 저장 ===
    cache_data = dict(analysis_result)
    cache_data['mode'] = mode
    QueryAnalysisCache.set(user_query, cache_data)
    # === PR-6 끝 ===

    temp_state_for_phase = {
        'user_query': user_query,
        'conversation_phase': state.get('conversation_phase', 'initial'),
        'dispute_slots': state.get('dispute_slots', {}),
        'onboarding': onboarding,
        'query_analysis': analysis_result,
    }
    phase_updates = update_slots_and_phase(temp_state_for_phase)

    new_phase = phase_updates.get('conversation_phase', 'initial')
    if should_trigger_clarification({'conversation_phase': new_phase}):
        mode = 'NEED_USER_CLARIFICATION'

    if new_phase in ('providing_law', 'providing_case', 'providing_procedure'):
        analysis_result['retriever_types'] = get_retriever_types_for_phase(new_phase)

    return {
        "query_analysis": analysis_result,
        "mode": mode,
        "conversation_phase": phase_updates.get('conversation_phase'),
        "dispute_slots": phase_updates.get('dispute_slots'),
        "dispute_slot_status": phase_updates.get('dispute_slot_status'),
        "last_phase_transition_reason": phase_updates.get('last_phase_transition_reason'),
    }


# === Backward Compatibility Exports ===
# 기존 코드와의 호환성을 위해 일부 함수/상수를 re-export
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

from .detectors import (
    is_ambiguous_query as _is_ambiguous_query,
    is_system_meta_query as _is_system_meta_query,
    detect_restricted_domain as _detect_restricted_domain,
    is_procedure_query as _is_procedure_query,
    should_promote_to_rag as _should_promote_to_rag,
)

from .classifiers import (
    classify_query_type as _classify_query_type,
    classify_mode as _classify_mode,
)

from .extractors import (
    extract_info_from_message as _extract_info_from_message,
    extract_keywords as _extract_keywords,
    normalize_query as _normalize_query,
    check_missing_onboarding_fields as _check_missing_onboarding_fields,
    determine_agency_hint as _determine_agency_hint,
    get_missing_fields_description as _get_missing_fields_description,
)

from .expanders import (
    expand_query_by_type as _expand_query_by_type,
    generate_search_queries as _generate_search_queries,
    create_synonym_variant_query as _create_synonym_variant_query,
)


__all__ = [
    # Main entry point
    "query_analysis_node",
    # Constants (backward compat)
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
    # Detectors (backward compat)
    "_is_ambiguous_query",
    "_is_system_meta_query",
    "_detect_restricted_domain",
    "_is_procedure_query",
    "_should_promote_to_rag",
    # Classifiers (backward compat)
    "_classify_query_type",
    "_classify_mode",
]
