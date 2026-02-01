"""LawRetrievalAgent - 법령 검색 전용 에이전트

통합 RRF 검색 사용 (Phase 8): SQL search_hybrid_rrf() → dataset_filter='law_guide'
[LEGACY] 기존 계층적 검색 (항/호 → 조_전체) 로직은 제거됨
"""

from typing import Dict, Any, List, ClassVar, Optional

from .base_retrieval_agent import BaseRetrievalAgent
from .tools.retriever import SearchResult


class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."
    domain_key: ClassVar[str] = "law"

    def _get_search_filters(
        self,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """법령 도메인 필터: dataset_filter='law_guide'"""
        filters: Dict[str, Any] = {"dataset_filter": "law_guide"}

        if metadata_filter:
            if metadata_filter.get("dataset_type"):
                filters["dataset_filter"] = metadata_filter["dataset_type"]
            if metadata_filter.get("document_types"):
                # 첫 번째 문서 유형을 필터로 사용
                filters["document_type_filter"] = metadata_filter["document_types"][0]

        return filters
    
    def _format_results(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        formatted = []
        for r in results:
            meta = r.metadata or {}
            full_path = None
            if isinstance(meta, dict):
                # RDS law_guide stores a hierarchy path list.
                hp = meta.get('hierarchy_path')
                if isinstance(hp, list):
                    full_path = ' > '.join(str(x) for x in hp if x)
                else:
                    full_path = meta.get('full_path')

            formatted.append({
                'unit_id': None,
                'law_name': meta.get('law_name') if isinstance(meta, dict) else None,
                'full_path': full_path,
                'text': r.content,
                'similarity': r.similarity,
            })
        return formatted
    
    def _build_sources(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for i, r in enumerate(results):
            meta = r.metadata or {}
            full_path = None
            if isinstance(meta, dict):
                hp = meta.get('hierarchy_path')
                if isinstance(hp, list):
                    full_path = ' > '.join(str(x) for x in hp if x)
                else:
                    full_path = meta.get('full_path')

            sources.append({
                'type': 'law',
                'index': i + 1,
                'unit_id': None,
                'law_name': r.doc_title,
                'full_path': full_path,
                'similarity': r.similarity,
            })
        return sources


law_retrieval_agent = LawRetrievalAgent()

__all__ = ["LawRetrievalAgent", "law_retrieval_agent"]
