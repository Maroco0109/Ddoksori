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
    value = value.strip().lower()
    value = re.sub(r"[^0-9a-z가-힣]+", "", value)
    return value


def _strip_korean_particle(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    return re.sub(
        r"(을|를|은|는|이|가|과|와|의|에|에서|으로|로|랑|하고|도|만|까지|부터|께|처럼|보다|마다|밖에|마저|조차|이나|나|라도|든지|든|께서|에게|한테|에서)$",
        "",
        value,
    ).strip()


@lru_cache(maxsize=1)
def _load_product_hierarchy() -> Tuple[Dict[str, Dict[str, str]], Dict[str, List[str]]]:
    """product_hierarchy.json 로드 + 소분류 목록 캐시"""
    base_dir = Path(__file__).resolve().parents[3]  # backend/
    path = base_dir / "data" / "category" / "product_hierarchy.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    normalized_map: Dict[str, Dict[str, str]] = {}
    subcategories = set()

    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        item = entry.get("item") or key
        normalized_map[_normalize_keyword(item)] = {
            "keyword": item,
            "subcategory_name": entry.get("subcategory_name"),
            "source": "rule",
        }
        if entry.get("subcategory_name"):
            subcategories.add(entry.get("subcategory_name"))

    hierarchy = {
        "subcategories": sorted(subcategories),
    }
    return normalized_map, hierarchy


@lru_cache(maxsize=1)
def _load_item_subcategory_map() -> Dict[str, Dict[str, str]]:
    """product_hierarchy.json 로드 (item -> subcategory)."""
    base_dir = Path(__file__).resolve().parents[3]  # backend/
    path = base_dir / "data" / "category" / "product_hierarchy.json"
    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    item_map: Dict[str, Dict[str, str]] = {}
    if isinstance(data, dict):
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            item = entry.get("item") or key
            subcategory = entry.get("subcategory_name")
            if not item or not subcategory:
                continue
            normalized = _normalize_keyword(item)
            if not normalized:
                continue
            item_map[normalized] = {
                "keyword": item,
                "subcategory_name": subcategory,
                "source": "rule",
            }
    return item_map


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
    text = text.strip().replace("\ufeff", "")
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
    if "[" in text and "]" in text:
        start = text.find("[")
        end = text.rfind("]") + 1
        return text[start:end].strip()
    if "{" in text and "}" in text:
        # Fallback: return dict list without brackets, caller may wrap.
        start = text.find("{")
        end = text.rfind("}") + 1
        return text[start:end].strip()
    return None


def _safe_json_load(text: str) -> Tuple[Optional[Any], Optional[str]]:
    """LLM JSON 응답 파싱을 위한 안전 로더."""
    if not text:
        return None, "empty"
    cleaned = text.strip().replace("\ufeff", "")
    # If it's a comma-separated list of objects without brackets, wrap it.
    if cleaned.startswith("{") and not cleaned.startswith("["):
        if re.search(r"}\s*,\s*{", cleaned):
            cleaned = f"[{cleaned}]"
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError:
        pass  # First attempt failed, try with cleanup below
    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError as exc:
        return None, f"json.loads after cleanup failed: {exc.msg} at {exc.pos}"


def _classify_with_llm(
    keywords: List[str],
    hierarchy: Dict[str, List[str]],
) -> List[Dict[str, str]]:
    """매핑 실패 키워드만 LLM으로 소분류 분류"""
    if not keywords:
        return []

    try:
        from dotenv import load_dotenv
        from openai import OpenAI

        from app.common.config import get_config

        # dotenv 로드 및 OpenAI 키 사용 (backend/.env)
        backend_dir = Path(__file__).resolve().parents[3]
        load_dotenv(dotenv_path=backend_dir / ".env")
        config = get_config().llm
        if not config.openai_api_key:
            logger.warning(
                "[CriteriaRetrieval] OPENAI_API_KEY missing, skipping classify"
            )
            return []

        client = OpenAI(api_key=config.openai_api_key)

        system_prompt = (
            "너는 소비자 분쟁 품목 분류 전문가다. "
            "주어진 키워드를 아래 소분류 목록 중 하나로 분류하라. "
            "분류가 필요없는 키워드는 제외하라. "
            "반드시 제공된 목록 값만 사용하라."
        )

        user_prompt = (
            "분류 체계 목록:\n"
            f"- 소분류(subcategory_name): {hierarchy['subcategories']}\n\n"
            "분류 대상 키워드:\n"
            f"{keywords}\n\n"
            "출력은 JSON 배열로만 반환하라. 예시:\n"
            "[\n"
            '  {"keyword":"위스키","subcategory_name":"주류"}\n'
            "]\n\n"
            "분류가 필요없는 키워드는 배열에 포함하지 마라."
        )

        print(f"[CriteriaRetrieval][DEBUG] LLM candidates: {keywords}")
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
        print(f"[CriteriaRetrieval][DEBUG] LLM raw: {content[:500]}")
        json_block = _extract_json_block(content) or "[]"
        parsed, parse_error = _safe_json_load(json_block)
        if parsed is None:
            logger.warning(
                "[CriteriaRetrieval] LLM response JSON parse failed (%s). raw=%s block=%s",
                parse_error,
                content[:500],
                repr(json_block)[:500],
            )
            return []
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
                    "subcategory_name": item.get("subcategory_name"),
                    "source": "llm",
                }
            )
        if not results and keywords:
            logger.warning(
                "[CriteriaRetrieval] LLM returned empty results. raw=%s",
                content[:500],
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
        self._last_keywords: List[str] = []

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
        item_map = _load_item_subcategory_map()
        for kw in list(remaining_keywords):
            normalized = _normalize_keyword(kw)
            if normalized in rule_map:
                mapped = dict(rule_map[normalized])
                mapped["keyword"] = kw
                keyword_category_map.append(mapped)
                remaining_keywords.remove(kw)
                continue
            if normalized in item_map:
                mapped = dict(item_map[normalized])
                mapped["keyword"] = kw
                keyword_category_map.append(mapped)
                remaining_keywords.remove(kw)

        llm_candidates = []
        for kw in remaining_keywords:
            if not _is_classification_candidate(kw):
                continue
            cleaned = _strip_korean_particle(kw)
            if not cleaned:
                continue
            llm_candidates.append(cleaned)
        llm_candidates = list(dict.fromkeys(llm_candidates))
        llm_results = _classify_with_llm(llm_candidates, hierarchy)
        keyword_category_map.extend(llm_results)

        # 이번 요청에 대한 분류 결과 저장
        self._last_keyword_category_map = keyword_category_map
        self._last_keywords = list(
            dict.fromkeys(
                [
                    k.get("keyword")
                    for k in keyword_category_map
                    if isinstance(k, dict) and k.get("keyword")
                ]
            )
        )

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
                        rrf_k,
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
                        {"subcategory_name": category_set.get("subcategory_name")},
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
                if not final_results:
                    ranked = await _search_and_fuse(expanded_queries, per_query_k)
                    final_results = ranked[:top_k]
            else:
                ranked = await _search_and_fuse(expanded_queries, per_query_k)
                final_results = ranked[:top_k]

            # Build parent chunk_id lookups for content augmentation (parent_chunk_id only).
            parent_ids: List[str] = []
            for result in final_results:
                meta = result.metadata if isinstance(result.metadata, dict) else {}
                parent_chunk_id = meta.get("parent_chunk_id")
                if isinstance(parent_chunk_id, str) and parent_chunk_id:
                    parent_ids.append(parent_chunk_id)

            parent_texts = retriever.fetch_chunk_texts(list(set(parent_ids)))

            for result in final_results:
                meta = result.metadata if isinstance(result.metadata, dict) else {}
                parent_chunk_id = meta.get("parent_chunk_id")
                if not (isinstance(parent_chunk_id, str) and parent_chunk_id):
                    # No parent_chunk_id -> leave text as-is.
                    continue

                chunk_id = result.chunk_id or ""
                parts = chunk_id.split("_")
                if len(parts) < 2:
                    continue
                last = parts[-1]
                second_last = parts[-2]

                is_grandchild = bool(
                    re.match(r"^조건\d+_?하위\d+$", f"{second_last}_{last}")
                )
                is_child = bool(re.match(r"^조건\d+$", last))

                parent_text = parent_texts.get(parent_chunk_id, "")
                current_text = result.text or ""
                parent_cap = 400
                current_cap = 600
                max_total = 1000
                parent_trim = parent_text[:parent_cap]
                current_trim = current_text[:current_cap]
                used = len(parent_trim) + len(current_trim)
                remaining = max_total - used
                if remaining > 0:
                    extra = min(
                        remaining, max(0, len(current_text) - len(current_trim))
                    )
                    current_trim += current_text[
                        len(current_trim) : len(current_trim) + extra
                    ]

                if is_grandchild:
                    label = "[하위]"
                elif is_child:
                    label = "[조건]"
                else:
                    label = "[내용]"

                composed = "\n".join(
                    [
                        "[부모]",
                        parent_trim,
                        "",
                        label,
                        current_trim,
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
            major = raw_meta.get("대분류")
            middle = raw_meta.get("중분류")
            sub = raw_meta.get("소분류")
            category_path = " > ".join([p for p in [major, middle, sub] if p])
            # Remove redundant/verbose metadata fields.
            for key in (
                "대분류",
                "중분류",
                "소분류",
                "created_at",
                "is_indexed",
                "embedded_at",
                "embedding_model",
                "embedding_dimensions",
                "has_embedding",
            ):
                merged_meta.pop(key, None)
            merged_meta.update(
                {
                    "source_label": raw_meta.get("source_label"),
                    "category": category_path or r.category,
                    "item": list(self._last_keywords),
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
        # NOTE: MAS pipeline discards per-agent sources; keep this as a no-op.
        # return [
        #     {
        #         "type": "criteria",
        #         "index": i + 1,
        #         "chunk_id": r.chunk_id,
        #         "category": r.category,
        #         "source_label": (r.metadata or {}).get("source_label"),
        #         "item": (r.metadata or {}).get("item"),
        #         "hierarchy_path": (r.metadata or {}).get("hierarchy_path"),
        #         "similarity": r.similarity,
        #     }
        #     for i, r in enumerate(results)
        # ]
        return []


criteria_retrieval_agent = CriteriaRetrievalAgent()

__all__ = ["CriteriaRetrievalAgent", "criteria_retrieval_agent"]
