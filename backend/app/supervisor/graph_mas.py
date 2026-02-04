"""
똑소리 프로젝트 - MAS Supervisor 그래프 정의

[현재 운영] Phase 7에서 기본 그래프로 전환됨.

포함된 그래프:
- create_mas_supervisor_graph(): Hub-Spoke 패턴 Supervisor 그래프
- 4개 Retrieval Agent 병렬 실행 (Fan-out/Fan-in)
"""

import logging
import time
from typing import Any, Callable, Dict

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from ..guardrail.nodes import input_guardrail_node, output_guardrail_node
from .checkpointer import get_checkpointer
from .graph import _create_timed_node
from .nodes.memory_save import memory_save_node
from .nodes.retrieval_merge import retrieval_merge_node
from .nodes.supervisor import SupervisorNode
from .state import ChatState

logger = logging.getLogger(__name__)


# === PR-6: 캐시 관련 함수 ===
from .cache import SupervisorResponseCache


def _cache_check_node(state: ChatState) -> Dict[str, Any]:
    """L1 캐시 체크 노드 (Phase 3-E: 턴 번호 포함하여 반복 답변 방지)"""
    messages = state.get("messages", [])
    if not messages:
        return {"_cache_hit": False}

    # Extract user_query from messages
    last_msg = messages[-1]
    if hasattr(last_msg, "content"):
        user_query = last_msg.content
    elif isinstance(last_msg, dict):
        user_query = last_msg.get("content", "")
    else:
        user_query = str(last_msg)

    session_id = state.get("session_id")
    total_turn_count = state.get("total_turn_count", 0)

    # Phase 3-E: Prevent repeat answers by including turn count in cache key
    # For turn 2+, append turn context to prevent exact cache hits
    if total_turn_count > 1:
        cache_query = f"{user_query}::turn{total_turn_count}"
        logger.debug(f"[L1 Cache] Modified cache key for turn {total_turn_count}")
    else:
        cache_query = user_query

    cached = SupervisorResponseCache.get(cache_query, session_id)
    if cached:
        logger.info(
            f"[L1 Cache] HIT for query: {user_query[:30]}... (turn={total_turn_count})"
        )
        return {
            "_cache_hit": True,
            "_cached_response": cached,
            "user_query": user_query,  # Save extracted user_query to state
        }

    return {
        "_cache_hit": False,
        "user_query": user_query,  # Save extracted user_query to state
    }


def _cache_response_node(state: ChatState) -> Dict[str, Any]:
    """캐시된 응답 반환 노드"""
    cached = state.get("_cached_response", {})
    logger.info("[L1 Cache] Returning cached response")
    return {
        "final_answer": cached.get("final_answer"),
        "mode": cached.get("mode"),
        "citations": cached.get("citations", []),
    }


def _route_cache_check(state: ChatState) -> str:
    """캐시 히트 여부에 따른 라우팅"""
    if state.get("_cache_hit"):
        return "cache_response"
    return "input_guardrail"


def _inject_cached_retrieval_node(state: ChatState) -> Dict[str, Any]:
    """
    Phase 3-C: FOLLOWUP_WITH_CONTEXT 모드에서 캐시된 retrieval 결과를 state에 주입

    동작 순서:
    1. _last_turn_context.retrieval 우선 사용 (in-memory)
    2. 없으면 L4 RetrievalResultCache(Redis) 사용
    3. 둘 다 없으면 경고 로그 (generation이 fallback 처리)
    """
    session_id = state.get("session_id")
    mode = state.get("mode", "")

    if mode != "FOLLOWUP_WITH_CONTEXT":
        logger.warning(f"[inject_cached_retrieval] Called with mode={mode}, skipping")
        return {}

    # Try _last_turn_context first (in-memory from previous turn)
    last_context = state.get("_last_turn_context") or {}
    cached_retrieval = last_context.get("retrieval")

    if cached_retrieval:
        logger.info("[inject_cached_retrieval] Using _last_turn_context.retrieval")
        return {"retrieval": cached_retrieval}

    # Fallback to L4 Redis cache
    if session_id:
        from .cache import RetrievalResultCache

        cached = RetrievalResultCache.get_by_session(session_id)
        if cached:
            logger.info(
                f"[inject_cached_retrieval] Using L4 RetrievalResultCache for session={session_id[:8]}"
            )
            return {"retrieval": cached}

    logger.warning(
        f"[inject_cached_retrieval] No cached retrieval found for session={session_id[:8] if session_id else 'None'}"
    )
    return {}


