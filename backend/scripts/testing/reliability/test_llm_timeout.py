"""
LLM Timeout and Failure Handling Tests

Tests that LLM timeouts and API errors trigger proper fallback behavior
(rule-based classification, next model in fallback chain, etc.).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
class TestQueryAnalysisLLMTimeout:
    """LLM timeout in query analysis should fallback to rule-based."""

    @pytest.mark.asyncio
    async def test_query_analysis_v2_llm_timeout_uses_rule_based(self):
        """When llm_classify times out, v2 uses rule-based classification."""
        mock_llm_classify = AsyncMock(side_effect=asyncio.TimeoutError("LLM timed out"))

        state = {
            "user_query": "노트북 환불하고 싶어요",
            "chat_type": "dispute",
            "onboarding": None,
            "conversation_history": [],
            "_last_turn_context": None,
        }

        with (
            patch(
                "app.agents.query_analysis.llm_classifier.llm_classify",
                mock_llm_classify,
            ),
            patch(
                "app.agents.query_analysis.expanders.expand_query_with_llm_v2",
                new_callable=AsyncMock,
                return_value=["노트북 환불"],
            ),
        ):
            from app.agents.query_analysis.agent import query_analysis_node_v2

            result = await query_analysis_node_v2(state)

        assert "query_analysis" in result
        assert "mode" in result
        assert result["query_analysis"]["query_type"] is not None

    @pytest.mark.asyncio
    async def test_query_analysis_v2_llm_exception_uses_rule_based(self):
        """When llm_classify raises Exception, v2 falls back to rule-based."""
        mock_llm_classify = AsyncMock(side_effect=Exception("OpenAI API error"))

        state = {
            "user_query": "안녕하세요",
            "chat_type": "general",
            "onboarding": None,
            "conversation_history": [],
            "_last_turn_context": None,
        }

        with (
            patch(
                "app.agents.query_analysis.llm_classifier.llm_classify",
                mock_llm_classify,
            ),
            patch(
                "app.agents.query_analysis.expanders.expand_query_with_llm_v2",
                new_callable=AsyncMock,
                return_value=["안녕하세요"],
            ),
        ):
            from app.agents.query_analysis.agent import query_analysis_node_v2

            result = await query_analysis_node_v2(state)

        assert "query_analysis" in result
        assert result["query_analysis"]["query_type"] is not None

    @pytest.mark.asyncio
    async def test_query_analysis_v2_llm_returns_none_uses_rule_based(self):
        """When llm_classify returns None, v2 uses rule-based result."""
        mock_llm_classify = AsyncMock(return_value=None)

        state = {
            "user_query": "환불 규정 알려주세요",
            "chat_type": "dispute",
            "onboarding": None,
            "conversation_history": [],
            "_last_turn_context": None,
        }

        with (
            patch(
                "app.agents.query_analysis.llm_classifier.llm_classify",
                mock_llm_classify,
            ),
            patch(
                "app.agents.query_analysis.expanders.expand_query_with_llm_v2",
                new_callable=AsyncMock,
                return_value=["환불 규정"],
            ),
        ):
            from app.agents.query_analysis.agent import query_analysis_node_v2

            result = await query_analysis_node_v2(state)

        assert "query_analysis" in result
        assert result["query_analysis"]["query_type"] is not None


@pytest.mark.unit
class TestSupervisorLLMTimeout:
    """Supervisor LLM timeout should fallback to rule-based routing."""

    @pytest.mark.asyncio
    async def test_supervisor_llm_none_uses_rule_based(self):
        """SupervisorNode with llm=None uses rule-based routing."""
        from app.supervisor.nodes.supervisor import SupervisorNode

        supervisor = SupervisorNode(llm=None)
        assert supervisor.llm is None

        state = {
            "user_query": "환불 가능한가요?",
            "mode": "NEED_RAG",
            "query_analysis": None,
            "supervisor": None,
            "individual_retrieval_results": None,
            "retrieval": None,
            "final_answer": None,
            "review": None,
        }

        node_fn = supervisor.as_node()
        result = await node_fn(state)

        assert "supervisor" in result
        supervisor_state = result["supervisor"]
        assert "next_agent" in supervisor_state


@pytest.mark.unit
class TestLLMAPIErrors:
    """LLM API errors (500, rate limit) should be handled."""

    @pytest.mark.asyncio
    async def test_llm_api_error_500_handled(self):
        """HTTP 500 from LLM API → caught by exception handler in v2."""
        mock_llm_classify = AsyncMock(
            side_effect=Exception("HTTP 500: Internal Server Error")
        )

        state = {
            "user_query": "배송 지연 보상 받을 수 있나요",
            "chat_type": "dispute",
            "onboarding": None,
            "conversation_history": [],
            "_last_turn_context": None,
        }

        with (
            patch(
                "app.agents.query_analysis.llm_classifier.llm_classify",
                mock_llm_classify,
            ),
            patch(
                "app.agents.query_analysis.expanders.expand_query_with_llm_v2",
                new_callable=AsyncMock,
                return_value=["배송 지연 보상"],
            ),
        ):
            from app.agents.query_analysis.agent import query_analysis_node_v2

            result = await query_analysis_node_v2(state)

        assert result["query_analysis"]["query_type"] is not None
        mock_llm_classify.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_rate_limit_handled(self):
        """Rate limit error from LLM → caught, falls back to rule-based."""
        mock_llm_classify = AsyncMock(
            side_effect=Exception("Rate limit exceeded. Please retry after 20s")
        )

        state = {
            "user_query": "소비자보호법 조항 알려줘",
            "chat_type": "general",
            "onboarding": None,
            "conversation_history": [],
            "_last_turn_context": None,
        }

        with (
            patch(
                "app.agents.query_analysis.llm_classifier.llm_classify",
                mock_llm_classify,
            ),
            patch(
                "app.agents.query_analysis.expanders.expand_query_with_llm_v2",
                new_callable=AsyncMock,
                return_value=["소비자보호법"],
            ),
        ):
            from app.agents.query_analysis.agent import query_analysis_node_v2

            result = await query_analysis_node_v2(state)

        assert "query_analysis" in result
        assert result["query_analysis"]["query_type"] is not None
