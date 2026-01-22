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

from .state import ChatState, ChatState_v2, SimpleState, UnifiedState
from .checkpointer import get_checkpointer
from .routing import (
    route_after_query_analysis,
    route_after_sufficiency,
    route_after_review as route_after_review_v2,
    route_after_generation,
)
from .budget import check_budget, BudgetTracker
from .nodes.search_plan import search_plan_node
from .nodes.sufficiency import sufficiency_node
from ..agents.query_analysis.agent import query_analysis_node
from ..agents.query_analysis.tools import ask_clarification_node as legacy_ask_clarification_node
from .nodes.clarify import ask_clarification_node
from ..agents.retrieval.agent import retrieval_node, retrieval_node_v2
from ..agents.answer_generation.agent import generation_node
from ..agents.answer_generation.tools.prompts import low_similarity_prompt_node
from ..agents.legal_review.agent import review_node, review_node_wrapper
from ..agents.react.react_think import react_think_node
from ..agents.react.react_act import react_act_node
from ..guardrail.nodes import input_guardrail_node, output_guardrail_node

logger = logging.getLogger(__name__)

NODE_TIMINGS_KEY = '_node_timings'

# 노드별 스냅샷 대상 필드 정의
NODE_SNAPSHOT_FIELDS = {
    'query_analysis': {
        'input': ['user_query', 'onboarding', 'chat_type'],
        'output': ['query_analysis', 'mode', 'query_analysis_v2'],
    },
    'retrieval': {
        'input': ['user_query', 'query_analysis', 'onboarding'],
        'output': ['retrieval', 'sources'],
    },
    'react_think': {
        'input': ['user_query', 'retrieval', 'react_steps', 'iteration_count'],
        'output': ['last_thought', 'last_action', 'should_continue', 'iteration_count'],
    },
    'react_act': {
        'input': ['last_action', 'last_thought'],
        'output': ['retrieval', 'tool_result'],
    },
    'generation': {
        'input': ['user_query', 'retrieval', 'query_analysis', 'react_steps'],
        'output': ['final_answer', 'draft_answer'],
    },
    'review': {
        'input': ['final_answer', 'draft_answer', 'retrieval'],
        'output': ['review', 'retry_count'],
    },
    'search_plan': {
        'input': ['user_query', 'query_analysis_v2'],
        'output': ['search_plan', 'iteration_count'],
    },
    'sufficiency': {
        'input': ['retrieval', 'search_plan'],
        'output': ['is_sufficient', 'mode'],
    },
    'input_guardrail': {
        'input': ['user_query'],
        'output': ['guardrail_blocked', 'guardrail_type'],
    },
    'output_guardrail': {
        'input': ['final_answer'],
        'output': ['guardrail_blocked', 'final_answer'],
    },
}


def _snapshot_state(state: Dict[str, Any], fields: list) -> Dict[str, Any]:
    """상태에서 지정된 필드만 추출하여 스냅샷 생성"""
    snapshot = {}
    for field in fields:
        if field in state:
            value = state[field]
            # 직렬화 가능하도록 처리
            if hasattr(value, '__dict__'):
                snapshot[field] = str(value)[:500]  # 객체는 문자열로 변환 (500자 제한)
            elif isinstance(value, (list, dict)):
                try:
                    import json
                    serialized = json.dumps(value, ensure_ascii=False, default=str)
                    snapshot[field] = json.loads(serialized[:2000])  # 2KB 제한
                except Exception:
                    snapshot[field] = str(value)[:500]
            else:
                snapshot[field] = value
    return snapshot


def _detect_state_changes(input_state: Dict[str, Any], output: Dict[str, Any]) -> list:
    """출력에서 변경/추가된 필드 목록 반환"""
    changes = []
    for key in output.keys():
        if key.startswith('_'):
            continue  # 내부 필드 제외
        if key not in input_state:
            changes.append(f"+{key}")  # 새로 추가된 필드
        elif input_state.get(key) != output.get(key):
            changes.append(f"~{key}")  # 변경된 필드
    return changes


