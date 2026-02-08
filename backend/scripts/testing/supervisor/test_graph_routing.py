"""
Graph Routing 테스트 - _route_mas_supervisor, _route_cache_check, _cache_check_node
작성일: 2026-02-08

테스트 대상:
- _route_mas_supervisor: MAS Supervisor 라우팅 로직
- _route_cache_check: 캐시 히트 여부에 따른 라우팅
- _cache_check_node: L1 캐시 체크 노드
"""

import sys
from pathlib import Path
from unittest.mock import patch

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest

pytestmark = pytest.mark.unit

from app.supervisor.graph_mas import (
    _cache_check_node,
    _cache_response_node,
    _route_cache_check,
    _route_mas_supervisor,
)

# ============================================================================
# Helper: minimal state dict builder
# ============================================================================


def _make_state(**overrides):
    """Create a minimal ChatState-like dict for routing tests."""
    base = {
        "user_query": "테스트 쿼리",
        "mode": "NEED_RAG",
        "supervisor": None,
        "query_analysis": None,
        "retrieval": None,
        "draft_answer": None,
        "review": None,
        "retry_count": 0,
        "_cache_hit": False,
        "_cached_response": None,
        "session_id": None,
        "total_turn_count": 0,
        "_last_turn_context": None,
    }
    base.update(overrides)
    return base


# ============================================================================
# _route_cache_check tests
# ============================================================================


class TestRouteCacheCheck:
    """_route_cache_check 라우팅 테스트"""

    def test_cache_hit_routes_to_cache_response(self):
        """캐시 히트 시 cache_response로 라우팅"""
        state = _make_state(_cache_hit=True)
        assert _route_cache_check(state) == "cache_response"

    def test_cache_miss_routes_to_input_guardrail(self):
        """캐시 미스 시 input_guardrail로 라우팅"""
        state = _make_state(_cache_hit=False)
        assert _route_cache_check(state) == "input_guardrail"

    def test_cache_hit_not_set_routes_to_guardrail(self):
        """_cache_hit 키가 없으면 input_guardrail로 라우팅"""
        state = {"user_query": "test"}
        assert _route_cache_check(state) == "input_guardrail"


# ============================================================================
# _cache_check_node tests
# ============================================================================


class TestCacheCheckNode:
    """L1 캐시 체크 노드 테스트"""

    def test_empty_query_returns_no_hit(self):
        """빈 쿼리는 캐시 히트 없음"""
        state = _make_state(user_query="")
        result = _cache_check_node(state)
        assert result["_cache_hit"] is False

    @patch("app.supervisor.graph_mas.SupervisorResponseCache")
    def test_cache_miss(self, mock_cache):
        """캐시에 없는 쿼리"""
        mock_cache.get.return_value = None
        state = _make_state(user_query="새로운 쿼리", session_id="sess-1")
        result = _cache_check_node(state)
        assert result["_cache_hit"] is False

    @patch("app.supervisor.graph_mas.SupervisorResponseCache")
    def test_cache_hit(self, mock_cache):
        """캐시에 있는 쿼리"""
        cached_data = {"final_answer": "cached answer", "mode": "NEED_RAG"}
        mock_cache.get.return_value = cached_data
        state = _make_state(user_query="캐시된 쿼리", session_id="sess-1")
        result = _cache_check_node(state)
        assert result["_cache_hit"] is True
        assert result["_cached_response"] == cached_data

    @patch("app.supervisor.graph_mas.SupervisorResponseCache")
    def test_turn2_modifies_cache_key(self, mock_cache):
        """턴 2 이상에서는 캐시 키에 턴 번호 포함"""
        mock_cache.get.return_value = None
        state = _make_state(
            user_query="반복 쿼리", session_id="sess-1", total_turn_count=2
        )
        _cache_check_node(state)
        # Should be called with modified key including turn number
        call_args = mock_cache.get.call_args
        assert "turn2" in call_args[0][0]


# ============================================================================
# _cache_response_node tests
# ============================================================================


class TestCacheResponseNode:
    """캐시 응답 반환 노드 테스트"""

    def test_returns_cached_data(self):
        """캐시된 데이터를 올바르게 반환"""
        cached = {
            "final_answer": "캐시된 답변",
            "mode": "NEED_RAG",
            "citations": [{"type": "law"}],
        }
        state = _make_state(_cached_response=cached)
        result = _cache_response_node(state)
        assert result["final_answer"] == "캐시된 답변"
        assert result["mode"] == "NEED_RAG"
        assert result["citations"] == [{"type": "law"}]

    def test_empty_cached_response(self):
        """빈 캐시 응답 처리"""
        state = _make_state(_cached_response={})
        result = _cache_response_node(state)
        assert result["final_answer"] is None
        assert result["citations"] == []


# ============================================================================
# _route_mas_supervisor tests - Fast Path
# ============================================================================


class TestRouteMasSupervisorFastPath:
    """Fast Path 라우팅 (NO_RETRIEVAL, CACHED_RAG, META_CONVERSATIONAL)"""

    def test_no_retrieval_skips_to_generation(self):
        """NO_RETRIEVAL 모드에서 retrieval_team → generation으로 스킵"""
        state = _make_state(
            mode="NO_RETRIEVAL",
            supervisor={"next_agent": "retrieval_team"},
        )
        assert _route_mas_supervisor(state) == "generation"

    def test_cached_rag_skips_to_generation(self):
        """CACHED_RAG 모드에서 retrieval_team → generation으로 스킵"""
        state = _make_state(
            mode="CACHED_RAG",
            supervisor={"next_agent": "retrieval_team"},
        )
        assert _route_mas_supervisor(state) == "generation"

    def test_meta_conversational_skips_to_generation(self):
        """META_CONVERSATIONAL 모드에서 retrieval_team → generation으로 스킵"""
        state = _make_state(
            mode="META_CONVERSATIONAL",
            supervisor={"next_agent": "retrieval_team"},
        )
        assert _route_mas_supervisor(state) == "generation"


