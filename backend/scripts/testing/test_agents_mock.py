from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from app.agents.answer_generation.agent import _build_general_response
from app.agents.legal_review.agent import _check_prohibited_expressions, review_node
from app.agents.query_analysis.agent import (
    _classify_query_type,
    _extract_info_from_message,
    query_analysis_node,
)
from app.supervisor.state import ChatState, OnboardingInfo, create_initial_state


class TestQueryAnalysisFunctions:

    def test_extract_info_from_message(self):
        query = "노트북 150만원에 샀는데 환불하고 싶어요."
        info = _extract_info_from_message(query)

        assert info.get("purchase_item") == "노트북"
        assert info.get("purchase_amount") == "1500000"
        assert "환불" in info.get("dispute_details", "")

    @patch("app.agents.query_analysis.agent._is_ambiguous_query", return_value=False)
    @patch("app.agents.query_analysis.agent._is_system_meta_query", return_value=False)
    def test_classify_query_type_dispute(self, mock_meta, mock_ambiguous):
        assert _classify_query_type("환불해주세요") == "dispute"

    @patch("app.agents.query_analysis.agent._is_ambiguous_query", return_value=False)
    @patch("app.agents.query_analysis.agent._is_system_meta_query", return_value=False)
    def test_classify_query_type_general(self, mock_meta, mock_ambiguous):
        assert _classify_query_type("안녕하세요") == "general"

    @patch("app.agents.query_analysis.agent._is_ambiguous_query", return_value=False)
    @patch("app.agents.query_analysis.agent._is_system_meta_query", return_value=False)
    def test_classify_query_type_law(self, mock_meta, mock_ambiguous):
        assert _classify_query_type("전자상거래법 제17조 알려줘") == "law"

    def test_query_analysis_node_general(self):
        state = create_initial_state(user_query="안녕하세요", chat_type="general")

        result = query_analysis_node(state)
        qa_result = result["query_analysis"]

        assert qa_result["query_type"] == "general"
        assert result["mode"] == "NO_RETRIEVAL"


class TestLegalReviewFunctions:

    def test_check_prohibited_expressions(self):
        text = "이 소송은 반드시 승소합니다."
        violations = _check_prohibited_expressions(text)
        assert len(violations) > 0
        assert any("반드시" in v[0] for v in violations)

    def test_review_node_pass(self):
        state = create_initial_state(user_query="환불 가능?", chat_type="dispute")
        # 출처/근거가 포함된 답변으로 수정 (법률 검토 통과 조건)
        state["draft_answer"] = (
            "관련 사례(KCA-2024-001)에 따르면 환불이 가능할 수 있습니다. 전자상거래법 제17조를 참고하세요."
        )
        state["query_analysis"] = {"query_type": "dispute"}
        state["sources"] = [
            {
                "doc_id": "1",
                "uid": "KCA-2024-001",
                "content": "전자상거래법 제17조에 따라 청약철회가 가능합니다.",
            }
        ]
        state["retrieval"] = {
            "disputes": [
                {
                    "doc_id": "1",
                    "uid": "KCA-2024-001",
                    "content": "전자상거래법 제17조에 따라 청약철회가 가능합니다.",
                }
            ]
        }

        # AgentSettings mock (Pydantic Settings 클래스)
        mock_agent_settings = MagicMock()
        mock_agent_settings.prohibited_violation_threshold = 3
        mock_agent_settings.max_review_retries = 2

        mock_config = MagicMock()
        mock_config.agent = mock_agent_settings

        with patch("app.common.config.get_config", return_value=mock_config):
            with patch(
                "app.agents.legal_review.agent._check_evidence_sufficiency",
                return_value=True,
            ):
                result = review_node(state)
                review_res = result["review"]

                assert review_res["passed"] is True
                assert "final_answer" in result

    def test_review_node_fail_retry(self):
        bad_answer = "반드시 승소합니다. 무조건 이깁니다. 100% 보장합니다."
        state = create_initial_state(user_query="환불 가능?", chat_type="dispute")
        state["draft_answer"] = bad_answer
        state["query_analysis"] = {"query_type": "dispute"}
        state["sources"] = [{"doc_id": "1"}]
        state["retrieval"] = {"disputes": [{"doc_id": "1"}]}

        # AgentSettings mock (Pydantic Settings 클래스)
        mock_agent_settings = MagicMock()
        mock_agent_settings.prohibited_violation_threshold = 1
        mock_agent_settings.max_review_retries = 2

        mock_config = MagicMock()
        mock_config.agent = mock_agent_settings

        with patch("app.common.config.get_config", return_value=mock_config):
            with patch(
                "app.agents.legal_review.agent._check_evidence_sufficiency",
                return_value=False,
            ):
                result = review_node(state)
                review_res = result["review"]

                assert review_res["passed"] is False
                assert result["retry_count"] == 1


class TestAnswerGenerationFunctions:

    def test_build_general_response(self):
        resp = _build_general_response("안녕하세요")
        assert "안녕하세요" in resp

    @pytest.mark.skip(
        reason="generation_node removed, replaced by async generation_node_v2"
    )
    def test_generation_node_restricted(self):
        pass

    @pytest.mark.skip(
        reason="generation_node removed, replaced by async generation_node_v2"
    )
    def test_generation_node_rag(self):
        pass
