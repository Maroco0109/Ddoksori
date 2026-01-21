import os
from typing import Dict, List, Any

from ....orchestrator.state import ChatState, RetrievalResult


def get_db_config() -> Dict[str, str]:
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'dbname': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
    }


def get_embed_api_url() -> str:
    return os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')


def merge_retrieval(
    current: Dict[str, Any],
    new_data: Dict[str, Any],
    section: str = None
) -> RetrievalResult:
    if section:
        merged = dict(current) if current else {}
        merged[section] = new_data
    else:
        merged = new_data

    all_similarities = []
    for key in ['disputes', 'counsels']:
        for item in merged.get(key, []):
            sim = item.get('similarity', 0)
            if sim:
                all_similarities.append(sim)

    max_sim = max(all_similarities) if all_similarities else 0.0
    avg_sim = sum(all_similarities) / len(all_similarities) if all_similarities else 0.0

    return RetrievalResult(
        agency=merged.get('agency', {}),
        disputes=merged.get('disputes', []),
        counsels=merged.get('counsels', []),
        laws=merged.get('laws', []),
        criteria=merged.get('criteria', []),
        max_similarity=max_sim,
        avg_similarity=avg_sim,
    )


def build_sources_from_retrieval(retrieval: RetrievalResult) -> List[Dict]:
    sources: List[Dict] = []

    for i, dispute in enumerate(retrieval.get('disputes', [])):
        sources.append({
            'type': 'dispute',
            'index': i + 1,
            'doc_id': dispute.get('doc_id', ''),
            'title': dispute.get('doc_title', ''),
            'source_org': dispute.get('source_org', ''),
            'similarity': dispute.get('similarity', 0),
            'url': dispute.get('url', ''),
        })

    for i, counsel in enumerate(retrieval.get('counsels', [])):
        sources.append({
            'type': 'counsel',
            'index': i + 1,
            'doc_id': counsel.get('doc_id', ''),
            'title': counsel.get('doc_title', ''),
            'source_org': counsel.get('source_org', ''),
            'similarity': counsel.get('similarity', 0),
            'url': counsel.get('url', ''),
        })

    for i, law in enumerate(retrieval.get('laws', [])):
        sources.append({
            'type': 'law',
            'index': i + 1,
            'unit_id': law.get('unit_id', ''),
            'law_name': law.get('law_name', ''),
            'full_path': law.get('full_path', ''),
            'similarity': law.get('similarity', 0),
        })

    for i, crit in enumerate(retrieval.get('criteria', [])):
        sources.append({
            'type': 'criteria',
            'index': i + 1,
            'unit_id': crit.get('unit_id', ''),
            'source_label': crit.get('source_label', ''),
            'category': crit.get('category', ''),
            'item': crit.get('item', ''),
            'similarity': crit.get('similarity', 0),
        })

    return sources
