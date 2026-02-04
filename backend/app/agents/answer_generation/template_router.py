"""
Template Router Module

Selects the optimal prompt template based on query analysis, retrieval results,
and hard routing rules.
"""

import logging
from typing import Dict

from .context_builder import ContextBuilder
from .routing_config import (
    get_criminal_keywords,
    get_high_amount_threshold,
    get_intl_keywords,
)

logger = logging.getLogger(__name__)

# Phase Constants
PHASE_1 = "solution"
PHASE_2 = "action"
PHASE_3 = "execution"


class TemplateRouter:
    """Routes queries to appropriate prompt templates based on analysis and rules."""

    @staticmethod
    def select_template(state: Dict) -> str:
        """
        Select optimal template based on strict routing rules.

        Routing order (first match wins):
        1. chat_type != "dispute" → "reject"
        2. Hard routing checks:
           a. amount > 5,000,000 → "fallback"
           b. criminal keywords → "fallback"
           c. international keywords → "fallback"
        3. needs_clarification → "inquiry"
        4. No retrieval results → "fallback"
        5. Phase-based routing (solution/action/execution)

        Args:
            state: State dictionary containing user query, analysis, and retrieval results

        Returns:
            Template name: "solution", "action", "execution", "inquiry", "fallback", "reject"
        """
        user_query = state.get("user_query", "")
        chat_type = state.get("chat_type", "")
        query_analysis = state.get("query_analysis", {})
        query_type = query_analysis.get("query_type", "") # 분석된 쿼리 타입 가져오기
        retrieval = state.get("retrieval", {})
        onboarding = state.get("onboarding") or {}

        logger.info(f"Routing template for query: {user_query[:50]}...")

        # 수정된 Rule 1: 무조건적인 거절 대신 유형별 분기
        # 1-1. 시스템/기능 문의나 일반 인사는 'inquiry' 템플릿으로 보내서 
        #      똑소리의 페르소나가 담긴 안내와 역질문이 나가도록 유도합니다.
        if query_type in ["system_meta", "general"]:
            logger.info(f"Routing to inquiry for persona response: query_type={query_type}")
            return "inquiry"

        # 1-2. 부적절한 언어나 정말 관련 없는 내용은 기존대로 reject 처리
        if chat_type == "INAPPROPRIATE" or chat_type == "IRRELEVANT":
            logger.info(f"Rejecting: chat_type={chat_type}")
            return "reject"

        # 1-3. 그 외 분쟁 상담이 아닌 경우의 기본값 처리
        # 'dispute' 타입을 리스트에 추가하여 상담 시작 시 거절되는 현상을 방지합니다.
        if chat_type != "dispute" and query_type not in ["dispute", "law", "criteria", "procedure"]:
            logger.info(f"Fallback to reject for unknown chat_type: {chat_type}, query_type: {query_type}")
            return "reject"

        # Rule 2a: High amount check
        amount_text = onboarding.get("purchase_amount", "") + " " + user_query
        amount = ContextBuilder.extract_amount(amount_text)

        if amount and amount > get_high_amount_threshold():
            logger.warning(
                f"Fallback: High amount detected ({amount:,}원 > {get_high_amount_threshold():,}원)"
            )
            return "fallback"

        # Rule 2b: Criminal keywords check
        if TemplateRouter._contains_criminal_keywords(user_query):
            logger.warning("Fallback: Criminal keywords detected in query")
            return "fallback"

        # Rule 2c: International keywords check
        if TemplateRouter._contains_international_keywords(user_query):
            logger.warning("Fallback: International transaction keywords detected")
            return "fallback"

        # Rule 3: Needs clarification
        if query_analysis.get("needs_clarification", False):
            logger.info("Template selected: inquiry (needs_clarification=True)")
            return "inquiry"

        # Rule 4: No retrieval results
        if not TemplateRouter._has_retrieval_results(retrieval):
            logger.warning("Fallback: No retrieval results available")
            return "fallback"

        # Rule 5: Phase-based routing
        template = TemplateRouter._route_by_phase(state)
        logger.info(f"Template selected: {template} (phase-based routing)")

        return template

    @staticmethod
    def get_fallback_reason(state: Dict) -> str:
        """
        Get Korean reason string for fallback cases.

        Args:
            state: State dictionary

        Returns:
            Korean reason string describing why fallback was triggered
        """
        user_query = state.get("user_query", "")
        onboarding = state.get("onboarding") or {}

        # Check high amount
        amount_text = onboarding.get("purchase_amount", "") + " " + user_query
        amount = ContextBuilder.extract_amount(amount_text)

        if amount and amount > get_high_amount_threshold():
            return f"피해 금액({amount:,}원) 고액 사건"

        # Check criminal keywords
        if TemplateRouter._contains_criminal_keywords(user_query):
            return "형사 사건(사기 등) 정황"

        # Check international keywords
        if TemplateRouter._contains_international_keywords(user_query):
            return "해외/국제 거래 사안"

        # Default
        return "상담 데이터 부족"

    @staticmethod
    def _contains_criminal_keywords(text: str) -> bool:
        """Check if text contains criminal-related keywords."""
        return any(keyword in text for keyword in get_criminal_keywords())

    @staticmethod
    def _contains_international_keywords(text: str) -> bool:
        """Check if text contains international transaction keywords."""
        return any(keyword in text for keyword in get_intl_keywords())

    @staticmethod
    def _has_retrieval_results(retrieval: Dict) -> bool:
        """
        Check if retrieval results contain any data.

        Args:
            retrieval: Retrieval results dictionary

        Returns:
            True if any retrieval category has results
        """
        if not retrieval:
            return False

        categories = ["disputes", "laws", "criteria", "counsels"]
        for category in categories:
            if retrieval.get(category):
                return True

        return False

    @staticmethod
    def _route_by_phase(state: Dict) -> str:
        """
        Route to template based on conversation phase.

        Phase mapping:
        - PHASE_1 (initial, providing_case_summary) → "solution"
        - PHASE_2 (providing_law_detail) → "action"
        - PHASE_3 (providing_procedure) → "execution"

        Args:
            state: State dictionary

        Returns:
            Template name based on phase
        """
        phase = TemplateRouter._map_phase(state)

        if phase == PHASE_3:
            return "execution"
        elif phase == PHASE_2:
            return "action"
        else:
            return "solution"

    @staticmethod
    def _map_phase(state: Dict) -> str:
        """
        Map conversation_phase to normalized phase constant.

        Args:
            state: State dictionary with optional conversation_phase

        Returns:
            One of: PHASE_1, PHASE_2, PHASE_3
        """
        conversation_phase = state.get("conversation_phase", "").lower()

        # PHASE_3: Procedure details
        if conversation_phase in ["providing_procedure"]:
            return PHASE_3

        # PHASE_2: Law details
        if conversation_phase in ["providing_law_detail"]:
            return PHASE_2

        # PHASE_1: Initial/case summary (default)
        # Includes: "initial", "providing_case_summary", or unknown phases
        return PHASE_1
