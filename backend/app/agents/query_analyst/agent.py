"""
QueryAnalystAgent - MAS Supervisor 아키텍처 질의 분석 에이전트

기존 query_analysis_node 로직을 BaseAgent 인터페이스로 래핑.
LLM: 7B (A.X Light), 호출빈도: 1회/요청
"""

from typing import Dict, Any, List, ClassVar

from ..base import BaseAgent
from ..query_analysis.agent import (
    _normalize_query,
    _classify_query_type,
    _extract_keywords,
    _determine_agency_hint,
    _extract_info_from_message,
    _expand_query_by_type,
    _generate_search_queries,
    _check_missing_onboarding_fields,
    _get_missing_fields_description,
    _classify_mode,
    DISPUTE_INTENT_KEYWORDS,
)


class QueryAnalystAgent(BaseAgent):
    """사용자 질문을 분석하여 의도, 엔티티, 쿼리 유형을 파악하는 에이전트"""
    
    agent_name: ClassVar[str] = "query_analyst"
    agent_description: ClassVar[str] = "사용자 질문을 분석하여 의도, 엔티티, 쿼리 유형을 파악합니다."
    required_inputs: ClassVar[List[str]] = ["user_query"]
    provided_outputs: ClassVar[List[str]] = [
        "query_type", "keywords", "intent", "entities", "mode",
        "needs_clarification", "rewritten_query", "search_queries",
    ]
    
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)
        
        context = request.get("context", {})
        user_query = context.get("user_query", "")
        chat_type = context.get("chat_type", "general")
        onboarding = context.get("onboarding")
        
        try:
            analysis_result = self._analyze_query(user_query, chat_type, onboarding)
            
            query_type = analysis_result.get("query_type", "general")
            mode = analysis_result.get("mode", "NO_RETRIEVAL")
            needs_clarification = analysis_result.get("needs_clarification", False)
            
            if needs_clarification or query_type == "ambiguous":
                missing_desc = analysis_result.get("missing_fields_description", "")
                return self.report_to_supervisor(
                    status="need_more_info",
                    result=analysis_result,
                    message=f"추가 정보가 필요합니다. {missing_desc}"
                )
            
            intent = self._extract_intent(analysis_result)
            return self.report_to_supervisor(
                status="success",
                result=analysis_result,
                message=f"분석 완료. 유형: {query_type}, 의도: {intent}, 모드: {mode}"
            )
            
        except Exception as e:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message=f"질의 분석 중 오류 발생: {str(e)}"
            )
    
    def _analyze_query(self, user_query: str, chat_type: str, onboarding: Any) -> Dict[str, Any]:
        normalized_query = _normalize_query(user_query)
        query_type = _classify_query_type(normalized_query)
        
        if chat_type == "general":
            has_dispute_intent = any(kw in normalized_query for kw in DISPUTE_INTENT_KEYWORDS)
            if has_dispute_intent:
                query_type = "dispute"
            elif query_type not in ("law", "criteria"):
                query_type = "general"
        
        keywords = _extract_keywords(normalized_query)
        agency_hint = _determine_agency_hint(normalized_query) if query_type == "dispute" else None
        extracted_info = _extract_info_from_message(user_query)
        
        rewritten_query, expansion_applied = _expand_query_by_type(
            query=normalized_query,
            query_type=query_type,
            onboarding=onboarding,
            extracted_info=extracted_info,
            keywords=keywords,
        )
        
        search_queries = _generate_search_queries(
            original=normalized_query, 
            expanded=rewritten_query, 
            keywords=keywords
        )
        
        missing_fields = _check_missing_onboarding_fields(chat_type, onboarding, extracted_info)
        missing_fields_description = _get_missing_fields_description(missing_fields, extracted_info)
        
        has_minimal_info = bool(
            extracted_info.get("purchase_item")
            or extracted_info.get("dispute_details")
            or (onboarding and (onboarding.get("purchase_item") or onboarding.get("dispute_details")))
        )
        needs_clarification = not has_minimal_info and query_type == "dispute"
        mode = _classify_mode(query_type, needs_clarification, user_query)
        
        return {
            "query_type": query_type,
            "keywords": keywords,
            "agency_hint": agency_hint,
            "needs_clarification": needs_clarification,
            "missing_fields": missing_fields,
            "extracted_info": extracted_info,
            "missing_fields_description": missing_fields_description,
            "rewritten_query": rewritten_query,
            "search_queries": search_queries,
            "expansion_applied": expansion_applied,
            "mode": mode,
        }
    
    def _extract_intent(self, analysis_result: Dict[str, Any]) -> str:
        extracted_info = analysis_result.get("extracted_info", {})
        query_type = analysis_result.get("query_type", "general")
        
        item = extracted_info.get("purchase_item", "")
        details = extracted_info.get("dispute_details", "")
        
        if item and details:
            return f"{item} - {details}"
        elif item:
            return f"{item} 관련 {query_type} 문의"
        elif details:
            return details
        return f"{query_type} 유형 질문"


query_analyst_agent = QueryAnalystAgent()


__all__ = ["QueryAnalystAgent", "query_analyst_agent"]
