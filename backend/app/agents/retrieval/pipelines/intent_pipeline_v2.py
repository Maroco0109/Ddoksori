from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from ..tools.retriever import SearchResult


@dataclass
class IntentPipelineV2:
    def build_queries(
        self,
        original_query: str,
        intent_label: str,
        slots: dict,
    ) -> List[str]:
        queries: List[str] = []
        q0 = original_query.strip()
        if q0:
            queries.append(q0)

        slot_terms = [v for v in slots.values() if isinstance(v, str) and v.strip()]
        intent_terms = (
            [intent_label] if intent_label and intent_label != "other" else []
        )
        q1 = " ".join(intent_terms + slot_terms).strip()
        if q1 and q1 not in queries:
            queries.append(q1)

        q2_parts = [intent_label] if intent_label else []
        q2 = " ".join(q2_parts).strip()
        if q2 and q2 not in queries:
            queries.append(q2)

        return queries

    def trigger_second_pass(
        self,
        results: Sequence[SearchResult],
        expected_keywords: Sequence[str],
        t_range: Tuple[float, float] = (0.35, 0.45),
    ) -> bool:
        if not results:
            return True

        top1_similarity = results[0].similarity or 0.0
        if top1_similarity < max(t_range):
            return True

        if self._unique_doc_ids(results) < 3:
            return True

        if expected_keywords:
            matches = self._count_keyword_hits(results[:3], expected_keywords)
            if matches <= 1:
                return True

        return False

    def rerank_and_dedupe(
        self,
        results: Sequence[SearchResult],
        expected_keywords: Sequence[str],
    ) -> List[SearchResult]:
        scored = []
        for item in results:
            text = f"{item.doc_title} {item.content}".lower()
            keyword_hits = sum(1 for k in expected_keywords if k.lower() in text)
            recency_boost = 0.01 if item.decision_date else 0.0
            score = (item.similarity or 0.0) + (0.05 * keyword_hits) + recency_boost
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        deduped: List[SearchResult] = []
        seen_keys = set()
        for _, item in scored:
            key = item.doc_id or item.url or item.chunk_id
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)

        return deduped

    def select_evidence(
        self,
        results: Sequence[SearchResult],
        min_n: int = 3,
        max_n: int = 7,
    ) -> List[SearchResult]:
        if not results:
            return []

        selected = list(results[:max_n])
        if len(selected) >= min_n:
            return selected
        return selected

    def _unique_doc_ids(self, results: Sequence[SearchResult]) -> int:
        keys = set()
        for item in results:
            key = item.doc_id or item.url or item.chunk_id
            if key:
                keys.add(key)
        return len(keys)

    def _count_keyword_hits(
        self, results: Iterable[SearchResult], keywords: Sequence[str]
    ) -> int:
        count = 0
        for item in results:
            text = f"{item.doc_title} {item.content}".lower()
            if any(k.lower() in text for k in keywords):
                count += 1
        return count
