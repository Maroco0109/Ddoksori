"""
똑소리 프로젝트 - Legacy 그래프 정의

[DEPRECATED] Phase 7에서 MAS Supervisor로 전환됨.
롤백이 필요한 경우에만 사용합니다.

포함된 그래프:
- create_legacy_chat_graph(): 선형 파이프라인 (S2-3)
- create_react_chat_graph(): ReAct 패턴 (S2-7)
- create_unified_chat_graph(): 통합 ReAct 그래프 (PR-2)
"""

import os
import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from .state import ChatState, UnifiedState
from .graph import _create_timed_node, SIMILARITY_THRESHOLD_HIGH
from .checkpointer import get_checkpointer
from .nodes.clarify import ask_clarification_node
from ..agents.query_analysis.agent import query_analysis_node
from ..agents.retrieval.agent import retrieval_node
from ..agents.answer_generation.agent import generation_node
from ..agents.answer_generation.tools.prompts import low_similarity_prompt_node
from ..agents.legal_review.agent import review_node, review_node_wrapper
from ..agents.react.react_think import react_think_node
from ..agents.react.react_act import react_act_node
from ..guardrail.nodes import input_guardrail_node, output_guardrail_node

logger = logging.getLogger(__name__)


# ============================================================================
# Legacy 라우팅 함수 (선형 파이프라인용)
# ============================================================================

def _route_after_query_analysis(state: ChatState) -> Literal['ask_clarification', 'retrieval']:
    query_analysis = state.get('query_analysis')

    if not query_analysis:
        return 'retrieval'

    if query_analysis.get('query_type') == 'general':
        return 'retrieval'

    extracted_info = query_analysis.get('extracted_info', {})
    has_minimal_info = bool(
        extracted_info.get('purchase_item') or
        extracted_info.get('dispute_details')
    )

    if not has_minimal_info and query_analysis.get('needs_clarification'):
        return 'ask_clarification'

    return 'retrieval'


def _route_after_retrieval(state: ChatState) -> Literal['generation', 'low_similarity_prompt']:
    retrieval = state.get('retrieval')
    query_analysis = state.get('query_analysis')

    if query_analysis and query_analysis.get('query_type') == 'general':
        return 'generation'

    if not retrieval:
        return 'low_similarity_prompt'

    max_sim = retrieval.get('max_similarity', 0.0)
    disputes = retrieval.get('disputes', [])
    counsels = retrieval.get('counsels', [])

    if not disputes and not counsels:
        return 'low_similarity_prompt'

    if max_sim >= SIMILARITY_THRESHOLD_HIGH:
        return 'generation'

    return 'low_similarity_prompt'


def _route_after_review(state: ChatState) -> str:
    review = state.get('review')
    retry_count = state.get('retry_count', 0)

    if review and not review.get('passed') and retry_count < 2:
        return 'generation'
    return END


# ============================================================================
# ReAct 패턴 라우팅 함수 (S2-7)
# ============================================================================

def _route_after_query_analysis_react(
    state: ChatState
) -> Literal['ask_clarification', 'react_think', 'generation']:
    """
    query_analysis 이후 라우팅 (ReAct 버전)

    - NO_RETRIEVAL 모드 (general, system_meta) → generation (직접 생성)
    - 추가 정보 필요 → ask_clarification
    - 그 외 → react_think (ReAct 루프 시작)
    """
    query_analysis = state.get('query_analysis')
    mode = state.get('mode', 'NEED_RAG')

    # Phase 4: NO_RETRIEVAL 모드는 검색 없이 바로 생성
    if mode == 'NO_RETRIEVAL':
        logger.info("[Routing] NO_RETRIEVAL mode, skipping ReAct loop")
        return 'generation'

    if not query_analysis:
        return 'react_think'

    query_type = query_analysis.get('query_type')
    if query_type in ('general', 'system_meta'):
        logger.info(f"[Routing] Query type={query_type}, skipping ReAct loop")
        return 'generation'

    extracted_info = query_analysis.get('extracted_info', {})
    has_minimal_info = bool(
        extracted_info.get('purchase_item') or
        extracted_info.get('dispute_details')
    )

    if not has_minimal_info and query_analysis.get('needs_clarification'):
        return 'ask_clarification'

    return 'react_think'


def _route_after_react_think(
    state: ChatState
) -> Literal['react_act', 'generation', 'ask_clarification']:
    """
    react_think 이후 라우팅

    - should_continue=True AND action 있음 → react_act (액션 실행)
    - should_continue=False → generation (답변 생성)
    - action='ask_clarification' → ask_clarification (사용자 대기)
    """
    should_continue = state.get('should_continue', False)
    last_action = state.get('last_action')

    if not should_continue:
        return 'generation'

    if last_action == 'ask_clarification':
        return 'ask_clarification'

    return 'react_act'


# ============================================================================
# Unified 그래프 라우팅 함수 (PR-2)
# ============================================================================