# ============================================================================
# _route_mas_supervisor tests - FOLLOWUP_WITH_CONTEXT
# ============================================================================


class TestRouteMasSupervisorFollowup:
    """FOLLOWUP_WITH_CONTEXT 모드 라우팅"""

    def test_followup_with_context_injects_cached_retrieval(self):
        """FOLLOWUP_WITH_CONTEXT → inject_cached_retrieval"""
        state = _make_state(
            mode="FOLLOWUP_WITH_CONTEXT",
            supervisor={"next_agent": "retrieval_team"},
        )
        assert _route_mas_supervisor(state) == "inject_cached_retrieval"


# ============================================================================
# _route_mas_supervisor tests - Full Path (NEED_RAG)
# ============================================================================


class TestRouteMasSupervisorFullPath:
    """Full Path 라우팅 (NEED_RAG)"""

    def test_retrieval_team_fans_out(self):
        """retrieval_team → 3개 retrieval agent로 fan-out"""
        state = _make_state(
            mode="NEED_RAG",
            supervisor={"next_agent": "retrieval_team"},
            query_analysis={"retriever_types": ["law", "criteria", "case"]},
        )
        result = _route_mas_supervisor(state)
        # Fan-out returns a list of Send objects
        assert isinstance(result, list)
        assert len(result) == 3

    def test_retrieval_team_selective_agents(self):
        """retriever_types에 따라 선택적 fan-out"""
        state = _make_state(
            mode="NEED_RAG",
            supervisor={"next_agent": "retrieval_team"},
            query_analysis={"retriever_types": ["law"]},
        )
        result = _route_mas_supervisor(state)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_retrieval_team_empty_types_goes_to_generation(self):
        """retriever_types가 비어있으면 generation으로"""
        state = _make_state(
            mode="NEED_RAG",
            supervisor={"next_agent": "retrieval_team"},
            query_analysis={"retriever_types": []},
        )
        result = _route_mas_supervisor(state)
        assert result == "generation"

    def test_retrieval_team_default_types(self):
        """retriever_types 미지정 시 기본값 사용"""
        state = _make_state(
            mode="NEED_RAG",
            supervisor={"next_agent": "retrieval_team"},
            query_analysis={},
        )
        result = _route_mas_supervisor(state)
        # Default retriever_types: ["law", "criteria", "case"]
        assert isinstance(result, list)
        assert len(result) == 3


# ============================================================================
# _route_mas_supervisor tests - Retry Logic
# ============================================================================


class TestRouteMasSupervisorRetry:
    """재생성 루프 라우팅"""

    def test_retry_generation_first_attempt(self):
        """첫 번째 재생성 시도 → generation"""
        state = _make_state(
            supervisor={"next_agent": "retry_generation"},
            retry_count=0,
        )
        assert _route_mas_supervisor(state) == "generation"

    def test_retry_generation_max_reached(self):
        """최대 재시도 도달 → output_guardrail"""
        state = _make_state(
            supervisor={"next_agent": "retry_generation"},
            retry_count=1,
        )
        assert _route_mas_supervisor(state) == "output_guardrail"


# ============================================================================
# _route_mas_supervisor tests - Direct Agent Routing
# ============================================================================


class TestRouteMasSupervisorDirectRouting:
    """직접 에이전트 라우팅"""

    def test_query_analyst_routes_to_query_analysis(self):
        """query_analyst → query_analysis"""
        state = _make_state(supervisor={"next_agent": "query_analyst"})
        assert _route_mas_supervisor(state) == "query_analysis"

    def test_answer_drafter_routes_to_generation(self):
        """answer_drafter → generation"""
        state = _make_state(supervisor={"next_agent": "answer_drafter"})
        assert _route_mas_supervisor(state) == "generation"

    def test_legal_reviewer_routes_to_review(self):
        """legal_reviewer → review"""
        state = _make_state(supervisor={"next_agent": "legal_reviewer"})
        assert _route_mas_supervisor(state) == "review"

    def test_unknown_agent_routes_to_output(self):
        """알 수 없는 에이전트 → output_guardrail"""
        state = _make_state(supervisor={"next_agent": "unknown_agent"})
        assert _route_mas_supervisor(state) == "output_guardrail"

    def test_none_next_agent_routes_to_output(self):
        """next_agent가 None이면 output_guardrail"""
        state = _make_state(supervisor={"next_agent": None})
        assert _route_mas_supervisor(state) == "output_guardrail"


# ============================================================================
# _route_mas_supervisor tests - Edge Cases
# ============================================================================


class TestRouteMasSupervisorEdgeCases:
    """엣지 케이스 라우팅"""

    def test_no_supervisor_state(self):
        """supervisor가 None인 경우"""
        state = _make_state(supervisor=None)
        # next_agent is None -> output_guardrail
        assert _route_mas_supervisor(state) == "output_guardrail"

    def test_empty_supervisor_state(self):
        """supervisor가 빈 dict인 경우"""
        state = _make_state(supervisor={})
        assert _route_mas_supervisor(state) == "output_guardrail"

    def test_no_query_analysis_for_retrieval_raises(self):
        """query_analysis가 None이면 .get() 호출 시 AttributeError 발생
        (실제 코드에서는 supervisor가 먼저 query_analysis를 수행하므로 이 상태는 발생하지 않음)
        """
        state = _make_state(
            mode="NEED_RAG",
            supervisor={"next_agent": "retrieval_team"},
            query_analysis=None,
        )
        with pytest.raises(AttributeError):
            _route_mas_supervisor(state)
