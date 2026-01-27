"""
S1-PR5: Answer Generation Fallback Chain Tests
"""

import pytest
from typing import Dict, Any
from unittest.mock import patch, MagicMock

from app.agents.answer_generation.fallback import (
    AnswerGenerationFallback,
    SAFE_FALLBACK_MESSAGE,
)
from app.agents.answer_generation.agent import generation_node
from app.orchestrator.state import create_initial_state


class TestAnswerGenerationFallback:

    @pytest.fixture
    def sample_retrieval(self) -> Dict[str, Any]:
        return {
            'agency': {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'full_name': '한국소비자원 소비자분쟁조정위원회',
                    'description': '일반 소비자 분쟁 조정',
                    'url': 'https://www.kca.go.kr'
                },
            },
            'disputes': [
                {'doc_title': '노트북 환불 분쟁', 'source_org': 'KCA'},
                {'doc_title': '스마트폰 AS 분쟁', 'source_org': 'KCA'},
            ],
            'counsels': [
                {'doc_title': '환불 상담 사례'},
            ],
            'laws': [
                {'law_name': '소비자기본법', 'full_path': '제16조'},
            ],
            'criteria': [
                {'item': '전자제품', 'source_label': '분쟁해결기준'},
            ],
        }

    @pytest.fixture
    def sample_agency_info(self) -> Dict[str, Any]:
        return {
            'agency': 'KCA',
            'agency_info': {
                'name': '한국소비자원',
                'full_name': '한국소비자원 소비자분쟁조정위원회',
                'description': '일반 소비자 분쟁 조정',
                'url': 'https://www.kca.go.kr'
            },
        }

    def test_rule_based_generation_contains_required_sections(
        self, sample_retrieval, sample_agency_info
    ):
        """rule_based generation includes all required sections"""
        result = AnswerGenerationFallback._rule_based_generation(
            retrieval=sample_retrieval,
            agency_info=sample_agency_info,
        )

        assert '## 1. 추천 기관' in result
        assert '한국소비자원' in result
        assert '## 2. 관련 사례' in result
        assert '분쟁조정사례' in result
        assert '노트북 환불 분쟁' in result
        assert '## 3. 관련 법령' in result
        assert '소비자기본법' in result
        assert '## 4. 관련 기준' in result
        assert '## 다음 단계' in result
        assert '본 답변은 정보 제공 목적이며 법률 자문이 아닙니다' in result

    def test_rule_based_generation_empty_retrieval(self, sample_agency_info):
        """rule_based generation handles empty retrieval gracefully"""
        empty_retrieval: Dict[str, Any] = {
            'agency': {},
            'disputes': [],
            'counsels': [],
            'laws': [],
            'criteria': [],
        }

        result = AnswerGenerationFallback._rule_based_generation(
            retrieval=empty_retrieval,
            agency_info=sample_agency_info,
        )

        assert '## 1. 추천 기관' in result
        assert '## 다음 단계' in result
        assert '## 2. 관련 사례' not in result
        assert '## 3. 관련 법령' not in result
        assert '## 4. 관련 기준' not in result

    def test_safe_fallback_message_contains_contact_info(self):
        """safe fallback message contains emergency contact info"""
        message = AnswerGenerationFallback._safe_fallback_message()

        assert '1372' in message
        assert 'consumer.go.kr' in message
        assert '오류' in message

    def test_fallback_chain_order(self):
        """fallback chain has correct order: gpt-4o -> gpt-4o-mini -> rule_based"""
        chain = AnswerGenerationFallback.FALLBACK_CHAIN

        assert len(chain) == 3
        assert chain[0] == ('gpt-4o', 'OpenAI')
        assert chain[1] == ('gpt-4o-mini', 'OpenAI')
        assert chain[2] == ('rule_based', 'Local')

    @patch.object(AnswerGenerationFallback, '_try_llm_generation')
    def test_fallback_to_rule_based_on_llm_failure(
        self, mock_llm, sample_retrieval, sample_agency_info
    ):
        """falls back to rule_based when all LLMs fail"""
        mock_llm.side_effect = Exception("LLM API error")

        answer, model_used, claim_map = AnswerGenerationFallback.generate_with_fallback(
            query="노트북 환불",
            retrieval=sample_retrieval,
            agency_info=sample_agency_info,
        )

        assert model_used == 'rule_based'
        assert '## 1. 추천 기관' in answer
        assert claim_map == []

    @patch.object(AnswerGenerationFallback, '_try_llm_generation')
    @patch.object(AnswerGenerationFallback, '_rule_based_generation')
    def test_fallback_to_safe_message_on_total_failure(
        self, mock_rule, mock_llm, sample_retrieval, sample_agency_info
    ):
        """falls back to safe message when everything fails"""
        mock_llm.side_effect = Exception("LLM API error")
        mock_rule.side_effect = Exception("Rule-based error")

        answer, model_used, claim_map = AnswerGenerationFallback.generate_with_fallback(
            query="노트북 환불",
            retrieval=sample_retrieval,
            agency_info=sample_agency_info,
        )

        assert model_used == 'safe_fallback'
        assert answer == SAFE_FALLBACK_MESSAGE
        assert claim_map == []

    @patch.object(AnswerGenerationFallback, '_try_llm_generation')
    def test_primary_llm_success_skips_fallback(
        self, mock_llm, sample_retrieval, sample_agency_info
    ):
        """primary LLM success skips fallback chain"""
        mock_llm.return_value = ("LLM generated answer", [{'claim': 'test'}])

        answer, model_used, claim_map = AnswerGenerationFallback.generate_with_fallback(
            query="노트북 환불",
            retrieval=sample_retrieval,
            agency_info=sample_agency_info,
        )

        assert model_used == 'gpt-4o-mini'
        assert answer == "LLM generated answer"
        assert claim_map == [{'claim': 'test'}]
        assert mock_llm.call_count == 1


