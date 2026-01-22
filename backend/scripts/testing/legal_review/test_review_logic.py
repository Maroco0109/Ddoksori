"""
S2-PR2: HybridLegalReviewer 테스트
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from app.agents.legal_review.llm_reviewer import (
    HybridLegalReviewer,
    LLMReviewResult,
    LLM_REVIEW_SYSTEM_PROMPT,
    hybrid_review_node,
    hybrid_review_node_wrapper,
    get_reviewer,
)
from app.orchestrator.state import ChatState


class TestHybridLegalReviewerInit:

    def test_init_default_llm_disabled(self):
        with patch.dict(os.environ, {'ENABLE_LLM_REVIEW': 'false'}):
            reviewer = HybridLegalReviewer()
            assert reviewer.enable_llm is False

    def test_init_llm_enabled_via_env(self):
        with patch.dict(os.environ, {'ENABLE_LLM_REVIEW': 'true'}):
            reviewer = HybridLegalReviewer()
            assert reviewer.enable_llm is True

    def test_init_explicit_enable_override(self):
        reviewer = HybridLegalReviewer(enable_llm=True)
        assert reviewer.enable_llm is True

    def test_init_explicit_disable_override(self):
        with patch.dict(os.environ, {'ENABLE_LLM_REVIEW': 'true'}):
            reviewer = HybridLegalReviewer(enable_llm=False)
            assert reviewer.enable_llm is False


class TestRuleBasedReview:

    @pytest.fixture
    def reviewer(self):
        return HybridLegalReviewer(enable_llm=False)

    def test_general_query_skips_review(self, reviewer):
        state: ChatState = {
            'query': '안녕하세요',
            'draft_answer': '안녕하세요! 무엇을 도와드릴까요?',
            'query_analysis': {'query_type': 'general'},
            'sources': [],
        }
        result = reviewer.review(state)

        assert result['review']['passed'] is True
        assert result['review']['violations'] == []
        assert result['final_answer'] == '안녕하세요! 무엇을 도와드릴까요?'

    def test_clean_answer_passes(self, reviewer):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '관련 규정에 따르면 환불을 요청할 수 있습니다. [출처: 소비자보호법 제10조]',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
        }
        result = reviewer.review(state)

        assert result['review']['passed'] is True
        assert 'final_answer' in result

    def test_prohibited_expression_detected(self, reviewer):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '반드시 환불받으실 수 있습니다. 100% 보장합니다.',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
        }
        result = reviewer.review(state)

        assert result['review']['passed'] is False
        assert any('금지 표현' in v for v in result['review']['violations'])

    def test_severe_violations_trigger_retry(self, reviewer):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '반드시 환불받으실 수 있습니다. 법적으로 위법입니다. 100% 승소할 것입니다.',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
            'retry_count': 0,
        }
        result = reviewer.review(state)

        assert 'retry_count' in result
        assert result['retry_count'] == 1

    def test_max_retries_respected(self, reviewer):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '반드시 환불받으실 수 있습니다. 법적으로 위법입니다. 100% 승소할 것입니다.',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
            'retry_count': 2,
        }
        result = reviewer.review(state)

        assert 'final_answer' in result
        assert 'retry_count' not in result


class TestLLMBasedReview:

    @pytest.fixture
    def reviewer_with_llm(self):
        return HybridLegalReviewer(enable_llm=True)

    def test_llm_review_called_when_rule_passes(self, reviewer_with_llm):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '관련 규정에 따르면 환불을 요청할 수 있습니다. [출처: 소비자보호법]',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
        }

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"passed": true, "issues": [], "severity": "low", "overall_comment": "Good"}'

        with patch('openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            result = reviewer_with_llm.review(state)

            mock_client.chat.completions.create.assert_called_once()
            assert result['review']['passed'] is True

    def test_llm_review_skipped_on_severe_rule_violation(self, reviewer_with_llm):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '반드시 환불받으셔야 합니다. 법적으로 위법입니다. 100% 승소합니다.',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
            'retry_count': 0,
        }

        with patch('openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            reviewer_with_llm.review(state)

            mock_client.chat.completions.create.assert_not_called()

    def test_llm_issues_merged_into_violations(self, reviewer_with_llm):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '관련 규정에 따르면 환불을 요청할 수 있습니다. [출처: 소비자보호법]',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
        }

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "passed": false,
            "issues": [{"type": "부적절한 조언", "text": "환불 요청", "suggestion": "수정 제안"}],
            "severity": "medium",
            "overall_comment": "Found issue"
        }
        '''

        with patch('openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            result = reviewer_with_llm.review(state)

            assert any('[LLM]' in v for v in result['review']['violations'])
            assert result['review']['passed'] is False

    def test_llm_failure_graceful_degradation(self, reviewer_with_llm):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '관련 규정에 따르면 환불을 요청할 수 있습니다. [출처: 소비자보호법]',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
        }

        with patch('openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("API Error")
            mock_openai.return_value = mock_client

            result = reviewer_with_llm.review(state)

            assert result['review']['passed'] is True
            assert 'final_answer' in result


class TestMetrics:

    def test_metrics_tracking(self):
        reviewer = HybridLegalReviewer(enable_llm=True)

        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '관련 규정에 따르면 환불을 요청할 수 있습니다. [출처: 소비자보호법]',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
        }

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"passed": true, "issues": [], "severity": "low", "overall_comment": "Good"}'

        with patch('openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            reviewer.review(state)
            reviewer.review(state)

            metrics = reviewer.get_metrics()

            assert metrics['llm_call_count'] == 2
            assert metrics['total_llm_latency_ms'] > 0
            assert metrics['enable_llm'] is True

    def test_metrics_reset(self):
        reviewer = HybridLegalReviewer(enable_llm=True)
        reviewer._llm_call_count = 10
        reviewer._total_llm_latency_ms = 500.0

        reviewer.reset_metrics()

        assert reviewer._llm_call_count == 0
        assert reviewer._total_llm_latency_ms == 0.0


class TestNodeFunctions:

    def test_hybrid_review_node(self):
        state: ChatState = {
            'query': '안녕하세요',
            'draft_answer': '안녕하세요!',
            'query_analysis': {'query_type': 'general'},
            'sources': [],
        }

        result = hybrid_review_node(state)

        assert result['review']['passed'] is True

    def test_hybrid_review_node_wrapper_general(self):
        state: ChatState = {
            'query': '안녕하세요',
            'draft_answer': '안녕하세요!',
            'chat_type': 'general',
        }

        result = hybrid_review_node_wrapper(state)

        assert result['review']['passed'] is True
        assert result['final_answer'] == '안녕하세요!'

    def test_hybrid_review_node_wrapper_dispute(self):
        state: ChatState = {
            'query': '환불 가능한가요?',
            'draft_answer': '관련 규정에 따르면 환불을 요청할 수 있습니다. [출처: 소비자보호법]',
            'chat_type': 'dispute',
            'query_analysis': {'query_type': 'dispute'},
            'sources': [{'doc_type': 'law'}],
            'retrieval': {'disputes': [{'content': 'sample'}]},
        }

        with patch.dict(os.environ, {'ENABLE_LLM_REVIEW': 'false'}):
            result = hybrid_review_node_wrapper(state)

        assert result['review']['passed'] is True


class TestLLMReviewSystemPrompt:

    def test_prompt_contains_required_sections(self):
        assert '법적 단정' in LLM_REVIEW_SYSTEM_PROMPT
        assert '전문가 사칭' in LLM_REVIEW_SYSTEM_PROMPT
        assert '근거 없는 주장' in LLM_REVIEW_SYSTEM_PROMPT
        assert '부적절한 조언' in LLM_REVIEW_SYSTEM_PROMPT
        assert 'JSON' in LLM_REVIEW_SYSTEM_PROMPT


class TestGetReviewer:

    def test_singleton_pattern(self):
        import app.agents.legal_review.llm_reviewer as module
        module._reviewer_instance = None

        r1 = get_reviewer()
        r2 = get_reviewer()

        assert r1 is r2

        module._reviewer_instance = None
