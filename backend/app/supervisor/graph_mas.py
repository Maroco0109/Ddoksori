"""
똑소리 프로젝트 - MAS Supervisor 그래프 정의

[현재 운영] Phase 7에서 기본 그래프로 전환됨.

포함된 그래프:
- create_mas_supervisor_graph(): Hub-Spoke 패턴 Supervisor 그래프
- 4개 Retrieval Agent 병렬 실행 (Fan-out/Fan-in)
"""

import os
import logging
import time
from typing import Callable, Dict, Any, List

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from .state import ChatState
from .graph import _create_timed_node
from .checkpointer import get_checkpointer
from .nodes.supervisor import SupervisorNode
from .nodes.retrieval_merge import retrieval_merge_node_sync
from .nodes.clarify import ask_clarification_node
from ..agents.query_analysis.agent import query_analysis_node
from ..agents.answer_generation.agent import generation_node
from ..agents.legal_review.agent import review_node_wrapper
from ..guardrail.nodes import input_guardrail_node, output_guardrail_node

logger = logging.getLogger(__name__)


# === PR-6: 캐시 관련 함수 ===
from .cache import SupervisorResponseCache, QueryAnalysisCache


def _cache_check_node(state: ChatState) -> Dict[str, Any]:
    """L1 캐시 체크 노드"""
    messages = state.get('messages', [])
    if not messages:
        return {'_cache_hit': False}

    # Extract user_query from messages
    last_msg = messages[-1]
    if hasattr(last_msg, 'content'):
        user_query = last_msg.content
    elif isinstance(last_msg, dict):
        user_query = last_msg.get('content', '')
    else:
        user_query = str(last_msg)

    session_id = state.get('session_id')

    cached = SupervisorResponseCache.get(user_query, session_id)
    if cached:
        logger.info(f"[L1 Cache] HIT for query: {user_query[:30]}...")
        return {
            '_cache_hit': True,
            '_cached_response': cached,
            'user_query': user_query,  # Save extracted user_query to state
        }

    return {
        '_cache_hit': False,
        'user_query': user_query,  # Save extracted user_query to state
    }


def _cache_response_node(state: ChatState) -> Dict[str, Any]:
    """캐시된 응답 반환 노드"""
    cached = state.get('_cached_response', {})
    logger.info("[L1 Cache] Returning cached response")
    return {
        'final_answer': cached.get('final_answer'),
        'mode': cached.get('mode'),
        'citations': cached.get('citations', []),
    }


def _route_cache_check(state: ChatState) -> str:
    """캐시 히트 여부에 따른 라우팅"""
    if state.get('_cache_hit'):
        return "cache_response"
    return "input_guardrail"
# === PR-6 끝 ===


# ============================================================================
# Retrieval Agent 노드 팩토리
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


# ============================================================================
# MAS Supervisor 라우팅
# ============================================================================

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
    supervisor_state = state.get('supervisor') or {}
    next_agent = supervisor_state.get('next_agent')

    logger.info(f"[MAS Router] next_agent={next_agent}")

    mode = state.get("mode", "NEED_RAG")
    if mode in ('NEED_USER_CLARIFICATION', 'NEED_CLARIFICATION'):
        logger.info(f"[MAS Router] Routing to ask_clarification for mode={mode}")
        return 'ask_clarification'

    if mode == "NO_RETRIEVAL" and next_agent == "retrieval_team":
        logger.info("[MAS Router] Fast path: NO_RETRIEVAL - skipping retrieval, routing to generation")
        return "generation"

    # === PR-2: Selective Retrieval 시작 ===
    if next_agent == 'retrieval_team':
        query_analysis = state.get('query_analysis', {})
        retriever_types = query_analysis.get('retriever_types', ['law', 'criteria', 'case'])

        fan_out_list = []

        if 'law' in retriever_types:
            fan_out_list.append(Send('retrieval_law', state))

        if 'criteria' in retriever_types:
            fan_out_list.append(Send('retrieval_criteria', state))

        if 'case' in retriever_types:
            fan_out_list.append(Send('retrieval_case', state))

        # counsel agent는 현재 사용하지 않음 (case로 통합)

        logger.info(f"[MAS Router] Selective fan-out to {len(fan_out_list)} retrieval agents: {retriever_types}")

        # 빈 리스트면 generation으로 (검색 불필요)
        if not fan_out_list:
            logger.info("[MAS Router] No retrievers needed, routing to generation")
            return "generation"

        return fan_out_list
    # === PR-2: Selective Retrieval 끝 ===

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


# ============================================================================
# MAS Supervisor 그래프 생성
# ============================================================================

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

    # === PR-6: L1 캐시 노드 추가 ===
    graph.add_node('cache_check', _cache_check_node)
    graph.add_node('cache_response', _cache_response_node)
    # === PR-6 끝 ===

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

    # === PR-6: 엔트리포인트 변경 ===
    logger.info("[PR-6 DEBUG] Setting entry point to 'cache_check'")
    graph.set_entry_point('cache_check')
    logger.info("[PR-6 DEBUG] Entry point set successfully")

    # cache_check → cache_response 또는 input_guardrail
    graph.add_conditional_edges(
        'cache_check',
        _route_cache_check,
        {
            'cache_response': 'cache_response',
            'input_guardrail': 'input_guardrail',
        }
    )

    # cache_response → END
    graph.add_edge('cache_response', END)
    # === PR-6 끝 ===

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
            'ask_clarification': 'ask_clarification',
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


# ============================================================================
# 컴파일 및 싱글톤
# ============================================================================

_mas_compiled_graph = None


def get_mas_supervisor_compiled_graph():
    """MAS Supervisor 그래프 컴파일"""
    graph = create_mas_supervisor_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


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
