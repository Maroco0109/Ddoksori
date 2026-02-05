"""CounselRetrievalAgent - 상담사례 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Any, ClassVar, Dict, List

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.rds_retriever import RDSRetriever


class CounselRetrievalAgent(BaseRetrievalAgent):
    """상담사례(counsel_case) 검색 에이전트 - 참고용 상담 사례"""

    agent_name: ClassVar[str] = "retrieval_counsel"
    agent_description: ClassVar[str] = (
        "상담사례를 검색합니다. 비슷한 상담 기록이 필요할 때 호출됩니다."
    )
    default_dataset: ClassVar[str] = "counsel_case"

    async def _execute_search(self, query: str, top_k: int) -> List[Dict]:
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        retriever = RDSRetriever(db_config, embed_url)
        retriever.connect()

        try:
            results = await asyncio.to_thread(
                retriever.search_hybrid_rrf,
                query_text=query,
                filter_dataset=self.default_dataset,
                filter_category=None,
                filter_document_type=None,
                filter_year=None,
                result_limit=top_k,
                rrf_k=60,
            )
            return results
        finally:
            retriever.close()

    def _format_results(self, results: List[Dict]) -> List[Dict[str, Any]]:
        formatted = []
        for r in results:
            if isinstance(r, dict):
                metadata = r.get("metadata") or {}
                content = r.get("text")
                source_url = r.get("source_url")
                source_file = r.get("source_file")
                similarity = r.get("vector_similarity", r.get("similarity", 0))
            else:
                metadata = r.metadata or {}
                content = r.text
                source_url = r.source_url
                source_file = r.source_file
                similarity = getattr(r, "similarity", 0)

            doc_title = metadata.get("doc_title") or source_file
            doc_id = metadata.get("doc_id") or (
                r.get("chunk_id") if isinstance(r, dict) else r.chunk_id
            )
            decision_date = metadata.get("decision_date")

            formatted.append(
                {
                    "chunk_id": r.get("chunk_id")
                    if isinstance(r, dict)
                    else r.chunk_id,
                    "doc_id": doc_id,
                    "chunk_type": metadata.get("chunk_type"),
                    "content": content,
                    "doc_title": doc_title,
                    "title": doc_title,
                    "source_org": metadata.get("source_org"),
                    "url": source_url,
                    "decision_date": decision_date,
                    "similarity": similarity,
                    "rrf_score": r.get("rrf_score") if isinstance(r, dict) else None,
                    "bm25_score": r.get("bm25_score") if isinstance(r, dict) else None,
                    "vector_similarity": r.get("vector_similarity")
                    if isinstance(r, dict)
                    else None,
                    "metadata": metadata,
                }
            )
        return formatted

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
