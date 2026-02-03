"""
Terminology and data isolation checker for legal review.

Validates that generated answers comply with the terminology glossary
and data isolation rules defined in the prompt templates.
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class TerminologyChecker:
    """Checks terminology glossary compliance and data isolation."""

    # 7 mandatory terminology pairs
    TERMINOLOGY_DICT = {
        "해제": "계약을 처음부터 없었던 일로 하는 것",
        "해지": "앞으로 계약을 그만두는 것",
        "위약금": "계약 취소에 따른 손해 배상금",
        "환급": "돈을 돌려받는 것",
        "공제": "일정 금액을 뺀 나머지",
        "청약철회": "주문을 취소하는 것",
        "항변권": "결제 중지 요청권",
    }

    # Forbidden structural headers
    FORBIDDEN_HEADERS = [
        "[공감]",
        "[가이드]",
        "[출처]",
        "[돌파 논리]",
        "[사건 요약]",
        "[상황 정리]",
        "[법적 근거]",
        "[근거 안내]",
        "[절차 안내]",
        "[법률]",
        "[해결기준]",
        "[유사사례]",
    ]

    def check(self, response: str, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Run all terminology and format checks.

        Args:
            response: Generated answer text
            input_data: State dict with retrieval context for data isolation check

        Returns:
            List of violation dicts with keys: type, description, severity, suggestion
        """
        violations = []
        violations.extend(self._check_terminology_compliance(response))
        violations.extend(self._check_forbidden_headers(response))
        violations.extend(self._check_bold_markdown(response))
        violations.extend(self._check_template_variables(response))
        violations.extend(self._check_data_isolation(response, input_data))
        return violations

    def _check_terminology_compliance(self, response: str) -> List[Dict[str, Any]]:
        """Check that legal terms have correct glossary annotations."""
        violations = []

        for term, expected_meaning in self.TERMINOLOGY_DICT.items():
            # Find all occurrences of the term
            # Skip if term doesn't appear at all
            if term not in response:
                continue

            # Check if the term has a parenthetical annotation nearby
            # Pattern: term followed by ( ... ) within reasonable distance
            # Allow flexible whitespace and minor particle differences
            pattern = rf"{re.escape(term)}\s*\(([^)]+)\)"
            matches = re.findall(pattern, response)

            if not matches:
                # Term appears but has no annotation at all
                # Check if the term appears ONLY inside an existing annotation
                # e.g. "해제(계약을 처음부터 없었던 일로 하는 것)" - "해제" is fine here
                # But standalone "해제" without annotation is a violation

                # Find standalone occurrences (not inside parentheses)
                standalone_pattern = rf"(?<!\()(?<!\（){re.escape(term)}(?!\s*[\(（])"
                standalone_matches = re.findall(standalone_pattern, response)

                # Also check if there's at least one annotated occurrence
                annotated_pattern = rf"{re.escape(term)}\s*[\(（]"
                has_annotation = bool(re.search(annotated_pattern, response))

                if standalone_matches and not has_annotation:
                    violations.append(
                        {
                            "type": "terminology_missing",
                            "description": f"용어 '{term}'에 대한 괄호 풀이가 누락되었습니다. "
                            f"올바른 형식: {term}({expected_meaning})",
                            "severity": "critical",
                            "suggestion": f"{term}({expected_meaning})",
                        }
                    )
            else:
                # Check if the meaning matches (allow minor particle differences)
                for match in matches:
                    match_clean = match.strip()
                    # Core meaning check: key words must be present
                    # Extract key content words from expected meaning
                    if not self._meanings_match(match_clean, expected_meaning):
                        violations.append(
                            {
                                "type": "terminology_mismatch",
                                "description": f"용어 '{term}'의 풀이가 사전과 다릅니다. "
                                f"현재: {term}({match_clean}), "
                                f"올바른 형식: {term}({expected_meaning})",
                                "severity": "critical",
                                "suggestion": f"{term}({expected_meaning})",
                            }
                        )

        return violations

    def _meanings_match(self, actual: str, expected: str) -> bool:
        """Check if two meanings match (allowing minor differences like particles)."""

        # Remove common particles and whitespace for comparison
        def normalize(text: str) -> str:
            # Remove particles and whitespace
            text = re.sub(r"\s+", "", text)
            # Remove common particles
            for particle in ["은", "는", "이", "가", "을", "를", "의", "에", "로"]:
                text = text.replace(particle, "")
            return text

        actual_norm = normalize(actual)
        expected_norm = normalize(expected)

        # Check if core content matches (80% character overlap)
        if actual_norm == expected_norm:
            return True

        # Check key words overlap
        actual_chars = set(actual_norm)
        expected_chars = set(expected_norm)
        overlap = len(actual_chars & expected_chars)
        total = len(expected_chars)

        if total > 0 and overlap / total >= 0.7:
            return True

        return False

    def _check_forbidden_headers(self, response: str) -> List[Dict[str, Any]]:
        """Check for forbidden structural headers."""
        violations = []
        for header in self.FORBIDDEN_HEADERS:
            if header in response:
                violations.append(
                    {
                        "type": "forbidden_header",
                        "description": f"금지된 구조적 헤더 '{header}'가 노출되었습니다.",
                        "severity": "critical",
                        "suggestion": f"'{header}' 헤더를 제거하고 자연스러운 문장으로 전환하세요.",
                    }
                )
        return violations

    def _check_bold_markdown(self, response: str) -> List[Dict[str, Any]]:
        """Check for forbidden bold markdown."""
        violations = []
        if "**" in response:
            violations.append(
                {
                    "type": "format_violation",
                    "description": "마크다운 볼드체(**)가 포함되어 있습니다.",
                    "severity": "critical",
                    "suggestion": "볼드체를 제거하고 『』 기호나 줄바꿈으로 강조하세요.",
                }
            )
        return violations

    def _check_template_variables(self, response: str) -> List[Dict[str, Any]]:
        """Check for unsubstituted template variables."""
        violations = []
        # Look for {variable_name} patterns that should have been replaced
        unsubstituted = re.findall(r"\{(\w+)\}", response)
        if unsubstituted:
            violations.append(
                {
                    "type": "template_variable",
                    "description": f"치환되지 않은 템플릿 변수가 발견되었습니다: {', '.join(unsubstituted)}",
                    "severity": "critical",
                    "suggestion": "템플릿 변수를 올바른 데이터로 치환하세요.",
                }
            )
        return violations

    def _check_data_isolation(
        self, response: str, input_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Check data isolation: if data is "데이터 없음", the section should not appear.

        Rules:
        - If law_data is "데이터 없음", no 『법률...』 section should exist
        - If criteria_data is "데이터 없음", no 『소비자분쟁해결기준』 section should exist
        - If case_data is "데이터 없음", no case-related section should exist
        """
        violations = []
        retrieval = input_data.get("retrieval", {})

        # Check law data isolation
        laws = retrieval.get("laws", [])
        if not laws:
            # Look for law-related headers in response
            law_indicators = [
                "『소비자보호법",
                "『전자상거래",
                "『약관규제",
                "『할부거래",
                "『민법",
                "『상법",
            ]
            for indicator in law_indicators:
                if indicator in response:
                    violations.append(
                        {
                            "type": "data_isolation",
                            "description": f"법률 데이터가 없는데 법률 관련 섹션({indicator}...)이 생성되었습니다.",
                            "severity": "warning",
                            "suggestion": "데이터가 없는 섹션은 제목을 포함하여 완전히 생략하세요.",
                        }
                    )
                    break

        # Check criteria data isolation
        criteria = retrieval.get("criteria", [])
        if not criteria:
            if "『소비자분쟁해결기준』" in response:
                violations.append(
                    {
                        "type": "data_isolation",
                        "description": "해결기준 데이터가 없는데 『소비자분쟁해결기준』 섹션이 생성되었습니다.",
                        "severity": "warning",
                        "suggestion": "데이터가 없는 섹션은 제목을 포함하여 완전히 생략하세요.",
                    }
                )

        # Check case data isolation
        disputes = retrieval.get("disputes", [])
        counsels = retrieval.get("counsels", [])
        if not disputes and not counsels:
            # Generic case indicators
            case_indicators = ["유사 사례", "조정사례", "상담사례"]
            for indicator in case_indicators:
                if indicator in response:
                    violations.append(
                        {
                            "type": "data_isolation",
                            "description": f"사례 데이터가 없는데 사례 관련 내용('{indicator}')이 생성되었습니다.",
                            "severity": "warning",
                            "suggestion": "데이터가 없는 섹션은 완전히 생략하세요.",
                        }
                    )
                    break

        return violations
