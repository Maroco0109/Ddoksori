"""CriteriaRetrievalAgent - 분쟁조정기준 검색 전용 에이전트

통합 RRF 검색 사용 (Phase 8): SQL search_hybrid_rrf() → dataset_filter='law_guide', document_type_filter='별표'
[LEGACY] 기존 계층적 검색 (품목매핑 → 기준 → 보충정보) 로직은 제거됨
"""

from typing import Dict, Any, List, ClassVar, Optional

from .base_retrieval_agent import BaseRetrievalAgent
from .tools.retriever import SearchResult


class CriteriaRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정기준(공정위 고시, 품목별 기준) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_criteria"
    agent_description: ClassVar[str] = "분쟁조정기준을 검색합니다. 환불/교환 기준이나 보상 규정이 필요할 때 호출됩니다."
    domain_key: ClassVar[str] = "criteria"

    def _get_search_filters(
        self,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """기준 도메인 필터: dataset_filter='law_guide', document_type_filter='별표'"""
        filters: Dict[str, Any] = {
            "dataset_filter": "law_guide",
            "document_type_filter": "별표",
        }

        if metadata_filter:
            if metadata_filter.get("dataset_type"):
                filters["dataset_filter"] = metadata_filter["dataset_type"]
            if metadata_filter.get("document_types"):
                filters["document_type_filter"] = metadata_filter["document_types"][0]

        return filters
    
    def _format_results(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for r in results:
            meta = r.metadata or {}
            source_label = meta.get('source') if isinstance(meta, dict) else None
            formatted.append({
                'unit_id': None,
                'source_id': None,
                'source_label': source_label,
                'category': (meta.get('category') if isinstance(meta, dict) else None) or (r.category_path[0] if r.category_path else None),
                'industry': None,
                'item_group': None,
                'item': r.doc_title,
                'dispute_type': None,
                'unit_text': r.content,
                'similarity': r.similarity,
                'title': r.doc_title,
            })
        return formatted
    
    def _build_sources(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                'type': 'criteria',
                'index': i + 1,
                'unit_id': None,
                'source_label': (r.source_org),
                'category': (r.category_path[0] if r.category_path else None),
                'item': r.doc_title,
                'similarity': r.similarity,
            }
            for i, r in enumerate(results)
        ]


criteria_retrieval_agent = CriteriaRetrievalAgent()

__all__ = ["CriteriaRetrievalAgent", "criteria_retrieval_agent"]
