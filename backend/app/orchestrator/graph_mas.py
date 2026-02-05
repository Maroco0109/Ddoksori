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


# ============================================================================
# Phase 2-2: Supervisor LLM 설정
# ============================================================================

def _create_supervisor_llm():
    """
    환경 변수 기반 Supervisor LLM 생성

    환경 변수:
    - SUPERVISOR_LLM_ENABLED: "true"로 설정 시 LLM 활성화
    - SUPERVISOR_LLM_MODEL: 사용할 모델 (기본: gpt-4o-mini)

    Returns:
        LLM 클라이언트 또는 None (비활성화 시)
    """
    enabled = os.getenv("SUPERVISOR_LLM_ENABLED", "false").lower() == "true"

    if not enabled:
        logger.info("[SupervisorLLM] LLM 비활성화 (SUPERVISOR_LLM_ENABLED != true)")
        return None

    model = os.getenv("SUPERVISOR_LLM_MODEL", "gpt-4o-mini")
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        logger.warning("[SupervisorLLM] OPENAI_API_KEY 미설정. 규칙 기반 모드로 전환.")
        return None

    try:
        from langchain_openai import ChatOpenAI

        class AsyncLLMWrapper:
            """LangChain ChatOpenAI를 Supervisor LLM 프로토콜로 래핑"""

            def __init__(self, chat_model):
                self.chat_model = chat_model

            async def generate(self, prompt: str) -> str:
                response = await self.chat_model.ainvoke(prompt)
                return response.content

        llm = ChatOpenAI(
            model=model,
            temperature=0,
            max_tokens=300,
            api_key=api_key,
        )

        logger.info(f"[SupervisorLLM] LLM 활성화: model={model}")
        return AsyncLLMWrapper(llm)

    except ImportError:
        logger.warning("[SupervisorLLM] langchain_openai 미설치. 규칙 기반 모드로 전환.")
        return None
    except Exception as e:
        logger.error(f"[SupervisorLLM] LLM 초기화 실패: {e}. 규칙 기반 모드로 전환.")
        return None


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

    # 1. 가드레일
    graph.add_node('input_guardrail', _create_timed_node(input_guardrail_node, 'input_guardrail'))
    graph.add_node('output_guardrail', _create_timed_node(output_guardrail_node, 'output_guardrail'))

    # 2. Supervisor (환경 변수 기반 LLM 활성화)
    supervisor_llm = _create_supervisor_llm()
    supervisor = SupervisorNode(llm=supervisor_llm)
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
