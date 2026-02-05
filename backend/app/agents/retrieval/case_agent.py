"""CaseRetrievalAgent - 분쟁조정사례 검색 전용 에이전트

통합 RRF 검색 사용 (Phase 8): SQL search_hybrid_rrf() → dataset_filter='case'
[LEGACY] 기존 2단계 우선순위 검색 (해결+조정 → 상담 보충) 로직은 제거됨
"""

import logging
from typing import Any, ClassVar, Dict, List, Optional

from .base_retrieval_agent import BaseRetrievalAgent
from .tools.retriever import SearchResult

logger = logging.getLogger(__name__)


class CaseRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정사례(mediation_case) 검색 에이전트 - 법적 효력이 있는 분쟁조정 결과"""

    agent_name: ClassVar[str] = "retrieval_case"
    agent_description: ClassVar[str] = (
        "분쟁조정사례를 검색합니다. 유사한 분쟁 해결 선례가 필요할 때 호출됩니다."
    )
    domain_key: ClassVar[str] = "case"

    def _get_search_filters(
        self,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """사례 도메인 필터: dataset_filter='case'"""
        filters: Dict[str, Any] = {"dataset_filter": "case"}

        if metadata_filter:
            if metadata_filter.get("dataset_type"):
                filters["dataset_filter"] = metadata_filter["dataset_type"]
            # categories → 첫 번째 카테고리를 category_filter로
            if metadata_filter.get("categories"):
                categories = metadata_filter["categories"]
                if len(categories) == 1:
                    filters["category_filter"] = categories[0]
                # 복수 카테고리는 SQL 함수가 단일 필터만 지원하므로 None (전체 검색)

        return filters

    def _format_results(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for r in results:
            formatted.append(
                {
                    "chunk_id": r.chunk_id,
                    "doc_id": r.doc_id,
                    "chunk_type": r.chunk_type,
                    "content": r.content,
                    "doc_title": r.doc_title,
                    "title": r.doc_title,
                    "source_org": r.source_org,
                    "url": r.url,
                    "source_file": r.source_file,
                    "printed_page": r.printed_page,
                    "decision_date": r.decision_date,
                    "similarity": r.similarity,
                    "metadata": r.metadata,  # 메타데이터 추가
                }
            )
        return formatted

    def _build_sources(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "mediation_case",
                "index": i + 1,
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "doc_title": r.doc_title,
                "source_org": r.source_org,
                "similarity": r.similarity,
            }
            for i, r in enumerate(results)
        ]


case_retrieval_agent = CaseRetrievalAgent()

__all__ = ["CaseRetrievalAgent", "case_retrieval_agent"]
