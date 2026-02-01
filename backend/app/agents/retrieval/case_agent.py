"""CaseRetrievalAgent - 분쟁조정사례 검색 전용 에이전트."""

import asyncio
import json
import logging
import math
from typing import Dict, Any, List, ClassVar, Tuple

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.rds_retriever import RDSRetriever


class CaseRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정사례(mediation_case) 검색 에이전트 - 법적 효력이 있는 분쟁조정 결과"""
    
    agent_name: ClassVar[str] = "retrieval_case"
    agent_description: ClassVar[str] = "분쟁조정사례를 검색합니다. 유사한 분쟁 해결 선례가 필요할 때 호출됩니다."
    default_dataset: ClassVar[str] = "mediation_case"
    retrieval_source: ClassVar[str] = "case"
    logger = logging.getLogger(__name__)

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
            "분쟁조정", "조정신청", "조정 접수", "조정위원회", "조정 결정", "조정 결과",
            "합의가 안돼", "합의 안돼", "합의 실패", "중재", "조정으로 가고 싶어",
            "상대방이 거부", "업체가 끝까지 거부", "대화가 안됨", "분쟁이 커짐",
        )
        adjust_mid = (
            "분쟁", "다툼", "쟁점", "서로 주장", "책임 공방",
            "민원 넣었는데 해결 안됨", "소비자원 조정 가능", "조정 절차", "조정 기간", "조정 서류",
        )
        adjust_weak = ("조정 가능", "조정 대상", "조정 신청서", "조정")

        # B) 해결 (피해구제/조치)
        relief_strong = (
            "배상", "손해배상", "보상", "위약금",
            "하자", "불량", "파손", "누수", "고장",
            "미배송", "배송지연", "오배송", "누락", "취소했는데 결제됨",
            "계약해지", "청약철회", "철회", "해지", "취소 수수료",
            "증빙", "영수증", "결제내역", "통화녹음", "사진", "진단서",
        )
        action_terms = (
            "환불", "환급", "교환", "반품", "수리", "as", "취소", "해지", "철회",
            "청약철회",
        )
        relief_mid = (
            "거부당함", "안해줌", "연락두절", "환불 거부", "거부",
        )
        relief_weak = ("어떻게 받아", "뭘 요구", "요구할 수 있어")

        # C) 상담 (안내/가능 여부)
        counsel_strong = (
            "상담", "문의", "안내", "절차", "방법", "준비서류", "기간", "어디에 연락",
            "가능한가요", "되나요", "해도 되나요", "권리", "의무", "주의사항", "유의점",
            "제가 뭘 하면", "제가 무엇을 하면",
        )
        counsel_request = (
            "요청", "원해", "원합니다", "받고 싶", "받고싶", "해주", "해주세요",
            "해 줘", "해줘", "가능", "될까", "할 수", "할수", "해주실",
        )
        counsel_mid = (
            "환불 되나요", "불법인가요", "어떻게 해야", "기준", "규정",
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
            frac = sorted(weights.keys(), key=lambda k: raw[k] - quotas[k], reverse=True)
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
            lowest = sorted(quotas.keys(), key=lambda k: (scores.get(k, 0), quotas[k]))[0]
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
    def _broaden_query(query: str, track: str) -> str:
        base = (query or "").strip()
        if not base:
            return base
        lower = base.lower()
        domain_terms = (
            "헬스장",
            "피트니스",
            "gym",
            "회원권",
            "pt",
            "퍼스널",
            "수강권",
        )
        has_domain = any(t in base or t in lower for t in domain_terms)

        if has_domain:
            if track == "상담":
                suffix = " 헬스장 회원권 환불 청약철회 상담 사례"
            else:
                suffix = " 헬스장 회원권 환불 분쟁조정 사례"
        else:
            if track == "상담":
                suffix = " 상담 사례"
            else:
                suffix = " 분쟁조정 사례"

        if suffix.strip() in base:
            return base
        return f"{base}{suffix}"

    @staticmethod
    def _best_similarity(results: List[Dict]) -> float:
        best = 0.0
        for item in results or []:
            if not isinstance(item, dict):
                continue
            score = item.get("vector_similarity", item.get("similarity", 0.0)) or 0.0
            if score > best:
                best = score
        return float(best)
    
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

            filter_dataset = getattr(self, "_last_filter_dataset", None) or self.default_dataset

            if filter_category in ("상담", "조정", "해결"):
                results = await asyncio.to_thread(
                    retriever.search_hybrid_rrf,
                    query_text=query,
                    filter_dataset=filter_dataset,
                    filter_category=filter_category,
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=top_k,
                    rrf_k=60,
                )
                return results

            scores, strong_hits = self._score_case_categories(
                query, getattr(self, "_last_query_analysis", {}) or {}
            )
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
                counsel_quota, dispute_quota, ratio = self._track_quotas(
                    top_k, confident, winner_track, scores, strong_hits
                )
            else:
                counsel_quota, dispute_quota, ratio = self._track_quotas(
                    top_k, confident, winner_track, scores, strong_hits
                )

            if dispute_quota > 0:
                if scores["조정"] == 0 and scores["해결"] == 0:
                    combined_weights = {"조정": 1, "해결": 1}
                else:
                    combined_weights = {
                        "조정": max(scores["조정"], 1),
                        "해결": max(scores["해결"], 1),
                    }
                combined_quotas = self._allocate_quotas(
                    dispute_quota,
                    combined_weights,
                    strong_hits,
                    scores,
                )
            else:
                combined_quotas = {"조정": 0, "해결": 0}

            self.logger.info(
                json.dumps(
                    {
                        "event": "case_quota_policy",
                        "K": top_k,
                        "confident": confident,
                        "winner_track": winner_track,
                        "ratio": ratio,
                        "counsel_score": counsel_score,
                        "combined_score": combined_score,
                        "score_gap": score_gap,
                        "p_dispute": p_dispute,
                        "confidence": confidence,
                        "quotas": {
                            "counsel": counsel_quota,
                            "dispute": dispute_quota,
                        },
                        "dispute_split": combined_quotas,
                    },
                    ensure_ascii=False,
                )
            )

            combined: List[Dict] = []
            counsel_results: List[Dict] = []
            adjust_results: List[Dict] = []
            relief_results: List[Dict] = []

            if counsel_quota > 0:
                counsel_results = await asyncio.to_thread(
                    retriever.search_hybrid_rrf,
                    query_text=query,
                    filter_dataset=filter_dataset,
                    filter_category="상담",
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=counsel_quota,
                    rrf_k=60,
                )
                combined += counsel_results

            for cat in ("조정", "해결"):
                quota = combined_quotas.get(cat, 0)
                if quota <= 0:
                    continue
                results = await asyncio.to_thread(
                    retriever.search_hybrid_rrf,
                    query_text=query,
                    filter_dataset=filter_dataset,
                    filter_category=cat,
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=quota,
                    rrf_k=60,
                )
                if cat == "조정":
                    adjust_results = results
                else:
                    relief_results = results
                combined += results

            # Quality gate: if winner track top1 is weak, add counsel results.
            extra_counsel = 0
            best_counsel = self._best_similarity(counsel_results)
            best_dispute = self._best_similarity(adjust_results + relief_results)
            delta = best_counsel - best_dispute
            winner_track_after_gate = winner_track
            if winner_track == "분쟁/구제":
                if delta >= 0.05:
                    extra_limit = 2 if delta >= 0.15 else 1
                    extra = await asyncio.to_thread(
                        retriever.search_hybrid_rrf,
                        query_text=query,
                        filter_dataset=filter_dataset,
                        filter_category="상담",
                        filter_document_type=None,
                        filter_year=None,
                        result_limit=extra_limit,
                        rrf_k=60,
                    )
                    extra_counsel = len(extra)
                    if extra:
                        counsel_results += extra
                        combined += extra
                if best_counsel >= best_dispute + 0.05:
                    winner_track_after_gate = "상담"
                elif best_dispute >= best_counsel + 0.05:
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

            # Fill stage 1: relax category within same dataset
            counsel_missing = max(counsel_quota - len(counsel_results), 0)
            dispute_missing = max(dispute_quota - (len(adjust_results) + len(relief_results)), 0)
            fill_counsel = 0
            fill_dispute = 0
            if counsel_missing > 0:
                fill = await asyncio.to_thread(
                    retriever.search_hybrid_rrf,
                    query_text=query,
                    filter_dataset=filter_dataset,
                    filter_category=None,
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=counsel_missing,
                    rrf_k=60,
                )
                fill_counsel = len(fill)
                combined += fill
            if dispute_missing > 0:
                fill = await asyncio.to_thread(
                    retriever.search_hybrid_rrf,
                    query_text=query,
                    filter_dataset=filter_dataset,
                    filter_category=None,
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=dispute_missing,
                    rrf_k=60,
                )
                fill_dispute = len(fill)
                combined += fill

            # Fill stage 2: broadened query
            remaining = top_k - len(combined)
            fill_broaden = 0
            if remaining > 0:
                broadened = self._broaden_query(query, winner_track)
                fill = await asyncio.to_thread(
                    retriever.search_hybrid_rrf,
                    query_text=broadened,
                    filter_dataset=filter_dataset,
                    filter_category=None,
                    filter_document_type=None,
                    filter_year=None,
                    result_limit=remaining,
                    rrf_k=60,
                )
                fill_broaden = len(fill)
                combined += fill

            final_counts = {
                "상담": len(counsel_results) + fill_counsel,
                "조정": len(adjust_results),
                "해결": len(relief_results),
            }
            if fill_dispute:
                final_counts["조정"] += fill_dispute

            self.logger.info(
                json.dumps(
                    {
                        "event": "case_track_counts",
                        "stage": "final",
                        "counts": final_counts,
                        "fills": {
                            "counsel": fill_counsel,
                            "dispute": fill_dispute,
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
        def _minmax(values: List[float]) -> List[float]:
            if not values:
                return []
            vmin = min(values)
            vmax = max(values)
            if vmax == vmin:
                return [0.0 for _ in values]
            return [(v - vmin) / (vmax - vmin) for v in values]

        def _scores(r_item: Any) -> Dict[str, float]:
            if isinstance(r_item, dict):
                vec = r_item.get("vector_similarity", r_item.get("similarity", 0.0)) or 0.0
                return {
                    "vec": float(vec),
                    "bm25": float(r_item.get("bm25_score") or 0.0),
                    "rrf": float(r_item.get("rrf_score") or 0.0),
                }
            vec = float(getattr(r_item, "similarity", 0.0) or 0.0)
            return {"vec": vec, "bm25": 0.0, "rrf": 0.0}

        score_list = [_scores(r) for r in results]
        norm_vec = _minmax([s["vec"] for s in score_list])
        norm_bm25 = _minmax([s["bm25"] for s in score_list])
        norm_rrf = _minmax([s["rrf"] for s in score_list])

        formatted = []
        seen_keys = set()
        for idx, r in enumerate(results):
            if isinstance(r, dict):
                metadata = r.get("metadata") or {}
                content = r.get("text")
                source_url = r.get("source_url")
                source_file = r.get("source_file")
                similarity = r.get("vector_similarity", r.get("similarity", 0))
                chunk_id = r.get("chunk_id")
                category = r.get("category") or metadata.get("category")
                dataset_type = r.get("dataset_type") or metadata.get("dataset_type")
            else:
                metadata = r.metadata or {}
                content = r.text
                source_url = r.source_url
                source_file = r.source_file
                similarity = getattr(r, "similarity", 0)
                chunk_id = r.chunk_id
                category = getattr(r, "category", None) or metadata.get("category")
                dataset_type = getattr(r, "dataset_type", None) or metadata.get("dataset_type")

            doc_title = metadata.get("doc_title") or metadata.get("title") or source_file or chunk_id
            doc_id = metadata.get("doc_id") or chunk_id
            case_number = metadata.get("case_number")
            decision_date = metadata.get("decision_date")

            dedup_key = doc_id or case_number or source_url or chunk_id
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            soft_score = (
                0.6 * norm_vec[idx]
                + 0.2 * norm_bm25[idx]
                + 0.2 * norm_rrf[idx]
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
                    "vector_similarity": r.get("vector_similarity") if isinstance(r, dict) else None,
                    "soft_score": soft_score,
                    "metadata": metadata,
                }
            )
        return formatted
    
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
