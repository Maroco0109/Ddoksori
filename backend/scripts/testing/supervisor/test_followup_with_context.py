"""
테스트: Phase D - FOLLOWUP_WITH_CONTEXT (후속 질문 컨텍스트 재활용)
작성일: 2026-01-31

Phase D 구현 검증:
- D-1: is_followup_with_context() 매칭 + detect_requested_detail_type()
- D-2: memory_save_node에서 _last_turn_context 저장
- D-3: graph_mas.py FOLLOWUP_WITH_CONTEXT 라우팅 (retrieval 생략)
- D-4: _followup_detail_response() + generation_node_v2 분기
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))
os.chdir(backend_path)


# ============================================================================
# D-1: 후속 질문 매칭 테스트
# ============================================================================


class TestFollowupMatching:
    """is_followup_with_context() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.query_analysis.detectors import is_followup_with_context

        self.match = is_followup_with_context

    def test_exact_match(self):
        """완전 일치"""
        assert (
            self.match(
                "관련 법령을 자세히 알려드릴까요?",
                ["관련 법령을 자세히 알려드릴까요?"],
            )
            is True
        )

    def test_near_match(self):
        """높은 유사도 매칭"""
        assert (
            self.match(
                "관련 법령을 자세히 알려주세요",
                ["관련 법령을 자세히 알려드릴까요?"],
                threshold=0.7,
            )
            is True
        )

    def test_no_match(self):
        """비매칭"""
        assert (
            self.match(
                "노트북 환불해줘",
                ["관련 법령을 자세히 알려드릴까요?"],
            )
            is False
        )

    def test_empty_followups(self):
        """빈 후속 질문 리스트"""
        assert self.match("아무 질문", []) is False

    def test_none_followups(self):
        """None 후속 질문"""
        assert self.match("아무 질문", None) is False

    def test_multiple_followups_one_match(self):
        """여러 후속 질문 중 하나 매칭"""
        followups = [
            "관련 법령을 자세히 알려드릴까요?",
            "비슷한 분쟁 조정 사례 5건도 확인해 보시겠어요?",
            "분쟁 해결 절차도 안내해드릴까요?",
        ]
        assert self.match("분쟁 해결 절차도 안내해드릴까요?", followups) is True

    def test_high_threshold_rejects(self):
        """높은 임계값에서 유사하지만 다른 문장 거부"""
        assert (
            self.match(
                "법령 관련 정보 좀 줘",
                ["관련 법령을 자세히 알려드릴까요?"],
                threshold=0.9,
            )
            is False
        )


# ============================================================================
# D-1: 요청 상세 유형 감지 테스트
# ============================================================================


