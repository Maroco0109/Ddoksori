"""
똑소리 프로젝트 - LangGraph 그래프 정의
작성일: 2026-01-14
S2-3: 오케스트레이터 워크플로우 정의 및 컴파일

워크플로우:
query_analysis → (조건) → retrieval → generation → review → (조건) → END
                    ↘ ask_clarification → END
"""

import os
from typing import Literal, Dict, Any, Callable
import time
import logging

from langgraph.graph import StateGraph, END

from .state import ChatState
from .checkpointer import get_checkpointer
from .nodes import (
    query_analysis_node,
    retrieval_node,
    generation_node,
    review_node,
    ask_clarification_node,
    low_similarity_prompt_node,
)

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


def _route_after_review(state: ChatState) -> Literal['generation', '__end__']:
    """
    review 이후 라우팅
    
    - passed=False AND retry_count < 2 → generation (재생성)
    - else → END (완료)
    """
    review = state.get('review')
    retry_count = state.get('retry_count', 0)
    
    if review and not review.get('passed') and retry_count < 2:
        return 'generation'
    return END


def create_chat_graph() -> StateGraph:
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


def get_compiled_graph():
    """
    Checkpointer와 함께 컴파일된 그래프 반환
    
    thread_id(=session_id)별로 상태가 저장됨.
    CHECKPOINTER_MODE 환경변수로 저장소 선택 (기본: memory)
    """
    graph = create_chat_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


_compiled_graph = None


def get_graph():
    """
    앱 전역에서 사용할 컴파일된 그래프 반환 (싱글톤)
    
    최초 호출 시 한 번만 컴파일하고, 이후에는 캐시된 인스턴스 반환.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = get_compiled_graph()
    return _compiled_graph


def reset_graph():
    """
    그래프 인스턴스 리셋 (테스트용)
    
    테스트에서 새로운 checkpointer로 그래프를 재생성할 때 사용.
    """
    global _compiled_graph
    _compiled_graph = None
