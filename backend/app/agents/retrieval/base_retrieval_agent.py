"""
BaseRetrievalAgent - Retrieval Agent 공통 베이스 클래스

4개의 Retrieval Agent(Law, Criteria, Case, Counsel)가 공유하는 공통 로직을 정의합니다.
"""

import os
import time
import logging
from abc import abstractmethod
from typing import Dict, Any, List, ClassVar, Optional

from ..base import BaseAgent
logger = logging.getLogger(__name__)


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
    
    default_top_k: ClassVar[int] = 5
    
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)
        
        context = request.get("context", {})
        user_query = context.get("user_query", "")
        query_analysis = context.get("query_analysis", {})
        params = request.get("params", {}) or {}

        metadata_filter = params.get("metadata_filter") or {}
        expanded_queries = params.get("expanded_queries") or query_analysis.get("expanded_queries") or []
        agent_keywords = params.get("agent_keywords") or query_analysis.get("keywords") or []
        ignore_threshold = bool(params.get("ignore_threshold", False))

        self._last_expanded_queries = [
            q for q in expanded_queries if isinstance(q, str) and q.strip()
        ]
        self._last_agent_keywords = [
            k for k in agent_keywords if isinstance(k, str) and k.strip()
        ]
        self._ignore_threshold = ignore_threshold

        self._last_filter_category = params.get("filter_category")
        if not self._last_filter_category:
            self._last_filter_category = self._normalize_categories(
                metadata_filter.get("categories")
            )
        self._last_filter_dataset = params.get("filter_dataset") or metadata_filter.get(
            "dataset_type"
        )
        self._last_query_analysis = query_analysis
        
        search_query = self._build_search_query(user_query, query_analysis)
        top_k = params.get("top_k", self.default_top_k)
        
        try:
            search_start = time.monotonic()
            results = await self._execute_search(search_query, top_k)
            search_time_ms = (time.monotonic() - search_start) * 1000
            if self._should_rerank(results, search_query, top_k):
                results = self._rerank_results(results, search_query)
            
            if not results:
                return self.report_to_supervisor(
                    status="failure",
                    result={
                        "results": [],
                        "documents": [],
                        "sources": [],
                        "final_query": search_query,
                        "rewritten_query": self._last_rewritten_query,
                        "search_time_ms": search_time_ms,
                        "error": "no_results",
                    },
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
                    "documents": formatted_results,
                    "sources": sources,
                    "max_similarity": max_sim,
                    "avg_similarity": avg_sim,
                    "final_query": search_query,
                    "rewritten_query": self._last_rewritten_query,
                    "search_time_ms": search_time_ms,
                    "error": None,
                },
                message=f"{self.agent_name}: {len(results)}건 검색 완료 (max_sim: {max_sim:.3f})"
            )
            
        except Exception as e:
            logger.exception(f"{self.agent_name} 검색 오류: {str(e)}")
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message=f"{self.agent_name} 검색 오류: {str(e)}"
            )
    
    def _build_search_query(self, user_query: str, query_analysis: Dict[str, Any]) -> str:
        # query_analysis is handled upstream; prefer expanded queries when provided.
        candidate = None
        expanded_queries = getattr(self, "_last_expanded_queries", None)
        if not expanded_queries:
            expanded_queries = query_analysis.get("expanded_queries") or []
        for q in expanded_queries:
            if isinstance(q, str) and q.strip():
                candidate = q.strip()
                break

        if candidate:
            self._last_rewritten_query = candidate
            self._last_final_query = candidate
            return candidate

        self._last_rewritten_query = None
        self._last_final_query = user_query
        return user_query

    @staticmethod
    def _normalize_categories(categories: Optional[List[str]]) -> Optional[str]:
        if not categories:
            return None
        normalized = [c for c in categories if isinstance(c, str)]
        if not normalized:
            return None
        normalized_set = set(normalized)
        if "상담" in normalized_set and ("조정" in normalized_set or "해결" in normalized_set):
            return None
        if "상담" in normalized_set:
            return "상담"
        if "조정" in normalized_set and "해결" in normalized_set:
            return "조정+해결"
        if "조정" in normalized_set:
            return "조정"
        if "해결" in normalized_set:
            return "해결"
        if normalized_set.intersection({"조정+해결", "조정_해결", "통합"}):
            return "조정+해결"
        return None

    def _should_rerank(self, results: List[Any], query: str, top_k: int) -> bool:
        return False

    def _rerank_results(self, results: List[Any], query: str) -> List[Any]:
        return results
    
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
