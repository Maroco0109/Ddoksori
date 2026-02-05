"""CriteriaRetrievalAgent - 분쟁조정기준 검색 전용 에이전트. LLM: 2.4B (EXAONE)

Phase 2-10: 분쟁해결기준 전용 쿼리 확장 적용
- 품목 → 분쟁해결기준 카테고리 변환 (노트북 → 컴퓨터, 전자제품)
- 분쟁유형 → 기준 키워드 변환 (환불 → 환급, 구입가 환급)
"""

import asyncio
import logging
import re
from typing import Any, ClassVar, Dict, List, TypedDict

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config
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
        # Phase 2-10: 분쟁해결기준 전용 쿼리 확장 적용
        criteria_specific_queries = await self._expand_for_criteria_search(query, task_input)

        # 기존 expanded_queries와 병합
        expanded_queries: List[str] = []
        if task_input:
            expanded_queries = task_input.get("expanded_queries") or []

        # 분쟁해결기준 전용 쿼리를 우선 사용, 기존 쿼리는 보조로 추가
        all_queries = criteria_specific_queries.copy()
        for eq in expanded_queries:
            if eq not in all_queries:
                all_queries.append(eq)
        all_queries = all_queries[:6]  # 최대 6개로 제한

        if not all_queries:
            all_queries = [query]

        logger.info(
            f"[CriteriaAgent] Using {len(all_queries)} queries: "
            f"criteria_specific={len(criteria_specific_queries)}, original={len(expanded_queries)}"
        )

        db_config = _get_db_config()

        document_types = None
        if task_input:
            metadata_filter = task_input.get("metadata_filter") or {}
            document_types = metadata_filter.get("document_types") or None

        retriever = CriteriaRetriever(db_config)
        retriever.connect()

        try:
            all_results: List[List[SimilarChunkResult]] = []
            for q in all_queries:
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

    async def _expand_for_criteria_search(
        self, query: str, task_input: Dict[str, Any] | None
    ) -> List[str]:
        """
        분쟁해결기준 검색 전용 쿼리 확장 (Phase 2-10)

        품목명을 분쟁해결기준 카테고리로 변환하고,
        분쟁유형을 기준 키워드로 변환합니다.
        """
        try:
            from app.agents.query_analysis.llm_expander import expand_query_for_criteria_search

            # task_input에서 추출된 정보 가져오기
            item = ""
            channel = ""
            dispute_type = ""
            keywords = []

            if task_input:
                keywords = task_input.get("agent_keywords") or []
                metadata_filter = task_input.get("metadata_filter") or {}

                # query_analysis에서 추출된 정보 활용
                if "item" in metadata_filter:
                    item = metadata_filter["item"]
                if "channel" in metadata_filter:
                    channel = metadata_filter["channel"]

            # 쿼리에서 품목/분쟁유형 추론
            if not item:
                if any(kw in query for kw in ["노트북", "컴퓨터", "PC"]):
                    item = "노트북"
                elif any(kw in query for kw in ["핸드폰", "휴대폰", "스마트폰", "폰"]):
                    item = "핸드폰"
                elif any(kw in query for kw in ["TV", "티비", "텔레비전"]):
                    item = "TV"

            if not dispute_type:
                if any(kw in query for kw in ["환불", "반품", "취소"]):
                    dispute_type = "환불"
                elif any(kw in query for kw in ["교환", "바꿔"]):
                    dispute_type = "교환"
                elif any(kw in query for kw in ["수리", "고장", "결함", "하자"]):
                    dispute_type = "하자"

            criteria_queries = await expand_query_for_criteria_search(
                query=query,
                item=item,
                channel=channel,
                dispute_type=dispute_type,
                keywords=keywords,
                timeout=5.0,
            )

            return criteria_queries

        except Exception as e:
            logger.warning(f"[CriteriaAgent] Criteria-specific expansion failed: {e}")
            return []

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
