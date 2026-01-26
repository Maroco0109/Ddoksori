"""LegalReviewerAgent - 법률 검토 에이전트. LLM: 32B (EXAONE)"""

from typing import Dict, Any, List, ClassVar

from ..base import BaseAgent
from .agent import review_node


class LegalReviewerAgent(BaseAgent):
    """법률 검토 에이전트 - 생성된 답변의 안전성/신뢰성 최종 검증"""
    
    agent_name: ClassVar[str] = "legal_reviewer"
    agent_description: ClassVar[str] = "생성된 답변이 법적 책임 소지가 있는지, 근거 없는 주장을 하는지 검증합니다."
    required_inputs: ClassVar[List[str]] = ["draft_answer"]
    provided_outputs: ClassVar[List[str]] = ["review", "final_answer", "passed"]
    
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)
        
        context = request.get("context", {})
        
        draft_answer = context.get("draft_answer")
        if not draft_answer:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message="검토할 답변이 없습니다 (draft_answer 누락)"
            )
        
        mock_state = {
            "draft_answer": draft_answer,
            "query_analysis": context.get("query_analysis"),
            "sources": context.get("sources", []),
            "retrieval": context.get("retrieval"),
            "retry_count": context.get("retry_count", 0),
        }
        
        try:
            result = review_node(mock_state)
            
            review = result.get("review", {})
            passed = review.get("passed", False)
            violations = review.get("violations", [])
            final_answer = result.get("final_answer")
            
            if passed:
                return self.report_to_supervisor(
                    status="success",
                    result={
                        "review": review,
                        "final_answer": final_answer or draft_answer,
                        "passed": True,
                        "violations": violations,
                    },
                    message="검토 통과. 답변 확정."
                )
            
            if result.get("retry_count", 0) > mock_state["retry_count"]:
                return self.report_to_supervisor(
                    status="failure",
                    result={
                        "review": review,
                        "passed": False,
                        "violations": violations,
                        "needs_retry": True,
                    },
                    message=f"검토 실패 - 재생성 필요. 위반: {', '.join(violations[:3])}"
                )
            
            filtered_answer = review.get("filtered_answer")
            return self.report_to_supervisor(
                status="success",
                result={
                    "review": review,
                    "final_answer": final_answer or filtered_answer or draft_answer,
                    "passed": False,
                    "violations": violations,
                    "was_filtered": filtered_answer is not None,
                },
                message=f"조건부 통과 (필터링 적용: {filtered_answer is not None})"
            )
            
        except Exception as e:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message=f"법률 검토 오류: {str(e)}"
            )


legal_reviewer_agent = LegalReviewerAgent()

__all__ = ["LegalReviewerAgent", "legal_reviewer_agent"]
