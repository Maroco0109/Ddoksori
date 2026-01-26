"""CounselRetrievalAgent - 상담사례 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.specialized_retrievers import CaseRetriever


class CounselRetrievalAgent(BaseRetrievalAgent):
    """상담사례(counsel_case) 검색 에이전트 - 참고용 상담 사례"""
    
    agent_name: ClassVar[str] = "retrieval_counsel"
    agent_description: ClassVar[str] = "상담사례를 검색합니다. 비슷한 상담 기록이 필요할 때 호출됩니다."
    
    async def _execute_search(self, query: str, top_k: int) -> List[Dict]:
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()
        
        retriever = CaseRetriever(db_config, embed_url)
        retriever.connect()
        
        try:
            results = await asyncio.to_thread(retriever.search_counsels, query, top_k)
            return results
        finally:
            retriever.close()
    
    def _format_results(self, results: List[Dict]) -> List[Dict[str, Any]]:
        return [
            {
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "chunk_type": r.get("chunk_type"),
                "content": r.get("content"),
                "doc_title": r.get("doc_title"),
                "source_org": r.get("source_org"),
                "url": r.get("url"),
                "decision_date": r.get("decision_date"),
                "similarity": r.get("similarity", 0),
            }
            for r in results
        ]
    
    def _build_sources(self, results: List[Dict]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "counsel_case",
                "index": i + 1,
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "doc_title": r.get("doc_title"),
                "source_org": r.get("source_org"),
                "similarity": r.get("similarity", 0),
            }
            for i, r in enumerate(results)
        ]


counsel_retrieval_agent = CounselRetrievalAgent()

__all__ = ["CounselRetrievalAgent", "counsel_retrieval_agent"]