class TestDetectRequestedDetailType:
    """detect_requested_detail_type() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.query_analysis.detectors import detect_requested_detail_type

        self.detect = detect_requested_detail_type

    def test_laws_detection(self):
        assert self.detect("관련 법령을 자세히 알려드릴까요?", {}) == "laws"
        assert self.detect("법적 근거를 알려주세요", {}) == "laws"

    def test_cases_detection(self):
        assert self.detect("비슷한 사례 5건도 확인해 보시겠어요?", {}) == "cases"
        assert self.detect("유사 조정 사례를 보여줘", {}) == "cases"

    def test_criteria_detection(self):
        assert self.detect("분쟁해결기준을 확인해보시겠어요?", {}) == "criteria"
        assert self.detect("배상 기준이 뭐야?", {}) == "criteria"

    def test_procedure_detection(self):
        assert self.detect("절차도 안내해드릴까요?", {}) == "procedure"
        assert self.detect("어떻게 신청하나요?", {}) == "procedure"
        assert self.detect("조정신청 과정을 알려주세요", {}) == "procedure"
        assert self.detect("소비자원에 접수하는 절차는?", {}) == "procedure"

    def test_full_fallback(self):
        assert self.detect("더 알려줘", {}) == "full"
        assert self.detect("자세히 설명해주세요", {}) == "full"


# ============================================================================
# D-1: classify_mode FOLLOWUP_WITH_CONTEXT 라우팅 테스트
# ============================================================================


class TestClassifyModeFollowup:
    """classify_mode의 FOLLOWUP_WITH_CONTEXT 분기 테스트"""

    @patch("app.common.config.get_config")
    def test_followup_detected_in_minimal_mode(self, mock_config):
        """minimal 모드에서 후속 질문 매칭 시 FOLLOWUP_WITH_CONTEXT"""
        mock_cfg = MagicMock()
        mock_cfg.response.response_mode = "minimal"
        mock_cfg.response.followup_similarity_threshold = 0.8
        mock_config.return_value = mock_cfg

        from app.agents.query_analysis.classifiers import classify_mode

        result = classify_mode(
            "dispute",
            False,
            "관련 법령을 자세히 알려드릴까요?",
            previous_followups=["관련 법령을 자세히 알려드릴까요?"],
        )
        assert result == "FOLLOWUP_WITH_CONTEXT"

    @patch("app.common.config.get_config")
    def test_legacy_mode_ignores_followup(self, mock_config):
        """legacy 모드에서는 FOLLOWUP_WITH_CONTEXT 비활성"""
        mock_cfg = MagicMock()
        mock_cfg.response.response_mode = "legacy"
        mock_cfg.response.followup_similarity_threshold = 0.8
        mock_config.return_value = mock_cfg

        from app.agents.query_analysis.classifiers import classify_mode

        result = classify_mode(
            "dispute",
            False,
            "관련 법령을 자세히 알려드릴까요?",
            previous_followups=["관련 법령을 자세히 알려드릴까요?"],
        )
        assert result == "NEED_RAG"

    def test_no_followups_normal_routing(self):
        """후속 질문 없으면 기존 라우팅"""
        from app.agents.query_analysis.classifiers import classify_mode

        result = classify_mode("dispute", False, "노트북 환불해줘")
        assert result == "NEED_RAG"

    @patch("app.common.config.get_config")
    def test_non_matching_followup(self, mock_config):
        """비매칭 후속 질문은 기존 라우팅"""
        mock_cfg = MagicMock()
        mock_cfg.response.response_mode = "minimal"
        mock_cfg.response.followup_similarity_threshold = 0.8
        mock_config.return_value = mock_cfg

        from app.agents.query_analysis.classifiers import classify_mode

        result = classify_mode(
            "dispute",
            False,
            "노트북 환불해줘",
            previous_followups=["관련 법령을 자세히 알려드릴까요?"],
        )
        assert result == "NEED_RAG"


# ============================================================================
# D-2: memory_save_node _last_turn_context 저장 테스트
# ============================================================================


class TestMemorySaveNodePhaseD:
    """memory_save_node의 Phase D 컨텍스트 저장 테스트"""

    def test_need_rag_saves_context(self):
        """NEED_RAG 모드에서 _last_turn_context 저장"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {
            "mode": "NEED_RAG",
            "user_query": "노트북 환불하고 싶어요",
            "final_answer": "환불은 구매일로부터 7일 이내에 요청하셔야 합니다.",
            "followup_questions": ["관련 법령을 자세히 알려드릴까요?"],
            "available_details": {"laws": {"count": 2, "preview": "소비자기본법"}},
            "retrieval": {"laws": [{"doc_title": "소비자기본법"}]},
            "rag_conversation_memory": [],
        }

        result = memory_save_node(state)
        assert "_last_turn_context" in result
        ctx = result["_last_turn_context"]
        assert ctx["followup_questions"] == ["관련 법령을 자세히 알려드릴까요?"]
        assert ctx["available_details"] is not None
        assert ctx["retrieval"] is not None

    def test_no_retrieval_skips_context(self):
        """NO_RETRIEVAL 모드에서는 컨텍스트 미저장"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {
            "mode": "NO_RETRIEVAL",
            "user_query": "안녕하세요",
            "final_answer": "안녕하세요!",
        }

        result = memory_save_node(state)
        assert "_last_turn_context" not in result

    def test_followup_mode_saves_context(self):
        """FOLLOWUP_WITH_CONTEXT 모드에서도 컨텍스트 저장"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {
            "mode": "FOLLOWUP_WITH_CONTEXT",
            "user_query": "관련 법령을 자세히 알려드릴까요?",
            "final_answer": "소비자기본법 제17조에 의하면...",
            "followup_questions": ["분쟁 해결 절차도 안내해드릴까요?"],
            "available_details": {"cases": {"count": 3, "preview": "유사 사례"}},
            "retrieval": {"laws": [{"doc_title": "소비자기본법"}]},
        }

        result = memory_save_node(state)
        assert "_last_turn_context" in result