class TestGenerationNodeWithFallback:

    @pytest.fixture
    def state_with_retrieval(self) -> Dict[str, Any]:
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )
        state['retrieval'] = {
            'agency': {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'url': 'https://www.kca.go.kr'
                },
            },
            'disputes': [{'doc_title': '테스트 분쟁'}],
            'counsels': [],
            'laws': [],
            'criteria': [],
        }
        return state

    @patch('app.agents.answer_generation.fallback.AnswerGenerationFallback.generate_with_fallback')
    def test_generation_node_uses_fallback_chain(self, mock_fallback, state_with_retrieval):
        """generation_node uses fallback chain"""
        mock_fallback.return_value = ("답변 내용", "gpt-4o-mini", [])

        result = generation_node(state_with_retrieval)

        assert mock_fallback.called
        assert result['draft_answer'] == "답변 내용"
        assert result['generation_model_used'] == "gpt-4o-mini"
        assert result['has_sufficient_evidence'] is True

    @patch('app.agents.answer_generation.fallback.AnswerGenerationFallback.generate_with_fallback')
    def test_generation_node_marks_low_evidence_for_fallback_models(
        self, mock_fallback, state_with_retrieval
    ):
        """generation_node marks has_sufficient_evidence=False for fallback models"""
        mock_fallback.return_value = ("규칙 기반 답변", "rule_based", [])

        result = generation_node(state_with_retrieval)

        assert result['has_sufficient_evidence'] is False
        assert result['generation_model_used'] == "rule_based"

    @patch('app.agents.answer_generation.fallback.AnswerGenerationFallback.generate_with_fallback')
    def test_generation_node_safe_fallback_evidence_flag(
        self, mock_fallback, state_with_retrieval
    ):
        """generation_node marks has_sufficient_evidence=False for safe_fallback"""
        mock_fallback.return_value = (SAFE_FALLBACK_MESSAGE, "safe_fallback", [])

        result = generation_node(state_with_retrieval)

        assert result['has_sufficient_evidence'] is False
        assert result['generation_model_used'] == "safe_fallback"

    def test_generation_node_no_retrieval_returns_clarifying_questions(self):
        """generation_node returns clarifying questions when no retrieval"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )
        state['retrieval'] = None

        result = generation_node(state)

        assert '관련 정보를 찾을 수 없습니다' in result['draft_answer']
        assert len(result['clarifying_questions']) > 0
        assert result['has_sufficient_evidence'] is False

    def test_generation_node_general_query_bypasses_fallback(self):
        """generation_node handles general queries without fallback"""
        state = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        state['query_analysis'] = {'query_type': 'general'}

        result = generation_node(state)

        assert '똑소리입니다' in result['draft_answer']
        assert result['has_sufficient_evidence'] is True
