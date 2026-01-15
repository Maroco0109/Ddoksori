"""
똑소리 프로젝트 - LangGraph 그래프 정의
작성일: 2026-01-14
S2-3: 오케스트레이터 워크플로우 정의 및 컴파일

워크플로우:
query_analysis → (조건) → retrieval → generation → review → (조건) → END
                    ↘ ask_clarification → END
"""

from typing import Literal

from langgraph.graph import StateGraph, END

from .state import ChatState
from .checkpointer import get_checkpointer
from .nodes import (
    query_analysis_node,
    retrieval_node,
    generation_node,
    review_node,
    ask_clarification_node,
)


def _route_after_query_analysis(state: ChatState) -> Literal['ask_clarification', 'retrieval']:
    """
    query_analysis 이후 라우팅
    
    - needs_clarification=True → ask_clarification (추가 정보 요청)
    - else → retrieval (검색 진행)
    """
    query_analysis = state.get('query_analysis')
    if query_analysis and query_analysis.get('needs_clarification'):
        return 'ask_clarification'
    return 'retrieval'


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
    """
    LangGraph StateGraph 생성
    
    노드:
    - query_analysis: 질의 분류, 키워드 추출, 누락 필드 탐지
    - retrieval: 4섹션 검색 (disputes, counsels, laws, criteria)
    - generation: LLM 답변 생성
    - review: 규칙 기반 검토 (금지 표현, 출처 검사)
    - ask_clarification: 추가 정보 요청 메시지 생성
    
    Returns:
        구성된 StateGraph (컴파일 전)
    """
    graph = StateGraph(ChatState)
    
    graph.add_node('query_analysis', query_analysis_node)
    graph.add_node('retrieval', retrieval_node)
    graph.add_node('generation', generation_node)
    graph.add_node('review', review_node)
    graph.add_node('ask_clarification', ask_clarification_node)
    
    graph.set_entry_point('query_analysis')
    
    graph.add_conditional_edges(
        'query_analysis',
        _route_after_query_analysis,
        {
            'ask_clarification': 'ask_clarification',
            'retrieval': 'retrieval',
        }
    )
    
    graph.add_edge('retrieval', 'generation')
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
