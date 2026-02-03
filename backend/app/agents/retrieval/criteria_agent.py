"""CriteriaRetrievalAgent - 분쟁조정기준 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Tuple, TypedDict

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config
from .tools.rds_internal_retriever import SimilarChunkResult
from .tools.specialized_retrievers import CriteriaRetriever

logger = logging.getLogger(__name__)

# 분류 제외 키워드(품목이 아닌 법령/절차/질문 표현)
NON_ITEM_KEYWORDS = {
    "법",
    "법률",
    "규정",
    "조항",
    "조문",
    "가능",
    "가능해요",
    "여부",
    "방법",
    "절차",
    "기간",
    "환불",
    "교환",
    "수리",
    "해요",
    "되나요",
    "문의",
}

def _normalize_keyword(value: str) -> str:
    return value.strip().lower().replace(" ", "")


@lru_cache(maxsize=1)
def _load_product_hierarchy() -> Tuple[Dict[str, Dict[str, str]], Dict[str, List[str]]]:
    """product_hierarchy.json 로드 + 분류 목록 캐시"""
    base_dir = Path(__file__).resolve().parents[3]  # backend/
    path = base_dir / "data" / "category" / "product_hierarchy.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    normalized_map: Dict[str, Dict[str, str]] = {}
    sections = set()
    categories = set()
    subcategories = set()

    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        item = entry.get("item") or key
        normalized_map[_normalize_keyword(item)] = {
            "keyword": item,
            "section_name": entry.get("section_name"),
            "category_name": entry.get("category_name"),
            "subcategory_name": entry.get("subcategory_name"),
            "source": "rule",
        }
        if entry.get("section_name"):
            sections.add(entry.get("section_name"))
        if entry.get("category_name"):
            categories.add(entry.get("category_name"))
        if entry.get("subcategory_name"):
            subcategories.add(entry.get("subcategory_name"))

    hierarchy = {
        "sections": sorted(sections),
        "categories": sorted(categories),
        "subcategories": sorted(subcategories),
    }
    return normalized_map, hierarchy


def _is_classification_candidate(keyword: str) -> bool:
    """품목 분류가 필요한 키워드인지 1차 판단"""
    if not keyword:
        return False
    if len(keyword.strip()) < 2:
        return False
    if keyword in NON_ITEM_KEYWORDS:
        return False
    if "법" in keyword:
        return False
    return True


def _extract_json_block(text: str) -> Optional[str]:
    """LLM 응답에서 JSON 블록만 추출"""
    text = text.strip()
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        return text[start:end].strip()
    if "[" in text and "]" in text:
        start = text.find("[")
        end = text.rfind("]") + 1
        return text[start:end].strip()
    return None


def _classify_with_llm(
    keywords: List[str],
    hierarchy: Dict[str, List[str]],
) -> List[Dict[str, str]]:
    """매핑 실패 키워드만 LLM으로 대/중/소 분류"""
    if not keywords:
        return []

    try:
        from dotenv import load_dotenv
        from openai import OpenAI
        from app.common.config import get_config

        #dotenv 로드 및 OpenAI 키 사용
        load_dotenv()
        config = get_config().llm
        if not config.openai_api_key:
            logger.warning("[CriteriaRetrieval] OPENAI_API_KEY missing, skipping classify")
            return []

        client = OpenAI(api_key=config.openai_api_key)

        system_prompt = (
            "너는 소비자 분쟁 품목 분류 전문가다. "
            "주어진 키워드를 아래 분류 체계(대/중/소) 중 하나씩으로 분류하라. "
            "분류가 필요없는 키워드는 제외하라. "
            "반드시 제공된 목록 값만 사용하라."
        )

        user_prompt = (
            "분류 체계 목록:\n"
            f"- 대분류(section_name): {hierarchy['sections']}\n"
            f"- 중분류(category_name): {hierarchy['categories']}\n"
            f"- 소분류(subcategory_name): {hierarchy['subcategories']}\n\n"
            "분류 대상 키워드:\n"
            f"{keywords}\n\n"
            "출력은 JSON 배열로만 반환하라. 예시:\n"
            "[\n"
            "  {\"keyword\":\"위스키\",\"section_name\":\"상품(재화) 부문\",\"category_name\":\"식료품\",\"subcategory_name\":\"주류\"}\n"
            "]\n\n"
            "분류가 필요없는 키워드는 배열에 포함하지 마라."
        )

        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        content = response.choices[0].message.content or ""
        json_block = _extract_json_block(content) or "[]"
        parsed = json.loads(json_block)
        if not isinstance(parsed, list):
            return []
        results = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            if not item.get("keyword"):
                continue
            results.append(
                {
                    "keyword": item.get("keyword"),
                    "section_name": item.get("section_name"),
                    "category_name": item.get("category_name"),
                    "subcategory_name": item.get("subcategory_name"),
                    "source": "llm",
                }
            )
        return results
    except Exception as e:
        logger.warning(f"[CriteriaRetrieval] LLM classify error: {e}")
        return []


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

    def __init__(self) -> None:
        super().__init__()
        self._last_keyword_category_map: List[Dict[str, str]] = []

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """분류 결과를 응답에 포함"""
        response = await super().process(request)
        if response.get("status") == "success":
            result = response.get("result") or {}
            result["keyword_category_map"] = self._last_keyword_category_map
            response["result"] = result
        return response

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

        document_types = None
        if task_input:
            metadata_filter = task_input.get("metadata_filter") or {}
            document_types = metadata_filter.get("document_types") or None

        # keywords 기반 품목 분류
        keywords = (task_input or {}).get("agent_keywords") or []
        keyword_category_map: List[Dict[str, str]] = []
        remaining_keywords = list(keywords)

        rule_map, hierarchy = _load_product_hierarchy()
        for kw in list(remaining_keywords):
            normalized = _normalize_keyword(kw)
            if normalized in rule_map:
                mapped = dict(rule_map[normalized])
                mapped["keyword"] = kw
                keyword_category_map.append(mapped)
                remaining_keywords.remove(kw)

        llm_candidates = [
            kw for kw in remaining_keywords if _is_classification_candidate(kw)
        ]
        llm_results = _classify_with_llm(llm_candidates, hierarchy)
        keyword_category_map.extend(llm_results)

        # 이번 요청에 대한 분류 결과 저장
        self._last_keyword_category_map = keyword_category_map

        retriever = CriteriaRetriever(db_config)
        retriever.connect()

        try:
            from app.common.config import get_config

            rrf_k = get_config().retrieval.rrf_k_python

            async def _search_and_fuse(
                queries: List[str],
                per_query_k: int,
                category_set: Optional[Dict[str, str]] = None,
            ) -> List[SimilarChunkResult]:
                all_results: List[List[SimilarChunkResult]] = []
                for q in queries:
                    results = await asyncio.to_thread(
                        retriever.criteria_search,
                        q,
                        per_query_k,
                        document_types,
                        category_set,
                    )
                    all_results.append(results)

                fused_scores: Dict[str, float] = {}
                fused_results: Dict[str, SimilarChunkResult] = {}
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

                return sorted(
                    fused_results.values(),
                    key=lambda r: r.similarity,
                    reverse=True,
                )

            # 분류 세트별 검색 → 병합 TopK
            per_query_k = max(top_k * 3, 12)
            if keyword_category_map:
                merged: Dict[str, SimilarChunkResult] = {}
                for category_set in keyword_category_map:
                    ranked = await _search_and_fuse(
                        expanded_queries,
                        per_query_k,
                        category_set,
                    )
                    for r in ranked:
                        if (
                            r.chunk_id not in merged
                            or merged[r.chunk_id].similarity < r.similarity
                        ):
                            merged[r.chunk_id] = r
                final_results = sorted(
                    merged.values(),
                    key=lambda r: r.similarity,
                    reverse=True,
                )[:top_k]
            else:
                ranked = await _search_and_fuse(expanded_queries, per_query_k)
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
