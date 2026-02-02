"""
BaseRetrievalAgent - Retrieval Agent 공통 베이스 클래스

3개의 Retrieval Agent(Law, Criteria, Case)가 공유하는 공통 로직을 정의합니다.

검색 방식:
- UnifiedRetriever를 사용한 통합 RRF 검색 (BM25 + Vector + SQL search_hybrid_rrf)
- 각 에이전트는 _get_search_filters()로 도메인별 필터만 지정

[LEGACY] 기존 HybridRetriever 기반 계층적 검색은 제거됨 (Phase 8)
"""

import asyncio
import inspect
import logging
import os
import time
from abc import abstractmethod
from typing import Dict, Any, List, ClassVar, Mapping, Optional, Sequence

from ..base import BaseAgent
from ...common.config import get_config

logger = logging.getLogger(__name__)


def _get_db_config() -> Dict[str, str]:
    """
    데이터베이스 설정을 반환합니다.
    get_config().database에서 중앙 관리되는 DB_* 환경변수를 사용합니다.
    """
    config = get_config().database
    conn = config.get_connection_dict()
    # psycopg2는 'dbname' 키를 사용하지만 get_connection_dict()는 'database'를 반환
    if 'database' in conn and 'dbname' not in conn:
        conn['dbname'] = conn.pop('database')
    return conn


def _get_embed_api_url() -> str:
    return os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')


class BaseRetrievalAgent(BaseAgent):
    """Retrieval Agent 공통 베이스 - 검색 결과 포맷팅 및 에러 처리 공유"""

    required_inputs: ClassVar[List[str]] = ["user_query"]
    provided_outputs: ClassVar[List[str]] = ["results", "sources", "max_similarity", "avg_similarity"]

    default_top_k: ClassVar[int] = 10

    # 서브클래스에서 오버라이드: 도메인 키 (law, criteria, case, counsel)
    domain_key: ClassVar[str] = ""

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)

        context = request.get("context") or {}
        user_query = context.get("user_query") or ""
        query_analysis = context.get("query_analysis") or {}

        task_input = context.get("retrieval_task_input")
        if task_input is None:
            task_input = query_analysis.get("retrieval_task_input")
        if task_input is None:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message=f"{self.agent_name}: retrieval_task_input missing."
            )

        search_query = user_query
        top_k = task_input.get("top_k", self.default_top_k)

        try:
            search_start = time.time()
            execute_params = inspect.signature(self._execute_search).parameters
            if "task_input" in execute_params:
                results = await self._execute_search(search_query, top_k, task_input)
            else:
                results = await self._execute_search(search_query, top_k)
            search_time_ms = (time.time() - search_start) * 1000

            if not results:
                return self.report_to_supervisor(
                    status="failure",
                    result={
                        "results": [],
                        "sources": [],
                        "search_time_ms": search_time_ms,
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
                    "search_time_ms": search_time_ms,
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

    def _get_search_filters(
        self,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        서브클래스에서 오버라이드: 도메인별 검색 필터 반환

        Returns:
            UnifiedRetriever.search()에 전달할 키워드 인자 dict
            예: {"dataset_filter": "law_guide", "document_type_filter": "별표"}
        """
        return {}

    async def _execute_search(
        self,
        query: str,
        top_k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
        ignore_threshold: bool = False,
        task_input: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """
        통합 RRF 검색 - UnifiedRetriever를 사용하여 SQL search_hybrid_rrf() 호출

        모든 에이전트가 동일한 로직을 사용합니다.
        도메인별 차이는 _get_search_filters()로 처리합니다.
        """
        from .tools.unified_retriever import UnifiedRetriever

        db_config = _get_db_config()
        retriever = UnifiedRetriever(db_config)
        retriever.connect()

        try:
            filters = self._get_search_filters(metadata_filter)

            # expanded_queries가 있으면 search_multi() 사용
            expanded_queries = (task_input or {}).get('expanded_queries', [])
            if expanded_queries and len(expanded_queries) > 1:
                results = await asyncio.to_thread(
                    retriever.search_multi,
                    queries=expanded_queries,
                    top_k=top_k,
                    **filters,
                )
            else:
                results = await asyncio.to_thread(
                    retriever.search,
                    query=query,
                    top_k=top_k,
                    **filters,
                )
            return results
        finally:
            retriever.close()

    @abstractmethod
    def _format_results(self, results: List[Any]) -> Sequence[Mapping[str, Any]]:
        """서브클래스에서 구현: 결과 포맷팅"""
        pass

    @abstractmethod
    def _build_sources(self, results: List[Any]) -> List[Dict[str, Any]]:
        """서브클래스에서 구현: 출처 정보 생성"""
        pass


__all__ = ["BaseRetrievalAgent", "_get_db_config", "_get_embed_api_url"]
