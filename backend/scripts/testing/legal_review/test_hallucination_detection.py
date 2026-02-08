"""
Legal Review - Hallucination Detection & Quality Tests

Tests for:
- Citation accuracy verification (verify_citation_accuracy)
- Prohibited expression detection (_check_prohibited_expressions)
- Citation presence checking (_check_citation_presence)
- Terminology checker (TerminologyChecker)
- HybridLegalReviewer rule-based review
"""

import pytest

from app.agents.legal_review.agent import (
    _check_citation_presence,
    _check_prohibited_expressions,
    _extract_law_references,
    verify_citation_accuracy,
)
from app.agents.legal_review.terminology_checker import TerminologyChecker


@pytest.mark.unit
class TestCitationAccuracyVerification:
    """Test verify_citation_accuracy for hallucination detection."""

    def test_review_with_valid_citations(self):
        """Answer referencing existing sources passes verification."""
        answer = "전자상거래법 제17조에 따라 7일 이내 청약철회가 가능합니다."
        sources = [
            {
                "content": "전자상거래법 제17조(청약철회등) 통신판매업자와 재화등의 구매에 관한 계약을 체결한 소비자는 7일 이내 청약철회 가능."
            }
        ]

        result = verify_citation_accuracy(answer, sources)

        assert result.passed is True
        assert len(result.verified_refs) > 0
        assert len(result.unverified_refs) == 0

    def test_review_catches_fabricated_law(self):
        """Answer mentioning non-existent law article flagged as unverified."""
        answer = "제999조에 의하면 환불이 가능합니다. 제17조도 참고하세요."
        sources = [{"content": "제17조(청약철회등) 7일 이내 청약철회 가능."}]

        result = verify_citation_accuracy(answer, sources, strict_mode=True)

        # 제999조 is not in sources, so should be unverified
        assert any("999" in ref for ref in result.unverified_refs)
        # In strict mode, unverified refs mean failure
        assert result.passed is False

    def test_review_empty_answer(self):
        """Empty response handled gracefully."""
        result = verify_citation_accuracy("", [])

        assert result.passed is True
        assert result.cited_refs == []
        assert result.accuracy == 1.0

    def test_review_no_law_refs_in_answer(self):
        """Answer with no law references passes (no verification needed)."""
        answer = "소비자 상담은 한국소비자원에 문의해 주세요."
        sources = [{"content": "제17조 청약철회"}]

        result = verify_citation_accuracy(answer, sources)

        assert result.passed is True
        assert result.cited_refs == []

    def test_lenient_mode_partial_verification(self):
        """In lenient mode (default), 50%+ verified refs pass."""
        answer = "제17조와 제18조를 참고하세요."
        sources = [{"content": "제17조(청약철회등) 7일 이내."}]
        # 제17조 is verified, 제18조 is not -> 50% accuracy
        result = verify_citation_accuracy(answer, sources, strict_mode=False)

        assert result.accuracy >= 0.5
        assert result.passed is True

    def test_strict_mode_all_must_verify(self):
        """In strict mode, all cited refs must be verified."""
        answer = "제17조와 제99조를 참고하세요."
        sources = [{"content": "제17조(청약철회등) 7일 이내."}]

        result = verify_citation_accuracy(answer, sources, strict_mode=True)

        # 제99조 is not in sources
        assert result.passed is False
        assert len(result.unverified_refs) > 0


@pytest.mark.unit
class TestProhibitedExpressions:
    """Test prohibited expression detection."""

    def test_review_with_prohibited_expression(self):
        """Prohibited legal terms detected."""
        answer = "반드시 환불해야 합니다. 이것은 위법입니다."
        violations = _check_prohibited_expressions(answer)

        assert len(violations) > 0
        # Should detect "반드시 ~합니다" and "위법입니다"
        descriptions = [v[0] for v in violations]
        assert any("반드시" in d for d in descriptions)

    def test_safe_expressions_pass(self):
        """Safe hedging expressions do not trigger violations."""
        answer = "환불이 가능할 수 있습니다. 관련 법령에 따르면 청약철회가 규정되어 있습니다."
        violations = _check_prohibited_expressions(answer)

        assert len(violations) == 0

    def test_expert_impersonation_detected(self):
        """Expert impersonation phrases are flagged."""
        answer = "법률 전문가로서 말씀드리면 이 경우 환불이 가능합니다."
        violations = _check_prohibited_expressions(answer)

        assert len(violations) > 0
        descriptions = [v[0] for v in violations]
        assert any("전문가" in d for d in descriptions)

    def test_definitive_prediction_detected(self):
        """Definitive prediction expressions are flagged."""
        answer = "확실히 배상받을 수 있습니다."
        violations = _check_prohibited_expressions(answer)

        assert len(violations) > 0


