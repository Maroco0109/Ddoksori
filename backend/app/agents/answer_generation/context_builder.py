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
        query_analysis = state.get("query_analysis", {}) or {}
        # Phase 2-16: 대화 히스토리 추가
        conversation_history = state.get("conversation_history", []) or []

        logger.info("Building template context from retrieval state")

        # 분쟁 사유 (단순변심 vs 하자) - query_analysis에서 추출
        dispute_reason = query_analysis.get("dispute_reason", "unknown")
        # 한글 변환
        dispute_reason_kr = {
            "simple_change_of_mind": "단순변심 (제품 하자 없음, 디자인/색상 불만족 등)",
            "defect": "제품 하자 (고장, 불량, 결함 등)",
            "unknown": "분쟁 사유 미확인",
        }.get(dispute_reason, "분쟁 사유 미확인")

        # Phase 2-16: 대화 히스토리를 텍스트로 변환 (최근 3턴)
        conversation_history_text = self._build_conversation_history_text(
            conversation_history, max_turns=3
        )

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
            # 분쟁 사유 (유사 사례 필터링용)
            "dispute_reason": dispute_reason_kr,
            # Phase 2-16: 대화 히스토리
            "conversation_history": conversation_history_text,
        }

        # Sanitize values to prevent template variable injection
        for key in ("user_query", "refined_user_case", "target_category"):
            if key in context:
                context[key] = context[key].replace("{", "{{").replace("}", "}}")

        logger.debug(
            f"Built context with {len(context)} variables: "
            f"laws={len(retrieval.get('laws', []))}, "
            f"criteria={len(retrieval.get('criteria', []))}, "
            f"cases={len(retrieval.get('disputes', [])) + len(retrieval.get('counsels', []))}, "
            f"dispute_reason={dispute_reason}"
        )

        return context

    def _build_conversation_history_text(
        self, history: List[Dict[str, Any]], max_turns: int = 3
    ) -> str:
        """
        Phase 2-16: 대화 히스토리를 텍스트로 변환 (후속 질문 컨텍스트)

        Args:
            history: 대화 히스토리 리스트 (각 항목: {'role': str, 'content': str})
            max_turns: 포함할 최대 턴 수

        Returns:
            포맷팅된 대화 히스토리 텍스트 (비어있으면 빈 문자열)
        """
        if not history:
            return ""

        recent = history[-max_turns:] if len(history) > max_turns else history
        if not recent:
            return ""

        lines = ["[이전 대화]"]
        for turn in recent:
            if isinstance(turn, dict):
                role = turn.get("role", "user")
                content = turn.get("content", "")[:200]  # 최대 200자로 제한
            else:
                continue
            prefix = "사용자" if role == "user" else "AI"
            lines.append(f"{prefix}: {content}")
        lines.append("")
        return "\n".join(lines)

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
            # MAS agents put law_name in metadata, legacy format has it at top level
            metadata = law.get("metadata") or {}
            law_name = (
                law.get("law_name")
                or metadata.get("law_name")
                or law.get("doc_title")
                or "정보 없음"
            )
            content = law.get("content", "내용 없음")

            # Extract article number from multiple possible fields (including metadata)
            article = (
                _get_field(law, "article")
                or metadata.get("article")
                or metadata.get("조문번호")
                or ""
            )
            # Strip "제" and "조" prefixes/suffixes
            article_num = article.replace("제", "").replace("조", "").strip()
            if not article_num:
                article_num = "정보 없음"

            # Extract title from multiple possible fields (including metadata)
            title = (
                _get_field(law, "title")
                or metadata.get("title")
                or metadata.get("조문제목")
                or "제목 없음"
            )

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
            # MAS agents put fields in metadata, legacy format has them at top level
            metadata = criterion.get("metadata") or {}
            source_label = (
                criterion.get("source_label")
                or metadata.get("source_label")
                or criterion.get("doc_title")
                or "소비자분쟁해결기준"
            )
            category = (
                criterion.get("category")
                or metadata.get("category")
                or metadata.get("품목분류")
                or ""
            )
            item = criterion.get("item") or metadata.get("item") or ""
            unit_text = criterion.get("unit_text") or metadata.get("unit_text") or ""
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

            # Include URL or source reference for citations
            url = case.get("url", "")
            doc_id = case.get("doc_id", "")
            decision_date = case.get("decision_date", "")
            source_file = case.get("source_file", "")
            printed_page = case.get("printed_page")

            # Build source reference
            source_ref_parts = []
            if url:
                source_ref_parts.append(f"URL: {url}")
            if source_file:
                page_info = f" (p.{printed_page})" if printed_page else ""
                source_ref_parts.append(f"PDF: {source_file}{page_info}")
            if doc_id and not url and not source_file:
                source_ref_parts.append(f"문서ID: {doc_id}")
            if decision_date:
                source_ref_parts.append(f"결정일: {decision_date}")

            source_ref = " | ".join(source_ref_parts) if source_ref_parts else ""

            formatted_block = f"『{title}』\n내용: {content}"
            if source_ref:
                formatted_block += f"\n출처정보: {source_ref}"
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