# ============================================================================
# D-2: ChatState _last_turn_context 필드 테스트
# ============================================================================


class TestChatStateLastTurnContext:
    """ChatState의 _last_turn_context 필드 테스트"""

    def test_field_exists(self):
        from app.supervisor.state import ChatState

        assert "_last_turn_context" in ChatState.__annotations__

    def test_initial_state_none(self):
        from app.supervisor.state import create_initial_state

        state = create_initial_state(user_query="테스트", chat_type="dispute")
        assert state.get("_last_turn_context") is None


# ============================================================================
# D-3: graph_mas.py FOLLOWUP_WITH_CONTEXT 라우팅 테스트
# ============================================================================


class TestMASRoutingFollowup:
    """FOLLOWUP_WITH_CONTEXT 모드 라우팅 테스트"""

    def test_followup_skips_retrieval(self):
        """FOLLOWUP_WITH_CONTEXT 모드에서 retrieval 생략"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            "supervisor": {"next_agent": "retrieval_team"},
            "mode": "FOLLOWUP_WITH_CONTEXT",
            "retry_count": 0,
            "query_analysis": {},
        }

        result = _route_mas_supervisor(state)
        assert result == "inject_cached_retrieval"

    def test_need_rag_still_fans_out(self):
        """NEED_RAG 모드에서는 여전히 retrieval fan-out"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            "supervisor": {"next_agent": "retrieval_team"},
            "mode": "NEED_RAG",
            "retry_count": 0,
            "query_analysis": {"retriever_types": ["law", "criteria", "case"]},
        }

        result = _route_mas_supervisor(state)
        # Fan-out은 list of Send 반환
        assert isinstance(result, list)


# ============================================================================
# D-4: _filter_retrieval_for_detail 테스트
# ============================================================================


