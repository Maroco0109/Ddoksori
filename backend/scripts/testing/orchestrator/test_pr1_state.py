"""
PR1 테스트: ChatState 스키마 및 Checkpointer 팩토리

실행:
    conda activate dsr
    pytest backend/scripts/testing/orchestrator/test_pr1_state.py -v
"""

import pytest
import os
from typing import Dict

from app.orchestrator.state import (
    ChatState,
    OnboardingInfo,
    QueryAnalysisResult,
    RetrievalResult,
    ReviewResult,
    create_initial_state,
)
from app.orchestrator.checkpointer import (
    get_checkpointer,
    get_checkpointer_mode,
)
from langgraph.checkpoint.memory import MemorySaver


class TestChatState:
    
    def test_create_initial_state_general(self):
        state = create_initial_state(
            user_query="환불 규정 알려줘",
            chat_type='general'
        )
        
        assert state['user_query'] == "환불 규정 알려줘"
        assert state['chat_type'] == 'general'
        assert state['onboarding'] is None
        assert state['messages'] == []
        assert state['sources'] == []
        assert state['retry_count'] == 0
    
    def test_create_initial_state_dispute_with_onboarding(self):
        onboarding: OnboardingInfo = {
            'purchase_date': '2026-01-01',
            'purchase_item': '헬스장 회원권',
            'purchase_amount': '500000',
        }
        
        state = create_initial_state(
            user_query="헬스장 환불 요청",
            chat_type='dispute',
            onboarding=onboarding
        )
        
        assert state['chat_type'] == 'dispute'
        assert state['onboarding'] is not None
        assert state['onboarding']['purchase_item'] == '헬스장 회원권'
    
    def test_state_has_required_fields(self):
        state = create_initial_state(user_query="테스트")
        
        required_fields = [
            'messages', 'user_query', 'chat_type', 'final_answer',
            'sources', 'has_sufficient_evidence', 'clarifying_questions'
        ]
        for field in required_fields:
            assert field in state


class TestOnboardingInfo:
    
    def test_partial_onboarding(self):
        onboarding: OnboardingInfo = {
            'purchase_item': '노트북',
        }
        
        assert onboarding.get('purchase_item') == '노트북'
        assert onboarding.get('purchase_date') is None
    
    def test_full_onboarding(self):
        onboarding: OnboardingInfo = {
            'purchase_date': '2026-01-10',
            'purchase_place': '삼성전자',
            'purchase_platform': '온라인',
            'purchase_item': '갤럭시 S26',
            'purchase_amount': '1500000',
            'dispute_details': '배터리 불량',
        }
        
        assert len(onboarding) == 6


class TestQueryAnalysisResult:
    
    def test_needs_clarification(self):
        result: QueryAnalysisResult = {
            'query_type': 'dispute',
            'keywords': ['환불', '헬스장'],
            'needs_clarification': True,
            'missing_fields': ['purchase_date', 'purchase_amount'],
        }
        
        assert result['needs_clarification'] is True
        assert len(result['missing_fields']) == 2
    
    def test_complete_query(self):
        result: QueryAnalysisResult = {
            'query_type': 'general',
            'keywords': ['전자상거래법', '청약철회'],
            'needs_clarification': False,
            'missing_fields': [],
        }
        
        assert result['needs_clarification'] is False


class TestCheckpointer:
    
    def test_default_mode_is_memory(self):
        original = os.environ.pop('CHECKPOINTER_MODE', None)
        try:
            mode = get_checkpointer_mode()
            assert mode == 'memory'
        finally:
            if original:
                os.environ['CHECKPOINTER_MODE'] = original
    
    def test_get_memory_checkpointer(self):
        checkpointer = get_checkpointer('memory')
        assert isinstance(checkpointer, MemorySaver)
    
    def test_postgres_not_implemented(self):
        with pytest.raises(NotImplementedError) as exc_info:
            get_checkpointer('postgres')
        
        assert 'PR3' in str(exc_info.value)
    
    def test_invalid_mode_raises_error(self):
        original = os.environ.get('CHECKPOINTER_MODE')
        try:
            os.environ['CHECKPOINTER_MODE'] = 'invalid'
            with pytest.raises(ValueError):
                get_checkpointer_mode()
        finally:
            if original:
                os.environ['CHECKPOINTER_MODE'] = original
            else:
                os.environ.pop('CHECKPOINTER_MODE', None)


class TestCheckpointerIntegration:
    
    def test_memory_saver_basic_operations(self):
        from langgraph.graph import StateGraph, START, END
        from typing import TypedDict
        
        class SimpleState(TypedDict):
            value: int
        
        def increment(state: SimpleState) -> Dict:
            return {'value': state['value'] + 1}
        
        builder = StateGraph(SimpleState)
        builder.add_node("increment", increment)
        builder.add_edge(START, "increment")
        builder.add_edge("increment", END)
        
        checkpointer = get_checkpointer('memory')
        graph = builder.compile(checkpointer=checkpointer)
        
        config = {"configurable": {"thread_id": "test-thread-1"}}
        result = graph.invoke({"value": 0}, config)
        
        assert result['value'] == 1
    
    def test_memory_saver_multi_turn(self):
        from langgraph.graph import StateGraph, START, END, MessagesState
        from langchain_core.messages import HumanMessage, AIMessage
        
        def echo(state: MessagesState) -> Dict:
            last_msg = state['messages'][-1]
            return {'messages': [AIMessage(content=f"Echo: {last_msg.content}")]}
        
        builder = StateGraph(MessagesState)
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)
        
        checkpointer = get_checkpointer('memory')
        graph = builder.compile(checkpointer=checkpointer)
        
        config = {"configurable": {"thread_id": "test-thread-2"}}
        
        result1 = graph.invoke(
            {"messages": [HumanMessage(content="Hello")]},
            config
        )
        assert len(result1['messages']) == 2
        
        result2 = graph.invoke(
            {"messages": [HumanMessage(content="World")]},
            config
        )
        assert len(result2['messages']) == 4