def _route_unified_after_guardrail(state: UnifiedState) -> str:
    """input_guardrail 이후 라우팅"""
    if state.get('guardrail_blocked'):
        return END
    return 'query_analysis'


def _route_unified_after_query_analysis(
    state: UnifiedState
) -> Literal['react_think', 'generation', 'ask_clarification']:
    """
    [Query Analysis 후 라우팅] (통합 그래프용)

    1. NO_RETRIEVAL: 검색 불필요 -> 즉시 답변 생성
    2. NEED_CLARIFICATION: 정보 부족 -> 되묻기
    3. NEED_RAG: 정보 검색 필요 -> ReAct Think
    """
    mode = state.get('mode', 'NEED_RAG')
    query_analysis = state.get('query_analysis')

    if mode == 'NO_RETRIEVAL':
        logger.info("[Unified] NO_RETRIEVAL mode, skipping ReAct loop")
        return 'generation'

    if mode in ('NEED_CLARIFICATION', 'NEED_USER_CLARIFICATION'):
        logger.info(f"[Unified] {mode} mode, asking user")
        return 'ask_clarification'

    if query_analysis:
        query_type = query_analysis.get('query_type')
        if query_type in ('general', 'system_meta'):
            logger.info(f"[Unified] Query type={query_type}, skipping ReAct loop")
            return 'generation'

        extracted_info = query_analysis.get('extracted_info', {})
        has_minimal_info = bool(
            extracted_info.get('purchase_item') or
            extracted_info.get('dispute_details')
        )
        if not has_minimal_info and query_analysis.get('needs_clarification'):
            logger.info("[Unified] Missing info, asking for clarification")
            return 'ask_clarification'

    return 'react_think'


def _route_unified_after_react_think(
    state: UnifiedState
) -> Literal['react_act', 'generation']:
    """
    [ReAct Think 후 라우팅]

    1. should_continue=True: 도구 사용 필요 → ReAct Act
    2. should_continue=False: 충분한 정보 → Generation
    """
    should_continue = state.get('should_continue', False)
    last_action = state.get('last_action')

    if not should_continue:
        return 'generation'

    if last_action and last_action != 'ask_clarification':
        return 'react_act'

    return 'generation'


def _route_unified_after_review(state: UnifiedState) -> str:
    """
    [Legal Review 후 라우팅]

    1. 검토 통과 → Output Guardrail
    2. 검토 실패 & 재시도 가능 → Generation
    3. 검토 실패 & 재시도 초과 → Output Guardrail
    """
    review = state.get('review')
    retry_count = state.get('retry_count', 0)
    chat_type = state.get('chat_type', 'dispute')

    if chat_type == 'general':
        return 'output_guardrail'

    if review and not review.get('passed') and retry_count < 2:
        return 'generation'

    return 'output_guardrail'


# ============================================================================
# [DEPRECATED] Legacy 선형 파이프라인 그래프
# ============================================================================

def create_legacy_chat_graph() -> StateGraph:
    """
    [DEPRECATED] 기존 선형 파이프라인 그래프 (S2-3)

    query_analysis → retrieval → generation → review → END

    Note:
        Phase 5에서 create_mas_supervisor_graph()로 대체됨.
        롤백 필요 시에만 사용.
    """
    graph = StateGraph(ChatState)

    graph.add_node('query_analysis', _create_timed_node(query_analysis_node, 'query_analysis'))
    graph.add_node('retrieval', _create_timed_node(retrieval_node, 'retrieval'))
    graph.add_node('generation', _create_timed_node(generation_node, 'generation'))
    graph.add_node('review', _create_timed_node(review_node, 'review'))
    graph.add_node('ask_clarification', _create_timed_node(ask_clarification_node, 'ask_clarification'))
    graph.add_node('low_similarity_prompt', _create_timed_node(low_similarity_prompt_node, 'low_similarity_prompt'))

    graph.set_entry_point('query_analysis')

    graph.add_conditional_edges(
        'query_analysis',
        _route_after_query_analysis,
        {
            'ask_clarification': 'ask_clarification',
            'retrieval': 'retrieval',
        }
    )

    graph.add_conditional_edges(
        'retrieval',
        _route_after_retrieval,
        {
            'generation': 'generation',
            'low_similarity_prompt': 'low_similarity_prompt',
        }
    )

    graph.add_edge('generation', 'review')

    graph.add_conditional_edges(
        'review',
        _route_after_review,
        {
            'generation': 'generation',
            END: END,
        }
    )

    graph.add_edge('ask_clarification', END)
    graph.add_edge('low_similarity_prompt', END)

    return graph


# ============================================================================
# [DEPRECATED] ReAct 패턴 그래프
# ============================================================================

