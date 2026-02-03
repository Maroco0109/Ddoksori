"""
테스트: OutputState 확장 + Meta Conversational Response + MAS 라우팅
작성일: 2026-01-31
수정일: 2026-02-03

검증 항목:
- C-1: StructuredResponse / OutputState 확장 (response_depth, available_details)
- E-2: _meta_conversational_response 구현
- MAS 라우팅: META_CONVERSATIONAL 모드

Note: Progressive Disclosure 관련 테스트(C-2, C-3)와 generation_node_v2 분기 테스트(E-1)는
Draft Agent 리팩토링(6da35af)에서 해당 기능/인터페이스가 제거되어 삭제되었습니다.
"""

import os
import sys
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))
os.chdir(backend_path)


# ============================================================================
# C-1: OutputState 확장 테스트
# ============================================================================


class TestOutputStateExtension:
    """response_depth, available_details 필드 추가 확인"""

    def test_response_depth_type_exists(self):
        """ResponseDepth 타입이 정의되어 있어야 함"""
        from app.supervisor.state import ResponseDepth

        # Literal type check
        assert ResponseDepth is not None

    def test_create_initial_state_has_response_depth(self):
        """create_initial_state 결과에 response_depth 포함"""
        from app.supervisor.state import create_initial_state

        state = create_initial_state(user_query="테스트", chat_type="dispute")
        assert state.get("response_depth") == "full"
        assert state.get("available_details") is None

    def test_chatstate_has_new_fields(self):
        """ChatState에 response_depth, available_details 필드 정의 확인"""
        from app.supervisor.state import ChatState

        annotations = ChatState.__annotations__
        assert "response_depth" in annotations
        assert "available_details" in annotations


# ============================================================================
# E-2: Meta Conversational Response 테스트
# ============================================================================


class TestMetaConversationalResponse:
    """_meta_conversational_response() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.answer_generation.agent import _meta_conversational_response

        self.meta_response = _meta_conversational_response

    def test_basic_meta_response(self):
        """기본 메타 응답 (온보딩 없음)"""
        state = {"user_query": "뭘 물어봐야 할까?", "mode": "META_CONVERSATIONAL"}
        result = self.meta_response(state)

        assert "draft_answer" in result
        assert "똑소리" in result["draft_answer"]
        assert "품목" in result["draft_answer"] or "제품" in result["draft_answer"]
        assert result["response_depth"] == "full"
        assert result["generation_model_used"] == "meta_conversational_template"

    def test_meta_response_with_onboarding(self):
        """온보딩 정보가 있으면 맞춤 응답"""
        state = {
            "user_query": "도와줘",
            "mode": "META_CONVERSATIONAL",
            "onboarding": {"purchase_item": "에어팟"},
        }
        result = self.meta_response(state)

        assert "에어팟" in result["draft_answer"]
        assert "문제 상황" in result["draft_answer"]

    def test_meta_response_has_messages(self):
        """messages 필드 포함 (LangGraph 호환)"""
        state = {"user_query": "도와줘", "mode": "META_CONVERSATIONAL"}
        result = self.meta_response(state)

        assert "messages" in result
        assert len(result["messages"]) == 1


# ============================================================================
# graph_mas.py 라우팅 테스트
# ============================================================================


class TestMASRoutingMetaConversational:
    """META_CONVERSATIONAL 모드 라우팅 테스트"""

    def test_meta_conversational_skips_retrieval(self):
        """META_CONVERSATIONAL 모드에서 retrieval 생략"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            "supervisor": {"next_agent": "retrieval_team"},
            "mode": "META_CONVERSATIONAL",
            "retry_count": 0,
            "query_analysis": {},
        }

        result = _route_mas_supervisor(state)
        assert result == "generation"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-p", "no:asyncio", "--tb=short"])
