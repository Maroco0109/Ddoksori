"""
똑소리 프로젝트 - LangGraph 그래프 정의 (Orchestrator Graph)

작성일: 2026-01-14
최종 수정: 2026-01-23 (v2 스키마 제거)

[역할]
전체 시스템의 워크플로우를 정의합니다. LangGraph를 사용하여 노드(Node)와 엣지(Edge)를 연결하고,
상태(State) 흐름을 제어합니다.

[주요 그래프]
- create_unified_chat_graph(): 현재 운영 중인 메인 그래프.
  ReAct 패턴, Fast Path, Clarification 기능을 모두 포함합니다.

[워크플로우 요약]
InputGuard -> QueryAnalysis -> [Routing] -> (ReAct Loop / Generation / Clarify) -> Review -> OutputGuard
"""

import os
from typing import Literal, Dict, Any, Callable, List
import time
import logging

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from .state import ChatState, UnifiedState
from .nodes.supervisor import (
    SupervisorNode,
    supervisor_router,
    create_initial_supervisor_state,
)
from .nodes.retrieval_merge import retrieval_merge_node_sync
from .checkpointer import get_checkpointer
from ..agents.query_analysis.agent import query_analysis_node
from .nodes.clarify import ask_clarification_node
from ..agents.retrieval.agent import retrieval_node
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
        'output': ['query_analysis', 'mode'],
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


