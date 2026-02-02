"""CounselRetrievalAgent - 상담사례 검색 전용 에이전트

통합 RRF 검색 사용 (Phase 8): SQL search_hybrid_rrf() → dataset_filter='case', category_filter='상담'
CaseRetrievalAgent와 동일한 로직이지만 상담사례(counsel)만 필터링합니다.
"""

import logging
from typing import Any, ClassVar, Dict, List, Optional

from .base_retrieval_agent import BaseRetrievalAgent
from .tools.retriever import SearchResult

logger = logging.getLogger(__name__)


class CounselRetrievalAgent(BaseRetrievalAgent):
    """상담사례(counsel_case) 검색 에이전트 - 소비자 상담 사례"""

    agent_name: ClassVar[str] = "retrieval_counsel"
    agent_description: ClassVar[str] = (
        "상담사례를 검색합니다. 소비자 상담 선례가 필요할 때 호출됩니다."
    )
    domain_key: ClassVar[str] = "counsel"

    def _get_search_filters(
        self,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """상담사례 도메인 필터: dataset_filter='case', category_filter='상담'"""
        filters: Dict[str, Any] = {"dataset_filter": "case", "category_filter": "상담"}

        if metadata_filter:
            # dataset_type 명시적 지정 시 덮어쓰기
            if metadata_filter.get("dataset_type"):
                filters["dataset_filter"] = metadata_filter["dataset_type"]
            # categories 명시적 지정 시 첫 번째 카테고리로 덮어쓰기
            if metadata_filter.get("categories"):
                categories = metadata_filter["categories"]
                if len(categories) == 1:
                    filters["category_filter"] = categories[0]
                # 복수 카테고리는 SQL 함수가 단일 필터만 지원하므로 None (전체 검색)
                elif len(categories) > 1:
                    filters.pop("category_filter", None)

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
                    "decision_date": r.decision_date,
                    "similarity": r.similarity,
                }
            )
        return formatted

    def _build_sources(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "counsel_case",
                "index": i + 1,
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "doc_title": r.doc_title,
                "source_org": r.source_org,
                "similarity": r.similarity,
            }
            for i, r in enumerate(results)
        ]


counsel_retrieval_agent = CounselRetrievalAgent()

__all__ = ["CounselRetrievalAgent", "counsel_retrieval_agent"]
