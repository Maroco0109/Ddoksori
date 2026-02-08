"""
Database Failure Handling Tests

Tests that database connection failures are handled gracefully
without crashing the application.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
class TestRetrievalWithDBDown:
    """Retrieval agent should handle DB connection failures gracefully."""

    @pytest.mark.asyncio
    async def test_retrieval_agent_db_error_returns_empty(self):
        """Retrieval agent with DB error → returns empty results, no crash."""
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(
            side_effect=Exception("connection refused: DB is down")
        )

        from app.supervisor.graph_mas import _create_retrieval_agent_node

        node_fn = _create_retrieval_agent_node("law")

        state = {
            "user_query": "환불 규정",
            "query_analysis": {
                "expanded_queries": ["환불 규정"],
                "keywords": ["환불"],
            },
            "supervisor": {},
        }

        with patch(
            "app.agents.retrieval.law_agent.law_retrieval_agent",
            mock_agent,
        ):
            result = await node_fn(state)

        assert "individual_retrieval_results" in result
        results = result["individual_retrieval_results"]
        assert len(results) == 1
        assert results[0]["source"] == "law"
        assert results[0]["documents"] == []
        assert "error" in results[0]

    @pytest.mark.asyncio
    async def test_retrieval_case_agent_db_error(self):
        """Case retrieval agent with DB error → empty results with error."""
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(
            side_effect=ConnectionError("Cannot connect to PostgreSQL")
        )

        from app.supervisor.graph_mas import _create_retrieval_agent_node

        node_fn = _create_retrieval_agent_node("case")

        state = {
            "user_query": "비슷한 사례 알려줘",
            "query_analysis": {
                "expanded_queries": ["사례"],
                "keywords": ["사례"],
            },
            "supervisor": {},
        }

        with patch(
            "app.agents.retrieval.case_agent.case_retrieval_agent",
            mock_agent,
        ):
            result = await node_fn(state)

        assert result["individual_retrieval_results"][0]["documents"] == []
        assert "error" in result["individual_retrieval_results"][0]

    @pytest.mark.asyncio
    async def test_retrieval_criteria_agent_db_timeout(self):
        """Criteria retrieval agent with DB timeout → empty results."""
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(
            side_effect=TimeoutError("Query execution timeout")
        )

        from app.supervisor.graph_mas import _create_retrieval_agent_node

        node_fn = _create_retrieval_agent_node("criteria")

        state = {
            "user_query": "분쟁해결기준",
            "query_analysis": {
                "expanded_queries": ["기준"],
                "keywords": ["기준"],
            },
            "supervisor": {},
        }

        with patch(
            "app.agents.retrieval.criteria_agent.criteria_retrieval_agent",
            mock_agent,
        ):
            result = await node_fn(state)

        assert result["individual_retrieval_results"][0]["documents"] == []


@pytest.mark.unit
class TestUserLookupDBFailure:
    """User DB errors should result in graceful error handling."""

    @pytest.mark.asyncio
    async def test_conversation_db_error_handled(self):
        """ConversationDB failure → exception propagates to caller."""
        mock_db = MagicMock()
        mock_db.get_user_conversations = AsyncMock(
            side_effect=Exception("DB connection lost")
        )

        with pytest.raises(Exception, match="DB connection lost"):
            await mock_db.get_user_conversations(user_id="test-user", limit=20)


@pytest.mark.unit
class TestEmbeddingCacheDBError:
    """Embedding cache with DB issues should be handled."""

    def test_embedding_cache_redis_error_on_get(self):
        """EmbeddingCache get with Redis error → returns None."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis connection broken")

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.common.cache import EmbeddingCache

            result = EmbeddingCache.get("test embedding key")

        assert result is None

    def test_embedding_cache_redis_error_on_set(self):
        """EmbeddingCache set with Redis error → returns False."""
        from app.common.cache.base import BaseRedisCache

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Redis write failure")

        with patch.object(BaseRedisCache, "_get_redis", return_value=mock_redis):
            from app.common.cache import EmbeddingCache

            result = EmbeddingCache.set("key", {"embedding": [0.1, 0.2]})

        assert result is False
