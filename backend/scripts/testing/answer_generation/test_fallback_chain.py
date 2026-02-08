"""
Fallback Chain Unit Tests

Tests for AnswerGenerationFallback class:
- Primary model success
- Fallback to secondary model
- Fallback to rule-based generation
- Safe fallback message
- Rule-based generation with various data
- Config-based chain construction
"""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.answer_generation.fallback import (
    SAFE_FALLBACK_MESSAGE,
    AnswerGenerationFallback,
)


@pytest.mark.unit
class TestPrimaryModelSuccess:
    """Test successful primary model generation."""

    @patch.object(AnswerGenerationFallback, "_get_fallback_chain")
    @patch.object(AnswerGenerationFallback, "_try_llm_generation")
    def test_primary_model_success(self, mock_try_llm, mock_chain):
        """Primary model succeeds on first call -> returns answer and model name."""
        mock_chain.return_value = [
            ("gpt-4o", "OpenAI"),
            ("gpt-4o-mini", "OpenAI"),
            ("rule_based", "Local"),
        ]
        mock_try_llm.return_value = ("환불 가능합니다.", [{"claim": "c1"}])

        answer, model, cem = AnswerGenerationFallback.generate_with_fallback(
            query="환불 가능한가요?",
            retrieval={"disputes": [], "counsels": [], "laws": [], "criteria": []},
            agency_info={"agency_info": {"name": "한국소비자원"}},
        )

        assert answer == "환불 가능합니다."
        assert model == "gpt-4o"
        assert cem == [{"claim": "c1"}]
        assert mock_try_llm.call_count == 1


@pytest.mark.unit
class TestFallbackToSecondary:
    """Test fallback from primary to secondary model."""

    @patch.object(AnswerGenerationFallback, "_get_fallback_chain")
    @patch.object(AnswerGenerationFallback, "_try_llm_generation")
    def test_fallback_to_secondary(self, mock_try_llm, mock_chain):
        """Primary raises Exception, secondary succeeds."""
        mock_chain.return_value = [
            ("gpt-4o", "OpenAI"),
            ("gpt-4o-mini", "OpenAI"),
            ("rule_based", "Local"),
        ]
        mock_try_llm.side_effect = [
            Exception("Rate limit exceeded"),
            ("보조 모델 답변입니다.", []),
        ]

        answer, model, cem = AnswerGenerationFallback.generate_with_fallback(
            query="배송 지연 문의",
            retrieval={"disputes": [], "counsels": [], "laws": [], "criteria": []},
            agency_info={"agency_info": {"name": "한국소비자원"}},
        )

        assert answer == "보조 모델 답변입니다."
        assert model == "gpt-4o-mini"
        assert mock_try_llm.call_count == 2


@pytest.mark.unit
class TestFallbackToRuleBased:
    """Test fallback to rule-based generation when all LLMs fail."""

    @patch.object(AnswerGenerationFallback, "_get_fallback_chain")
    @patch.object(AnswerGenerationFallback, "_try_llm_generation")
    def test_fallback_to_rule_based(self, mock_try_llm, mock_chain):
        """All LLMs fail -> rule_based generation used."""
        mock_chain.return_value = [
            ("gpt-4o", "OpenAI"),
            ("gpt-4o-mini", "OpenAI"),
            ("rule_based", "Local"),
        ]
        mock_try_llm.side_effect = Exception("API error")

        answer, model, cem = AnswerGenerationFallback.generate_with_fallback(
            query="환불 문의",
            retrieval={
                "disputes": [{"doc_title": "분쟁사례1", "source_org": "KCA"}],
                "counsels": [],
                "laws": [],
                "criteria": [],
            },
            agency_info={"agency_info": {"name": "한국소비자원"}},
        )

        assert model == "rule_based"
        assert cem == []
        assert "한국소비자원" in answer
        assert mock_try_llm.call_count == 2


@pytest.mark.unit
class TestAllFailSafeFallback:
    """Test safe fallback when everything fails."""

    @patch.object(AnswerGenerationFallback, "_get_fallback_chain")
    @patch.object(AnswerGenerationFallback, "_try_llm_generation")
    @patch.object(AnswerGenerationFallback, "_rule_based_generation")
    def test_all_fail_safe_fallback(self, mock_rule, mock_try_llm, mock_chain):
        """All LLMs and rule_based fail -> SAFE_FALLBACK_MESSAGE returned."""
        mock_chain.return_value = [
            ("gpt-4o", "OpenAI"),
            ("gpt-4o-mini", "OpenAI"),
            ("rule_based", "Local"),
        ]
        mock_try_llm.side_effect = Exception("API error")
        mock_rule.side_effect = Exception("Rule-based generation failed")

        answer, model, cem = AnswerGenerationFallback.generate_with_fallback(
            query="환불",
            retrieval={},
            agency_info={},
        )

        assert model == "safe_fallback"
        assert answer == SAFE_FALLBACK_MESSAGE
        assert cem == []