class TestFilterRetrievalForDetail:
    """_filter_retrieval_for_detail() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.answer_generation.agent import _filter_retrieval_for_detail

        self.filter = _filter_retrieval_for_detail

    def test_laws_filter(self):
        retrieval = {
            "laws": [{"doc_title": "소비자기본법"}],
            "criteria": [{"doc_title": "환불기준"}],
            "disputes": [{"doc_title": "사례1"}],
            "counsels": [{"doc_title": "상담1"}],
        }
        result = self.filter(retrieval, "laws")
        assert "laws" in result
        assert "criteria" in result
        assert "disputes" not in result
        assert "counsels" not in result

    def test_cases_filter(self):
        retrieval = {
            "laws": [{"doc_title": "법률"}],
            "disputes": [{"doc_title": "사례1"}],
            "counsels": [{"doc_title": "상담1"}],
        }
        result = self.filter(retrieval, "cases")
        assert "disputes" in result
        assert "counsels" in result
        assert "laws" not in result

    def test_criteria_filter(self):
        retrieval = {
            "laws": [{"doc_title": "법률"}],
            "criteria": [{"doc_title": "기준1"}],
        }
        result = self.filter(retrieval, "criteria")
        assert "criteria" in result
        assert "laws" not in result

    def test_full_returns_all(self):
        retrieval = {"laws": [], "criteria": [], "disputes": [], "counsels": []}
        result = self.filter(retrieval, "full")
        assert result == retrieval

    def test_preserves_agency(self):
        retrieval = {
            "laws": [],
            "agency": {"agency": "KCA"},
        }
        result = self.filter(retrieval, "laws")
        assert "agency" in result


# ============================================================================
# D-4: _followup_detail_response 테스트
# ============================================================================


class TestFollowupDetailResponse:
    """_followup_detail_response() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.answer_generation.agent import _followup_detail_response

        self.detail_response = _followup_detail_response

    def test_procedure_request(self):
        """절차 안내 요청 → 템플릿 응답"""
        state = {
            "user_query": "분쟁 해결 절차도 안내해드릴까요?",
            "_last_turn_context": {
                "retrieval": {"laws": [{"doc_title": "법률"}]},
                "available_details": {"laws": {"count": 1}},
                "followup_questions": [],
            },
        }
        result = self.detail_response(state)
        assert result["response_depth"] == "detail"
        assert "한국소비자원" in result["draft_answer"]
        assert result["generation_model_used"] == "procedure_template"

    def test_no_cache_fallback(self):
        """캐시 없을 때 fallback"""
        state = {
            "user_query": "관련 법령 알려줘",
            "_last_turn_context": None,
        }
        result = self.detail_response(state)
        assert result["has_sufficient_evidence"] is False
        assert result["generation_model_used"] == "followup_no_cache"

    @patch("app.agents.answer_generation.agent.AnswerGenerationFallback")
    def test_laws_detail_uses_llm(self, mock_fallback):
        """법령 상세 요청 → LLM 생성"""
        mock_fallback.generate_with_fallback.return_value = (
            "소비자기본법 제17조에 의하면 청약철회가 가능합니다.",
            "gpt-4o-mini",
            [],
        )

        state = {
            "user_query": "관련 법령을 자세히 알려드릴까요?",
            "_last_turn_context": {
                "retrieval": {
                    "laws": [{"doc_title": "소비자기본법 제17조"}],
                    "criteria": [{"doc_title": "환불기준"}],
                    "disputes": [{"doc_title": "사례1"}],
                    "counsels": [],
                },
                "available_details": {
                    "laws": {"count": 1, "preview": "소비자기본법"},
                    "cases": {"count": 1, "preview": "유사 사례"},
                },
                "followup_questions": [
                    "관련 법령을 자세히 알려드릴까요?",
                    "비슷한 분쟁 조정 사례 1건도 확인해 보시겠어요?",
                ],
            },
        }
        result = self.detail_response(state)
        assert result["response_depth"] == "detail"
        assert "소비자기본법" in result["draft_answer"]
        # Remaining details should exclude 'laws'
        remaining = result.get("available_details", {})
        if remaining:
            assert "laws" not in remaining

    def test_has_messages_field(self):
        """messages 필드 포함 (LangGraph 호환)"""
        state = {
            "user_query": "절차 안내해줘",
            "_last_turn_context": {
                "retrieval": {},
                "available_details": {},
                "followup_questions": [],
            },
        }
        result = self.detail_response(state)
        assert "messages" in result
        assert len(result["messages"]) == 1


# ============================================================================
# D-4: generation_node_v2 FOLLOWUP_WITH_CONTEXT 분기 테스트
# ============================================================================


class TestGenerationNodeV2Followup:
    """generation_node_v2에서 FOLLOWUP_WITH_CONTEXT 분기 테스트"""

    @pytest.mark.asyncio
    @patch("app.agents.answer_generation.agent.get_config")
    async def test_followup_mode_triggers_detail(self, mock_config):
        """FOLLOWUP_WITH_CONTEXT 모드에서 상세 응답"""
        from app.agents.answer_generation.agent import generation_node_v2

        mock_cfg = MagicMock()
        mock_cfg.response.response_mode = "minimal"
        mock_config.return_value = mock_cfg

        state = {
            "user_query": "분쟁 해결 절차도 안내해드릴까요?",
            "mode": "FOLLOWUP_WITH_CONTEXT",
            "_last_turn_context": {
                "retrieval": {"laws": []},
                "available_details": {},
                "followup_questions": [],
            },
        }

        result = await generation_node_v2(state)
        assert result["response_depth"] == "detail"
        assert "한국소비자원" in result["draft_answer"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-p", "no:asyncio", "--tb=short"])
