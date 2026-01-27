"""CriteriaRetrievalAgent - 분쟁조정기준 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.hybrid_retriever import HybridRetriever
from .tools.retriever import SearchResult


class CriteriaRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정기준(공정위 고시, 품목별 기준) 검색 에이전트"""
    
    agent_name: ClassVar[str] = "retrieval_criteria"
    agent_description: ClassVar[str] = "분쟁조정기준을 검색합니다. 환불/교환 기준이나 보상 규정이 필요할 때 호출됩니다."
    domain_rewrite_prompt: ClassVar[str] = "Convert this everyday language query into a dispute resolution criteria search query: {query}"
    
    async def _execute_search(self, query: str, top_k: int) -> List[SearchResult]:
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()
        
        try:
            return await asyncio.to_thread(
                retriever.search,
                query=query,
                top_k=top_k,
                doc_type_filter='criteria',
            )
        finally:
            retriever.close()
    
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