@pytest.mark.unit
class TestRuleBasedGeneration:
    """Test rule-based generation with various data combinations."""

    def test_rule_based_with_all_data(self):
        """Call _rule_based_generation with disputes, counsels, laws, criteria."""
        retrieval = {
            "disputes": [
                {"doc_title": "배송지연 분쟁", "source_org": "ECMC"},
                {"doc_title": "환불 분쟁", "source_org": "KCA"},
            ],
            "counsels": [
                {"doc_title": "전자상거래 환불 상담"},
            ],
            "laws": [
                {"law_name": "전자상거래법", "full_path": "제17조"},
            ],
            "criteria": [
                {"item": "청약철회 기준", "source_label": "소비자분쟁해결기준"},
            ],
        }
        agency_info = {
            "agency_info": {
                "name": "한국소비자원",
                "url": "https://www.kca.go.kr",
            }
        }

        result = AnswerGenerationFallback._rule_based_generation(retrieval, agency_info)

        assert "한국소비자원" in result
        assert "분쟁조정사례 2건" in result
        assert "상담사례 1건" in result
        assert "전자상거래법" in result
        assert "청약철회 기준" in result
        assert "법률 자문이 아닙니다" in result

    def test_rule_based_empty_retrieval(self):
        """Call _rule_based_generation with empty dicts."""
        result = AnswerGenerationFallback._rule_based_generation(
            retrieval={},
            agency_info={},
        )

        assert "한국소비자원" in result
        assert "법률 자문이 아닙니다" in result
        assert "다음 단계" in result

    def test_rule_based_includes_disclaimer(self):
        """Rule-based output contains disclaimer text."""
        result = AnswerGenerationFallback._rule_based_generation(
            retrieval={"disputes": [], "counsels": [], "laws": [], "criteria": []},
            agency_info={"agency_info": {"name": "테스트기관"}},
        )

        assert "법률 자문이 아닙니다" in result
        assert "정보 제공 목적" in result


@pytest.mark.unit
class TestSafeFallbackMessage:
    """Test safe fallback message content."""

    def test_safe_fallback_contains_emergency(self):
        """_safe_fallback_message contains 1372 (한국소비자원 번호)."""
        msg = AnswerGenerationFallback._safe_fallback_message()
        assert "1372" in msg
        assert "한국소비자원" in msg

    def test_safe_fallback_matches_constant(self):
        """_safe_fallback_message returns SAFE_FALLBACK_MESSAGE constant."""
        msg = AnswerGenerationFallback._safe_fallback_message()
        assert msg == SAFE_FALLBACK_MESSAGE


@pytest.mark.unit
class TestFallbackChainConfig:
    """Test fallback chain configuration."""

    @patch("app.common.config.get_config")
    def test_get_fallback_chain_reads_config(self, mock_get_config):
        """Mock config to verify chain order."""
        mock_config = MagicMock()
        mock_config.models.draft_agent = "gpt-4o-test"
        mock_get_config.return_value = mock_config

        chain = AnswerGenerationFallback._get_fallback_chain()

        assert chain[0] == ("gpt-4o-test", "OpenAI")
        assert chain[1] == ("gpt-4o-mini", "OpenAI")
        assert chain[2] == ("rule_based", "Local")
        assert len(chain) == 3


@pytest.mark.unit
class TestEmptyAnswerFallback:
    """Test that empty LLM answers trigger fallback."""

    @patch.object(AnswerGenerationFallback, "_get_fallback_chain")
    @patch.object(AnswerGenerationFallback, "_try_llm_generation")
    def test_empty_answer_from_llm_triggers_fallback(self, mock_try_llm, mock_chain):
        """_try_llm_generation returns empty -> ValueError -> next in chain."""
        mock_chain.return_value = [
            ("gpt-4o", "OpenAI"),
            ("gpt-4o-mini", "OpenAI"),
            ("rule_based", "Local"),
        ]
        # First call raises ValueError (empty answer), second succeeds
        mock_try_llm.side_effect = [
            ValueError("Empty answer from LLM"),
            ("두 번째 모델 답변", []),
        ]

        answer, model, cem = AnswerGenerationFallback.generate_with_fallback(
            query="환불",
            retrieval={},
            agency_info={},
        )

        assert answer == "두 번째 모델 답변"
        assert model == "gpt-4o-mini"
        assert mock_try_llm.call_count == 2
