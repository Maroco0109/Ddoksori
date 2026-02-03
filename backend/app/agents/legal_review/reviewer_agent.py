"""
LegalReviewerAgent - 법률 검토 에이전트 (Enhanced)

기능:
1. 금지 표현 탐지 (규칙 기반)
2. 인용 정확성 검증 (Hallucination 방지)
3. Query-Answer 관련성 검증
4. 법적 판단 탐지 (LLM 기반, 조건부)
5. Confidence Score 계산
"""

import logging
from typing import Any, ClassVar, Dict, List, Optional

from ..base import BaseAgent
from .agent import verify_citation_accuracy
from .llm_reviewer import get_reviewer
from .relevance_checker import get_relevance_checker

logger = logging.getLogger(__name__)


class LegalReviewerAgent(BaseAgent):
    """
    법률 검토 에이전트 - 생성된 답변의 안전성/신뢰성 최종 검증

    Enhanced Features:
    - Hallucination 탐지 (인용 정확성 검증)
    - Query-Answer 관련성 검증
    - 법적 판단 탐지 (LLM 2차 검증)
    - Confidence Score 계산
    """

    agent_name: ClassVar[str] = "legal_reviewer"
    agent_description: ClassVar[str] = (
        "생성된 답변이 법적 책임 소지가 있는지, 근거 없는 주장을 하는지 검증합니다. "
        "Hallucination 탐지, Query 관련성 검증, 법적 판단 탐지를 수행합니다."
    )
    required_inputs: ClassVar[List[str]] = ["draft_answer"]
    provided_outputs: ClassVar[List[str]] = [
        "review",
        "final_answer",
        "passed",
        "hallucination_check",
        "relevance_check",
        "confidence_score",
    ]

    def __init__(self):
        super().__init__()
        self._relevance_checker = None

    def _get_relevance_checker(self):
        """지연 초기화로 RelevanceChecker 로드"""
        if self._relevance_checker is None:
            try:
                self._relevance_checker = get_relevance_checker()
            except Exception as e:
                logger.warning(
                    f"[LegalReviewerAgent] RelevanceChecker init failed: {e}"
                )
        return self._relevance_checker

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(
                status="failure", result=None, message=error
            )

        context = request.get("context", {})

        draft_answer = context.get("draft_answer")
        if not draft_answer:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message="검토할 답변이 없습니다 (draft_answer 누락)",
            )

        # 상태 구성
        user_query = context.get("query", "") or context.get("user_query", "")
        sources = context.get("sources", [])

        mock_state = {
            "draft_answer": draft_answer,
            "query": user_query,
            "query_analysis": context.get("query_analysis"),
            "sources": sources,
            "retrieval": context.get("retrieval"),
            "retry_count": context.get("retry_count", 0),
            "chat_type": context.get("chat_type", "dispute"),
        }

        try:
            # 1. 하이브리드 리뷰 (규칙 + 조건부 LLM)
            reviewer = get_reviewer()
            result = reviewer.review(mock_state)

            review = result.get("review", {})
            passed = review.get("passed", False)
            violations = review.get("violations", [])
            final_answer = result.get("final_answer")

            # 2. 관련성 검증 (Query-Answer)
            relevance_check = self._check_relevance(user_query, draft_answer, sources)
            if relevance_check and not relevance_check.get("passed", True):
                violations.append(f"관련성 부족: {relevance_check.get('message', '')}")
                if relevance_check.get("query_answer_score", 1.0) < 0.3:
                    passed = False

            # 3. 인용 정확성 검증 (Hallucination)
            hallucination_check = self._check_hallucination(draft_answer, sources)
            if hallucination_check and not hallucination_check.get("passed", True):
                unverified = hallucination_check.get("unverified_refs", [])
                if unverified:
                    violations.append(
                        f"Hallucination 의심: {', '.join(unverified[:3])}"
                    )

            # 4. Confidence Score 계산
            confidence_score = self._calculate_confidence(
                relevance_check, hallucination_check, review
            )

            # 5. Enhanced Review 결과 구성
            enhanced_review = {
                **review,
                "hallucination_check": hallucination_check,
                "relevance_check": relevance_check,
                "confidence_score": confidence_score,
            }

            if passed:
                return self.report_to_supervisor(
                    status="success",
                    result={
                        "review": enhanced_review,
                        "final_answer": final_answer or draft_answer,
                        "passed": True,
                        "violations": violations,
                        "confidence_score": confidence_score,
                    },
                    message=f"검토 통과. 신뢰도: {confidence_score:.2f}",
                )

            if result.get("retry_count", 0) > mock_state["retry_count"]:
                return self.report_to_supervisor(
                    status="failure",
                    result={
                        "review": enhanced_review,
                        "passed": False,
                        "violations": violations,
                        "needs_retry": True,
                        "confidence_score": confidence_score,
                    },
                    message=f"검토 실패 - 재생성 필요. 위반: {', '.join(violations[:3])}",
                )

            filtered_answer = review.get("filtered_answer")
            return self.report_to_supervisor(
                status="success",
                result={
                    "review": enhanced_review,
                    "final_answer": final_answer or filtered_answer or draft_answer,
                    "passed": False,
                    "violations": violations,
                    "was_filtered": filtered_answer is not None,
                    "confidence_score": confidence_score,
                },
                message=f"조건부 통과 (신뢰도: {confidence_score:.2f})",
            )

        except Exception as e:
            logger.error(f"[LegalReviewerAgent] Error: {e}")
            return self.report_to_supervisor(
                status="failure", result=None, message=f"법률 검토 오류: {str(e)}"
            )

    def _check_relevance(
        self, query: str, answer: str, sources: List[Dict]
    ) -> Optional[Dict]:
        """Query-Answer 관련성 검증"""
        if not query or not answer:
            return None

        try:
            checker = self._get_relevance_checker()
            if not checker:
                return None

            # Query-Answer 관련성
            qa_result = checker.check_query_answer_relevance(query, answer)

            # 검색 결과 텍스트 추출
            source_texts = []
            for s in sources[:5]:
                text = s.get("content", "") or s.get("text", "")
                if text:
                    source_texts.append(text)

            # Answer-Source 관련성
            as_result = None
            if source_texts:
                as_result = checker.check_answer_source_relevance(answer, source_texts)

            return {
                "passed": qa_result.passed and (as_result is None or as_result.passed),
                "query_answer_score": qa_result.score,
                "answer_source_score": as_result.score if as_result else 0.0,
                "message": qa_result.message
                or (as_result.message if as_result else None),
            }

        except Exception as e:
            logger.warning(f"[LegalReviewerAgent] Relevance check failed: {e}")
            return None

    def _check_hallucination(self, answer: str, sources: List[Dict]) -> Optional[Dict]:
        """인용 정확성 검증 (Hallucination 탐지)"""
        if not answer:
            return None

        try:
            result = verify_citation_accuracy(answer, sources)
            return {
                "passed": result.passed,
                "cited_refs": result.cited_refs,
                "verified_refs": result.verified_refs,
                "unverified_refs": result.unverified_refs,
                "accuracy": result.accuracy,
            }
        except Exception as e:
            logger.warning(f"[LegalReviewerAgent] Hallucination check failed: {e}")
            return None

    def _calculate_confidence(
        self,
        relevance_check: Optional[Dict],
        hallucination_check: Optional[Dict],
        review: Dict,
    ) -> float:
        """
        종합 신뢰도 점수 계산 (0.0 ~ 1.0)

        가중치:
        - 관련성 점수: 30%
        - 인용 정확도: 30%
        - 규칙 기반 통과: 40%
        """
        score = 0.0

        # 규칙 기반 통과 (40%)
        if review.get("passed", False):
            score += 0.4
        elif review.get("filtered_answer"):
            score += 0.2  # 필터링된 경우 부분 점수

        # 관련성 점수 (30%)
        if relevance_check:
            qa_score = relevance_check.get("query_answer_score", 0.5)
            score += qa_score * 0.3

        # 인용 정확도 (30%)
        if hallucination_check:
            accuracy = hallucination_check.get("accuracy", 0.5)
            score += accuracy * 0.3

        return min(1.0, max(0.0, score))


legal_reviewer_agent = LegalReviewerAgent()

__all__ = ["LegalReviewerAgent", "legal_reviewer_agent"]
