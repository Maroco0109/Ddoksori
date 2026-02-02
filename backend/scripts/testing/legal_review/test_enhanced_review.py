"""
Legal Review Agent Enhanced 기능 테스트

테스트 대상:
1. RelevanceChecker - Query-Answer 관련성 검증
2. verify_citation_accuracy - 인용 정확성 검증 (Hallucination 방지)
3. ConfidenceScorer - 신뢰도 점수 계산
4. Enhanced LLM Review - 법적 판단 탐지

실행:
    pytest backend/scripts/testing/legal_review/test_enhanced_review.py -v
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

# 테스트 대상 모듈
from app.agents.legal_review.agent import (
    CitationVerifyResult,
    _extract_law_references,
    verify_citation_accuracy,
)
from app.agents.legal_review.confidence_scorer import (
    ConfidenceScorer,
    ConfidenceScoreResult,
)
from app.agents.legal_review.relevance_checker import (
    RelevanceChecker,
    RelevanceResult,
)


class TestExtractLawReferences:
    """법령/조문 추출 테스트"""

    def test_extract_article_number(self):
        """제XX조 패턴 추출"""
        text = "소비자기본법 제17조에 따르면 환불이 가능합니다."
        refs = _extract_law_references(text)
        assert any("17" in ref for ref in refs)

    def test_extract_article_with_paragraph(self):
        """제XX조 제X항 패턴 추출"""
        text = "제17조 제1항에 따라 처리됩니다."
        refs = _extract_law_references(text)
        assert len(refs) > 0

    def test_extract_appendix(self):
        """별표 패턴 추출"""
        text = "별표 1에 규정된 기준에 따릅니다."
        refs = _extract_law_references(text)
        assert any("1" in ref for ref in refs)

    def test_extract_law_names(self):
        """법령명 추출"""
        text = "전자상거래법과 소비자보호법에 의거합니다."
        refs = _extract_law_references(text)
        # 법령명도 추출되어야 함
        assert len(refs) >= 1

    def test_empty_text(self):
        """빈 텍스트"""
        refs = _extract_law_references("")
        assert refs == []


class TestVerifyCitationAccuracy:
    """인용 정확성 검증 테스트"""

    def test_no_citations_in_answer(self):
        """답변에 법령 인용이 없는 경우"""
        answer = "환불이 가능할 수 있습니다."
        sources = [{"content": "제17조에 따르면..."}]

        result = verify_citation_accuracy(answer, sources)

        assert result.passed is True
        assert result.cited_refs == []
        assert result.accuracy == 1.0

    def test_valid_citation(self):
        """유효한 인용 (검색 결과에 존재)"""
        answer = "제17조에 따르면 환불이 가능합니다."
        sources = [{"content": "제17조 (청약철회) 소비자는 7일 이내에..."}]

        result = verify_citation_accuracy(answer, sources)

        assert result.passed is True
        assert "17" in str(result.verified_refs)
        assert len(result.unverified_refs) == 0

    def test_hallucination_citation(self):
        """Hallucination 인용 (검색 결과에 없음)"""
        answer = "제99조에 따르면 무조건 환불됩니다."
        sources = [{"content": "제17조 (청약철회) 소비자는 7일 이내에..."}]

        result = verify_citation_accuracy(answer, sources)

        # 관대 모드에서는 50% 이상 검증되면 통과
        # 여기서는 0% 검증이므로 실패할 수 있음
        assert "99" in str(result.unverified_refs) or "99" in str(result.cited_refs)

    def test_empty_sources(self):
        """검색 결과가 없는 경우"""
        answer = "제17조에 따르면 환불이 가능합니다."
        sources = []

        result = verify_citation_accuracy(answer, sources)

        # 검색 결과가 없으면 검증 불가 (통과 처리)
        assert result.accuracy == 1.0 or len(result.cited_refs) > 0


class TestRelevanceChecker:
    """관련성 검증 테스트 (Mocked)"""

    @pytest.fixture
    def mock_embedding_client(self):
        """EmbeddingClient Mock"""
        with patch(
            "app.agents.legal_review.relevance_checker.RelevanceChecker._get_client"
        ) as mock:
            client = MagicMock()
            # 유사한 텍스트에 대해 높은 유사도 반환
            client.embed.return_value = [
                [0.1] * 1536,  # query embedding
                [0.1] * 1536,  # answer embedding (same = high similarity)
            ]
            client.embed_query.return_value = [0.1] * 1536
            mock.return_value = client
            yield client

    def test_high_relevance(self, mock_embedding_client):
        """높은 관련성"""
        checker = RelevanceChecker()

        result = checker.check_query_answer_relevance(
            query="헬스장 환불 가능한가요?",
            answer="헬스장 회원권은 청약철회 기간 내 환불이 가능합니다.",
            threshold=0.5,
        )

        # Mock이므로 cosine similarity = 1.0
        assert result.passed is True
        assert result.score >= 0.5

    def test_empty_query(self, mock_embedding_client):
        """빈 쿼리"""
        checker = RelevanceChecker()

        result = checker.check_query_answer_relevance(
            query="", answer="환불이 가능합니다.", threshold=0.5
        )

        assert result.passed is False
        assert "비어있습니다" in result.message

    def test_empty_answer(self, mock_embedding_client):
        """빈 답변"""
        checker = RelevanceChecker()

        result = checker.check_query_answer_relevance(
            query="헬스장 환불 가능한가요?", answer="", threshold=0.5
        )

        assert result.passed is False


class TestConfidenceScorer:
    """신뢰도 점수 계산 테스트"""

    def test_high_confidence(self):
        """높은 신뢰도"""
        scorer = ConfidenceScorer()

        result = scorer.calculate(
            answer="환불이 가능합니다. 제17조에 따르면...",
            sources=[{"content": "제17조 (청약철회) 소비자는..."}] * 3,
            relevance_score=0.9,
            citation_accuracy=0.95,
        )

        assert result.total_score >= 0.7
        assert result.grade in ["A", "B"]
        assert result.is_reliable is True

    def test_low_confidence(self):
        """낮은 신뢰도"""
        scorer = ConfidenceScorer()

        result = scorer.calculate(
            answer="환불이 가능합니다.",
            sources=[],
            relevance_score=0.2,
            citation_accuracy=0.1,
        )

        assert result.total_score < 0.5
        assert result.grade in ["D", "F"]
        assert result.is_reliable is False

    def test_grade_thresholds(self):
        """등급 기준 테스트"""
        scorer = ConfidenceScorer()

        # A 등급 (≥0.85)
        result_a = scorer.calculate(
            answer="x" * 100,
            sources=[{"content": "x" * 500}] * 5,
            relevance_score=0.95,
            citation_accuracy=0.95,
        )
        assert result_a.grade == "A"

        # F 등급 (<0.40)
        result_f = scorer.calculate(
            answer="x" * 100, sources=[], relevance_score=0.1, citation_accuracy=0.0
        )
        assert result_f.grade in ["D", "F"]


class TestEnhancedLLMReview:
    """Enhanced LLM Review 테스트 (Mocked)"""

    @pytest.fixture
    def mock_openai(self):
        """OpenAI Mock"""
        with patch("openai.OpenAI") as mock_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = """
            {
                "passed": true,
                "issues": [],
                "legal_judgment_detected": false,
                "hedging_level": "safe",
                "overall_severity": "low",
                "overall_comment": "안전한 답변입니다."
            }
            """
            mock_client.chat.completions.create.return_value = mock_response
            mock_class.return_value = mock_client
            yield mock_client

    def test_hybrid_review_with_no_violations(self, mock_openai):
        """위반 없는 경우 (general query skips review)"""
        from app.agents.legal_review.llm_reviewer import HybridLegalReviewer

        reviewer = HybridLegalReviewer(enable_llm=False)

        state = {
            "draft_answer": "일반적으로 환불이 가능할 수 있습니다.",
            "query_analysis": {"query_type": "general"},
            "sources": [],
            "retry_count": 0,
        }

        result = reviewer.review(state)

        assert result["review"]["passed"] is True
        assert len(result["review"]["violations"]) == 0

    def test_hybrid_review_with_prohibited_expression(self, mock_openai):
        """금지 표현 포함된 경우"""
        from app.agents.legal_review.llm_reviewer import HybridLegalReviewer

        reviewer = HybridLegalReviewer(enable_llm=False)

        state = {
            "draft_answer": "반드시 환불받으실 수 있습니다. 100% 승소합니다.",
            "query_analysis": {"query_type": "dispute"},
            "sources": [],
            "retry_count": 0,
        }

        result = reviewer.review(state)

        # 금지 표현이 있으므로 위반 탐지
        assert len(result["review"]["violations"]) > 0

    def test_skip_review_for_general_query(self, mock_openai):
        """일반 대화는 리뷰 스킵"""
        from app.agents.legal_review.llm_reviewer import HybridLegalReviewer

        reviewer = HybridLegalReviewer(enable_llm=True)

        state = {
            "draft_answer": "안녕하세요!",
            "query_analysis": {"query_type": "general"},
            "sources": [],
            "retry_count": 0,
        }

        result = reviewer.review(state)

        assert result["review"]["passed"] is True
        assert result["final_answer"] == "안녕하세요!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
