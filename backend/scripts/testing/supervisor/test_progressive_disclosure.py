"""
테스트: Progressive Disclosure + Meta Conversational Response
작성일: 2026-01-31

Phase C+E 구현 검증:
- C-1: StructuredResponse / OutputState 확장 (response_depth, available_details)
- C-2: Progressive summary 생성 로직
- C-3: 후속 질문 생성 개선 (available_details 연동)
- E-1: generation_node_v2 분기 로직 (response_mode별)
- E-2: _meta_conversational_response 구현
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

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
        assert state.get('response_depth') == 'full'
        assert state.get('available_details') is None

    def test_chatstate_has_new_fields(self):
        """ChatState에 response_depth, available_details 필드 정의 확인"""
        from app.supervisor.state import ChatState
        annotations = ChatState.__annotations__
        assert 'response_depth' in annotations
        assert 'available_details' in annotations


# ============================================================================
# C-2: Progressive Summary 생성 테스트
# ============================================================================

class TestProgressiveSummary:
    """_build_progressive_summary() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.answer_generation.agent import (
            _build_progressive_summary,
            _build_available_details,
            _build_progressive_followups,
        )
        self.build_summary = _build_progressive_summary
        self.build_details = _build_available_details
        self.build_followups = _build_progressive_followups

    def test_summary_truncates_long_answer(self):
        """긴 답변을 max_length로 자르기"""
        long_answer = "가" * 500
        result = self.build_summary(long_answer, {}, max_length=200)
        assert len(result) <= 210  # 약간의 여유 (말줄임표 등)

    def test_summary_removes_markdown_headings(self):
        """마크다운 헤딩 제거"""
        answer = "## 제목\n본문 내용입니다.\n### 소제목\n추가 내용."
        result = self.build_summary(answer, {}, max_length=500)
        assert "## 제목" not in result
        assert "### 소제목" not in result
        assert "본문 내용입니다" in result

    def test_summary_removes_disclaimer(self):
        """> 본 답변 면책 제거"""
        answer = "핵심 내용입니다.\n> 본 답변은 법률 자문이 아닙니다."
        result = self.build_summary(answer, {}, max_length=500)
        assert "본 답변" not in result

    def test_summary_empty_answer_fallback(self):
        """빈 답변 시 기본 메시지"""
        result = self.build_summary("", {})
        assert len(result) > 0
        assert "확인" in result or "정보" in result

    def test_summary_preserves_sentence_boundary(self):
        """문장 경계에서 자르기"""
        answer = "첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장이 여기 있습니다."
        result = self.build_summary(answer, {}, max_length=30)
        # 30자 제한이면 첫 문장만 남거나 말줄임표 처리
        assert result.endswith('.') or result.endswith('...')


# ============================================================================
# C-3: available_details 구축 테스트
# ============================================================================

