import logging
from typing import Literal

from .state import ChatState_v2, RoutingMode

logger = logging.getLogger(__name__)

# Phase 5: 최대 반복 횟수 (무한 루프 방지)
MAX_TOTAL_ITERATIONS = 15  # search_round + retry_count 합산 최대값

FAST_PATH_PROMOTION_KEYWORDS = [
    "위법", "불법", "합법", "소송", "고소", "고발",
    "청약철회", "환불기간", "보증기간", "제척기간", "소멸시효",
    "손해배상", "위약금", "분쟁조정", "피해구제",
    "법원", "판결", "판례", "조정위원회",
]


def should_promote_to_rag(query: str, mode: RoutingMode) -> bool:
    if mode != 'NO_RETRIEVAL':
        return False
    query_lower = query.lower()
    return any(kw in query_lower for kw in FAST_PATH_PROMOTION_KEYWORDS)


def route_after_query_analysis(
    state: ChatState_v2
) -> Literal['generation', 'search_plan', 'ask_clarification']:
    mode = state.get('mode', 'NEED_RAG')
    user_query = state.get('user_query', '')
    
    if should_promote_to_rag(user_query, mode):
        logger.info(f"[Routing] Fast Path promotion: NO_RETRIEVAL -> NEED_RAG")
        mode = 'NEED_RAG'
    
    logger.info(f"[Routing] route_after_query_analysis: mode={mode}")
    
    if mode == 'NO_RETRIEVAL':
        return 'generation'
    elif mode == 'NEED_USER_CLARIFICATION':
        return 'ask_clarification'
    else:
        return 'search_plan'


def route_after_sufficiency(
    state: ChatState_v2
) -> Literal['generation', 'search_plan', 'ask_clarification']:
    report = state.get('retrieval_report_v2')
    search_round = state.get('search_round', 0)
    retry_count = state.get('retry_count', 0)
    search_plan = state.get('search_plan')
    rounds_budget = search_plan.get('rounds_budget', 3) if search_plan else 3

    # Phase 5: 전체 반복 횟수 체크 (무한 루프 방지)
    total_iterations = search_round + retry_count
    if total_iterations >= MAX_TOTAL_ITERATIONS:
        logger.warning(f"[Routing] MAX_TOTAL_ITERATIONS ({MAX_TOTAL_ITERATIONS}) reached, forcing generation")
        return 'generation'

    if not report:
        logger.warning("[Routing] No retrieval report, proceeding to generation")
        return 'generation'

    relevance = report.get('relevance', 0.0)
    coverage = report.get('coverage', [])
    missing_slots = [s for s in coverage if s.get('status') == 'missing']

    logger.info(f"[Routing] Sufficiency check: relevance={relevance:.2f}, missing_slots={len(missing_slots)}, round={search_round}/{rounds_budget}, total_iter={total_iterations}")

    if relevance >= 0.7 and not missing_slots:
        return 'generation'

    if relevance < 0.3 and search_round >= 1:
        logger.info("[Routing] Low relevance after search, asking user for clarification")
        return 'ask_clarification'

    if search_round < rounds_budget:
        logger.info(f"[Routing] Continuing search: round {search_round + 1}")
        return 'search_plan'

    logger.info("[Routing] Search budget exhausted, proceeding to generation")
    return 'generation'


def route_after_review(
    state: ChatState_v2
) -> Literal['generation', 'retrieval', 'output_guardrail']:
    review = state.get('review_report_v2')
    retry_count = state.get('retry_count', 0)
    search_round = state.get('search_round', 0)
    max_retries = 2

    # Phase 5: 전체 반복 횟수 체크 (무한 루프 방지)
    total_iterations = search_round + retry_count
    if total_iterations >= MAX_TOTAL_ITERATIONS:
        logger.warning(f"[Routing] MAX_TOTAL_ITERATIONS ({MAX_TOTAL_ITERATIONS}) reached in review, forcing output")
        return 'output_guardrail'

    if not review:
        return 'output_guardrail'

    if review.get('passed', False):
        logger.info("[Routing] Review passed, proceeding to output guardrail")
        return 'output_guardrail'

    if retry_count >= max_retries:
        logger.warning(f"[Routing] Max retries ({max_retries}) reached, proceeding to output guardrail")
        return 'output_guardrail'

    if review.get('required_more_evidence', False):
        logger.info(f"[Routing] More evidence required, re-retrieving (retry={retry_count + 1})")
        return 'retrieval'

    logger.info(f"[Routing] Review failed, regenerating (retry={retry_count + 1})")
    return 'generation'
