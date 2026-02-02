from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from app.common.config import reload_config
from app.supervisor import (
    create_initial_state,
    reset_graph,
)
from app.supervisor.graph_mas import create_mas_supervisor_graph


@pytest.fixture(autouse=True)
def reset_config_cache():
    """각 테스트 후 config 캐시를 클리어하여 환경변수 변경이 반영되도록 함"""
    yield
    reload_config()


def create_mock_retrieval_node(retrieval_result: Dict[str, Any]):
    def mock_node(state):
        return {
            "retrieval": retrieval_result,
            "sources": retrieval_result.get("disputes", [])
            + retrieval_result.get("counsels", []),
        }

    return mock_node


def create_mock_generation_node(answer: str = "테스트 답변입니다. [1]"):
    def mock_node(state):
        return {
            "draft_answer": answer,
            "final_answer": answer,
            "has_sufficient_evidence": True,
        }

    return mock_node


def create_mock_review_node(passed: bool = True, violations: list = None):
    def mock_node(state):
        retry_count = state.get("retry_count", 0)
        return {
            "review": {
                "passed": passed,
                "violations": violations or [],
                "filtered_answer": None if passed else state.get("draft_answer"),
            },
            "retry_count": retry_count + (0 if passed else 1),
            "final_answer": state.get("draft_answer"),
        }

    return mock_node


class TestSupervisorGraphStructure:
    """MAS Supervisor 그래프 구조 테스트"""

    def test_graph_has_all_nodes(self, uncompiled_graph):
        graph = uncompiled_graph
        nodes = list(graph.nodes.keys())

        # MAS Supervisor 그래프 노드들
        expected_nodes = [
            "input_guardrail",
            "supervisor",
            "query_analysis",
            "generation",
            "review",
            "output_guardrail",
        ]

        for node in expected_nodes:
            assert node in nodes, f"Missing node: {node}"

    def test_graph_entry_point(self, uncompiled_graph):
        graph = uncompiled_graph
        nodes = list(graph.nodes.keys())
        # MAS Supervisor는 input_guardrail 또는 supervisor로 시작
        assert "input_guardrail" in nodes or "supervisor" in nodes

    def test_graph_compiles_without_error(self, compiled_graph):
        assert compiled_graph is not None


@pytest.mark.e2e
@pytest.mark.skip(
    reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
)
class TestHappyPathDispute:
    def test_dispute_query_analysis_completes(self, compiled_graph):
        """분쟁 질의에 대해 query_analysis가 정상 완료되는지 확인 (MAS Supervisor)"""
        state = create_initial_state(
            user_query="노트북 환불받고 싶어요",
            chat_type="dispute",
            onboarding={"purchase_item": "노트북"},
        )

        config = {"configurable": {"thread_id": "test-happy-path"}}
        result = compiled_graph.invoke(state, config)

        assert result.get("query_analysis") is not None
        assert result["query_analysis"]["query_type"] == "dispute"


@pytest.mark.e2e
@pytest.mark.skip(
    reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
)
class TestAskClarificationBranch:
    def test_minimal_info_triggers_clarification(self, compiled_graph):
        state = create_initial_state(
            user_query="환불해줘", chat_type="dispute", onboarding=None
        )

        config = {"configurable": {"thread_id": "test-clarification"}}
        result = compiled_graph.invoke(state, config)

        assert result.get("query_analysis") is not None

        qa = result["query_analysis"]
        if qa.get("needs_clarification") and not qa.get("extracted_info", {}).get(
            "purchase_item"
        ):
            assert (
                result.get("clarifying_questions") is not None
                or result.get("final_answer") is not None
            )


@pytest.mark.e2e
@pytest.mark.skip(
    reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
)
class TestLowSimilarityBranch:
    def test_unusual_product_query_analysis(self, compiled_graph):
        """특이한 제품 질의도 query_analysis 노드를 정상 통과하는지 확인"""
        state = create_initial_state(
            user_query="아무도 모르는 특이한 제품 환불",
            chat_type="dispute",
            onboarding={"purchase_item": "특이한제품"},
        )

        config = {"configurable": {"thread_id": "test-low-sim"}}
        result = compiled_graph.invoke(state, config)

        assert result.get("query_analysis") is not None


@pytest.mark.e2e
@pytest.mark.skip(
    reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
)
class TestGeneralConversation:
    def test_general_chat_path(self, compiled_graph):
        state = create_initial_state(
            user_query="안녕하세요", chat_type="general", onboarding=None
        )

        config = {"configurable": {"thread_id": "test-general"}}
        result = compiled_graph.invoke(state, config)

        assert result.get("query_analysis") is not None
        assert result["query_analysis"]["query_type"] == "general"