# === PR-6 끝 ===


# ============================================================================
# MAS Supervisor (formerly v2)
# ============================================================================


def _create_retrieval_agent_node(agent_type: str) -> Callable:
    """
    Retrieval Agent 노드 v2 (메타데이터 필터 지원)

    변경사항:
    - metadata_filter 파라미터 지원
    - expanded_queries 사용
    - agent_keywords 사용
    """
    from ..agents.retrieval.case_agent import case_retrieval_agent
    from ..agents.retrieval.criteria_agent import criteria_retrieval_agent
    from ..agents.retrieval.law_agent import law_retrieval_agent

    agent_map = {
        "law": law_retrieval_agent,
        "criteria": criteria_retrieval_agent,
        "case": case_retrieval_agent,
    }

    agent = agent_map.get(agent_type)

    async def retrieval_agent_node(state: ChatState) -> Dict[str, Any]:
        """개별 Retrieval Agent 노드 (v2)"""
        start_time = time.time()

        # v2: query_analysis에서 expanded_queries 사용
        query_analysis = state.get("query_analysis") or {}
        expanded_queries = query_analysis.get("expanded_queries") or []
        user_query = state.get("user_query") or ""

        # v2: supervisor에서 전달받은 agent_keywords 사용
        supervisor_state = state.get("supervisor") or {}
        agent_keywords = supervisor_state.get("agent_keywords") or {}
        keywords = (
            agent_keywords.get(agent_type) or query_analysis.get("keywords") or []
        )

        # 메타데이터 필터 설정 (agent_type에 따라)
        metadata_filter = {}
        if agent_type == "law":
            metadata_filter = {
                "dataset_type": "law_guide",
                "document_types": ["법률", "시행령"],
            }
        elif agent_type == "criteria":
            metadata_filter = {
                "dataset_type": "law_guide",
                "document_types": ["행정규칙", "별표"],
            }
        elif agent_type == "case":
            metadata_filter = {
                "categories": ["조정", "해결", "상담"],
            }

        retrieval_task_input = {
            "expanded_queries": expanded_queries,
            "agent_keywords": keywords,
            "metadata_filter": metadata_filter,
            "top_k": 10,
            "ignore_threshold": agent_type in ("law", "criteria"),
        }

        request = {
            "context": {
                "user_query": user_query,
                "query_analysis": query_analysis,
                "retrieval_task_input": retrieval_task_input,
            },
        }

        try:
            if agent is None:
                raise ValueError(f"Agent '{agent_type}' not found in agent_map")

            result = await agent.process(request)
            search_time_ms = (time.time() - start_time) * 1000

            # 방어적 체크: result가 None인 경우 처리
            if result is None:
                logger.warning(
                    f"[RetrievalAgent_v2:{agent_type}] agent.process() returned None"
                )
                result = {
                    "status": "failure",
                    "message": "Agent returned None",
                    "result": None,
                }

            result_data = result.get("result") or {}
            individual_result = {
                "source": agent_type,
                "documents": result_data.get("results", []),
                "max_similarity": result_data.get("max_similarity", 0.0),
                "avg_similarity": result_data.get("avg_similarity", 0.0),
                "search_time_ms": search_time_ms,
            }

            if result.get("status") == "failure":
                individual_result["error"] = result.get("message", "Unknown error")

            logger.info(
                f"[RetrievalAgent_v2:{agent_type}] {len(individual_result['documents'])} docs, "
                f"max_sim={individual_result['max_similarity']:.3f}, "
                f"time={search_time_ms:.1f}ms"
            )

        except Exception as e:
            import traceback

            individual_result = {
                "source": agent_type,
                "documents": [],
                "max_similarity": 0.0,
                "avg_similarity": 0.0,
                "search_time_ms": (time.time() - start_time) * 1000,
                "error": str(e),
            }
            logger.error(
                f"[RetrievalAgent_v2:{agent_type}] Error: {e}\n{traceback.format_exc()}"
            )

        return {"individual_retrieval_results": [individual_result]}

    return retrieval_agent_node


