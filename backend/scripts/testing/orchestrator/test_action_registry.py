"""
ActionRegistry 단위 테스트
S2-PR1: 액션 레지스트리 패턴 도입
"""

import pytest
from unittest.mock import MagicMock, patch

from app.agents.react.action_registry import (
    ActionRegistry,
    BaseAction,
    ActionResult,
)
from app.orchestrator.state import ChatState


class MockAction(BaseAction):
    """테스트용 모의 액션"""
    name = "mock_action"
    description = "테스트용 모의 액션"

    def execute(self, state: ChatState, query: str) -> ActionResult:
        return ActionResult(
            observation=f"mock executed with query: {query}",
        )


class FailingAction(BaseAction):
    """실패하는 테스트용 액션"""
    name = "failing_action"
    description = "항상 실패하는 액션"

    def execute(self, state: ChatState, query: str) -> ActionResult:
        raise RuntimeError("Intentional failure")


class TestActionResult:
    def test_to_state_update_basic(self):
        result = ActionResult(observation="test observation")
        update = result.to_state_update(
            thought="test thought",
            action="test_action",
            action_input={"query": "test"},
        )
        
        assert update['last_observation'] == "test observation"
        assert len(update['react_steps']) == 1
        assert update['react_steps'][0]['thought'] == "test thought"
        assert update['react_steps'][0]['action'] == "test_action"
        assert update['react_steps'][0]['observation'] == "test observation"

    def test_to_state_update_with_retrieval(self):
        from app.orchestrator.state import RetrievalResult
        
        retrieval = RetrievalResult(
            agency={},
            disputes=[],
            counsels=[],
            laws=[],
            criteria=[],
            max_similarity=0.8,
            avg_similarity=0.6,
        )
        
        result = ActionResult(
            observation="retrieved",
            retrieval=retrieval,
            sources=[{"type": "test"}],
        )
        update = result.to_state_update("t", "a", {})
        
        assert 'retrieval' in update
        assert 'sources' in update
        assert update['sources'] == [{"type": "test"}]

    def test_to_state_update_with_clarification(self):
        result = ActionResult(
            observation="questions generated",
            clarifying_questions=["Q1", "Q2"],
            awaiting_user_choice=True,
            should_continue=False,
        )
        update = result.to_state_update("t", "a", {})
        
        assert update['clarifying_questions'] == ["Q1", "Q2"]
        assert update['awaiting_user_choice'] is True
        assert update['should_continue'] is False


class TestActionRegistry:
    def setup_method(self):
        ActionRegistry.clear()

    def test_register_action(self):
        action = MockAction()
        ActionRegistry.register(action)
        
        assert ActionRegistry.get("mock_action") is action

    def test_register_action_without_name_raises(self):
        class NoNameAction(BaseAction):
            name = ""
            description = "No name"
            def execute(self, state, query):
                return ActionResult(observation="")
        
        with pytest.raises(ValueError):
            ActionRegistry.register(NoNameAction())

    def test_unregister_action(self):
        action = MockAction()
        ActionRegistry.register(action)
        
        result = ActionRegistry.unregister("mock_action")
        assert result is True
        assert ActionRegistry.get("mock_action") is None

    def test_unregister_nonexistent_action(self):
        result = ActionRegistry.unregister("nonexistent")
        assert result is False

    def test_list_actions(self):
        ActionRegistry.register(MockAction())
        
        actions = ActionRegistry.list_actions()
        assert "mock_action" in actions
        assert actions["mock_action"] == "테스트용 모의 액션"

    def test_get_action_names(self):
        ActionRegistry.register(MockAction())
        
        names = ActionRegistry.get_action_names()
        assert "mock_action" in names

    def test_execute_registered_action(self):
        ActionRegistry.register(MockAction())
        
        state = ChatState(user_query="test")
        result = ActionRegistry.execute("mock_action", state, "test query", "thought")
        
        assert "mock executed" in result['last_observation']
        assert len(result['react_steps']) == 1

    def test_execute_unknown_action(self):
        state = ChatState(user_query="test")
        result = ActionRegistry.execute("unknown", state, "test", "thought")
        
        assert "알 수 없는 액션" in result['last_observation']

    def test_execute_failing_action(self):
        ActionRegistry.register(FailingAction())
        
        state = ChatState(user_query="test")
        result = ActionRegistry.execute("failing_action", state, "test", "thought")
        
        assert "액션 실행 실패" in result['last_observation']

    def test_clear_actions(self):
        ActionRegistry.register(MockAction())
        ActionRegistry.clear()
        
        assert len(ActionRegistry._actions) == 0


class TestDefaultActions:
    def setup_method(self):
        ActionRegistry.clear()
        ActionRegistry._initialized = False

    def test_default_actions_auto_registered(self):
        names = ActionRegistry.get_action_names()
        
        assert "search_all" in names
        assert "search_criteria" in names
        assert "search_laws" in names
        assert "ask_clarification" in names

    def test_search_all_action_exists(self):
        action = ActionRegistry.get("search_all")
        assert action is not None
        assert action.name == "search_all"

    def test_ask_clarification_action_exists(self):
        action = ActionRegistry.get("ask_clarification")
        assert action is not None
        assert action.name == "ask_clarification"


class TestAskClarificationAction:
    def setup_method(self):
        ActionRegistry.clear()
        ActionRegistry._initialized = False

    def test_generates_questions_for_missing_fields(self):
        action = ActionRegistry.get("ask_clarification")
        
        state = ChatState(
            user_query="환불 받고 싶어요",
            query_analysis={
                'missing_fields': ['purchase_item', 'purchase_date'],
            },
        )
        
        result = action.execute(state, "test")
        
        assert result.clarifying_questions is not None
        assert len(result.clarifying_questions) >= 1
        assert result.awaiting_user_choice is True
        assert result.should_continue is False

    def test_generates_default_questions_when_no_missing_fields(self):
        action = ActionRegistry.get("ask_clarification")
        
        state = ChatState(
            user_query="환불",
            query_analysis={'missing_fields': []},
        )
        
        result = action.execute(state, "test")
        
        assert result.clarifying_questions is not None
        assert len(result.clarifying_questions) == 2


class TestIntegrationWithReactActNode:
    def setup_method(self):
        ActionRegistry.clear()
        ActionRegistry._initialized = False

    @patch('app.agents.retrieval.tools.specialized_retrievers.StructuredRetriever')
    def test_react_act_node_uses_registry(self, mock_retriever_class):
        from app.agents.react.react_act import react_act_node
        
        mock_retriever = MagicMock()
        mock_retriever.search_all_sections.return_value = {
            'disputes': [{'doc_id': '1', 'similarity': 0.8}],
            'counsels': [],
            'laws': [],
            'criteria': [],
        }
        mock_retriever_class.return_value = mock_retriever
        
        state = ChatState(
            user_query="환불 방법",
            last_action="search_all",
            last_thought="검색 필요",
        )
        
        result = react_act_node(state)
        
        assert 'last_observation' in result
        assert 'react_steps' in result

    def test_react_act_node_handles_unknown_action(self):
        from app.agents.react.react_act import react_act_node
        
        state = ChatState(
            user_query="test",
            last_action="nonexistent_action",
        )
        
        result = react_act_node(state)
        
        assert "알 수 없는 액션" in result['last_observation']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
