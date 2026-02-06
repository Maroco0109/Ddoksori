"""LawRetrievalAgent - 법령 검색 전용 에이전트. LLM: 2.4B (EXAONE)

Phase 2-10: 법령 전용 쿼리 확장 적용
- 자연어 → 법률 용어 변환 (환불 → 청약철회)
- 관련 법률명 자동 추가 (전자상거래법 등)
"""

import asyncio
import logging
import re
from typing import Any, ClassVar, Dict, List, TypedDict

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config
from .tools.rds_internal_retriever import SimilarChunkResult
from .tools.specialized_retrievers import LawRetriever

logger = logging.getLogger(__name__)


class LawDocument(TypedDict):
    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    similarity: float


class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = (
        "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."
    )

    async def _execute_search(
        self,
        query: str,
        top_k: int,
        task_input: Dict[str, Any] | None = None,
    ) -> List[SimilarChunkResult]:
        db_config = _get_db_config()
        retriever = LawRetriever(db_config)
        retriever.connect()

        try:
            # PRIORITY 1: 조문 번호 직접 검색 (chunk_id 패턴 매칭)
            article_pattern = r'([\w가-힣]+법?)\s*제?(\d+)조'
            article_match = re.search(article_pattern, query)

            direct_results: List[SimilarChunkResult] = []
            if article_match:
                law_name_part = article_match.group(1)
                article_num = article_match.group(2)

                # 법률명 정규화 ("법" suffix가 없으면 추가)
                if not law_name_part.endswith("법"):
                    law_name_part = law_name_part + "법"

                logger.info(
                    f"[LawAgent] Article pattern detected: {law_name_part} 제{article_num}조, "
                    f"attempting direct chunk_id lookup"
                )

                direct_results = retriever.direct_search_by_article_number(
                    law_name_part, article_num
                )

                if direct_results:
                    logger.info(
                        f"[LawAgent] Direct lookup SUCCESS: found {len(direct_results)} chunks"
                    )
                    # Direct match gets top priority - assign high RRF scores
                    for idx, result in enumerate(direct_results):
                        result.similarity = 10.0 - idx * 0.1  # Very high base score
                        result.rrf_score = 10.0 - idx * 0.1

                    # If we found direct matches, we can return early or supplement with hybrid search
                    if len(direct_results) >= top_k:
                        return direct_results[:top_k]

            # PRIORITY 2: Hybrid search with query expansion
            # Phase 2-10: 법령 전용 쿼리 확장 적용
            law_specific_queries = await self._expand_for_law_search(query, task_input)

            # 기존 expanded_queries와 병합
            expanded_queries: List[str] = []
            if task_input:
                expanded_queries = task_input.get("expanded_queries") or []

            # 법령 전용 쿼리를 우선 사용, 기존 쿼리는 보조로 추가
            all_queries = law_specific_queries.copy()
            for eq in expanded_queries:
                if eq not in all_queries:
                    all_queries.append(eq)
            all_queries = all_queries[:6]  # 최대 6개로 제한

            if not all_queries:
                all_queries = [query]

            logger.info(
                f"[LawAgent] Using {len(all_queries)} queries: "
                f"law_specific={len(law_specific_queries)}, original={len(expanded_queries)}"
            )

            document_types = None
            if task_input:
                metadata_filter = task_input.get("metadata_filter") or {}
                document_types = metadata_filter.get("document_types") or None
            per_query_k = max(top_k, 12)
            all_results: List[List[SimilarChunkResult]] = []
            for q in all_queries:
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

            # Merge direct results first (highest priority)
            for result in direct_results:
                chunk_id = result.chunk_id
                fused_scores[chunk_id] = result.similarity
                fused_results[chunk_id] = result

            # Then merge hybrid search results
            for results in all_results:
                for rank, result in enumerate(results, start=1):
                    chunk_id = result.chunk_id
                    # Don't overwrite direct match scores
                    if chunk_id in direct_results:
                        continue
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

    async def _expand_for_law_search(
        self, query: str, task_input: Dict[str, Any] | None
    ) -> List[str]:
        """
        법령 검색 전용 쿼리 확장 (Phase 2-10)

        자연어 쿼리를 법률 용어가 포함된 쿼리로 변환합니다.
        """
        try:
            from app.agents.query_analysis.llm_expander import expand_query_for_law_search

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

            # 쿼리에서 채널/분쟁유형 추론
            if not channel:
                if any(kw in query for kw in ["온라인", "인터넷", "쿠팡", "배달", "앱"]):
                    channel = "온라인구매"
                elif any(kw in query for kw in ["방문", "집으로"]):
                    channel = "방문판매"

            if not dispute_type:
                if any(kw in query for kw in ["환불", "반품", "취소"]):
                    dispute_type = "환불"
                elif any(kw in query for kw in ["교환", "바꿔"]):
                    dispute_type = "교환"
                elif any(kw in query for kw in ["수리", "고장", "결함"]):
                    dispute_type = "하자"

            law_queries = await expand_query_for_law_search(
                query=query,
                item=item,
                channel=channel,
                dispute_type=dispute_type,
                keywords=keywords,
                timeout=5.0,  # LLM 타임아웃 증가 (3초 → 5초)
            )

            return law_queries

        except Exception as e:
            logger.warning(f"[LawAgent] Law-specific expansion failed: {e}")
            return []

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