def _route_mas_supervisor(state: ChatState):
    """
    MAS Supervisor v2 라우팅

    변경사항:
    - 재생성 루프 지원 (max 1회)
    - 3개 Retrieval Agent만 사용 (law, criteria, case)
    """
    supervisor_state = state.get("supervisor") or {}
    next_agent = supervisor_state.get("next_agent")
    retry_count = state.get("retry_count", 0)

    logger.info(f"[MAS Router v2] next_agent={next_agent}, retry_count={retry_count}")

    mode = state.get("mode", "NEED_RAG")

    # Phase 3-C: FOLLOWUP_WITH_CONTEXT → inject cached retrieval before generation
    if mode == "FOLLOWUP_WITH_CONTEXT" and next_agent == "retrieval_team":
        logger.info("[MAS Router v2] FOLLOWUP_WITH_CONTEXT → inject_cached_retrieval")
        return "inject_cached_retrieval"

    # Fast Path: NO_RETRIEVAL / CACHED_RAG / META_CONVERSATIONAL → Retrieval 생략
    if (
        mode in ("NO_RETRIEVAL", "CACHED_RAG", "META_CONVERSATIONAL")
        and next_agent == "retrieval_team"
    ):
        logger.info(f"[MAS Router v2] mode={mode}, skipping retrieval → generation")
        return "generation"

    # 재생성 요청 처리 (review → generation)
    if next_agent == "retry_generation":
        if retry_count < 1:
            logger.info("[MAS Router v2] Retry generation requested")
            return "generation"
        else:
            logger.info("[MAS Router v2] Max retries reached, routing to output")
            return "output_guardrail"

    # Selective Retrieval (v2: 3개 Agent만 사용)
    if next_agent == "retrieval_team":
        query_analysis = state.get("query_analysis", {})
        retriever_types = query_analysis.get(
            "retriever_types", ["law", "criteria", "case"]
        )

        fan_out_list = []
        for rt in ["law", "criteria", "case"]:
            if rt in retriever_types:
                fan_out_list.append(Send(f"retrieval_{rt}", state))

        logger.info(
            f"[MAS Router v2] Fan-out to {len(fan_out_list)} agents: {retriever_types}"
        )

        if not fan_out_list:
            return "generation"

        return fan_out_list

    routing_map = {
        "query_analyst": "query_analysis",
        "answer_drafter": "generation",
        "legal_reviewer": "review",
    }

    if next_agent in routing_map:
        return routing_map[next_agent]

    return "output_guardrail"