def _create_timed_node(node_fn: Callable, node_name: str) -> Callable:
    """노드 함수를 감싸서 실행 시간과 I/O 스냅샷을 기록하는 래퍼 생성"""
    def timed_wrapper(state: ChatState) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[NODE START] {node_name}")

        # 입력 스냅샷 수집
        snapshot_config = NODE_SNAPSHOT_FIELDS.get(node_name, {'input': [], 'output': []})
        input_snapshot = _snapshot_state(dict(state), snapshot_config['input'])

        result = node_fn(state)

        end_time = time.time()
        duration_ms = round((end_time - start_time) * 1000, 2)
        logger.info(f"[NODE END] {node_name} - {duration_ms}ms")

        # 출력 스냅샷 수집
        output_snapshot = _snapshot_state(result, snapshot_config['output'])

        # 상태 변경 감지
        state_changes = _detect_state_changes(dict(state), result)

        existing_timings = state.get(NODE_TIMINGS_KEY)
        timings = dict(existing_timings) if existing_timings else {}
        timings[node_name] = {
            'start': start_time,
            'end': end_time,
            'duration_ms': duration_ms,
            'input_snapshot': input_snapshot,
            'output_snapshot': output_snapshot,
            'state_changes': state_changes,
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

    # query_analysis → react_think 또는 ask_clarification 또는 generation (Phase 4)
    graph.add_conditional_edges(
        'query_analysis',
        _route_after_query_analysis_react,
        {
            'ask_clarification': 'ask_clarification',
            'react_think': 'react_think',
            'generation': 'generation',  # NO_RETRIEVAL 모드용
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

    graph.add_conditional_edges(
        'generation',
        route_after_generation,
        {
            'review': 'review',
            'output_guardrail': 'output_guardrail',
        }
    )

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

    # draft_answer 또는 final_answer 중 하나 사용
    final_answer = result.get('final_answer') or result.get('draft_answer', '')
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


# === PR-2: 통합 그래프 라우팅 함수 ===

def _route_unified_after_guardrail(state: UnifiedState) -> str:
    """input_guardrail 이후 라우팅"""
    if state.get('guardrail_blocked'):
        return END
    return 'query_analysis'


def _route_unified_after_query_analysis(
    state: UnifiedState
) -> Literal['react_think', 'generation', 'ask_clarification']:
    """
    query_analysis 이후 라우팅 (통합 버전)

    - NO_RETRIEVAL 모드 → generation (직접 생성)
    - NEED_CLARIFICATION 모드 → ask_clarification (역질문)
    - NEED_RAG 모드 → react_think (ReAct 루프)
    """
    mode = state.get('mode', 'NEED_RAG')
    query_analysis = state.get('query_analysis')

    if mode == 'NO_RETRIEVAL':
        logger.info("[Unified] NO_RETRIEVAL mode, skipping ReAct loop")
        return 'generation'

    # PR-4: NEED_CLARIFICATION 분기 (두 가지 모드 모두 체크)
    if mode in ('NEED_CLARIFICATION', 'NEED_USER_CLARIFICATION'):
        logger.info(f"[Unified] {mode} mode, asking user")
        return 'ask_clarification'

    if query_analysis:
        query_type = query_analysis.get('query_type')
        if query_type in ('general', 'system_meta'):
            logger.info(f"[Unified] Query type={query_type}, skipping ReAct loop")
            return 'generation'

        # PR-4: needs_clarification 플래그 확인
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
    react_think 이후 라우팅 (통합 버전)

    - should_continue=True AND action 있음 → react_act
    - should_continue=False → generation
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
    review 이후 라우팅 (통합 버전)

    - retry 필요 시 → generation
    - 그 외 → output_guardrail
    """
    review = state.get('review')
    retry_count = state.get('retry_count', 0)
    chat_type = state.get('chat_type', 'dispute')

    # 일반 채팅은 retry 없음
    if chat_type == 'general':
        return 'output_guardrail'

    # 분쟁 상담: retry 로직
    if review and not review.get('passed') and retry_count < 2:
        return 'generation'

    return 'output_guardrail'


def create_unified_chat_graph() -> StateGraph:
    """
    PR-2: 통합 ReAct 그래프 + PR-4: Clarify 기능

    분쟁상담/일반채팅 모두 단일 그래프로 처리.
    chat_type과 mode에 따라 동적으로 경로 결정.

    아키텍처:
    input_guardrail → query_analysis → [라우팅]
        ├─ NO_RETRIEVAL: generation → review → output_guardrail → END
        ├─ NEED_CLARIFICATION: ask_clarification → END
        └─ NEED_RAG: react_think ↔ react_act → generation → review → output_guardrail → END

    - review: chat_type=general이면 자동 통과 (review_node_wrapper)
    - max_iterations: general=1, dispute=2 (state 초기화 시 설정)
    - ask_clarification: 유사도 낮거나 필수 정보 누락 시 역질문
    """
    graph = StateGraph(UnifiedState)

    # 노드 등록
    graph.add_node('input_guardrail', _create_timed_node(input_guardrail_node, 'input_guardrail'))
    graph.add_node('query_analysis', _create_timed_node(query_analysis_node, 'query_analysis'))
    graph.add_node('react_think', _create_timed_node(react_think_node, 'react_think'))
    graph.add_node('react_act', _create_timed_node(react_act_node, 'react_act'))
    graph.add_node('generation', _create_timed_node(generation_node, 'generation'))
    graph.add_node('review', _create_timed_node(review_node_wrapper, 'review'))
    graph.add_node('output_guardrail', _create_timed_node(output_guardrail_node, 'output_guardrail'))
    # PR-4: Clarify 노드
    graph.add_node('ask_clarification', _create_timed_node(ask_clarification_node, 'ask_clarification'))

    # 진입점
    graph.set_entry_point('input_guardrail')

    # input_guardrail → query_analysis 또는 END
    graph.add_conditional_edges(
        'input_guardrail',
        _route_unified_after_guardrail,
        {
            END: END,
            'query_analysis': 'query_analysis',
        }
    )

    # query_analysis → react_think, generation, 또는 ask_clarification
    graph.add_conditional_edges(
        'query_analysis',
        _route_unified_after_query_analysis,
        {
            'react_think': 'react_think',
            'generation': 'generation',
            'ask_clarification': 'ask_clarification',
        }
    )

    # react_think → react_act 또는 generation
    graph.add_conditional_edges(
        'react_think',
        _route_unified_after_react_think,
        {
            'react_act': 'react_act',
            'generation': 'generation',
        }
    )

    # react_act → react_think (루프)
    graph.add_edge('react_act', 'react_think')

    # generation → review
    graph.add_edge('generation', 'review')

    # review → output_guardrail 또는 generation (retry)
    graph.add_conditional_edges(
        'review',
        _route_unified_after_review,
        {
            'generation': 'generation',
            'output_guardrail': 'output_guardrail',
        }
    )

    # output_guardrail → END
    graph.add_edge('output_guardrail', END)

    # PR-4: ask_clarification → END
    graph.add_edge('ask_clarification', END)

    return graph


def get_unified_compiled_graph():
    """통합 그래프 컴파일"""
    graph = create_unified_chat_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


_unified_compiled_graph = None


def get_unified_graph():
    """통합 그래프 싱글톤"""
    global _unified_compiled_graph
    if _unified_compiled_graph is None:
        _unified_compiled_graph = get_unified_compiled_graph()
    return _unified_compiled_graph


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
    """
    PR-2: 모든 chat_type에 대해 통합 그래프 반환

    chat_type별 동작 차이는 state 초기화 시 설정:
    - general: max_iterations=1, review 자동 통과
    - dispute: max_iterations=2, 전체 review 수행
    """
    # 항상 통합 그래프 반환
    return get_unified_graph()


def reset_graph():
    global _compiled_graph, _simple_compiled_graph, _unified_compiled_graph
    _compiled_graph = None
    _simple_compiled_graph = None
    _unified_compiled_graph = None
