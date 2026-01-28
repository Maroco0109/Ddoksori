"""
BaseRetrievalAgent - Retrieval Agent 공통 베이스 클래스

4개의 Retrieval Agent(Law, Criteria, Case, Counsel)가 공유하는 공통 로직을 정의합니다.
LLM: 2.4B (EXAONE), 역할: 쿼리 재작성
"""

import os
import logging
from abc import abstractmethod
from typing import Dict, Any, List, ClassVar, Optional

from ..base import BaseAgent

logger = logging.getLogger(__name__)

REWRITE_ENABLED = os.getenv("QUERY_REWRITE_ENABLED", "true").lower() == "true"
REWRITE_MODEL = os.getenv("QUERY_REWRITE_MODEL", "gpt-4o-mini")
REWRITE_TIMEOUT_SEC = float(os.getenv("QUERY_REWRITE_TIMEOUT_SEC", "4.0"))
REWRITE_MIN_CHARS = int(os.getenv("QUERY_REWRITE_MIN_CHARS", "5"))


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
            if self._should_rerank(results, search_query, top_k):
                results = self._rerank_results(results, search_query)
            
            if not results:
                return self.report_to_supervisor(
                    status="failure",
                    result={
                        "results": [],
                        "sources": [],
                        "final_query": search_query,
                        "rewritten_query": self._last_rewritten_query,
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
                    "sources": sources,
                    "max_similarity": max_sim,
                    "avg_similarity": avg_sim,
                    "final_query": search_query,
                    "rewritten_query": self._last_rewritten_query,
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
        # query_analysis is intentionally unused; rewrite happens in this base agent.
        self._last_rewritten_query = None
        self._last_final_query = user_query

        if not user_query:
            return user_query

        if len(user_query.strip()) < REWRITE_MIN_CHARS:
            return user_query

        if REWRITE_ENABLED:
            rewritten = self._rewrite_query(user_query)
            if rewritten and rewritten != user_query:
                self._last_rewritten_query = rewritten
                self._last_final_query = rewritten
                return rewritten

        return user_query

    def _rewrite_query(self, query: str) -> Optional[str]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("openai package is not available; skipping rewrite.")
            return None

        client = OpenAI(api_key=api_key, timeout=REWRITE_TIMEOUT_SEC)
        system_prompt = (
            "너는 검색(Retrieval: BM25+벡터 하이브리드)을 위해 사용자 질문을 '검색용 쿼리'로 재작성한다.\n"
            "규칙:\n"
            "1) 의도는 그대로 유지하고, 짧고 검색 친화적으로 만든다.\n"
            "2) 설명/부연/따옴표/불릿/포맷 없이 '한 줄 텍스트'만 출력한다.\n"
            "3) 고유명사(기관/제품/서비스명), 숫자, 날짜, 사건번호는 절대 변경하지 않는다.\n"
            "4) 이미 명확하면 원문을 그대로 반환한다.\n"
            "5) 입력 언어를 유지한다(한국어면 한국어).\n"
            "출력: 재작성된 쿼리 1줄만."
        )
        try:
            response = client.chat.completions.create(
                model=REWRITE_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("Query rewrite failed: %s", exc)
            return None

        rewritten = response.choices[0].message.content if response.choices else None
        if rewritten:
            return rewritten.strip()
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