class TestAvailableDetails:
    """_build_available_details() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.answer_generation.agent import _build_available_details
        self.build_details = _build_available_details

    def test_empty_retrieval(self):
        """빈 검색 결과"""
        result = self.build_details({})
        assert result == {}

    def test_laws_section(self):
        """법령 결과 포함"""
        retrieval = {
            'laws': [
                {'doc_title': '소비자기본법 제17조'},
                {'doc_title': '전자상거래법 제18조'},
            ]
        }
        result = self.build_details(retrieval)
        assert 'laws' in result
        assert result['laws']['count'] == 2
        assert '소비자기본법' in result['laws']['preview']

    def test_criteria_section(self):
        """분쟁해결기준 결과 포함"""
        retrieval = {
            'criteria': [
                {'doc_title': '환불 기준'},
            ]
        }
        result = self.build_details(retrieval)
        assert 'criteria' in result
        assert result['criteria']['count'] == 1

    def test_cases_section(self):
        """사례 결과 포함 (disputes + counsels 합산)"""
        retrieval = {
            'disputes': [{'doc_title': '사례1'}],
            'counsels': [{'doc_title': '사례2'}, {'doc_title': '사례3'}],
        }
        result = self.build_details(retrieval)
        assert 'cases' in result
        assert result['cases']['count'] == 3

    def test_all_sections(self):
        """모든 섹션 포함"""
        retrieval = {
            'laws': [{'doc_title': '법률1'}],
            'criteria': [{'doc_title': '기준1'}],
            'disputes': [{'doc_title': '사례1'}],
            'counsels': [],
        }
        result = self.build_details(retrieval)
        assert len(result) == 3  # laws, criteria, cases


# ============================================================================
# C-3: 후속 질문 생성 개선 테스트
# ============================================================================

class TestProgressiveFollowups:
    """_build_progressive_followups() 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.agents.answer_generation.agent import _build_progressive_followups
        self.build_followups = _build_progressive_followups

    def test_no_details_still_has_procedure(self):
        """상세가 없어도 절차 안내 제안"""
        result = self.build_followups({}, {})
        assert len(result) >= 1
        assert any("절차" in q for q in result)

    def test_laws_detail_generates_law_question(self):
        """법령 상세 있으면 법령 질문 생성"""
        details = {'laws': {'count': 2, 'preview': '소비자기본법'}}
        result = self.build_followups({}, details)
        assert any("법령" in q for q in result)

    def test_cases_detail_generates_case_question(self):
        """사례 상세 있으면 사례 질문 생성 (건수 포함)"""
        details = {'cases': {'count': 5, 'preview': '유사 사례'}}
        result = self.build_followups({}, details)
        assert any("5건" in q for q in result)

    def test_max_three_followups(self):
        """최대 3개 후속 질문"""
        details = {
            'laws': {'count': 2, 'preview': '법률'},
            'criteria': {'count': 1, 'preview': '기준'},
            'cases': {'count': 5, 'preview': '사례'},
        }
        result = self.build_followups({}, details)
        assert len(result) <= 3


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
        state = {'user_query': '뭘 물어봐야 할까?', 'mode': 'META_CONVERSATIONAL'}
        result = self.meta_response(state)

        assert 'draft_answer' in result
        assert '똑소리' in result['draft_answer']
        assert '품목' in result['draft_answer'] or '제품' in result['draft_answer']
        assert result['response_depth'] == 'full'
        assert result['generation_model_used'] == 'meta_conversational_template'

    def test_meta_response_with_onboarding(self):
        """온보딩 정보가 있으면 맞춤 응답"""
        state = {
            'user_query': '도와줘',
            'mode': 'META_CONVERSATIONAL',
            'onboarding': {'purchase_item': '에어팟'},
        }
        result = self.meta_response(state)

        assert '에어팟' in result['draft_answer']
        assert '문제 상황' in result['draft_answer']

    def test_meta_response_has_messages(self):
        """messages 필드 포함 (LangGraph 호환)"""
        state = {'user_query': '도와줘', 'mode': 'META_CONVERSATIONAL'}
        result = self.meta_response(state)

        assert 'messages' in result
        assert len(result['messages']) == 1


# ============================================================================
# E-1: generation_node_v2 분기 로직 테스트
# ============================================================================

