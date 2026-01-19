"""
똑소리 프로젝트 - LangGraph 그래프 정의
작성일: 2026-01-14
S2-3: 오케스트레이터 워크플로우 정의 및 컴파일
S2-7: ReAct 패턴 적용 (Thought-Action-Observation 루프)

워크플로우 (ReAct):
query_analysis → react_think ⟷ react_act → generation → review → END
                    ↘ ask_clarification → END
"""

import os
from typing import Literal, Dict, Any, Callable
import time
import logging

from langgraph.graph import StateGraph, END

from .state import ChatState, ChatState_v2, SimpleState
from .checkpointer import get_checkpointer
from .routing import route_after_query_analysis, route_after_sufficiency, route_after_review as route_after_review_v2
from .budget import check_budget, BudgetTracker
from .nodes.search_plan import search_plan_node
from .nodes.sufficiency import sufficiency_node
from ..agents.query_analysis.agent import query_analysis_node
from ..agents.query_analysis.tools import ask_clarification_node
from ..agents.retrieval.agent import retrieval_node, retrieval_node_v2
from ..agents.answer_generation.agent import generation_node
from ..agents.answer_generation.tools.prompts import low_similarity_prompt_node
from ..agents.legal_review.agent import review_node
from ..agents.react.react_think import react_think_node
from ..agents.react.react_act import react_act_node
from ..guardrail.nodes import input_guardrail_node, output_guardrail_node

logger = logging.getLogger(__name__)

NODE_TIMINGS_KEY = '_node_timings'


def _create_timed_node(node_fn: Callable, node_name: str) -> Callable:
    """노드 함수를 감싸서 실행 시간을 측정하는 래퍼 생성"""
    def timed_wrapper(state: ChatState) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[NODE START] {node_name}")
        
        result = node_fn(state)
        
        end_time = time.time()
        duration_ms = round((end_time - start_time) * 1000, 2)
        logger.info(f"[NODE END] {node_name} - {duration_ms}ms")
        
        existing_timings = state.get(NODE_TIMINGS_KEY)
        timings = dict(existing_timings) if existing_timings else {}
        timings[node_name] = {
            'start': start_time,
            'end': end_time,
            'duration_ms': duration_ms
        }
        result[NODE_TIMINGS_KEY] = timings
        
        return result
    
    return timed_wrapper


SIMILARITY_THRESHOLD_HIGH = 0.55


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


# === ReAct 패턴 라우팅 함수 (S2-7) ===

def _route_after_query_analysis_react(
    state: ChatState
) -> Literal['ask_clarification', 'react_think']:
    """
    query_analysis 이후 라우팅 (ReAct 버전)

    - 추가 정보 필요 → ask_clarification
    - 그 외 → react_think (ReAct 루프 시작)
    """
    query_analysis = state.get('query_analysis')

    if not query_analysis:
        return 'react_think'

    if query_analysis.get('query_type') == 'general':
        return 'react_think'

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


