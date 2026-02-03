"""
Context Builder Module

Converts retrieval results from supervisor state into template variables
for the markdown template system.
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# 한/영 필드명 매핑 (데이터 소스에 따라 필드명이 다를 수 있음)
FIELD_ALIASES = {
    "article": ["article", "조문번호"],
    "title": ["title", "조문제목"],
    "doc_title": ["doc_title", "title", "사건명"],
}

# Pre-compiled regex patterns for amount extraction
_MAN_WON_RE = re.compile(r"(\d+)\s*만\s*원")
_NUMBERS_RE = re.compile(r"\d+")


def _get_field(data: dict, field_name: str, default: str = "") -> str:
    """필드 별칭 체인을 통해 값을 가져옵니다."""
    for alias in FIELD_ALIASES.get(field_name, [field_name]):
        val = data.get(alias)
        if val:
            return val
    return default


class ContextBuilder:
    """Builds template context variables from retrieval state."""

    def build(self, state: Dict[str, Any]) -> Dict[str, str]:
        """
        Build template variables from supervisor state.

        Args:
            state: Supervisor state containing retrieval results and user info

        Returns:
            Dictionary of template variable names to formatted content
        """
        retrieval = state.get("retrieval", {}) or {}
        onboarding = state.get("onboarding", {}) or {}
        user_query = state.get("user_query", "") or ""

        logger.info("Building template context from retrieval state")

        context = {
            "user_query": user_query,
            "refined_user_case": onboarding.get("dispute_details", "정보 없음"),
            "target_category": onboarding.get("purchase_item", "알 수 없음"),
            "기관명": "한국소비자원",
            "law_data": self._build_law_data(retrieval.get("laws", [])),
            "criteria_data": self._build_criteria_data(retrieval.get("criteria", [])),
            "case_data": self._build_case_data(
                retrieval.get("disputes", []), retrieval.get("counsels", [])
            ),
        }

        # Sanitize values to prevent template variable injection
        for key in ("user_query", "refined_user_case", "target_category"):
            if key in context:
                context[key] = context[key].replace("{", "{{").replace("}", "}}")

        logger.debug(
            f"Built context with {len(context)} variables: "
            f"laws={len(retrieval.get('laws', []))}, "
            f"criteria={len(retrieval.get('criteria', []))}, "
            f"cases={len(retrieval.get('disputes', [])) + len(retrieval.get('counsels', []))}"
        )

        return context

    def _build_law_data(self, laws: List[Dict[str, Any]]) -> str:
        """
        Format law entries into template-ready text.

        Format: 『{law_name}』 제{article}조 ({title})
                내용: {content}

        Args:
            laws: List of law dictionaries from retrieval

        Returns:
            Formatted law data or "데이터 없음"
        """
        if not laws:
            return "데이터 없음"

        formatted_laws = []
        for law in laws:
            law_name = law.get("law_name", "정보 없음")
            content = law.get("content", "내용 없음")

            # Extract article number from multiple possible fields
            article = _get_field(law, "article")
            # Strip "제" and "조" prefixes/suffixes
            article_num = article.replace("제", "").replace("조", "").strip()
            if not article_num:
                article_num = "정보 없음"

            # Extract title from multiple possible fields
            title = _get_field(law, "title", "제목 없음")

            formatted_block = (
                f"『{law_name}』 제{article_num}조 ({title})\n내용: {content}"
            )
            formatted_laws.append(formatted_block)

        return "\n\n".join(formatted_laws)

    def _build_criteria_data(self, criteria: List[Dict[str, Any]]) -> str:
        """
        Format criteria entries into template-ready text.

        Args:
            criteria: List of criteria dictionaries from retrieval

        Returns:
            Formatted criteria data or "데이터 없음"
        """
        if not criteria:
            return "데이터 없음"

        formatted_criteria = []
        for criterion in criteria:
            source_label = criterion.get("source_label", "정보 없음")
            category = criterion.get("category", "")
            item = criterion.get("item", "")
            unit_text = criterion.get("unit_text", "")
            content = criterion.get("content", "내용 없음")

            # Build title from available fields
            title_parts = [p for p in [category, item, unit_text] if p]
            title = " - ".join(title_parts) if title_parts else "제목 없음"

            formatted_block = f"『{source_label}』 {title}\n내용: {content}"
            formatted_criteria.append(formatted_block)

        return "\n\n".join(formatted_criteria)

    def _build_case_data(
        self, disputes: List[Dict[str, Any]], counsels: List[Dict[str, Any]]
    ) -> str:
        """
        Format case/dispute entries into template-ready text.

        Args:
            disputes: List of dispute dictionaries from retrieval
            counsels: List of counsel dictionaries from retrieval

        Returns:
            Formatted case data or "데이터 없음"
        """
        all_cases = disputes + counsels
        if not all_cases:
            return "데이터 없음"

        formatted_cases = []
        for case in all_cases:
            # Try multiple possible title fields
            title = _get_field(case, "doc_title", "제목 없음")
            content = case.get("content", "내용 없음")

            # Include source organization if available
            source_org = case.get("source_org", "")
            if source_org:
                title = f"[{source_org}] {title}"

            formatted_block = f"『{title}』\n내용: {content}"
            formatted_cases.append(formatted_block)

        return "\n\n".join(formatted_cases)

    @staticmethod
    def extract_amount(text: str) -> int:
        """
        Extract monetary amount from text for template routing.

        Handles formats like:
        - "50만원" -> 500000
        - "500,000원" -> 500000
        - "1000" -> 1000

        Args:
            text: Text containing monetary amount

        Returns:
            Extracted amount as integer, 0 if no amount found
        """
        if not text:
            return 0

        # Remove commas for easier parsing
        text = text.replace(",", "")

        # Try to match "N만원" pattern first
        man_match = _MAN_WON_RE.search(text)
        if man_match:
            return int(man_match.group(1)) * 10000

        # Fallback: find all numbers and return the largest
        numbers = _NUMBERS_RE.findall(text)
        if numbers:
            return max([int(n) for n in numbers])

        return 0

    @staticmethod
    def extract_case_info(case: Dict[str, Any]) -> Dict[str, str]:
        """Extract standardized case info from a case dictionary.

        Used by both context_builder and agent.py to avoid code duplication.

        Args:
            case: Case dictionary with potentially varying field names

        Returns:
            Dictionary with standardized keys: title, content, source_org
        """
        title = _get_field(case, "doc_title", "제목 없음")
        content = case.get("content", "내용 없음")
        source_org = case.get("source_org", "")
        return {"title": title, "content": content, "source_org": source_org}
