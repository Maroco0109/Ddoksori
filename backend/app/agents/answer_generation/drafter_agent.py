"""AnswerDrafterAgent - 답변 초안 생성 에이전트. LLM: 30B (Kanana)"""

from typing import Dict, Any, List, ClassVar

from ..base import BaseAgent
from .agent import generation_node_v2


class AnswerDrafterAgent(BaseAgent):
    """답변 초안 생성 에이전트 - 검색 결과를 바탕으로 사용자 답변 초안 작성"""
    
    agent_name: ClassVar[str] = "answer_drafter"
    agent_description: ClassVar[str] = "검색된 정보를 종합하여 사용자 질문에 대한 답변 초안을 생성합니다."
    required_inputs: ClassVar[List[str]] = ["user_query"]
    provided_outputs: ClassVar[List[str]] = ["draft_answer", "has_sufficient_evidence", "claim_evidence_map"]
    
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)
        
        context = request.get("context", {})
        
        mock_state = {
            "user_query": context.get("user_query", ""),
            "query_analysis": context.get("query_analysis"),
            "retrieval": context.get("retrieval"),
            "mode": context.get("mode", "NEED_RAG"),
            "sources": context.get("sources", []),
        }
        
        try:
            import asyncio
            result = asyncio.run(generation_node_v2(mock_state))
            
            draft = result.get("draft_answer", "")
            has_evidence = result.get("has_sufficient_evidence", False)
            model_used = result.get("generation_model_used", "unknown")
            
            if not draft:
                return self.report_to_supervisor(
                    status="failure",
                    result={"draft_answer": "", "has_sufficient_evidence": False},
                    message="답변 생성 실패: 빈 답변"
                )
            
            return self.report_to_supervisor(
                status="success",
                result={
                    "draft_answer": draft,
                    "has_sufficient_evidence": has_evidence,
                    "claim_evidence_map": result.get("claim_evidence_map", []),
                    "clarifying_questions": result.get("clarifying_questions", []),
                    "is_restricted": result.get("is_restricted", False),
                    "model_used": model_used,
                },
                message=f"답변 생성 완료 (model: {model_used}, evidence: {has_evidence})"
            )
            
        except Exception as e:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message=f"답변 생성 오류: {str(e)}"
            )


answer_drafter_agent = AnswerDrafterAgent()

__all__ = ["AnswerDrafterAgent", "answer_drafter_agent"]