def create_react_chat_graph() -> StateGraph:
    """
    [DEPRECATED] ReAct 패턴 그래프 (S2-7)

    query_analysis → react_think ⟷ react_act → generation → review → END

    Note:
        Phase 5에서 create_mas_supervisor_graph()로 대체됨.
        Supervisor 기반 의사결정으로 ReAct 루프 제거.
    """
    graph = StateGraph(ChatState)

    graph.add_node('query_analysis', _create_timed_node(query_analysis_node, 'query_analysis'))
    graph.add_node('react_think', _create_timed_node(react_think_node, 'react_think'))
    graph.add_node('react_act', _create_timed_node(react_act_node, 'react_act'))
    graph.add_node('generation', _create_timed_node(generation_node, 'generation'))
    graph.add_node('review', _create_timed_node(review_node, 'review'))
    graph.add_node('ask_clarification', _create_timed_node(ask_clarification_node, 'ask_clarification'))

    graph.set_entry_point('query_analysis')

    graph.add_conditional_edges(
        'query_analysis',
        _route_after_query_analysis_react,
        {
            'ask_clarification': 'ask_clarification',
            'react_think': 'react_think',
            'generation': 'generation',
        }
    )

    graph.add_conditional_edges(
        'react_think',
        _route_after_react_think,
        {
            'react_act': 'react_act',
            'generation': 'generation',
            'ask_clarification': 'ask_clarification',
        }
    )

    graph.add_edge('react_act', 'react_think')
    graph.add_edge('generation', 'review')

    graph.add_conditional_edges(
        'review',
        _route_after_review,
        {
            'generation': 'generation',
            END: END,
        }
    )

    graph.add_edge('ask_clarification', END)

    return graph


# ============================================================================
# [DEPRECATED] 통합 ReAct 그래프
# ============================================================================

def create_unified_chat_graph() -> StateGraph:
    """
    [DEPRECATED] 통합 ReAct 그래프 생성 (PR-2)

    [Architecture]
    1. Input Guardrail: 사용자 입력 필터링
    2. Query Analysis: 의도 파악 및 라우팅 결정
    3. Branching:
       - NO_RETRIEVAL → Generation
       - NEED_CLARIFICATION → Ask Clarification
       - NEED_RAG → ReAct Loop → Generation
    4. Legal Review: 법률/정책 위반 검토
    5. Output Guardrail: 최종 출력 필터링

    Note:
        Phase 7에서 create_mas_supervisor_graph()로 대체됨.
        롤백 필요 시에만 사용.
    """
    graph = StateGraph(UnifiedState)

    graph.add_node('input_guardrail', _create_timed_node(input_guardrail_node, 'input_guardrail'))
    graph.add_node('query_analysis', _create_timed_node(query_analysis_node, 'query_analysis'))
    graph.add_node('react_think', _create_timed_node(react_think_node, 'react_think'))
    graph.add_node('react_act', _create_timed_node(react_act_node, 'react_act'))
    graph.add_node('generation', _create_timed_node(generation_node, 'generation'))
    graph.add_node('review', _create_timed_node(review_node_wrapper, 'review'))
    graph.add_node('output_guardrail', _create_timed_node(output_guardrail_node, 'output_guardrail'))
    graph.add_node('ask_clarification', _create_timed_node(ask_clarification_node, 'ask_clarification'))

    graph.set_entry_point('input_guardrail')

    graph.add_conditional_edges(
        'input_guardrail',
        _route_unified_after_guardrail,
        {END: END, 'query_analysis': 'query_analysis'}
    )

    graph.add_conditional_edges(
        'query_analysis',
        _route_unified_after_query_analysis,
        {
            'react_think': 'react_think',
            'generation': 'generation',
            'ask_clarification': 'ask_clarification',
        }
    )

    graph.add_conditional_edges(
        'react_think',
        _route_unified_after_react_think,
        {'react_act': 'react_act', 'generation': 'generation'}
    )

    graph.add_edge('react_act', 'react_think')
    graph.add_edge('generation', 'review')

    graph.add_conditional_edges(
        'review',
        _route_unified_after_review,
        {'generation': 'generation', 'output_guardrail': 'output_guardrail'}
    )

    graph.add_edge('output_guardrail', END)
    graph.add_edge('ask_clarification', END)

    return graph


# ============================================================================
# 컴파일 및 싱글톤
# ============================================================================

_unified_compiled_graph = None


def get_unified_compiled_graph():
    """통합 그래프 컴파일"""
    graph = create_unified_chat_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


def get_unified_graph():
    """통합 그래프 싱글톤"""
    global _unified_compiled_graph
    if _unified_compiled_graph is None:
        _unified_compiled_graph = get_unified_compiled_graph()
    return _unified_compiled_graph


def create_chat_graph() -> StateGraph:
    """ORCHESTRATOR_MODE 환경변수 기반 그래프 선택 (deprecated)"""
    mode = os.getenv('ORCHESTRATOR_MODE', 'react').lower()

    if mode == 'legacy':
        logger.info("Using legacy linear pipeline graph")
        return create_legacy_chat_graph()
    else:
        logger.info("Using ReAct pattern graph")
        return create_react_chat_graph()


def reset_legacy_graphs():
    """Legacy 그래프 리셋"""
    global _unified_compiled_graph
    _unified_compiled_graph = None