@pytest.mark.unit
class TestCitationPresence:
    """Test citation presence checking."""

    def test_citation_with_source_marker(self):
        """Answer with [출처: ...] passes citation check."""
        answer = "환불이 가능합니다. [출처: 전자상거래법 제17조]"
        assert _check_citation_presence(answer, has_sources=True) is True

    def test_citation_with_law_name(self):
        """Answer mentioning law names passes citation check."""
        answer = "전자상거래법에 따라 7일 이내 환불이 가능합니다."
        assert _check_citation_presence(answer, has_sources=True) is True

    def test_no_citation_fails_when_sources_exist(self):
        """Answer without any citation fails when sources exist."""
        answer = "환불이 가능합니다. 상담을 받아보세요."
        assert _check_citation_presence(answer, has_sources=True) is False

    def test_no_citation_passes_when_no_sources(self):
        """No citation needed when no sources were retrieved."""
        answer = "환불이 가능합니다."
        assert _check_citation_presence(answer, has_sources=False) is True


@pytest.mark.unit
class TestTerminologyChecker:
    """Test TerminologyChecker for glossary compliance."""

    def test_terminology_with_correct_annotation(self):
        """Correctly annotated terms pass check."""
        checker = TerminologyChecker()
        response = "해제(계약을 처음부터 없었던 일로 하는 것)를 요청할 수 있습니다."
        violations = checker._check_terminology_compliance(response)

        assert len(violations) == 0

    def test_terminology_missing_annotation(self):
        """Term without annotation triggers violation."""
        checker = TerminologyChecker()
        response = "계약 해제를 요청할 수 있습니다."
        violations = checker._check_terminology_compliance(response)

        assert len(violations) > 0
        assert any(v["type"] == "terminology_missing" for v in violations)

    def test_forbidden_header_detected(self):
        """Forbidden structural headers are flagged."""
        checker = TerminologyChecker()
        response = "[공감] 많이 불편하셨겠습니다. [법적 근거] 전자상거래법에 따르면..."
        violations = checker._check_forbidden_headers(response)

        assert len(violations) >= 2

    def test_bold_markdown_detected(self):
        """Bold markdown ** is flagged."""
        checker = TerminologyChecker()
        response = "**중요** 환불 가능합니다."
        violations = checker._check_bold_markdown(response)

        assert len(violations) == 1
        assert violations[0]["type"] == "format_violation"

    def test_template_variable_detected(self):
        """Unsubstituted template variables are flagged."""
        checker = TerminologyChecker()
        response = "안녕하세요, {user_name}님. 환불 가능합니다."
        violations = checker._check_template_variables(response)

        assert len(violations) == 1
        assert violations[0]["type"] == "template_variable"

    def test_data_isolation_law_section_without_data(self):
        """Law section without law data triggers violation."""
        checker = TerminologyChecker()
        response = "『소비자보호법 제17조』에 따라 환불이 가능합니다."
        input_data = {
            "retrieval": {"laws": [], "criteria": [], "disputes": [], "counsels": []}
        }
        violations = checker._check_data_isolation(response, input_data)

        assert len(violations) > 0
        assert any(v["type"] == "data_isolation" for v in violations)

    def test_data_isolation_passes_with_data(self):
        """Law section with law data present passes."""
        checker = TerminologyChecker()
        response = "『소비자보호법 제17조』에 따라 환불이 가능합니다."
        input_data = {
            "retrieval": {
                "laws": [{"law_name": "소비자보호법", "full_path": "제17조"}],
                "criteria": [],
                "disputes": [],
                "counsels": [],
            }
        }
        violations = checker._check_data_isolation(response, input_data)

        assert len(violations) == 0

    def test_full_check_combines_all(self):
        """Full check() method combines all sub-checks."""
        checker = TerminologyChecker()
        response = "**중요** [공감] 해제를 하세요. {template_var}"
        input_data = {
            "retrieval": {"laws": [], "criteria": [], "disputes": [], "counsels": []}
        }

        violations = checker.check(response, input_data)

        violation_types = {v["type"] for v in violations}
        assert "format_violation" in violation_types
        assert "forbidden_header" in violation_types
        assert "terminology_missing" in violation_types
        assert "template_variable" in violation_types


@pytest.mark.unit
class TestLawReferenceExtraction:
    """Test law reference extraction from text."""

    def test_extract_article_number(self):
        """Extract article numbers like 제17조."""
        refs = _extract_law_references("제17조에 따라 환불이 가능합니다.")
        assert any("17" in ref for ref in refs)

    def test_extract_law_name(self):
        """Extract law names like 전자상거래법."""
        refs = _extract_law_references("전자상거래법에 의해 보호됩니다.")
        assert len(refs) > 0

    def test_extract_no_references(self):
        """No references in plain text."""
        refs = _extract_law_references("안녕하세요, 도움이 필요하시면 말씀해주세요.")
        assert len(refs) == 0
