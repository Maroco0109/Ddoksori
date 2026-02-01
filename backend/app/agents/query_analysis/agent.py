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
from typing import Any, Dict

from ...supervisor.state import (
    ChatState,
    QueryAnalysisResult,
)

# 분할된 모듈에서 import
from .constants import (
    QUERY_TYPE_TO_RETRIEVERS,
    RESTRICTED_DOMAIN_AGENCIES,
    DISPUTE_INTENT_KEYWORDS,
)
from .detectors import detect_restricted_domain
from .classifiers import classify_query_type, classify_query_type_with_confidence, classify_mode, classify_query_complexity
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
        cached_mode = cached.get("mode", "NEED_RAG")
        logger.info(
            f"[QueryAnalysis] Cache HIT for: '{user_query[:30]}...', mode={cached_mode}"
        )
        return {
            "query_analysis": cached,
            "mode": cached_mode,
            "_qa_cache_hit": True,
        }
    # === PR-6 끝 ===

    # Step 1: 쿼리 정규화
    normalized_query = normalize_query(user_query)

    # Step 2: 질의 유형 분류 (with confidence for logging)
    query_type, rule_confidence = classify_query_type_with_confidence(normalized_query)

    # Step 2.5: 쿼리 복잡도 분류 (Adaptive RAG)
    query_complexity = classify_query_complexity(normalized_query)

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
    restricted_domain = (
        detect_restricted_domain(normalized_query)
        if query_type == "restricted"
        else None
    )
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

    # 라우팅 모드 결정 (clarification 제거됨)
    mode = classify_mode(query_type, False, user_query)

    logger.info(
        f"[QueryAnalysis] mode={mode}, query_type={query_type}"
    )

    # v1 호환 결과 구조
    analysis_result: QueryAnalysisResult = {
        "query_type": query_type,
        "keywords": keywords,
        "agency_hint": agency_hint,
        "extracted_info": extracted_info,
        "missing_fields_description": missing_fields_description,
        "rewritten_query": rewritten_query,
        "search_queries": search_queries,
        "expansion_applied": expansion_applied,
        # === PR-2: Selective Retrieval 시작 ===
        "retriever_types": QUERY_TYPE_TO_RETRIEVERS.get(
            query_type, ["law", "criteria"]
        ),
        # === PR-2: Selective Retrieval 끝 ===
        # === Phase 9: Restricted Domain 정보 ===
        "restricted_domain": restricted_domain,
        "restricted_agency_info": RESTRICTED_DOMAIN_AGENCIES.get(restricted_domain)
        if restricted_domain
        else None,
        # === Adaptive RAG: 쿼리 복잡도 ===
        "query_complexity": query_complexity.value,
    }

    # === PR-6: L2 캐시 저장 ===
    cache_data = dict(analysis_result)
    cache_data["mode"] = mode
    QueryAnalysisCache.set(user_query, cache_data)
    # === PR-6 끝 ===

    phase_result = {}

    return {
        "query_analysis": analysis_result,
        "mode": mode,
        "query_complexity": query_complexity.value,
        **phase_result,
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
    is_meta_conversational as _is_meta_conversational,
)