class TestGenerationNodeV2Branching:
    """generation_node_v2 response_mode 분기 테스트"""

    @pytest.mark.asyncio
    @patch('app.agents.answer_generation.agent.get_config')
    async def test_legacy_mode_unchanged(self, mock_config):
        """legacy 모드는 기존 동작 유지 (general 쿼리는 response_depth 미포함 - early return)"""
        from app.agents.answer_generation.agent import generation_node_v2

        mock_cfg = MagicMock()
        mock_cfg.response.response_mode = 'legacy'
        mock_cfg.chatbot_features.enable_followup_questions = False
        mock_config.return_value = mock_cfg

        state = {
            'user_query': '안녕하세요',
            'query_analysis': {'query_type': 'general'},
            'retrieval': None,
            'retry_context': None,
            'mode': 'NO_RETRIEVAL',
        }

        result = await generation_node_v2(state)
        assert 'draft_answer' in result
        assert '똑소리' in result['draft_answer']
        # general 쿼리 early return은 기존 동작 유지 (response_depth 미포함)

    @pytest.mark.asyncio
    @patch('app.agents.answer_generation.agent.get_config')
    async def test_meta_conversational_triggers_guide(self, mock_config):
        """META_CONVERSATIONAL 모드에서 가이드 응답"""
        from app.agents.answer_generation.agent import generation_node_v2

        mock_cfg = MagicMock()
        mock_cfg.response.response_mode = 'minimal'
        mock_config.return_value = mock_cfg

        state = {
            'user_query': '뭘 물어봐야 할까?',
            'query_analysis': {'query_type': 'meta_conversational'},
            'mode': 'META_CONVERSATIONAL',
        }

        result = await generation_node_v2(state)
        assert result['generation_model_used'] == 'meta_conversational_template'
        assert '똑소리' in result['draft_answer']

    @pytest.mark.asyncio
    @patch('app.agents.answer_generation.agent.get_config')
    @patch('app.agents.answer_generation.agent.AnswerGenerationFallback')
    @patch('app.agents.answer_generation.agent.RetrievalSufficiencyChecker')
    async def test_minimal_mode_returns_summary(self, mock_checker, mock_fallback, mock_config):
        """minimal 모드 NEED_RAG에서 summary 응답"""
        from app.agents.answer_generation.agent import generation_node_v2

        mock_cfg = MagicMock()
        mock_cfg.response.response_mode = 'minimal'
        mock_cfg.response.summary_max_length = 100
        mock_config.return_value = mock_cfg

        # Mock sufficiency checker
        mock_suf = MagicMock()
        mock_suf.evaluate.return_value = MagicMock(
            confidence=0.8,
            is_sufficient=True,
            level='sufficient',
        )
        mock_checker.return_value = mock_suf

        # Mock LLM answer generation
        mock_fallback.generate_with_fallback.return_value = (
            "## 환불 안내\n\n환불은 구매일로부터 7일 이내에 요청하셔야 합니다. 전자상거래법에 따르면 소비자는 청약철회 권리가 있습니다.\n\n### 관련 법령\n소비자기본법 제17조에 의거합니다.",
            'gpt-4o-mini',
            [],
        )

        state = {
            'user_query': '노트북 환불하고 싶어요',
            'query_analysis': {'query_type': 'dispute'},
            'retrieval': {
                'laws': [{'doc_title': '소비자기본법 제17조'}],
                'criteria': [],
                'disputes': [{'doc_title': '노트북 환불 사례'}],
                'counsels': [],
            },
            'retry_context': None,
            'mode': 'NEED_RAG',
        }

        result = await generation_node_v2(state)
        assert result['response_depth'] == 'summary'
        assert result['available_details'] is not None
        assert 'laws' in result['available_details']
        assert len(result.get('followup_questions', [])) > 0
        # Summary should be shorter than full answer
        assert "##" not in result['draft_answer']


# ============================================================================
# graph_mas.py 라우팅 테스트
# ============================================================================

class TestMASRoutingMetaConversational:
    """META_CONVERSATIONAL 모드 라우팅 테스트"""

    def test_meta_conversational_skips_retrieval(self):
        """META_CONVERSATIONAL 모드에서 retrieval 생략"""
        from app.supervisor.graph_mas import _route_mas_supervisor

        state = {
            'supervisor': {'next_agent': 'retrieval_team'},
            'mode': 'META_CONVERSATIONAL',
            'retry_count': 0,
            'query_analysis': {},
        }

        result = _route_mas_supervisor(state)
        assert result == 'generation'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-p", "no:asyncio", "--tb=short"])
