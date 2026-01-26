"""CounselRetrievalAgent - 상담사례 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.hybrid_retriever import HybridRetriever
from .tools.retriever import SearchResult


class CounselRetrievalAgent(BaseRetrievalAgent):
    """상담사례(counsel_case) 검색 에이전트 - 참고용 상담 사례"""
    
    agent_name: ClassVar[str] = "retrieval_counsel"
    agent_description: ClassVar[str] = "상담사례를 검색합니다. 비슷한 상담 기록이 필요할 때 호출됩니다."
    
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
                doc_type_filter='counsel_case',
            )
        finally:
            retriever.close()
    
    def _format_results(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for r in results:
            formatted.append({
                'chunk_id': r.chunk_id,
                'doc_id': r.doc_id,
                'chunk_type': r.chunk_type,
                'content': r.content,
                'doc_title': r.doc_title,
                'title': r.doc_title,
                'source_org': r.source_org,
                'url': r.url,
                'decision_date': r.decision_date,
                'similarity': r.similarity,
            })
        return formatted
    
    def _build_sources(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                'type': 'counsel_case',
                'index': i + 1,
                'chunk_id': r.chunk_id,
                'doc_id': r.doc_id,
                'doc_title': r.doc_title,
                'source_org': r.source_org,
                'similarity': r.similarity,
            }
            for i, r in enumerate(results)
        ]


counsel_retrieval_agent = CounselRetrievalAgent()

__all__ = ["CounselRetrievalAgent", "counsel_retrieval_agent"]
