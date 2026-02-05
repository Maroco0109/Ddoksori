"""CaseRetrievalAgent - 상담/조정/해결 통합(case) 검색 에이전트."""

import asyncio
import json
import logging
import math
import os
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.rds_retriever import RDSRetriever


class CaseRetrievalAgent(BaseRetrievalAgent):
    """상담/조정/해결 통합(case) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_case"
    agent_description: ClassVar[str] = "상담/조정/해결 통합 사례를 검색합니다."
    default_dataset: ClassVar[str] = "case"
    retrieval_source: ClassVar[str] = "case_combined"
    logger = logging.getLogger(__name__)

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        response = await super().process(request)
        result = response.get("result")
        if isinstance(result, dict):
            documents = result.get("documents") or result.get("results") or []
            result["documents"] = documents
            result["source"] = "case"
            if documents:
                max_sim = max(
                    (d.get("similarity", 0.0) for d in documents), default=0.0
                )
                avg_sim = sum((d.get("similarity", 0.0) for d in documents)) / len(
                    documents
                )
                result["max_similarity"] = max_sim
                result["avg_similarity"] = avg_sim
        return response

    @staticmethod
    def _score_case_categories(
        query: str, query_analysis: Dict[str, Any]
    ) -> Tuple[Dict[str, int], Dict[str, bool]]:
        """Rule-based scoring for 상담/조정/해결."""
        scores = {"상담": 0, "조정": 0, "해결": 0}
        strong_hits = {"조정": False, "해결": False}

        # 1) Use explicit hints from query_analysis if present
        for key in ("case_category", "case_subtype", "subtype", "subtype_label"):
            value = query_analysis.get(key)
            if value in ("상담", "조정", "해결"):
                scores[value] = 999
                strong_hits["조정"] = value == "조정"
                strong_hits["해결"] = value == "해결"
                return scores, strong_hits
            if value in ("조정+해결", "조정_해결", "통합"):
                scores["조정"] = 999
                scores["해결"] = 999
                strong_hits["조정"] = True
                strong_hits["해결"] = True
                return scores, strong_hits

        normalized = (query or "").strip().lower()
        if not normalized:
            return scores, strong_hits

        def _count_hits(text: str, keywords: Tuple[str, ...]) -> int:
            return sum(1 for k in keywords if k in text)

        # A) 조정 (분쟁조정/절차)
        adjust_strong = (
            "분쟁조정",
            "조정신청",
            "조정 접수",
            "조정위원회",
            "조정 결정",
            "조정 결과",
            "합의가 안돼",
            "합의 안돼",
            "합의 실패",
            "중재",
            "조정으로 가고 싶어",
            "상대방이 거부",
            "업체가 끝까지 거부",
            "대화가 안됨",
            "분쟁이 커짐",
        )
        adjust_mid = (
            "분쟁",
            "다툼",
            "쟁점",
            "서로 주장",
            "책임 공방",
            "민원 넣었는데 해결 안됨",
            "소비자원 조정 가능",
            "조정 절차",
            "조정 기간",
            "조정 서류",
        )
        adjust_weak = ("조정 가능", "조정 대상", "조정 신청서", "조정")

        # B) 해결 (피해구제/조치)
        relief_strong = (
            "배상",
            "손해배상",
            "보상",
            "위약금",
            "하자",
            "불량",
            "파손",
            "누수",
            "고장",
            "미배송",
            "배송지연",
            "오배송",
            "누락",
            "취소했는데 결제됨",
            "계약해지",
            "청약철회",
            "철회",
            "해지",
            "취소 수수료",
            "증빙",
            "영수증",
            "결제내역",
            "통화녹음",
            "사진",
            "진단서",
        )
        action_terms = (
            "환불",
            "환급",
            "교환",
            "반품",
            "수리",
            "as",
            "취소",
            "해지",
            "철회",
            "청약철회",
        )
        relief_mid = (
            "거부당함",
            "안해줌",
            "연락두절",
            "환불 거부",
            "거부",
        )
        relief_weak = ("어떻게 받아", "뭘 요구", "요구할 수 있어")

        # C) 상담 (안내/가능 여부)
        counsel_strong = (
            "상담",
            "문의",
            "안내",
            "절차",
            "방법",
            "준비서류",
            "기간",
            "어디에 연락",
            "가능한가요",
            "되나요",
            "해도 되나요",
            "권리",
            "의무",
            "주의사항",
            "유의점",
            "제가 뭘 하면",
            "제가 무엇을 하면",
        )
        counsel_request = (
            "요청",
            "원해",
            "원합니다",
            "받고 싶",
            "받고싶",
            "해주",
            "해주세요",
            "해 줘",
            "해줘",
            "가능",
            "될까",
            "할 수",
            "할수",
            "해주실",
        )
        counsel_mid = (
            "환불 되나요",
            "불법인가요",
            "어떻게 해야",
            "기준",
            "규정",
        )
        counsel_weak = ("정리해줘", "요약해줘", "선택지", "어떤 선택")

        scores["조정"] += 3 * _count_hits(normalized, adjust_strong)
        scores["조정"] += 2 * _count_hits(normalized, adjust_mid)
        scores["조정"] += 1 * _count_hits(normalized, adjust_weak)

        scores["해결"] += 3 * _count_hits(normalized, relief_strong)
        scores["해결"] += 1 * _count_hits(normalized, action_terms)
        scores["해결"] += 2 * _count_hits(normalized, relief_mid)
        scores["해결"] += 1 * _count_hits(normalized, relief_weak)

        scores["상담"] += 3 * _count_hits(normalized, counsel_strong)
        scores["상담"] += 2 * _count_hits(normalized, counsel_request)
        scores["상담"] += 2 * _count_hits(normalized, counsel_mid)
        scores["상담"] += 1 * _count_hits(normalized, counsel_weak)

        # Numeric details signal -> 해결 +2
        if any(ch.isdigit() for ch in normalized):
            scores["해결"] += 2

        strong_hits["조정"] = _count_hits(normalized, adjust_strong) > 0
        strong_hits["해결"] = _count_hits(normalized, relief_strong) > 0
        return scores, strong_hits

    @staticmethod
    def _allocate_quotas(
        top_k: int,
        weights: Dict[str, int],
        strong_hits: Dict[str, bool],
        scores: Dict[str, int],
    ) -> Dict[str, int]:
        total_weight = sum(weights.values()) or 1
        raw = {k: (weights[k] / total_weight) * top_k for k in weights}
        quotas = {k: int(raw[k]) for k in weights}
        remaining = top_k - sum(quotas.values())
        if remaining > 0:
            frac = sorted(
                weights.keys(), key=lambda k: raw[k] - quotas[k], reverse=True
            )
            for k in frac:
                if remaining <= 0:
                    break
                quotas[k] += 1
                remaining -= 1

        # Minimum guarantee for strong signals (if possible)
        for cat, hit in strong_hits.items():
            if hit:
                quotas[cat] = max(quotas.get(cat, 0), min(3, top_k))

        # If guarantees exceed top_k, reduce lowest-score categories
        while sum(quotas.values()) > top_k:
            lowest = sorted(quotas.keys(), key=lambda k: (scores.get(k, 0), quotas[k]))[
                0
            ]
            if quotas[lowest] > 0:
                quotas[lowest] -= 1
            else:
                break

        return quotas

    @staticmethod
    def _track_quotas(
        top_k: int,
        confident: bool,
        winner_track: str,
        scores: Dict[str, int],
        strong_hits: Dict[str, bool],
    ) -> Tuple[int, int, float]:
        def _min_counsel_quota(k: int) -> int:
            if k <= 2:
                return 0
            if k <= 5:
                return 1
            return max(1, round(k * 0.2))

        def _is_dispute_strong() -> bool:
            combined_score = scores.get("조정", 0) + scores.get("해결", 0)
            counsel_score = scores.get("상담", 0)
            if strong_hits.get("조정") or strong_hits.get("해결"):
                return True
            if combined_score - counsel_score >= 4:
                return True
            return False

        if top_k <= 5:
            if confident:
                winner_quota = min(top_k - 1, max(1, top_k - 1))
            else:
                winner_quota = 3 if top_k == 5 else 2 if top_k in (3, 4) else 1
            other_quota = max(top_k - winner_quota, 1) if top_k > 1 else 0
            if winner_track == "분쟁/구제":
                dispute_quota = winner_quota
                counsel_quota = other_quota
            else:
                counsel_quota = winner_quota
                dispute_quota = other_quota
            if top_k == 5 and not confident:
                counsel_quota = max(counsel_quota, 2)
                dispute_quota = max(top_k - counsel_quota, 1)
            ratio = dispute_quota / top_k if top_k else 0.0
            return counsel_quota, dispute_quota, ratio

        if confident:
            ratio = 0.7
            if winner_track == "분쟁/구제":
                dispute_quota = int(math.ceil(ratio * top_k))
                counsel_quota = top_k - dispute_quota
                min_counsel = _min_counsel_quota(top_k)
                if counsel_quota < min_counsel:
                    counsel_quota = min_counsel
                    dispute_quota = max(top_k - counsel_quota, 0)
            else:
                counsel_quota = int(math.ceil(ratio * top_k))
                dispute_quota = top_k - counsel_quota
        else:
            ratio = 0.5
            dispute_quota = int(math.ceil(ratio * top_k))
            counsel_quota = top_k - dispute_quota
            if winner_track == "분쟁/구제":
                min_counsel = _min_counsel_quota(top_k)
                if counsel_quota < min_counsel:
                    counsel_quota = min_counsel
                    dispute_quota = max(top_k - counsel_quota, 0)

        return counsel_quota, dispute_quota, ratio

    @staticmethod
    def _get_rank_mode_threshold() -> Tuple[str, float]:
        mode = os.getenv("CASE_RANK_MODE", "default").lower()
        if mode == "stable":
            return "stable", 0.01
        if mode == "threshold":
            try:
                threshold = float(os.getenv("CASE_RANK_THRESHOLD", "0.01"))
            except ValueError:
                threshold = 0.01
            return "threshold", threshold
        return "default", 0.01

    @staticmethod
    def _get_fill_policy() -> Dict[str, Any]:
        def _get_int(name: str, default: int) -> int:
            value = os.getenv(name)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default

        def _get_bool(name: str, default: bool) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            lowered = value.strip().lower()
            if lowered in ("1", "true", "yes", "y", "on"):
                return True
            if lowered in ("0", "false", "no", "n", "off"):
                return False
            return default

        max_stages = max(_get_int("CASE_FILL_MAX_STAGES", 3), 0)
        enable_broaden = _get_bool("CASE_FILL_ENABLE_BROADEN", True)
        max_db_calls = _get_int("CASE_FILL_MAX_DB_CALLS", 0)
        if max_db_calls < 0:
            max_db_calls = 0
        return {
            "max_stages": max_stages,
            "enable_broaden": enable_broaden,
            "max_db_calls": max_db_calls,
        }

    @staticmethod
    def _rank_key(item: Dict[str, Any]) -> Tuple[float, float, float]:
        rrf = float(item.get("rrf_score") or 0.0)
        vec = float(item.get("vector_similarity", item.get("similarity", 0.0)) or 0.0)
        bm25 = float(item.get("bm25_score") or 0.0)
        mode, threshold = CaseRetrievalAgent._get_rank_mode_threshold()
        if mode == "stable":
            return (rrf, vec, bm25)
        if mode == "threshold":
            if rrf <= threshold:
                return (vec, rrf, bm25)
            return (rrf, vec, bm25)
        if rrf <= 0.01:
            return (vec, rrf, bm25)
        return (rrf, vec, bm25)

    @classmethod
    def _best_rank_key(cls, results: List[Dict]) -> Tuple[float, float, float]:
        best = (0.0, 0.0, 0.0)
        for item in results or []:
            if not isinstance(item, dict):
                continue
            key = cls._rank_key(item)
            if key > best:
                best = key
        return best

    @staticmethod
    def _dedup_key(item: Dict[str, Any]) -> Any:
        metadata = item.get("metadata") or {}
        doc_id = metadata.get("doc_id") or item.get("doc_id")
        case_number = metadata.get("case_number")
        source_url = item.get("source_url") or item.get("url")
        chunk_id = item.get("chunk_id")
        return doc_id or case_number or source_url or chunk_id

    @staticmethod
    def _dedup_key_with_type(item: Dict[str, Any]) -> Tuple[str, Any]:
        metadata = item.get("metadata") or {}
        doc_id = metadata.get("doc_id") or item.get("doc_id")
        if doc_id:
            return "doc_id", doc_id
        case_number = metadata.get("case_number")
        if case_number:
            return "case_number", case_number
        source_url = item.get("source_url") or item.get("url")
        if source_url:
            return "url", source_url
        chunk_id = item.get("chunk_id")
        return "chunk_id", chunk_id

    @staticmethod
    def _broaden_query(query: str, winner_track: str) -> str:
        base = (query or "").strip()
        if not base:
            return base
        suffix = ""
        if winner_track == "상담":
            suffix = " 상담 사례"
        else:
            suffix = " 분쟁조정 사례"
        if suffix.strip() in base:
            return base
        return f"{base}{suffix}"

    def _decide_tracks_and_scores(
        self,
        query: str,
        query_analysis: Dict[str, Any],
        forced_combined: bool,
    ) -> Tuple[Dict[str, int], Dict[str, bool], Dict[str, Any]]:
        scores, strong_hits = self._score_case_categories(query, query_analysis)
        counsel_score = scores["상담"]
        combined_score = scores["조정"] + scores["해결"]
        score_gap = combined_score - counsel_score
        denom = float(counsel_score + combined_score) + 1e-6
        p_dispute = combined_score / denom
        confidence = abs(p_dispute - 0.5) * 2
        confident = confidence >= 0.8
        if counsel_score >= combined_score:
            winner_track = "상담"
        else:
            winner_track = "분쟁/구제"
        if forced_combined:
            confident = True
            winner_track = "분쟁/구제"
        meta = {
            "counsel_score": counsel_score,
            "combined_score": combined_score,
            "score_gap": score_gap,
            "p_dispute": p_dispute,
            "confidence": confidence,
            "confident": confident,
            "winner_track": winner_track,
        }
        return scores, strong_hits, meta

    def _decide_quotas(
        self,
        top_k: int,
        scores: Dict[str, int],
        strong_hits: Dict[str, bool],
        confident: bool,
        winner_track: str,
        meta: Dict[str, Any],
    ) -> Tuple[
        int, int, float, Dict[str, int], Optional[str], Optional[Dict[str, int]]
    ]:
        counsel_quota, dispute_quota, ratio = self._track_quotas(
            top_k, confident, winner_track, scores, strong_hits
        )

        dispute_split_reason = None
        min_split_guard = None
        if dispute_quota > 0:
            if scores["조정"] == 0 and scores["해결"] == 0:
                combined_weights = {"조정": 1, "해결": 1}
                dispute_split_reason = "score_zero"
            else:
                combined_weights = {
                    "조정": max(scores["조정"], 1),
                    "해결": max(scores["해결"], 1),
                }
                dispute_split_reason = "ratio_based"
            combined_quotas = self._allocate_quotas(
                dispute_quota,
                combined_weights,
                strong_hits,
                scores,
            )
        else:
            combined_quotas = {"조정": 0, "해결": 0}
            dispute_split_reason = "no_dispute_quota"

        guard_applied = {}
        if dispute_quota > 0:
            guard_value = min(3, dispute_quota)
            for cat in ("조정", "해결"):
                if strong_hits.get(cat) and combined_quotas.get(cat, 0) > 0:
                    guard_applied[cat] = guard_value
            if guard_applied:
                min_split_guard = guard_applied
                dispute_split_reason = "min_guard_applied"

        if dispute_quota > 0 and (
            combined_quotas.get("조정", 0) == 0 or combined_quotas.get("해결", 0) == 0
        ):
            zero_reason = "ratio_rounding"
            if combined_quotas.get("조정", 0) == 0:
                if scores["조정"] == 0:
                    zero_reason = "adjust_score_zero"
                elif dispute_quota <= 1:
                    zero_reason = "quota_too_small"
            if combined_quotas.get("해결", 0) == 0:
                if scores["해결"] == 0:
                    zero_reason = "relief_score_zero"
                elif dispute_quota <= 1:
                    zero_reason = "quota_too_small"
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_dispute_split",
                        "dispute_quota": dispute_quota,
                        "scores": {"조정": scores["조정"], "해결": scores["해결"]},
                        "split": {
                            "조정": combined_quotas.get("조정", 0),
                            "해결": combined_quotas.get("해결", 0),
                        },
                        "reason": zero_reason,
                    },
                    ensure_ascii=False,
                )
            )

        self.logger.info(
            json.dumps(
                {
                    "event": "case_quota_policy",
                    "K": top_k,
                    "confident": confident,
                    "winner_track": winner_track,
                    "ratio": ratio,
                    "counsel_score": meta["counsel_score"],
                    "combined_score": meta["combined_score"],
                    "score_gap": meta["score_gap"],
                    "p_dispute": meta["p_dispute"],
                    "confidence": meta["confidence"],
                    "category_scores": {
                        "상담": float(scores["상담"]),
                        "조정": float(scores["조정"]),
                        "해결": float(scores["해결"]),
                    },
                    "dispute_split_reason": dispute_split_reason,
                    "min_split_guard": min_split_guard,
                    "quotas": {
                        "counsel": counsel_quota,
                        "dispute": dispute_quota,
                    },
                    "dispute_split": combined_quotas,
                },
                ensure_ascii=False,
            )
        )

        return (
            counsel_quota,
            dispute_quota,
            ratio,
            combined_quotas,
            dispute_split_reason,
            min_split_guard,
        )

    async def _search_by_quotas(
        self,
        query: str,
        filter_dataset: Optional[str],
        counsel_quota: int,
        combined_quotas: Dict[str, int],
        search_fn,
    ) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict]]:
        combined: List[Dict] = []
        counsel_results: List[Dict] = []
        adjust_results: List[Dict] = []
        relief_results: List[Dict] = []

        if counsel_quota > 0:
            counsel_results = await asyncio.to_thread(
                search_fn,
                query,
                filter_dataset,
                "상담",
                counsel_quota,
            )
            combined += counsel_results

        for cat in ("조정", "해결"):
            quota = combined_quotas.get(cat, 0)
            if quota <= 0:
                continue
            results = await asyncio.to_thread(
                search_fn,
                query,
                filter_dataset,
                cat,
                quota,
            )
            if cat == "조정":
                adjust_results = results
            else:
                relief_results = results
            combined += results

        return combined, counsel_results, adjust_results, relief_results

    async def _apply_quality_gate(
        self,
        query: str,
        filter_dataset: Optional[str],
        combined: List[Dict],
        counsel_results: List[Dict],
        adjust_results: List[Dict],
        relief_results: List[Dict],
        winner_track: str,
        search_fn,
    ) -> Tuple[
        List[Dict],
        List[Dict],
        str,
        int,
        Tuple[float, float, float],
        Tuple[float, float, float],
        float,
    ]:
        extra_counsel = 0
        best_counsel = self._best_rank_key(counsel_results)
        best_dispute = self._best_rank_key(adjust_results + relief_results)
        delta = best_counsel[0] - best_dispute[0]
        winner_track_after_gate = winner_track
        if winner_track == "분쟁/구제":
            if delta >= 0.05:
                extra_limit = 2 if delta >= 0.15 else 1
                extra = await asyncio.to_thread(
                    search_fn,
                    query,
                    filter_dataset,
                    "상담",
                    extra_limit,
                )
                extra_counsel = len(extra)
                if extra:
                    counsel_results += extra
                    combined += extra
            if best_counsel[0] >= best_dispute[0] + 0.05:
                winner_track_after_gate = "상담"
            elif best_dispute[0] >= best_counsel[0] + 0.05:
                winner_track_after_gate = "분쟁/구제"
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_quality_gate",
                        "winner_track": winner_track,
                        "winner_track_after_gate": winner_track_after_gate,
                        "best_counsel": best_counsel,
                        "best_dispute": best_dispute,
                        "delta": delta,
                        "extra_counsel": extra_counsel,
                    },
                    ensure_ascii=False,
                )
            )
        return (
            combined,
            counsel_results,
            winner_track_after_gate,
            extra_counsel,
            best_counsel,
            best_dispute,
            delta,
        )

    def _finalize_candidates(
        self,
        candidates: List[Dict],
        limit: int,
        stage: Optional[str] = None,
    ) -> List[Dict]:
        if not candidates:
            if stage:
                self.logger.info(
                    json.dumps(
                        {
                            "event": "case_dedup_state",
                            "stage": stage,
                            "raw": 0,
                            "deduped": 0,
                            "removed": 0,
                            "group_max": 0,
                        },
                        ensure_ascii=False,
                    )
                )
            return []
        sorted_items = sorted(candidates, key=self._rank_key, reverse=True)
        seen = set()
        deduped = []
        group_counts: Dict[Any, int] = {}
        removed_items: List[Dict] = []
        for item in sorted_items:
            key = self._dedup_key(item)
            group_counts[key] = group_counts.get(key, 0) + 1
            if key in seen:
                removed_items.append(item)
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        if stage:
            removed = len(sorted_items) - len(deduped)
            group_max = max(group_counts.values()) if group_counts else 0
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_dedup_state",
                        "stage": stage,
                        "raw": len(sorted_items),
                        "deduped": len(deduped),
                        "removed": removed,
                        "group_max": group_max,
                    },
                    ensure_ascii=False,
                )
            )
            if removed_items:
                samples = []
                for item in removed_items[:3]:
                    if not isinstance(item, dict):
                        continue
                    key_type, key_value = self._dedup_key_with_type(item)
                    metadata = item.get("metadata") or {}
                    samples.append(
                        {
                            "key_type": key_type,
                            "key_value": key_value,
                            "category": item.get("category")
                            or metadata.get("category"),
                            "source_url": item.get("source_url") or item.get("url"),
                        }
                    )
                if samples:
                    self.logger.info(
                        json.dumps(
                            {
                                "event": "case_dedup_removed_samples",
                                "stage": stage,
                                "samples": samples,
                            },
                            ensure_ascii=False,
                        )
                    )
        return deduped

    async def _fill_if_needed(
        self,
        query: str,
        filter_dataset: Optional[str],
        winner_track_after_gate: str,
        combined: List[Dict],
        top_k: int,
        search_fn,
        fill_policy: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict], int, int, int, int]:
        policy = fill_policy or self._get_fill_policy()
        max_stages = int(policy.get("max_stages", 3))
        enable_broaden = bool(policy.get("enable_broaden", True))
        max_db_calls = int(policy.get("max_db_calls", 0))
        if max_stages < 0:
            max_stages = 0
        if max_db_calls < 0:
            max_db_calls = 0

        combined = self._finalize_candidates(combined, top_k, stage="initial")

        fill_counsel = 0
        fill_dispute = 0
        fill_relax = 0
        fill_broaden = 0
        db_calls_used = 0

        def _log_stage(
            stage: str,
            stage_index: int,
            before: int,
            after: int,
            added: int,
            skipped: bool,
            skipped_reason: Optional[str],
        ) -> None:
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_fill_stage",
                        "stage": stage,
                        "stage_index": stage_index,
                        "before": before,
                        "after": after,
                        "added": added,
                        "still_missing": max(0, top_k - after),
                        "db_calls_used": db_calls_used,
                        "skipped": skipped,
                        "skipped_reason": skipped_reason,
                    },
                    ensure_ascii=False,
                )
            )

        def _skip_reason(stage: str, stage_index: int, before: int) -> Optional[str]:
            if before >= top_k:
                return "not_needed"
            if stage_index >= max_stages:
                return "max_stages_reached"
            if max_db_calls > 0 and db_calls_used >= max_db_calls:
                return "db_call_budget_exhausted"
            if stage == "broaden" and not enable_broaden:
                return "broaden_disabled"
            return None

        # Stage 0: track_fill
        stage = "track_fill"
        stage_index = 0
        before = len(combined)
        skipped_reason = _skip_reason(stage, stage_index, before)
        if skipped_reason:
            _log_stage(stage, stage_index, before, before, 0, True, skipped_reason)
        else:
            remaining = top_k - len(combined)
            if winner_track_after_gate == "상담":
                db_calls_used += 1
                fill = await asyncio.to_thread(
                    search_fn,
                    query,
                    filter_dataset,
                    "상담",
                    remaining,
                )
                fill_counsel = len(fill)
            else:
                fill = []
                for cat in ("조정", "해결"):
                    if remaining <= 0:
                        break
                    db_calls_used += 1
                    chunk = await asyncio.to_thread(
                        search_fn,
                        query,
                        filter_dataset,
                        cat,
                        remaining,
                    )
                    fill += chunk
                    remaining = top_k - len(
                        self._finalize_candidates(combined + fill, top_k)
                    )
                fill_dispute = len(fill)
            combined = self._finalize_candidates(
                combined + fill, top_k, stage="track_fill"
            )
            after = len(combined)
            added = max(0, after - before)
            stage_reason = "no_candidates_added" if added == 0 else None
            _log_stage(stage, stage_index, before, after, added, False, stage_reason)

        # Stage 1: category_relax
        stage = "category_relax"
        stage_index = 1
        before = len(combined)
        skipped_reason = _skip_reason(stage, stage_index, before)
        if skipped_reason:
            _log_stage(stage, stage_index, before, before, 0, True, skipped_reason)
        else:
            remaining = top_k - len(combined)
            db_calls_used += 1
            fill = await asyncio.to_thread(
                search_fn,
                query,
                filter_dataset,
                None,
                remaining,
            )
            fill_relax = len(fill)
            combined = self._finalize_candidates(
                combined + fill, top_k, stage="category_relax"
            )
            after = len(combined)
            added = max(0, after - before)
            stage_reason = "no_candidates_added" if added == 0 else None
            _log_stage(stage, stage_index, before, after, added, False, stage_reason)

        # Stage 2: broaden
        stage = "broaden"
        stage_index = 2
        before = len(combined)
        skipped_reason = _skip_reason(stage, stage_index, before)
        if skipped_reason:
            _log_stage(stage, stage_index, before, before, 0, True, skipped_reason)
        else:
            broadened = self._broaden_query(query, winner_track_after_gate)
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_broaden_query",
                        "winner_track": winner_track_after_gate,
                        "original_query": query,
                        "broadened_query": broadened,
                    },
                    ensure_ascii=False,
                )
            )
            remaining = top_k - len(combined)
            db_calls_used += 1
            fill = await asyncio.to_thread(
                search_fn,
                broadened,
                filter_dataset,
                None,
                remaining,
            )
            fill_broaden = len(fill)
            combined = self._finalize_candidates(
                combined + fill, top_k, stage="broaden"
            )
            after = len(combined)
            added = max(0, after - before)
            stage_reason = "no_candidates_added" if added == 0 else None
            _log_stage(stage, stage_index, before, after, added, False, stage_reason)

        return combined, fill_counsel, fill_dispute, fill_relax, fill_broaden

    async def _execute_search(self, query: str, top_k: int) -> List[Dict]:
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        retriever = RDSRetriever(db_config, embed_url)
        retriever.connect()

        try:
            filter_category = self._last_filter_category
            forced_combined = False
            if filter_category in ("조정+해결", "조정_해결", "통합"):
                forced_combined = True
                filter_category = None

            filter_dataset = (
                getattr(self, "_last_filter_dataset", None) or self.default_dataset
            )

            def _search_rrf(
                query_text: str,
                dataset: Optional[str],
                category: Optional[str],
                limit: int,
            ) -> List[Dict]:
                results = retriever.search_hybrid_rrf_best(
                    query_text=query_text,
                    filter_dataset=dataset,
                    filter_category=category,
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=limit,
                    rrf_k=60,
                )
                if results or dataset is None:
                    return results
                fallback = retriever.search_hybrid_rrf_best(
                    query_text=query_text,
                    filter_dataset=None,
                    filter_category=category,
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=limit,
                    rrf_k=60,
                )
                self.logger.info(
                    json.dumps(
                        {
                            "event": "case_filter_fallback",
                            "reason": "dataset_empty",
                            "filter_dataset": dataset,
                            "filter_category": category,
                        },
                        ensure_ascii=False,
                    )
                )
                return fallback

            if filter_category in ("상담", "조정", "해결"):
                results = await asyncio.to_thread(
                    _search_rrf,
                    query,
                    filter_dataset,
                    filter_category,
                    top_k,
                )
                return results

            scores, strong_hits, track_meta = self._decide_tracks_and_scores(
                query,
                getattr(self, "_last_query_analysis", {}) or {},
                forced_combined,
            )
            (
                counsel_quota,
                dispute_quota,
                ratio,
                combined_quotas,
                _split_reason,
                _min_guard,
            ) = self._decide_quotas(
                top_k,
                scores,
                strong_hits,
                track_meta["confident"],
                track_meta["winner_track"],
                track_meta,
            )
            winner_track = track_meta["winner_track"]

            bonus_enabled = (
                os.getenv("CASE_WINNER_TRACK_BONUS_ENABLED", "false").lower() == "true"
            )
            if bonus_enabled:
                try:
                    bonus_eps = float(os.getenv("CASE_WINNER_TRACK_BONUS_EPS", "1e-6"))
                except ValueError:
                    bonus_eps = 1e-6
            else:
                bonus_eps = 0.0
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_winner_track_bonus",
                        "enabled": bool(bonus_enabled),
                        "eps": bonus_eps,
                        "winner_track": winner_track,
                    },
                    ensure_ascii=False,
                )
            )

            rank_mode, rank_threshold = self._get_rank_mode_threshold()
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_rank_key_mode",
                        "mode": rank_mode,
                        "threshold": rank_threshold,
                    },
                    ensure_ascii=False,
                )
            )

            (
                combined,
                counsel_results,
                adjust_results,
                relief_results,
            ) = await self._search_by_quotas(
                query,
                filter_dataset,
                counsel_quota,
                combined_quotas,
                _search_rrf,
            )
            (
                combined,
                counsel_results,
                winner_track_after_gate,
                extra_counsel,
                best_counsel,
                best_dispute,
                delta,
            ) = await self._apply_quality_gate(
                query,
                filter_dataset,
                combined,
                counsel_results,
                adjust_results,
                relief_results,
                winner_track,
                _search_rrf,
            )

            self.logger.info(
                json.dumps(
                    {
                        "event": "case_track_counts",
                        "stage": "initial",
                        "counts": {
                            "상담": len(counsel_results),
                            "조정": len(adjust_results),
                            "해결": len(relief_results),
                        },
                        "quotas": {
                            "상담": counsel_quota,
                            "조정": combined_quotas.get("조정", 0),
                            "해결": combined_quotas.get("해결", 0),
                        },
                        "quality_gate": {
                            "extra_counsel": extra_counsel,
                        },
                    },
                    ensure_ascii=False,
                )
            )

            if bonus_enabled and bonus_eps:
                for item in combined:
                    category = item.get("category") if isinstance(item, dict) else None
                    in_winner = False
                    if winner_track == "상담":
                        in_winner = category == "상담"
                    else:
                        in_winner = category in ("조정", "해결")
                    if in_winner and isinstance(item, dict):
                        item["rrf_score"] = (
                            float(item.get("rrf_score") or 0.0) + bonus_eps
                        )
            fill_policy = self._get_fill_policy()
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_fill_policy",
                        "max_stages": fill_policy.get("max_stages", 3),
                        "enable_broaden": fill_policy.get("enable_broaden", True),
                        "max_db_calls": fill_policy.get("max_db_calls", 0),
                        "top_k": top_k,
                    },
                    ensure_ascii=False,
                )
            )
            (
                combined,
                fill_counsel,
                fill_dispute,
                fill_relax,
                fill_broaden,
            ) = await self._fill_if_needed(
                query,
                filter_dataset,
                winner_track_after_gate,
                combined,
                top_k,
                _search_rrf,
                fill_policy=fill_policy,
            )

            final_counts = {
                "상담": len(counsel_results) + fill_counsel,
                "조정": len(adjust_results),
                "해결": len(relief_results),
            }
            if fill_dispute and winner_track_after_gate != "상담":
                final_counts["조정"] += fill_dispute

            sample = combined[0] if combined else {}
            sample_meta = sample.get("metadata") or {}
            self.logger.info(
                json.dumps(
                    {
                        "event": "case_return_state",
                        "len": len(combined),
                        "type": self.retrieval_source,
                        "keys": list(sample.keys()) if isinstance(sample, dict) else [],
                        "has_metadata": bool(sample_meta),
                        "sample_category": sample.get("category")
                        if isinstance(sample, dict)
                        else None,
                        "sample_dataset_type": sample.get("dataset_type")
                        if isinstance(sample, dict)
                        else None,
                        "sample_source": sample.get("source_url")
                        if isinstance(sample, dict)
                        else None,
                        "sample_doc_id": sample_meta.get("doc_id"),
                    },
                    ensure_ascii=False,
                )
            )

            self.logger.info(
                json.dumps(
                    {
                        "event": "case_track_counts",
                        "stage": "final",
                        "counts": final_counts,
                        "fills": {
                            "counsel": fill_counsel,
                            "dispute": fill_dispute,
                            "relax": fill_relax,
                            "broaden": fill_broaden,
                        },
                        "total": len(combined),
                    },
                    ensure_ascii=False,
                )
            )

            return combined
        finally:
            retriever.close()

    def _format_results(self, results: List[Dict]) -> List[Dict[str, Any]]:
        def _rank_norm(values: List[float]) -> List[float]:
            if not values:
                return []
            if len(values) == 1:
                return [0.5]
            vmin = min(values)
            vmax = max(values)
            if vmin == vmax:
                return [0.5 for _ in values]
            counts: Dict[float, int] = {}
            for v in values:
                counts[v] = counts.get(v, 0) + 1
            unique = sorted(set(values), reverse=True)
            rank_map = {v: idx for idx, v in enumerate(unique)}
            denom = max(len(unique) - 1, 1)
            norms = []
            for v in values:
                if counts[v] > 1:
                    norms.append(0.5)
                else:
                    norms.append(1.0 - (rank_map[v] / denom))
            return norms

        def _scores(r_item: Any) -> Dict[str, float]:
            if isinstance(r_item, dict):
                vec = (
                    r_item.get("vector_similarity", r_item.get("similarity", 0.0))
                    or 0.0
                )
                return {
                    "vec": float(vec),
                    "bm25": float(r_item.get("bm25_score") or 0.0),
                    "rrf": float(r_item.get("rrf_score") or 0.0),
                }
            vec = float(getattr(r_item, "similarity", 0.0) or 0.0)
            return {"vec": vec, "bm25": 0.0, "rrf": 0.0}

        score_list = [_scores(r) for r in results]
        norm_vec = _rank_norm([s["vec"] for s in score_list])
        norm_bm25 = _rank_norm([s["bm25"] for s in score_list])
        norm_rrf = _rank_norm([s["rrf"] for s in score_list])

        formatted = []
        for idx, r in enumerate(results):
            if isinstance(r, dict):
                metadata = r.get("metadata") or {}
                content = r.get("text") or r.get("content")
                source_url = r.get("source_url") or r.get("url")
                source_file = r.get("source_file")
                similarity = r.get("vector_similarity", r.get("similarity", 0))
                chunk_id = r.get("chunk_id")
                category = r.get("category") or metadata.get("category")
                dataset_type = r.get("dataset_type") or metadata.get("dataset_type")
            else:
                metadata = r.metadata or {}
                content = r.text or getattr(r, "content", None)
                source_url = r.source_url or getattr(r, "url", None)
                source_file = r.source_file
                similarity = getattr(r, "similarity", 0)
                chunk_id = r.chunk_id
                category = getattr(r, "category", None) or metadata.get("category")
                dataset_type = getattr(r, "dataset_type", None) or metadata.get(
                    "dataset_type"
                )

            doc_title = (
                metadata.get("doc_title")
                or metadata.get("title")
                or source_file
                or chunk_id
            )
            doc_id = metadata.get("doc_id") or chunk_id
            decision_date = metadata.get("decision_date")

            merged_metadata = dict(metadata)
            extra_meta = {
                "category": category,
                "dataset_type": dataset_type,
                "chunk_id": chunk_id,
                "source_year": r.get("source_year") if isinstance(r, dict) else None,
                "rrf_score": r.get("rrf_score") if isinstance(r, dict) else None,
                "bm25_score": r.get("bm25_score") if isinstance(r, dict) else None,
                "vector_similarity": r.get("vector_similarity")
                if isinstance(r, dict)
                else None,
            }
            for key, value in extra_meta.items():
                if value is not None and key not in merged_metadata:
                    merged_metadata[key] = value

            soft_score = (
                0.6 * norm_vec[idx] + 0.2 * norm_bm25[idx] + 0.2 * norm_rrf[idx]
            )

            formatted.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "chunk_type": metadata.get("chunk_type"),
                    "content": content,
                    "doc_title": doc_title,
                    "title": doc_title,
                    "source_org": metadata.get("source_org"),
                    "url": source_url,
                    "decision_date": decision_date,
                    "similarity": similarity,
                    "category": category,
                    "dataset_type": dataset_type,
                    "rrf_score": r.get("rrf_score") if isinstance(r, dict) else None,
                    "bm25_score": r.get("bm25_score") if isinstance(r, dict) else None,
                    "vector_similarity": r.get("vector_similarity")
                    if isinstance(r, dict)
                    else None,
                    "soft_score": soft_score,
                    "metadata": merged_metadata,
                }
            )
        return formatted

    def _build_sources(self, results: List[Dict]) -> List[Dict[str, Any]]:
        sources = []
        for i, r in enumerate(results):
            metadata = (r.get("metadata") or {}) if isinstance(r, dict) else {}
            dataset_type = r.get("dataset_type") if isinstance(r, dict) else None
            source_type = (
                dataset_type or metadata.get("dataset_type") or "case_combined"
            )
            sources.append(
                {
                    "type": source_type,
                    "index": i + 1,
                    "chunk_id": r.get("chunk_id") if isinstance(r, dict) else None,
                    "doc_id": metadata.get("doc_id") if isinstance(r, dict) else None,
                    "doc_title": metadata.get("doc_title")
                    if isinstance(r, dict)
                    else None,
                    "source_org": metadata.get("source_org")
                    if isinstance(r, dict)
                    else None,
                    "similarity": r.get("similarity", 0) if isinstance(r, dict) else 0,
                }
            )
        return sources


case_retrieval_agent = CaseRetrievalAgent()

__all__ = ["CaseRetrievalAgent", "case_retrieval_agent"]