@pytest.mark.e2e
@pytest.mark.skip(
    reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
)
class TestNodeTimings:
    def test_node_timings_recorded(self, compiled_graph):
        state = create_initial_state(
            user_query="안녕하세요", chat_type="general", onboarding=None
        )

        config = {"configurable": {"thread_id": "test-timings"}}
        result = compiled_graph.invoke(state, config)

        timings = result.get("_node_timings", {})

        assert "query_analysis" in timings
        assert "duration_ms" in timings["query_analysis"]
        assert timings["query_analysis"]["duration_ms"] >= 0

    def test_timing_includes_start_end(self, compiled_graph):
        state = create_initial_state(
            user_query="테스트", chat_type="general", onboarding=None
        )

        config = {"configurable": {"thread_id": "test-timing-fields"}}
        result = compiled_graph.invoke(state, config)

        timings = result.get("_node_timings", {})

        if "query_analysis" in timings:
            qa_timing = timings["query_analysis"]
            assert "start" in qa_timing
            assert "end" in qa_timing
            assert qa_timing["end"] >= qa_timing["start"]


class TestStateTransitions:
    def test_initial_state_fields(self):
        """Unit test - no graph invocation needed"""
        state = create_initial_state(
            user_query="테스트 질문",
            chat_type="dispute",
            onboarding={"purchase_item": "테스트"},
        )

        assert state["user_query"] == "테스트 질문"
        assert state["chat_type"] == "dispute"
        assert state["onboarding"]["purchase_item"] == "테스트"
        assert state["query_analysis"] is None
        assert state["retrieval"] is None
        assert state["draft_answer"] is None
        assert state["review"] is None
        assert state["final_answer"] is None
        assert state["sources"] == []
        assert state["retry_count"] == 0

    @pytest.mark.e2e
    @pytest.mark.skip(
        reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
    )
    def test_query_analysis_updates_state(self, compiled_graph):
        state = create_initial_state(
            user_query="노트북 환불",
            chat_type="dispute",
            onboarding={"purchase_item": "노트북"},
        )

        config = {"configurable": {"thread_id": "test-qa-state"}}
        result = compiled_graph.invoke(state, config)

        qa = result.get("query_analysis")
        assert qa is not None
        assert "query_type" in qa
        assert "keywords" in qa


@pytest.mark.e2e
@pytest.mark.skip(
    reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
)
class TestMultiTurnSession:
    def test_same_thread_id_shares_state(self, compiled_graph):
        thread_id = "test-multi-turn"
        config = {"configurable": {"thread_id": thread_id}}

        state1 = create_initial_state(
            user_query="안녕하세요", chat_type="general", onboarding=None
        )
        result1 = compiled_graph.invoke(state1, config)

        state2 = create_initial_state(
            user_query="노트북 환불 문의",
            chat_type="dispute",
            onboarding={"purchase_item": "노트북"},
        )
        result2 = compiled_graph.invoke(state2, config)

        assert result1 is not None
        assert result2 is not None

    def test_different_thread_ids_isolated(self, compiled_graph):
        state = create_initial_state(
            user_query="테스트", chat_type="general", onboarding=None
        )

        config1 = {"configurable": {"thread_id": "thread-a"}}
        config2 = {"configurable": {"thread_id": "thread-b"}}

        result1 = compiled_graph.invoke(state, config1)
        result2 = compiled_graph.invoke(state, config2)

        assert result1.get("query_analysis") is not None
        assert result2.get("query_analysis") is not None


@pytest.mark.e2e
@pytest.mark.skip(
    reason="MAS Supervisor uses async nodes - requires ainvoke() and LLM API"
)
class TestQueryRewritingIntegration:
    def test_query_rewriting_fields_populated(self, compiled_graph):
        state = create_initial_state(
            user_query="노트북 환불받고 싶어요",
            chat_type="dispute",
            onboarding={"purchase_item": "노트북"},
        )

        config = {"configurable": {"thread_id": "test-rewriting"}}
        result = compiled_graph.invoke(state, config)

        qa = result.get("query_analysis")
        assert qa is not None

        if "rewritten_query" in qa:
            assert isinstance(qa["rewritten_query"], str)
        if "search_queries" in qa:
            assert isinstance(qa["search_queries"], list)
        if "expansion_applied" in qa:
            assert isinstance(qa["expansion_applied"], str)