def create_react_chat_graph() -> StateGraph:
    """
    [DEPRECATED] ReAct 패턴 그래프 (S2-7)

    query_analysis → react_think ⟷ react_act → generation → review → END
                        ↘ ask_clarification → END

    Note:
        Phase 5에서 create_mas_supervisor_graph()로 대체됨.
        Supervisor 기반 의사결정으로 ReAct 루프 제거.

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
    [Query Analysis 후 라우팅] (통합 그래프용)

    질의 분석 결과를 바탕으로 다음 단계를 결정합니다.

    1. NO_RETRIEVAL: 검색 불필요 (일반 대화, 시스템 질문) -> 즉시 답변 생성 (Generation)
    2. NEED_CLARIFICATION: 정보 부족/모호 -> 사용자에게 되묻기 (Ask Clarification)
    3. NEED_RAG (Default): 정보 검색 필요 -> ReAct 추론 루프 시작 (ReAct Think)
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
    [ReAct Think 후 라우팅]

    ReAct 에이전트의 사고(Thought) 결과에 따라 행동을 결정합니다.

    1. should_continue=True: 도구 사용 필요 -> 도구 실행 (ReAct Act)
    2. should_continue=False: 충분한 정보 수집 완료 -> 답변 생성 (Generation)
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

    검토 결과를 확인하고 재시도 여부를 결정합니다.

    1. 검토 통과 (Passed): 출력 가드레일(Output Guardrail)로 이동
    2. 검토 실패 & 재시도 횟수 남음: 다시 생성(Generation)으로 회귀
    3. 검토 실패 & 재시도 초과: 그냥 출력 (Output Guardrail) - 실패 사유 포함될 수 있음
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
    [DEPRECATED] 통합 ReAct 그래프 생성

    PR-2에서 도입된 통합 그래프입니다. 분쟁상담과 일반채팅을 모두 처리할 수 있는 단일 그래프 구조를 가집니다.

    Note:
        Phase 5에서 create_mas_supervisor_graph()로 대체 예정.
        MAS 전환 완료 전까지 운영 유지.

    [Architecture]
    1. Input Guardrail: 사용자 입력 필터링
    2. Query Analysis: 의도 파악 및 라우팅 결정
    3. Branching (분기):
       - NO_RETRIEVAL -> Generation (바로 답변)
       - NEED_CLARIFICATION -> Ask Clarification (되묻기)
       - NEED_RAG -> ReAct Loop (Think <-> Act) -> Generation
    4. Generation: 답변 생성
    5. Legal Review: 법률/정책 위반 검토 (실패 시 Retry Loop)
    6. Output Guardrail: 최종 출력 필터링
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
    else:
        logger.info("Using ReAct pattern graph")
        return create_react_chat_graph()


def get_compiled_graph():
    graph = create_chat_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = get_compiled_graph()
    return _compiled_graph


def get_graph_for_chat_type(chat_type: str, session_id: str = None):
    """
    Phase 6: Feature Flag 기반 그래프 선택

    chat_type별 동작 차이는 state 초기화 시 설정:
    - general: max_iterations=1, review 자동 통과
    - dispute: max_iterations=2, 전체 review 수행

    Feature Flag:
    - MAS_SUPERVISOR_ENABLED=true: MAS Supervisor 그래프 사용
    - MAS_SUPERVISOR_CANARY_PERCENT=N: N% 트래픽에 MAS 그래프 적용 (Canary 배포)

    Args:
        chat_type: 'dispute' 또는 'general'
        session_id: Canary 배포 시 일관된 라우팅을 위한 세션 ID (선택)

    Returns:
        컴파일된 LangGraph 그래프
    """
    # 1. 전체 전환 플래그 확인
    if os.getenv('MAS_SUPERVISOR_ENABLED', 'false').lower() == 'true':
        logger.info(f"[GraphSelect] MAS_SUPERVISOR_ENABLED=true, using MAS graph")
        return get_mas_supervisor_graph()

    # 2. Canary 배포 확인
    canary_percent = int(os.getenv('MAS_SUPERVISOR_CANARY_PERCENT', '0'))
    if canary_percent > 0 and session_id:
        # 세션 ID 해시 기반 일관된 라우팅 (같은 세션은 항상 같은 그래프)
        session_hash = hash(session_id) % 100
        if session_hash < canary_percent:
            logger.info(f"[GraphSelect] Canary {canary_percent}%, session in canary group, using MAS graph")
            return get_mas_supervisor_graph()

    # 3. 기본값: 기존 Unified 그래프
    return get_unified_graph()


def reset_graph():
    global _compiled_graph, _unified_compiled_graph
    _compiled_graph = None
    _unified_compiled_graph = None


# ============================================================================
# Phase 5: MAS Supervisor Graph (Fan-out/Fan-in 아키텍처)
# ============================================================================

def _create_retrieval_agent_node(agent_type: str) -> Callable:
    """
    특정 타입의 Retrieval Agent 노드 함수를 생성합니다.

    Args:
        agent_type: 'law', 'criteria', 'case', 'counsel' 중 하나

    Returns:
        LangGraph 노드 함수
    """
    from ..agents.retrieval.law_agent import law_retrieval_agent
    from ..agents.retrieval.criteria_agent import criteria_retrieval_agent
    from ..agents.retrieval.case_agent import case_retrieval_agent
    from ..agents.retrieval.counsel_agent import counsel_retrieval_agent

    agent_map = {
        'law': law_retrieval_agent,
        'criteria': criteria_retrieval_agent,
        'case': case_retrieval_agent,
        'counsel': counsel_retrieval_agent,
    }

    agent = agent_map.get(agent_type)

    async def retrieval_agent_node(state: ChatState) -> Dict[str, Any]:
        """개별 Retrieval Agent 노드"""
        import time
        start_time = time.time()

        user_query = state.get('user_query', '')
        query_analysis = state.get('query_analysis', {})

        request = {
            'context': {
                'user_query': user_query,
                'query_analysis': query_analysis,
            },
            'params': {'top_k': 3},
        }

        try:
            result = await agent.process(request)
            search_time_ms = (time.time() - start_time) * 1000

            # IndividualRetrievalResult 형식으로 변환
            individual_result = {
                'source': agent_type,
                'documents': result.get('result', {}).get('results', []),
                'max_similarity': result.get('result', {}).get('max_similarity', 0.0),
                'avg_similarity': result.get('result', {}).get('avg_similarity', 0.0),
                'search_time_ms': search_time_ms,
            }

            if result.get('status') == 'failure':
                individual_result['error'] = result.get('message', 'Unknown error')

            logger.info(
                f"[RetrievalAgent:{agent_type}] {len(individual_result['documents'])} docs, "
                f"max_sim={individual_result['max_similarity']:.3f}, "
                f"time={search_time_ms:.1f}ms"
            )

        except Exception as e:
            individual_result = {
                'source': agent_type,
                'documents': [],
                'max_similarity': 0.0,
                'avg_similarity': 0.0,
                'search_time_ms': (time.time() - start_time) * 1000,
                'error': str(e),
            }
            logger.error(f"[RetrievalAgent:{agent_type}] Error: {e}")

        # operator.add로 누적되도록 리스트로 반환
        return {'individual_retrieval_results': [individual_result]}

    return retrieval_agent_node


def _route_mas_supervisor(state: ChatState):
    """
    MAS Supervisor의 결정을 기반으로 다음 노드를 결정합니다.

    routing 맵:
    - query_analyst → query_analysis 노드
    - retrieval_team → Fan-out (4개 Agent 병렬 실행) - List[Send] 반환
    - answer_drafter → generation 노드
    - legal_reviewer → review 노드
    - respond/None → output_guardrail

    Args:
        state: 현재 ChatState

    Returns:
        다음 노드 이름 (str) 또는 List[Send] (Fan-out)
    """
    supervisor_state = state.get('supervisor', {})
    next_agent = supervisor_state.get('next_agent')

    logger.info(f"[MAS Router] next_agent={next_agent}")

    # retrieval_team → Fan-out (4개 Agent 병렬)
    if next_agent == 'retrieval_team':
        logger.info("[MAS Router] Fan-out to 4 retrieval agents")
        return [
            Send('retrieval_law', state),
            Send('retrieval_criteria', state),
            Send('retrieval_case', state),
            Send('retrieval_counsel', state),
        ]

    # 라우팅 맵
    routing_map = {
        'query_analyst': 'query_analysis',
        'answer_drafter': 'generation',
        'legal_reviewer': 'review',
    }

    if next_agent in routing_map:
        return routing_map[next_agent]

    # respond 또는 None → 출력
    return 'output_guardrail'


def create_mas_supervisor_graph() -> StateGraph:
    """
    MAS Supervisor 그래프 생성 (Phase 5)

    [Architecture - Hub-Spoke Pattern]

    Entry → input_guardrail → supervisor ←→ [Agents] → output_guardrail → END

    [Supervisor → Agent 라우팅]
    - query_analyst → query_analysis 노드
    - retrieval_team → Fan-out (4개 Retrieval Agent 병렬) → retrieval_merge
    - answer_drafter → generation 노드
    - legal_reviewer → review 노드

    [Fan-out/Fan-in for Retrieval]
    supervisor → fan_out → [law|criteria|case|counsel] → retrieval_merge → supervisor

    [주요 특징]
    1. ReAct 루프 제거 → Supervisor 기반 의사결정
    2. 4개 Retrieval Agent 병렬 실행 (LangGraph Send API)
    3. 규칙 기반 fallback으로 안정성 보장
    4. 최대 10회 iteration 제한

    Returns:
        컴파일 전 StateGraph
    """
    graph = StateGraph(ChatState)

    # === 노드 등록 ===

    # 1. 가드레일
    graph.add_node('input_guardrail', _create_timed_node(input_guardrail_node, 'input_guardrail'))
    graph.add_node('output_guardrail', _create_timed_node(output_guardrail_node, 'output_guardrail'))

    # 2. Supervisor (LLM 없이 규칙 기반으로 시작)
    supervisor = SupervisorNode(llm=None)
    graph.add_node('supervisor', supervisor.as_node())

    # 3. 기능 에이전트
    graph.add_node('query_analysis', _create_timed_node(query_analysis_node, 'query_analysis'))
    graph.add_node('generation', _create_timed_node(generation_node, 'generation'))
    graph.add_node('review', _create_timed_node(review_node_wrapper, 'review'))
    graph.add_node('ask_clarification', _create_timed_node(ask_clarification_node, 'ask_clarification'))

    # 4. Retrieval Agents (4개 병렬)
    for agent_type in ['law', 'criteria', 'case', 'counsel']:
        node_fn = _create_retrieval_agent_node(agent_type)
        graph.add_node(f'retrieval_{agent_type}', node_fn)

    # 5. Retrieval Merge (Fan-in)
    graph.add_node('retrieval_merge', retrieval_merge_node_sync)

    # === 엣지 설정 ===

    # Entry: input_guardrail
    graph.set_entry_point('input_guardrail')

    # input_guardrail → supervisor 또는 END
    graph.add_conditional_edges(
        'input_guardrail',
        lambda state: END if state.get('guardrail_blocked') else 'supervisor',
        {END: END, 'supervisor': 'supervisor'}
    )

    # supervisor → 다음 노드 (conditional routing)
    # Fan-out: retrieval_team → List[Send] 반환으로 4개 Agent 병렬 실행
    graph.add_conditional_edges(
        'supervisor',
        _route_mas_supervisor,
        {
            'query_analysis': 'query_analysis',
            'retrieval_law': 'retrieval_law',
            'retrieval_criteria': 'retrieval_criteria',
            'retrieval_case': 'retrieval_case',
            'retrieval_counsel': 'retrieval_counsel',
            'generation': 'generation',
            'review': 'review',
            'output_guardrail': 'output_guardrail',
        }
    )

    # 각 Retrieval Agent → retrieval_merge (Fan-in)
    for agent_type in ['law', 'criteria', 'case', 'counsel']:
        graph.add_edge(f'retrieval_{agent_type}', 'retrieval_merge')

    # retrieval_merge → supervisor (결과 보고)
    graph.add_edge('retrieval_merge', 'supervisor')

    # query_analysis → supervisor (결과 보고)
    graph.add_edge('query_analysis', 'supervisor')

    # generation → supervisor (결과 보고)
    graph.add_edge('generation', 'supervisor')

    # review → supervisor (결과 보고)
    graph.add_edge('review', 'supervisor')

    # output_guardrail → END
    graph.add_edge('output_guardrail', END)

    # ask_clarification → END
    graph.add_edge('ask_clarification', END)

    logger.info("[MAS Graph] Created MAS Supervisor graph with Fan-out/Fan-in architecture")

    return graph


def get_mas_supervisor_compiled_graph():
    """MAS Supervisor 그래프 컴파일"""
    graph = create_mas_supervisor_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


_mas_compiled_graph = None


def get_mas_supervisor_graph():
    """MAS Supervisor 그래프 싱글톤"""
    global _mas_compiled_graph
    if _mas_compiled_graph is None:
        _mas_compiled_graph = get_mas_supervisor_compiled_graph()
    return _mas_compiled_graph


def reset_mas_graph():
    """MAS 그래프 리셋"""
    global _mas_compiled_graph
    _mas_compiled_graph = None
