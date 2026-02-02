"""LawRetrievalAgent - 법령 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
import logging
import os
import re
from typing import Dict, Any, List, ClassVar, TypedDict

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.specialized_retrievers import LawRetriever
from .tools.rds_internal_retriever import SimilarChunkResult


logger = logging.getLogger(__name__)


class LawDocument(TypedDict):
    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    similarity: float


class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""
    
    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."


    async def _execute_search(
        self,
        query: str,
        top_k: int,
        task_input: Dict[str, Any] | None = None,
    ) -> List[SimilarChunkResult]:
        expanded_queries: List[str] = []
        if task_input:
            expanded_queries = task_input.get("expanded_queries") or []
        if not expanded_queries:
            expanded_queries = [query]

        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        document_types = None
        if task_input:
            metadata_filter = task_input.get("metadata_filter") or {}
            document_types = metadata_filter.get("document_types") or None
        
        retriever = LawRetriever(db_config, embed_url)
        retriever.connect()
        
        try:
            per_query_k = max(top_k, 12)
            all_results: List[List[SimilarChunkResult]] = []
            for q in expanded_queries:
                results = await asyncio.to_thread(
                    retriever.hybrid_search,
                    q,
                    per_query_k,
                    document_types,
                )
                all_results.append(results)

            fused_scores: Dict[str, float] = {}
            fused_results: Dict[str, SimilarChunkResult] = {}
            from app.common.config import get_config
            rrf_k = get_config().retrieval.rrf_k_python

            for results in all_results:
                for rank, result in enumerate(results, start=1):
                    chunk_id = result.chunk_id
                    fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (1.0 / (rrf_k + rank))
                    if chunk_id not in fused_results:
                        fused_results[chunk_id] = result

            for chunk_id, score in fused_scores.items():
                fused_results[chunk_id].similarity = score

            ranked = sorted(
                fused_results.values(),
                key=lambda r: r.similarity,
                reverse=True,
            )
            # Filter deleted articles and limit to 2 per law/article key.
            filtered: List[SimilarChunkResult] = []
            seen_per_article: Dict[str, int] = {}
            for result in ranked:
                text = result.text or ""
                if re.search(r"\(\).*삭제\s*<", text, re.DOTALL):
                    continue

                chunk_id = result.chunk_id or ""
                parts = chunk_id.split("_")
                if len(parts) >= 2:
                    article_key = f"{parts[0]}_{parts[1]}"
                else:
                    article_key = chunk_id

                count = seen_per_article.get(article_key, 0)
                if count >= 2:
                    continue
                seen_per_article[article_key] = count + 1
                filtered.append(result)
                if len(filtered) >= top_k:
                    break

            return filtered
        finally:
            retriever.close()
    
    def _format_results(self, results: List[SimilarChunkResult]) -> List[LawDocument]:
        formatted: List[LawDocument] = []
        for r in results:
            raw_meta = r.metadata if isinstance(r.metadata, dict) else {}
            merged_meta = dict(raw_meta)
            merged_meta.update(
                {
                    "law_name": r.law_name,
                    "full_path": raw_meta.get("hierarchy_path"),
                    "article": raw_meta.get("조문번호"),
                    "document_type": r.document_type,
                    "dataset_type": r.dataset_type,
                }
            )

            formatted.append(
                {
                    "chunk_id": r.chunk_id,
                    "content": r.text,
                    "metadata": merged_meta,
                    "similarity": r.similarity,
                }
            )

        return formatted
    
    def _build_sources(self, results: List[SimilarChunkResult]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "law",
                "index": i + 1,
                "chunk_id": r.chunk_id,
                "law_name": r.law_name,
                "hierarchy_path": (r.metadata or {}).get("hierarchy_path"),
                "similarity": r.similarity,
            }
            for i, r in enumerate(results)
        ]


law_retrieval_agent = LawRetrievalAgent()

__all__ = ["LawRetrievalAgent", "law_retrieval_agent"]
