import logging
from typing import Dict, Any, List, Set

from ..state import (
    ChatState_v2,
    RetrievalReport_v2,
    SlotStatus,
    RetrievalResult,
)
from ..budget import increment_search_round

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD_HIGH = 0.7
RELEVANCE_THRESHOLD_LOW = 0.3
MIN_CHUNKS_FOR_COVERAGE = 3
TOP_K_FOR_RELEVANCE = 5


def _extract_all_similarities(retrieval: RetrievalResult) -> List[float]:
    similarities: List[float] = []
    
    for d in retrieval.get('disputes', []):
        if sim := d.get('similarity'):
            similarities.append(float(sim))
    
    for c in retrieval.get('counsels', []):
        if sim := c.get('similarity'):
            similarities.append(float(sim))
    
    for law in retrieval.get('laws', []):
        if sim := law.get('similarity'):
            similarities.append(float(sim))
    
    for crit in retrieval.get('criteria', []):
        if sim := crit.get('similarity'):
            similarities.append(float(sim))
    
    return sorted(similarities, reverse=True)


def _calculate_relevance(retrieval: RetrievalResult) -> float:
    similarities = _extract_all_similarities(retrieval)
    
    if not similarities:
        return 0.0
    
    top_k = similarities[:TOP_K_FOR_RELEVANCE]
    
    weights = [1.0, 0.8, 0.6, 0.4, 0.2][:len(top_k)]
    total_weight = sum(weights)
    
    weighted_sum = sum(s * w for s, w in zip(top_k, weights))
    
    return weighted_sum / total_weight if total_weight > 0 else 0.0


def _get_chunk_text_content(chunk: Dict[str, Any]) -> str:
    return str(chunk.get('content', '') or chunk.get('text', '') or chunk.get('unit_text', ''))


def _extract_chunk_ids(retrieval: RetrievalResult) -> Set[str]:
    chunk_ids: Set[str] = set()
    
    for d in retrieval.get('disputes', []):
        if cid := d.get('chunk_id') or d.get('doc_id'):
            chunk_ids.add(cid)
    
    for c in retrieval.get('counsels', []):
        if cid := c.get('chunk_id') or c.get('doc_id'):
            chunk_ids.add(cid)
    
    for law in retrieval.get('laws', []):
        if cid := law.get('unit_id') or law.get('doc_id'):
            chunk_ids.add(cid)
    
    for crit in retrieval.get('criteria', []):
        if cid := crit.get('unit_id') or crit.get('chunk_id'):
            chunk_ids.add(cid)
    
    return chunk_ids


def _calculate_coverage(
    retrieval: RetrievalResult,
    required_slots: List[str],
) -> List[SlotStatus]:
    coverage: List[SlotStatus] = []
    
    disputes = retrieval.get('disputes', [])
    counsels = retrieval.get('counsels', [])
    laws = retrieval.get('laws', [])
    criteria = retrieval.get('criteria', [])
    
    all_chunks = disputes + counsels + laws + criteria
    all_texts = [_get_chunk_text_content(c) for c in all_chunks]
    combined_text = ' '.join(all_texts).lower()
    
    slot_keywords = {
        'dispute_case': ['분쟁', '조정', '피해', '사례'],
        'counsel_case': ['상담', '문의', '질문', '답변'],
        'law_reference': ['법', '조', '항', '법률'],
        'criteria_reference': ['기준', '별표', '환불', '위약금', '보상'],
        'purchase_item': ['품목', '상품', '제품', '서비스'],
        'dispute_details': ['환불', '교환', '수리', '해지', '취소', '피해'],
        'refund_policy': ['환불', '반품', '취소', '철회'],
        'warranty_period': ['기간', '보증', '보유'],
        'penalty_info': ['위약금', '손해배상', '배상'],
    }
    
    for slot in required_slots:
        keywords = slot_keywords.get(slot, [slot])
        matched = any(kw in combined_text for kw in keywords)
        
        evidence_ids: List[str] = []
        confidence = 0.0
        
        if matched:
            for chunk in all_chunks:
                chunk_text = _get_chunk_text_content(chunk).lower()
                if any(kw in chunk_text for kw in keywords):
                    cid = chunk.get('chunk_id') or chunk.get('unit_id') or chunk.get('doc_id')
                    if cid:
                        evidence_ids.append(cid)
                    if len(evidence_ids) >= 3:
                        break
            
            confidence = min(1.0, len(evidence_ids) * 0.4) if evidence_ids else 0.5
        
        status_value = 'filled' if matched else 'missing'
        if matched and not evidence_ids:
            status_value = 'partial'
        
        status: SlotStatus = {
            'slot_name': slot,
            'status': status_value,
            'evidence_chunk_ids': evidence_ids,
            'confidence': round(confidence, 2),
        }
        coverage.append(status)
    
    if not required_slots:
        total_chunks = len(all_chunks)
        chunk_ids = list(_extract_chunk_ids(retrieval))[:5]
        
        if total_chunks >= MIN_CHUNKS_FOR_COVERAGE:
            status_value = 'filled'
            confidence = min(1.0, total_chunks / 10)
        elif total_chunks > 0:
            status_value = 'partial'
            confidence = total_chunks / MIN_CHUNKS_FOR_COVERAGE * 0.5
        else:
            status_value = 'missing'
            confidence = 0.0
        
        default_status: SlotStatus = {
            'slot_name': 'general_evidence',
            'status': status_value,
            'evidence_chunk_ids': chunk_ids,
            'confidence': round(confidence, 2),
        }
        coverage.append(default_status)
    
    return coverage


