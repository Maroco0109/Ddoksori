import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.guardrail.moderation import (
    InputModerator,
    ModerationResult,
    get_moderator,
    MODERATION_MODEL,
)
from app.guardrail.policies import (
    BLOCKED_CATEGORIES,
    WARN_CATEGORIES,
    should_block,
    get_flagged_categories,
    get_fallback_message,
)


class TestPolicies:
    
    def test_blocked_categories_defined(self):
        assert len(BLOCKED_CATEGORIES) > 0
        assert "hate" in BLOCKED_CATEGORIES
        assert "violence/graphic" in BLOCKED_CATEGORIES
        assert "sexual/minors" in BLOCKED_CATEGORIES
    
    def test_warn_categories_defined(self):
        assert len(WARN_CATEGORIES) > 0
        assert "harassment" in WARN_CATEGORIES
        assert "violence" in WARN_CATEGORIES
    
    def test_should_block_with_blocked_category(self):
        categories = {"hate": True, "violence": False}
        assert should_block(categories) is True
    
    def test_should_block_with_warn_only(self):
        categories = {"harassment": True, "violence": True, "hate": False}
        assert should_block(categories) is False
    
    def test_should_block_empty(self):
        assert should_block({}) is False
    
    def test_get_flagged_categories(self):
        categories = {"hate": True, "violence": False, "harassment": True}
        flagged = get_flagged_categories(categories)
        assert set(flagged) == {"hate", "harassment"}
    
    def test_get_fallback_message_blocked(self):
        msg = get_fallback_message("blocked")
        assert "서비스 정책상" in msg
    
    def test_get_fallback_message_error(self):
        msg = get_fallback_message("error")
        assert "오류" in msg
    
    def test_get_fallback_message_timeout(self):
        msg = get_fallback_message("timeout")
        assert "시간" in msg


class TestModerationResult:
    
    def test_should_proceed_when_not_blocked(self):
        result = ModerationResult(
            flagged=False,
            blocked=False,
            categories={},
            category_scores={},
            flagged_categories=[],
        )
        assert result.should_proceed is True
    
    def test_should_not_proceed_when_blocked(self):
        result = ModerationResult(
            flagged=True,
            blocked=True,
            categories={"hate": True},
            category_scores={"hate": 0.9},
            flagged_categories=["hate"],
        )
        assert result.should_proceed is False
    
    def test_should_not_proceed_on_error(self):
        result = ModerationResult(
            flagged=False,
            blocked=False,
            categories={},
            category_scores={},
            flagged_categories=[],
            error="timeout",
        )
        assert result.should_proceed is False


class TestInputModerator:
    
    def test_moderator_initialization(self):
        moderator = InputModerator(api_key="test-key")
        assert moderator.api_key == "test-key"
        assert moderator.model == MODERATION_MODEL
        assert moderator.fail_open is True
    
    def test_check_empty_input(self):
        moderator = InputModerator()
        result = moderator.check("")
        
        assert result.flagged is False
        assert result.blocked is False
        assert result.should_proceed is True
    
    def test_check_whitespace_input(self):
        moderator = InputModerator()
        result = moderator.check("   ")
        
        assert result.flagged is False
        assert result.blocked is False
    
    @patch("app.guardrail.moderation.OpenAI")
    def test_check_normal_input(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_result = MagicMock()
        mock_result.flagged = False
        mock_result.categories = {"hate": False, "violence": False}
        mock_result.category_scores = {"hate": 0.01, "violence": 0.01}
        
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_client.moderations.create.return_value = mock_response
        
        moderator = InputModerator(api_key="test-key")
        moderator._client = mock_client
        
        result = moderator.check("헬스장 환불 문의입니다")
        
        mock_client.moderations.create.assert_called_once()
        assert result.flagged is False
        assert result.blocked is False
    
    @patch("app.guardrail.moderation.OpenAI")
    def test_fail_open_on_api_error(self, mock_openai_class):
        from openai import APIError
        
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.moderations.create.side_effect = APIError(
            message="API Error",
            request=MagicMock(),
            body=None
        )
        
        moderator = InputModerator(api_key="test-key", fail_open=True)
        moderator._client = mock_client
        
        result = moderator.check("테스트 입력")
        
        assert result.blocked is False
        assert result.error == "error"
    
    @patch("app.guardrail.moderation.OpenAI")
    def test_fail_close_on_api_error(self, mock_openai_class):
        from openai import APIError
        
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.moderations.create.side_effect = APIError(
            message="API Error",
            request=MagicMock(),
            body=None
        )
        
        moderator = InputModerator(api_key="test-key", fail_open=False)
        moderator._client = mock_client
        
        result = moderator.check("테스트 입력")
        
        assert result.blocked is True
        assert result.error == "error"
    
    def test_get_fallback_response_blocked(self):
        moderator = InputModerator()
        result = ModerationResult(
            flagged=True,
            blocked=True,
            categories={},
            category_scores={},
            flagged_categories=[],
        )
        
        response = moderator.get_fallback_response(result)
        assert "서비스 정책상" in response
    
    def test_get_fallback_response_error(self):
        moderator = InputModerator()
        result = ModerationResult(
            flagged=False,
            blocked=False,
            categories={},
            category_scores={},
            flagged_categories=[],
            error="timeout",
        )
        
        response = moderator.get_fallback_response(result)
        assert "시간" in response


class TestGetModerator:
    
    def test_get_moderator_default(self):
        moderator = get_moderator()
        assert isinstance(moderator, InputModerator)
        assert moderator.fail_open is True
    
    def test_get_moderator_fail_close(self):
        moderator = get_moderator(fail_open=False)
        assert moderator.fail_open is False
    
    def test_get_moderator_custom_timeout(self):
        moderator = get_moderator(timeout=10.0)
        assert moderator.timeout == 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-p", "no:asyncio"])
