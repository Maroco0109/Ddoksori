"""
똑소리 프로젝트 - ReAct 액션 노드
작성일: 2026-01-17
S2-7: ReAct 패턴 구현 - 액션(Action) 노드
S2-PR1: 액션 레지스트리 패턴 도입 (2026-01-21)

ReAct 패턴의 Action 단계를 담당하는 노드.
ActionRegistry를 통해 last_action에 따라 적절한 도구를 실행.
"""

from typing import Dict

from ...orchestrator.state import ChatState
from .action_registry import ActionRegistry


def _build_search_query(state: ChatState) -> str:
    user_query = state.get('user_query', '')
    onboarding = state.get('onboarding')
    query_analysis = state.get('query_analysis') or {}

    query_parts = [user_query]

    if onboarding:
        onboarding_dict = dict(onboarding)
        purchase_item = onboarding_dict.get('purchase_item')
        dispute_details = onboarding_dict.get('dispute_details')
        if purchase_item:
            query_parts.append(f"품목: {purchase_item}")
        if dispute_details:
            query_parts.append(f"상황: {dispute_details}")

    rewritten_query = query_analysis.get('rewritten_query')
    if rewritten_query:
        return rewritten_query

    return " ".join(query_parts)


def react_act_node(state: ChatState) -> Dict:
    """
    ReAct 액션 노드

    ActionRegistry를 통해 last_action에 따라 적절한 도구(검색기)를 실행하고
    결과를 state에 저장, react_steps에 기록.

    지원 액션 (ActionRegistry에 등록된 액션):
    - search_all: 전체 섹션 검색
    - search_criteria: 분쟁해결기준만 검색
    - search_laws: 법령만 검색
    - ask_clarification: 사용자에게 추가 정보 요청

    Args:
        state: 현재 ChatState

    Returns:
        부분 상태 업데이트:
        {
            'retrieval': RetrievalResult,
            'sources': List[Dict],
            'last_observation': str,
            'react_steps': List[ReActStep],
        }
    """
    action = state.get('last_action')
    thought = state.get('last_thought', '')
    query = _build_search_query(state)

    return ActionRegistry.execute(action, state, query, thought)