def _calculate_diversity(retrieval: RetrievalResult) -> float:
    disputes = retrieval.get('disputes', [])
    counsels = retrieval.get('counsels', [])
    laws = retrieval.get('laws', [])
    criteria = retrieval.get('criteria', [])
    
    source_orgs: Set[str] = set()
    
    for d in disputes:
        if org := d.get('source_org'):
            source_orgs.add(org)
    
    for c in counsels:
        if org := c.get('source_org'):
            source_orgs.add(org)
    
    for law in laws:
        if name := law.get('law_name'):
            source_orgs.add(f"law:{name[:20]}")
    
    for crit in criteria:
        if label := crit.get('source_label'):
            source_orgs.add(f"criteria:{label[:20]}")
    
    section_count = 0
    if disputes:
        section_count += 1
    if counsels:
        section_count += 1
    if laws:
        section_count += 1
    if criteria:
        section_count += 1
    
    section_diversity = section_count / 4.0
    org_diversity = min(1.0, len(source_orgs) / 5.0)
    
    return section_diversity * 0.5 + org_diversity * 0.5


def _calculate_marginal_gain(
    current_relevance: float,
    current_chunk_ids: Set[str],
    history: List[RetrievalReport_v2],
    previous_chunk_ids: Set[str],
) -> float:
    if not history:
        return current_relevance
    
    last_relevance = history[-1].get('relevance', 0.0)
    relevance_gain = max(0.0, current_relevance - last_relevance)
    
    if previous_chunk_ids:
        new_chunks = current_chunk_ids - previous_chunk_ids
        new_chunk_ratio = len(new_chunks) / max(1, len(current_chunk_ids))
    else:
        new_chunk_ratio = 1.0
    
    return relevance_gain * 0.6 + new_chunk_ratio * 0.4


def _get_sources_distribution(retrieval: RetrievalResult) -> Dict[str, int]:
    return {
        'disputes': len(retrieval.get('disputes', [])),
        'counsels': len(retrieval.get('counsels', [])),
        'laws': len(retrieval.get('laws', [])),
        'criteria': len(retrieval.get('criteria', [])),
    }


def sufficiency_node(state: ChatState_v2) -> Dict[str, Any]:
    retrieval = state.get('retrieval')
    query_analysis = state.get('query_analysis_v2')
    history = state.get('retrieval_report_history', [])
    
    if not retrieval:
        logger.warning("[Sufficiency] No retrieval result, creating empty report")
        empty_report: RetrievalReport_v2 = {
            'relevance': 0.0,
            'coverage': [],
            'diversity': 0.0,
            'marginal_gain': 0.0,
            'total_chunks': 0,
            'sources_distribution': {},
        }
        return {
            'retrieval_report_v2': empty_report,
            'retrieval_report_history': [empty_report],
            **increment_search_round(state),
        }
    
    required_slots = []
    if query_analysis:
        required_slots = query_analysis.get('required_slots', [])
    
    relevance = _calculate_relevance(retrieval)
    coverage = _calculate_coverage(retrieval, required_slots)
    diversity = _calculate_diversity(retrieval)
    
    current_chunk_ids = _extract_chunk_ids(retrieval)
    
    previous_chunk_ids: Set[str] = set()
    if history:
        prev_retrieval = state.get('previous_retrieval')
        if prev_retrieval:
            previous_chunk_ids = _extract_chunk_ids(prev_retrieval)
    
    marginal_gain = _calculate_marginal_gain(
        relevance, current_chunk_ids, history, previous_chunk_ids
    )
    
    total_chunks = sum([
        len(retrieval.get('disputes', [])),
        len(retrieval.get('counsels', [])),
        len(retrieval.get('laws', [])),
        len(retrieval.get('criteria', [])),
    ])
    
    report: RetrievalReport_v2 = {
        'relevance': round(relevance, 3),
        'coverage': coverage,
        'diversity': round(diversity, 3),
        'marginal_gain': round(marginal_gain, 3),
        'total_chunks': total_chunks,
        'sources_distribution': _get_sources_distribution(retrieval),
    }
    
    missing_count = len([s for s in coverage if s.get('status') == 'missing'])
    
    logger.info(
        f"[Sufficiency] relevance={relevance:.3f}, "
        f"diversity={diversity:.3f}, "
        f"marginal_gain={marginal_gain:.3f}, "
        f"total_chunks={total_chunks}, "
        f"missing_slots={missing_count}"
    )
    
    return {
        'retrieval_report_v2': report,
        'retrieval_report_history': [report],
        **increment_search_round(state),
    }
