"""
BaseRetrievalAgent - Retrieval Agent 공통 베이스 클래스

4개의 Retrieval Agent(Law, Criteria, Case, Counsel)가 공유하는 공통 로직을 정의합니다.
LLM: 2.4B (EXAONE), 역할: 쿼리 재작성
"""

import os
from abc import abstractmethod
from typing import Dict, Any, List, ClassVar, Optional

from ..base import BaseAgent


def _get_db_config() -> Dict[str, str]:
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'dbname': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
    }


def _get_embed_api_url() -> str:
    return os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')


class BaseRetrievalAgent(BaseAgent):
    """Retrieval Agent 공통 베이스 - 검색 결과 포맷팅 및 에러 처리 공유"""
    
    required_inputs: ClassVar[List[str]] = ["user_query"]
    provided_outputs: ClassVar[List[str]] = ["results", "sources", "max_similarity", "avg_similarity"]
    
    default_top_k: ClassVar[int] = 3
    
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)
        
        context = request.get("context", {})
        user_query = context.get("user_query", "")
        query_analysis = context.get("query_analysis", {})
        
        search_query = self._build_search_query(user_query, query_analysis)
        top_k = request.get("params", {}).get("top_k", self.default_top_k)
        
        try:
            results = await self._execute_search(search_query, top_k)
            
            if not results:
                return self.report_to_supervisor(
                    status="failure",
                    result={"results": [], "sources": []},
                    message=f"{self.agent_name}: 검색 결과 없음. 다른 키워드로 재시도 권장."
                )
            
            formatted_results = self._format_results(results)
            sources = self._build_sources(results)
            
            max_sim = max((r.get("similarity", 0) for r in formatted_results), default=0)
            avg_sim = sum(r.get("similarity", 0) for r in formatted_results) / len(formatted_results) if formatted_results else 0
            
            return self.report_to_supervisor(
                status="success",
                result={
                    "results": formatted_results,
                    "sources": sources,
                    "max_similarity": max_sim,
                    "avg_similarity": avg_sim,
                },
                message=f"{self.agent_name}: {len(results)}건 검색 완료 (max_sim: {max_sim:.3f})"
            )
            
        except Exception as e:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message=f"{self.agent_name} 검색 오류: {str(e)}"
            )
    
    def _build_search_query(self, user_query: str, query_analysis: Dict[str, Any]) -> str:
        rewritten = query_analysis.get("rewritten_query")
        if rewritten and rewritten != user_query:
            return rewritten
        return user_query
    
    @abstractmethod
    async def _execute_search(self, query: str, top_k: int) -> List[Any]:
        """서브클래스에서 구현: 실제 검색 수행"""
        pass
    
    @abstractmethod
    def _format_results(self, results: List[Any]) -> List[Dict[str, Any]]:
        """서브클래스에서 구현: 결과 포맷팅"""
        pass
    
    @abstractmethod
    def _build_sources(self, results: List[Any]) -> List[Dict[str, Any]]:
        """서브클래스에서 구현: 출처 정보 생성"""
        pass


__all__ = ["BaseRetrievalAgent", "_get_db_config", "_get_embed_api_url"]