def create_legacy_chat_graph() -> StateGraph:
    """
    기존 선형 파이프라인 그래프 (S2-3)

    query_analysis → retrieval → generation → review → END
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


def create_react_chat_graph() -> StateGraph:
    """
    ReAct 패턴 그래프 (S2-7)

    query_analysis → react_think ⟷ react_act → generation → review → END
                        ↘ ask_clarification → END

    ReAct 루프: react_think → react_act → react_think (max 2회)
    """
    graph = StateGraph(ChatState)

    # 노드 등록
    graph.add_node('query_analysis', _create_timed_node(query_analysis_node, 'query_analysis'))
    graph.add_node('react_think', _create_timed_node(react_think_node, 'react_think'))
    graph.add_node('react_act', _create_timed_node(react_act_node, 'react_act'))
    graph.add_node('generation', _create_timed_node(generation_node, 'generation'))
    graph.add_node('review', _create_timed_node(review_node, 'review'))
    graph.add_node('ask_clarification', _create_timed_node(ask_clarification_node, 'ask_clarification'))

    # 진입점
    graph.set_entry_point('query_analysis')

    # query_analysis → react_think 또는 ask_clarification
    graph.add_conditional_edges(
        'query_analysis',
        _route_after_query_analysis_react,
        {
            'ask_clarification': 'ask_clarification',
            'react_think': 'react_think',
        }
    )

    # react_think → react_act 또는 generation 또는 ask_clarification
    graph.add_conditional_edges(
        'react_think',
        _route_after_react_think,
        {
            'react_act': 'react_act',
            'generation': 'generation',
            'ask_clarification': 'ask_clarification',
        }
    )

    # react_act → react_think (루프)
    graph.add_edge('react_act', 'react_think')

    # generation → review
    graph.add_edge('generation', 'review')

    # review → generation (재시도) 또는 END
    graph.add_conditional_edges(
        'review',
        _route_after_review,
        {
            'generation': 'generation',
            END: END,
        }
    )

    # ask_clarification → END
    graph.add_edge('ask_clarification', END)

    return graph


def _route_after_input_guardrail_v2(state: ChatState_v2) -> str:
    if state.get('guardrail_blocked'):
        return END
    return 'query_analysis'


def _route_after_query_analysis_v2(state: ChatState_v2) -> str:
    return route_after_query_analysis(state)


def _route_after_sufficiency_v2(state: ChatState_v2) -> str:
    return route_after_sufficiency(state)


def _route_after_review_v2_wrapper(state: ChatState_v2) -> str:
    return route_after_review_v2(state)


def _budget_gate(state: ChatState_v2) -> str:
    if not check_budget(state):
        logger.warning("[BudgetGate] Budget exhausted, forcing generation")
        return 'generation'
    return 'continue'


def create_v2_chat_graph() -> StateGraph:
    graph = StateGraph(ChatState_v2)

    graph.add_node('input_guardrail', _create_timed_node(input_guardrail_node, 'input_guardrail'))
    graph.add_node('query_analysis', _create_timed_node(query_analysis_node, 'query_analysis'))
    graph.add_node('search_plan', _create_timed_node(search_plan_node, 'search_plan'))
    graph.add_node('retrieval', _create_timed_node(retrieval_node_v2, 'retrieval'))
    graph.add_node('sufficiency', _create_timed_node(sufficiency_node, 'sufficiency'))
    graph.add_node('generation', _create_timed_node(generation_node, 'generation'))
    graph.add_node('review', _create_timed_node(review_node, 'review'))
    graph.add_node('ask_clarification', _create_timed_node(ask_clarification_node, 'ask_clarification'))
    graph.add_node('output_guardrail', _create_timed_node(output_guardrail_node, 'output_guardrail'))

    graph.set_entry_point('input_guardrail')

    graph.add_conditional_edges(
        'input_guardrail',
        _route_after_input_guardrail_v2,
        {
            END: END,
            'query_analysis': 'query_analysis',
        }
    )

    graph.add_conditional_edges(
        'query_analysis',
        _route_after_query_analysis_v2,
        {
            'generation': 'generation',
            'search_plan': 'search_plan',
            'ask_clarification': 'ask_clarification',
        }
    )

    graph.add_edge('search_plan', 'retrieval')
    graph.add_edge('retrieval', 'sufficiency')

    graph.add_conditional_edges(
        'sufficiency',
        _route_after_sufficiency_v2,
        {
            'generation': 'generation',
            'search_plan': 'search_plan',
            'ask_clarification': 'ask_clarification',
        }
    )

    graph.add_edge('generation', 'review')

    graph.add_conditional_edges(
        'review',
        _route_after_review_v2_wrapper,
        {
            'generation': 'generation',
            'retrieval': 'retrieval',
            'output_guardrail': 'output_guardrail',
        }
    )

    graph.add_edge('output_guardrail', END)
    graph.add_edge('ask_clarification', END)

    return graph


def _simple_query_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    result = query_analysis_node(state)  # type: ignore
    
    query_analysis = result.get('query_analysis') or result.get('query_analysis_v2')
    if query_analysis:
        mode = query_analysis.get('mode', 'NEED_RAG')
        if mode not in ['NO_RETRIEVAL', 'NEED_RAG']:
            mode = 'NEED_RAG'
        return {
            'query_analysis_v2': query_analysis,
            'mode': mode,
        }
    
    return {
        'query_analysis_v2': None,
        'mode': 'NEED_RAG',
    }


def _simple_retrieval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    result = retrieval_node(state)  # type: ignore
    
    retrieval = result.get('retrieval')
    return {'retrieval': retrieval}


def _simple_generation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    result = generation_node(state)  # type: ignore
    
    final_answer = result.get('final_answer', '')
    if not final_answer:
        final_answer = "죄송합니다. 답변을 생성할 수 없습니다."
    
    return {'final_answer': final_answer}


def _route_simple_after_guardrail(state: Dict[str, Any]) -> str:
    if state.get('guardrail_blocked'):
        return END
    return 'query_analysis'


def _route_simple_after_query_analysis(state: Dict[str, Any]) -> str:
    mode = state.get('mode', 'NEED_RAG')
    if mode == 'NO_RETRIEVAL':
        return 'generation'
    return 'retrieval'


def create_simple_chat_graph() -> StateGraph:
    graph = StateGraph(SimpleState)

    graph.add_node('input_guardrail', _create_timed_node(input_guardrail_node, 'input_guardrail'))
    graph.add_node('query_analysis', _create_timed_node(_simple_query_analysis_node, 'query_analysis'))
    graph.add_node('retrieval', _create_timed_node(_simple_retrieval_node, 'retrieval'))
    graph.add_node('generation', _create_timed_node(_simple_generation_node, 'generation'))
    graph.add_node('output_guardrail', _create_timed_node(output_guardrail_node, 'output_guardrail'))

    graph.set_entry_point('input_guardrail')

    graph.add_conditional_edges(
        'input_guardrail',
        _route_simple_after_guardrail,
        {
            END: END,
            'query_analysis': 'query_analysis',
        }
    )

    graph.add_conditional_edges(
        'query_analysis',
        _route_simple_after_query_analysis,
        {
            'retrieval': 'retrieval',
            'generation': 'generation',
        }
    )

    graph.add_edge('retrieval', 'generation')
    graph.add_edge('generation', 'output_guardrail')
    graph.add_edge('output_guardrail', END)

    return graph


def create_chat_graph() -> StateGraph:
    mode = os.getenv('ORCHESTRATOR_MODE', 'react').lower()

    if mode == 'legacy':
        logger.info("Using legacy linear pipeline graph")
        return create_legacy_chat_graph()
    elif mode == 'v2':
        logger.info("Using v2 3-path routing graph")
        return create_v2_chat_graph()
    else:
        logger.info("Using ReAct pattern graph")
        return create_react_chat_graph()


def get_compiled_graph():
    graph = create_chat_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


def get_simple_compiled_graph():
    graph = create_simple_chat_graph()
    return graph.compile()


_compiled_graph = None
_simple_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = get_compiled_graph()
    return _compiled_graph


def get_simple_graph():
    global _simple_compiled_graph
    if _simple_compiled_graph is None:
        _simple_compiled_graph = get_simple_compiled_graph()
    return _simple_compiled_graph


def get_graph_for_chat_type(chat_type: str):
    if chat_type == 'general':
        return get_simple_graph()
    return get_graph()


def reset_graph():
    global _compiled_graph, _simple_compiled_graph
    _compiled_graph = None
    _simple_compiled_graph = None
