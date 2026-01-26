"""CaseRetrievalAgent - 분쟁조정사례 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.specialized_retrievers import CaseRetriever


class CaseRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정사례(mediation_case) 검색 에이전트 - 법적 효력이 있는 분쟁조정 결과"""
    
    agent_name: ClassVar[str] = "retrieval_case"
    agent_description: ClassVar[str] = "분쟁조정사례를 검색합니다. 유사한 분쟁 해결 선례가 필요할 때 호출됩니다."
    
    async def _execute_search(self, query: str, top_k: int) -> List[Dict]:
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()
        
        retriever = CaseRetriever(db_config, embed_url)
        retriever.connect()
        
        try:
            results = await asyncio.to_thread(retriever.search_disputes, query, top_k)
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
                "doc_similarity": r.get("doc_similarity"),
                "doc_chunk_count": r.get("doc_chunk_count"),
            }
            for r in results
        ]
    
    def _build_sources(self, results: List[Dict]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "mediation_case",
                "index": i + 1,
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "doc_title": r.get("doc_title"),
                "source_org": r.get("source_org"),
                "similarity": r.get("similarity", 0),
            }
            for i, r in enumerate(results)
        ]


case_retrieval_agent = CaseRetrievalAgent()

__all__ = ["CaseRetrievalAgent", "case_retrieval_agent"]
