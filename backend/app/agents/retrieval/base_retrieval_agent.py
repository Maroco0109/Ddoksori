"""
BaseRetrievalAgent - Retrieval Agent 공통 베이스 클래스

4개의 Retrieval Agent(Law, Criteria, Case, Counsel)가 공유하는 공통 로직을 정의합니다.

각 에이전트는 원본 쿼리를 사용하여 검색을 수행합니다.
"""

import logging
import os
from abc import abstractmethod
from typing import Dict, Any, List, ClassVar, Optional

from ..base import BaseAgent
from ...common.config import get_config

logger = logging.getLogger(__name__)


def _get_db_config() -> Dict[str, str]:
    """
    데이터베이스 설정을 반환합니다.
    USE_RDS_FOR_TESTS=true인 경우 RDS READ_ONLY 설정을 사용합니다.
    기본값은 get_config().database에서 중앙 관리됩니다.
    """
    use_rds = os.getenv('USE_RDS_FOR_TESTS', 'false').lower() == 'true'

    if use_rds:
        return {
            'host': os.getenv('DB_TEST_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'dbname': os.getenv('DB_TEST_NAME', 'ddoksori'),
            'user': os.getenv('DB_TEST_USER', 'readonly_user'),
            'password': os.getenv('DB_TEST_PASSWORD', ''),
        }

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

    default_top_k: ClassVar[int] = 3

    # 서브클래스에서 오버라이드: 도메인 키 (law, criteria, case, counsel)
    domain_key: ClassVar[str] = ""

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)

        context = request.get("context", {})
        user_query = context.get("user_query", "")
        query_analysis = context.get("query_analysis", {})

        # === v2: 확장 쿼리 및 에이전트 키워드 지원 ===
        expanded_queries = context.get("expanded_queries", [])
        agent_keywords = context.get("agent_keywords", [])

        params = request.get("params", {})
        top_k = params.get("top_k", self.default_top_k)

        # === v2: 메타데이터 필터 및 임계치 무시 옵션 ===
        metadata_filter = params.get("metadata_filter", {})
        ignore_threshold = params.get("ignore_threshold", False)

        search_query = self._build_search_query(user_query, query_analysis)

        try:
            results = await self._execute_search(
                search_query, top_k, metadata_filter, ignore_threshold
            )

            # === P0.3: Similarity Threshold Filtering ===
            # 도메인별 threshold 적용 (law=0.60, criteria=0.50, dispute=0.55, general=0.45)
            threshold = get_config().agent.get_similarity_threshold(self.domain_key or None)
            # Filter results by similarity threshold
            filtered_results = [r for r in results if r.similarity >= threshold]

            logger.info(f"[{self.agent_name}] Threshold filtering: {len(results)} -> {len(filtered_results)} results (threshold={threshold:.2f})")

            if not filtered_results:
                return self.report_to_supervisor(
                    status="failure",
                    result={"results": [], "sources": []},
                    message=f"{self.agent_name}: 검색 결과 없음 (similarity < {threshold:.2f}). 다른 키워드로 재시도 권장."
                )

            # Use filtered results
            results = filtered_results
            # === End P0.3 ===

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
    async def _execute_search(
        self,
        query: str,
        top_k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
        ignore_threshold: bool = False
    ) -> List[Any]:
        """
        서브클래스에서 구현: 실제 검색 수행

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            metadata_filter: v2 메타데이터 필터 (optional)
                - dataset_type: 데이터셋 유형 ('law_guide', 'case')
                - document_types: 문서 유형 리스트 (['법률', '시행령'] 등)
                - categories: 카테고리 리스트 (['조정', '해결', '상담'] 등)
            ignore_threshold: True면 유사도 임계치 무시

        Returns:
            검색 결과 리스트
        """
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