from .classifiers import (
    classify_query_type as _classify_query_type,
    classify_query_type_with_confidence as _classify_query_type_with_confidence,
    classify_mode as _classify_mode,
    classify_query_complexity as _classify_query_complexity,
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


async def query_analysis_node_v2(state: Dict, config: Any = None) -> Dict:
    """
    [질의분석 노드 v2 진입점]
    LLM 기반 다중 쿼리 확장이 적용된 새로운 질의분석 노드입니다.

    [주요 변경사항]
    - gpt-4o-mini 기반 쿼리 확장
    - 의도 분류: 'general' | 'information_search' | 'followup'
    - 다중 확장 쿼리 리스트 반환
    - Progressive Disclosure: 후속 턴 감지 및 CACHED_RAG 모드 지원

    [Output State]
    - intent: 의도 ('general' | 'information_search' | 'followup')
    - original_query: 원본 질문
    - expanded_queries: 확장된 쿼리 리스트 (최대 5개)
    - keywords: 핵심 키워드
    - retriever_types: 추천 검색 에이전트
    - needs_clarification: 추가 정보 필요 여부
    - missing_fields: 누락된 필드
    """
    _ = config  # LangGraph 노드 호환성 (unused)
    from .expanders import expand_query_with_llm_v2

    user_query = state.get("user_query", "")
    chat_type = state.get("chat_type", "general")
    onboarding = state.get("onboarding")

    # Step 1: 쿼리 정규화
    normalized_query = normalize_query(user_query)

    # Step 2: 질의 유형 분류 (Hybrid: Rule + LLM Fallback)
    from .classifiers import classify_query_type_with_confidence
    from .llm_classifier import llm_classify

    query_type, rule_confidence = classify_query_type_with_confidence(normalized_query)
    logger.info(
        f"[QueryAnalysis v2] Rule-based classification: query_type={query_type}, confidence={rule_confidence:.2f}"
    )

    # LLM Fallback: confidence < 0.7이면 LLM으로 2차 분류
    llm_used = False
    if rule_confidence < 0.7:
        logger.info(
            f"[QueryAnalysis v2] Low confidence ({rule_confidence:.2f}), trying LLM fallback..."
        )
        try:
            llm_result = await llm_classify(normalized_query)
            if llm_result:
                llm_type, llm_confidence, llm_reasoning = llm_result
                logger.info(
                    f"[QueryAnalysis v2] LLM classification: type={llm_type}, confidence={llm_confidence:.2f}, "
                    f"reasoning='{llm_reasoning[:100]}'"
                )
                if llm_confidence > rule_confidence:
                    logger.info(
                        f"[QueryAnalysis v2] LLM override: {query_type}({rule_confidence:.2f}) -> {llm_type}({llm_confidence:.2f})"
                    )
                    query_type = llm_type
                    llm_used = True
                else:
                    logger.info(
                        f"[QueryAnalysis v2] Rule-based confidence higher, keeping: {query_type}({rule_confidence:.2f})"
                    )
        except Exception as e:
            logger.warning(f"[QueryAnalysis v2] LLM fallback failed, using rule-based: {e}")
    else:
        logger.info(
            f"[QueryAnalysis v2] High confidence ({rule_confidence:.2f}), skipping LLM fallback"
        )

    # Step 2.5: 쿼리 복잡도 분류 (Adaptive RAG)
    query_complexity = classify_query_complexity(normalized_query)

    # Step 3: 의도 분류 (v2 신규)
    # 'general'은 일반 대화, 나머지는 'information_search'
    if query_type in ("general", "system_meta"):
        intent = "general"
    else:
        intent = "information_search"

    # PR-7: 일반 채팅에서도 분쟁 의도 키워드가 있으면 information_search로 처리
    if chat_type == "general" and intent == "general":
        has_dispute_intent = any(
            kw in normalized_query for kw in DISPUTE_INTENT_KEYWORDS
        )
        if has_dispute_intent:
            intent = "information_search"
            query_type = "dispute"

    # Step 4: 키워드 추출
    keywords = extract_keywords(normalized_query)

    # Step 5: LLM 기반 쿼리 확장 (v2 핵심)
    expanded_queries = await expand_query_with_llm_v2(
        query=normalized_query,
        keywords=keywords,
        intent=intent,
        use_fallback=True,
    )

    # Step 6: 정보 추출 및 누락 필드 확인
    extracted_info = extract_info_from_message(user_query)
    missing_fields = check_missing_onboarding_fields(
        chat_type, onboarding, extracted_info
    )

    # Step 6.5: 날짜 계산 및 카테고리 결정 (Onboarding 정보 보강)
    from .extractors import compute_days_since_purchase, determine_product_category

    # onboarding dict을 수정 가능한 dict로 변환
    enriched_onboarding = dict(onboarding) if onboarding else {}

    if enriched_onboarding.get('purchase_date'):
        days = compute_days_since_purchase(enriched_onboarding['purchase_date'])
        if days is not None:
            enriched_onboarding['days_since_purchase'] = days
            logger.info(
                f"[QueryAnalysis v2] Computed days_since_purchase: {days} days from {enriched_onboarding['purchase_date']}"
            )

    if enriched_onboarding.get('purchase_item'):
        category = determine_product_category(enriched_onboarding['purchase_item'])
        if category:
            enriched_onboarding['product_category'] = category
            logger.info(
                f"[QueryAnalysis v2] Determined product_category: {category} for {enriched_onboarding['purchase_item']}"
            )

    needs_clarification = False  # LEGACY: clarification 제거됨

    # Step 7: retriever_types 결정 (하이브리드 방식)
    retriever_types = QUERY_TYPE_TO_RETRIEVERS.get(query_type, ["law", "criteria"])

    # 'case' 추가 (사례 검색 기본 포함)
    if "case" not in retriever_types and intent == "information_search":
        retriever_types = list(retriever_types) + ["case"]

    # Step 8: 라우팅 모드 결정
    logger.info(
        f"[QueryAnalysis v2] Before classify_mode: query_type={query_type}, intent={intent}"
    )
    mode = classify_mode(query_type, needs_clarification, user_query)
    logger.info(
        f"[QueryAnalysis v2] After classify_mode: mode={mode}"
    )

    phase_result = {}

    logger.info(
        f"[QueryAnalysis v2] Final result: intent={intent}, query_type={query_type}, "
        f"mode={mode}, llm_used={llm_used}, "
        f"expanded_queries={len(expanded_queries)}, retriever_types={retriever_types}"
    )

    # v2 출력 형식
    result = {
        "query_analysis": {
            "intent": intent,
            "original_query": user_query,
            "expanded_queries": expanded_queries,
            "keywords": keywords,
            "retriever_types": retriever_types,
            # v1 호환 필드
            "query_type": query_type,
            "extracted_info": extracted_info,
            "rewritten_query": expanded_queries[0] if expanded_queries else user_query,
            "search_queries": expanded_queries,
            "query_complexity": query_complexity.value,
        },
        "mode": mode,
        "query_complexity": query_complexity.value,
        **phase_result,
    }

    # enriched_onboarding이 변경되었다면 state에 반영
    if enriched_onboarding and enriched_onboarding != onboarding:
        result["onboarding"] = enriched_onboarding

    return result


__all__ = [
    # Main entry points
    "query_analysis_node",
    "query_analysis_node_v2",
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
    "_is_meta_conversational",
    # Classifiers (backward compat)
    "_classify_query_type",
    "_classify_mode",
    "_classify_query_complexity",
]
