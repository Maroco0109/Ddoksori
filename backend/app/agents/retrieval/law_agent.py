"""LawRetrievalAgent - 법령 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.hybrid_retriever import HybridRetriever
from .tools.retriever import SearchResult


class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""
    
    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."
    domain_rewrite_prompt: ClassVar[str] = "Convert this user query into a formal legal search query focusing on relevant laws and regulations: {query}"
    
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
                doc_type_filter='law',
            )
        finally:
            retriever.close()
    
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
