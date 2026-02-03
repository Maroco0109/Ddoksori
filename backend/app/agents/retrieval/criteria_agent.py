"""CriteriaRetrievalAgent - 분쟁조정기준 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
import logging
import re
from typing import Any, ClassVar, Dict, List, TypedDict

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.rds_internal_retriever import SimilarChunkResult
from .tools.specialized_retrievers import CriteriaRetriever

logger = logging.getLogger(__name__)


class CriteriaDocument(TypedDict):
    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    similarity: float


class CriteriaRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정기준(공정위 고시, 품목별 기준) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_criteria"
    agent_description: ClassVar[str] = (
        "분쟁조정기준을 검색합니다. 환불/교환 기준이나 보상 규정이 필요할 때 호출됩니다."
    )

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

        retriever = CriteriaRetriever(db_config, embed_url)
        retriever.connect()

        try:
            all_results: List[List[SimilarChunkResult]] = []
            for q in expanded_queries:
                results = await asyncio.to_thread(
                    retriever.hybrid_search,
                    q,
                    top_k,
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
                    fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (
                        1.0 / (rrf_k + rank)
                    )
                    if chunk_id not in fused_results:
                        fused_results[chunk_id] = result

            for chunk_id, score in fused_scores.items():
                fused_results[chunk_id].similarity = score

            ranked = sorted(
                fused_results.values(),
                key=lambda r: r.similarity,
                reverse=True,
            )
            final_results = ranked[:top_k]

            # Build parent/child chunk_id lookups for content augmentation.
            parent_ids: List[str] = []
            child_ids: List[str] = []
            for result in final_results:
                chunk_id = result.chunk_id or ""
                parts = chunk_id.split("_")
                if len(parts) < 2:
                    continue
                last = parts[-1]
                second_last = parts[-2]

                is_grandchild = bool(
                    re.match(r"^조건\d+_하위\d+$", f"{second_last}_{last}")
                )
                is_child = bool(re.match(r"^조건\d+$", last))

                if is_grandchild:
                    base = "_".join(parts[:-2])
                    parent_ids.append(f"{base}_부모")
                    child_ids.append(f"{base}_{second_last}")
                elif is_child:
                    base = "_".join(parts[:-1])
                    parent_ids.append(f"{base}_부모")

            parent_texts = retriever.fetch_chunk_texts(list(set(parent_ids)))
            child_texts = retriever.fetch_chunk_texts(list(set(child_ids)))

            for result in final_results:
                chunk_id = result.chunk_id or ""
                parts = chunk_id.split("_")
                if len(parts) < 2:
                    continue
                last = parts[-1]
                second_last = parts[-2]

                is_grandchild = bool(
                    re.match(r"^조건\d+_하위\d+$", f"{second_last}_{last}")
                )
                is_child = bool(re.match(r"^조건\d+$", last))

                if not (is_grandchild or is_child):
                    continue

                if is_grandchild:
                    base = "_".join(parts[:-2])
                    parent_id = f"{base}_부모"
                    child_id = f"{base}_{second_last}"
                    parent_text = parent_texts.get(parent_id, "")
                    child_text = child_texts.get(child_id, "")
                    grand_text = result.text or ""
                    # Base caps with dynamic redistribution: 하위 -> 조건 -> 부모
                    parent_cap = 400
                    child_cap = 300
                    grand_cap = 400
                    max_total = 1000
                    parent_trim = parent_text[:parent_cap]
                    child_trim = child_text[:child_cap]
                    grand_trim = grand_text[:grand_cap]
                    used = len(parent_trim) + len(child_trim) + len(grand_trim)
                    remaining = max_total - used
                    if remaining > 0:
                        extra = min(
                            remaining, max(0, len(grand_text) - len(grand_trim))
                        )
                        grand_trim += grand_text[
                            len(grand_trim) : len(grand_trim) + extra
                        ]
                        remaining -= extra
                    if remaining > 0:
                        extra = min(
                            remaining, max(0, len(child_text) - len(child_trim))
                        )
                        child_trim += child_text[
                            len(child_trim) : len(child_trim) + extra
                        ]
                        remaining -= extra
                    if remaining > 0:
                        extra = min(
                            remaining, max(0, len(parent_text) - len(parent_trim))
                        )
                        parent_trim += parent_text[
                            len(parent_trim) : len(parent_trim) + extra
                        ]

                    composed = "\n".join(
                        [
                            "[부모]",
                            parent_trim,
                            "",
                            "[조건]",
                            child_trim,
                            "",
                            "[하위]",
                            grand_trim,
                        ]
                    ).strip()
                else:
                    base = "_".join(parts[:-1])
                    parent_id = f"{base}_부모"
                    parent_text = parent_texts.get(parent_id, "")
                    child_text = result.text or ""
                    parent_cap = 400
                    child_cap = 300
                    max_total = 1000
                    parent_trim = parent_text[:parent_cap]
                    child_trim = child_text[:child_cap]
                    used = len(parent_trim) + len(child_trim)
                    remaining = max_total - used
                    if remaining > 0:
                        extra = min(
                            remaining, max(0, len(child_text) - len(child_trim))
                        )
                        child_trim += child_text[
                            len(child_trim) : len(child_trim) + extra
                        ]
                        remaining -= extra
                    if remaining > 0:
                        extra = min(
                            remaining, max(0, len(parent_text) - len(parent_trim))
                        )
                        parent_trim += parent_text[
                            len(parent_trim) : len(parent_trim) + extra
                        ]

                    composed = "\n".join(
                        [
                            "[부모]",
                            parent_trim,
                            "",
                            "[조건]",
                            child_trim,
                        ]
                    ).strip()

                result.text = composed

            return final_results
        finally:
            retriever.close()

    def _format_results(
        self, results: List[SimilarChunkResult]
    ) -> List[CriteriaDocument]:
        formatted: List[CriteriaDocument] = []
        for r in results:
            raw_meta = r.metadata if isinstance(r.metadata, dict) else {}
            merged_meta = dict(raw_meta)
            merged_meta.update(
                {
                    "source_label": raw_meta.get("source_label"),
                    "category": r.category,
                    "item": raw_meta.get("item"),
                    "title": raw_meta.get("title"),
                    "document_type": r.document_type or raw_meta.get("document_type"),
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
                "type": "criteria",
                "index": i + 1,
                "chunk_id": r.chunk_id,
                "category": r.category,
                "source_label": (r.metadata or {}).get("source_label"),
                "item": (r.metadata or {}).get("item"),
                "hierarchy_path": (r.metadata or {}).get("hierarchy_path"),
                "similarity": r.similarity,
            }
            for i, r in enumerate(results)
        ]


criteria_retrieval_agent = CriteriaRetrievalAgent()

__all__ = ["CriteriaRetrievalAgent", "criteria_retrieval_agent"]