def create_mas_supervisor_graph() -> StateGraph:
    """
    MAS Supervisor 그래프 생성

    [아키텍처]
    1. LLM 기반 쿼리 확장
    2. 3개 Retrieval Agent (law, criteria, case)
    3. 메타데이터 필터 기반 검색
    4. 재생성 루프 지원 (max 1회)
    """
    from ..agents.answer_generation.agent import generation_node_v2 as gen_node
    from ..agents.legal_review.agent import review_node_v2 as rev_node
    from ..agents.query_analysis.agent import query_analysis_node_v2 as qa_node

    graph = StateGraph(ChatState)

    # === 노드 등록 ===
    graph.add_node("cache_check", _create_timed_node(_cache_check_node, "cache_check"))
    graph.add_node(
        "cache_response", _create_timed_node(_cache_response_node, "cache_response")
    )
    graph.add_node(
        "input_guardrail", _create_timed_node(input_guardrail_node, "input_guardrail")
    )
    graph.add_node(
        "output_guardrail",
        _create_timed_node(output_guardrail_node, "output_guardrail"),
    )

    # v2: Supervisor (추후 LLM 기반으로 변경)
    supervisor = SupervisorNode(llm=None)
    graph.add_node("supervisor", _create_timed_node(supervisor.as_node(), "supervisor"))

    graph.add_node("query_analysis", _create_timed_node(qa_node, "query_analysis"))
    graph.add_node("generation", _create_timed_node(gen_node, "generation"))
    graph.add_node("review", _create_timed_node(rev_node, "review"))

    # v2: 3개 Retrieval Agent (counsel 제외)
    for agent_type in ["law", "criteria", "case"]:
        node_fn = _create_retrieval_agent_node(agent_type)
        graph.add_node(
            f"retrieval_{agent_type}",
            _create_timed_node(node_fn, f"retrieval_{agent_type}"),
        )

    graph.add_node(
        "retrieval_merge", _create_timed_node(retrieval_merge_node, "retrieval_merge")
    )
    graph.add_node("memory_save", _create_timed_node(memory_save_node, "memory_save"))

    # Phase 3-C: Cache injection node for FOLLOWUP_WITH_CONTEXT
    graph.add_node(
        "inject_cached_retrieval",
        _create_timed_node(_inject_cached_retrieval_node, "inject_cached_retrieval"),
    )

    # === 엣지 설정 ===
    graph.set_entry_point("cache_check")

    graph.add_conditional_edges(
        "cache_check",
        _route_cache_check,
        {"cache_response": "cache_response", "input_guardrail": "input_guardrail"},
    )
    graph.add_edge("cache_response", END)

    graph.add_conditional_edges(
        "input_guardrail",
        lambda state: END if state.get("guardrail_blocked") else "supervisor",
        {END: END, "supervisor": "supervisor"},
    )

    # v2 라우팅 (Phase 3-C: inject_cached_retrieval 추가)
    graph.add_conditional_edges(
        "supervisor",
        _route_mas_supervisor,
        {
            "query_analysis": "query_analysis",
            "retrieval_law": "retrieval_law",
            "retrieval_criteria": "retrieval_criteria",
            "retrieval_case": "retrieval_case",
            "generation": "generation",
            "review": "review",
            "output_guardrail": "output_guardrail",
            "inject_cached_retrieval": "inject_cached_retrieval",
        },
    )

    # Fan-in
    for agent_type in ["law", "criteria", "case"]:
        graph.add_edge(f"retrieval_{agent_type}", "retrieval_merge")

    graph.add_edge("retrieval_merge", "supervisor")
    graph.add_edge("query_analysis", "supervisor")
    graph.add_edge("generation", "supervisor")
    graph.add_edge("review", "supervisor")
    graph.add_edge("output_guardrail", "memory_save")
    graph.add_edge("memory_save", END)

    # Phase 3-C: inject_cached_retrieval → generation
    graph.add_edge("inject_cached_retrieval", "generation")

    logger.info("[MAS Graph v2] Created MAS Supervisor v2 graph")

    return graph


_mas_compiled_graph = None


def get_mas_supervisor_graph():
    """MAS Supervisor v2 그래프 싱글톤"""
    global _mas_compiled_graph
    if _mas_compiled_graph is None:
        graph = create_mas_supervisor_graph()
        checkpointer = get_checkpointer()
        _mas_compiled_graph = graph.compile(checkpointer=checkpointer)
    return _mas_compiled_graph


def reset_mas_graph():
    """MAS 그래프 리셋 (테스트용)"""
    global _mas_compiled_graph
    _mas_compiled_graph = None
