import logging
from typing import Dict, Any, List, Optional

from ..state import ChatState_v2, SearchPlan, QueryAnalysisResult_v2

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 10
DEFAULT_ROUNDS_BUDGET = 3
DEFAULT_TIME_BUDGET_MS = 10000

RETRIEVER_TYPE_STRUCTURED = 'structured'
RETRIEVER_TYPE_HYBRID = 'hybrid'
RETRIEVER_TYPE_LAW = 'law'
RETRIEVER_TYPE_CRITERIA = 'criteria'
RETRIEVER_TYPE_DISPUTE = 'dispute'
RETRIEVER_TYPE_COUNSEL = 'counsel'
RETRIEVER_TYPE_RDB = 'rdb'

RETRIEVER_MAP = {
    'dispute': [RETRIEVER_TYPE_HYBRID, RETRIEVER_TYPE_DISPUTE, RETRIEVER_TYPE_COUNSEL],
    'law': [RETRIEVER_TYPE_LAW, RETRIEVER_TYPE_HYBRID],
    'criteria': [RETRIEVER_TYPE_CRITERIA, RETRIEVER_TYPE_HYBRID],
    'general': [RETRIEVER_TYPE_HYBRID],
}

TOP_K_MAP = {
    'dispute': 10,
    'law': 5,
    'criteria': 5,
    'general': 5,
}


def _select_retrievers(
    query_type: str,
    keywords: Optional[List[str]] = None,
    sql_params: Optional[Dict[str, Any]] = None,
) -> List[str]:
    base_retrievers = RETRIEVER_MAP.get(query_type, [RETRIEVER_TYPE_STRUCTURED])
    
    if sql_params and sql_params.get('enable_rdb_query'):
        if RETRIEVER_TYPE_RDB not in base_retrievers:
            base_retrievers = [RETRIEVER_TYPE_RDB] + base_retrievers
    
    if keywords:
        law_keywords = ['법', '법률', '조항', '조문', '소비자보호법', '전자상거래법']
        criteria_keywords = ['기준', '분쟁조정기준', '별표', '환불', '위약금', '보상']
        
        has_law = any(kw in ' '.join(keywords) for kw in law_keywords)
        has_criteria = any(kw in ' '.join(keywords) for kw in criteria_keywords)
        
        if has_law and RETRIEVER_TYPE_LAW not in base_retrievers:
            base_retrievers = base_retrievers + [RETRIEVER_TYPE_LAW]
        if has_criteria and RETRIEVER_TYPE_CRITERIA not in base_retrievers:
            base_retrievers = base_retrievers + [RETRIEVER_TYPE_CRITERIA]
    
    return base_retrievers


def _determine_top_k(query_type: str, has_filters: bool) -> int:
    base_k = TOP_K_MAP.get(query_type, DEFAULT_TOP_K)
    if has_filters:
        return min(base_k + 5, 20)
    return base_k


def _should_rerank(query_type: str) -> bool:
    return query_type in ('dispute', 'law', 'criteria')


def search_plan_node(state: ChatState_v2) -> Dict[str, Any]:
    query_analysis = state.get('query_analysis_v2')
    user_query = state.get('user_query', '')
    search_round = state.get('search_round', 0)
    
    if not query_analysis:
        logger.warning("[SearchPlan] No query_analysis_v2, using defaults")
        search_plan: SearchPlan = {
            'retrievers': [RETRIEVER_TYPE_STRUCTURED],
            'top_k': DEFAULT_TOP_K,
            'rerank': True,
            'rounds_budget': DEFAULT_ROUNDS_BUDGET,
            'time_budget_ms': DEFAULT_TIME_BUDGET_MS,
            'filters': {},
            'query': user_query,
        }
        return {'search_plan': search_plan}
    
    query_type = query_analysis.get('query_type', 'dispute')
    filters_candidate = query_analysis.get('filters_candidate', {})
    sql_params_candidate = query_analysis.get('sql_params_candidate') or {}
    rewritten_query = query_analysis.get('rewritten_query', user_query)
    keywords = query_analysis.get('keywords', [])
    search_queries = query_analysis.get('search_queries', [])
    
    sql_params_dict: Dict[str, Any] = dict(sql_params_candidate) if sql_params_candidate else {}
    retrievers = _select_retrievers(query_type, keywords, sql_params_dict)
    has_filters = bool(filters_candidate)
    top_k = _determine_top_k(query_type, has_filters)
    rerank = _should_rerank(query_type)
    
    if search_round > 0:
        top_k = min(top_k + 5, 20)
        if search_queries and len(search_queries) > search_round:
            rewritten_query = search_queries[search_round]
            logger.info(f"[SearchPlan] Round {search_round}: using alternate query")
    
    combined_filters = {**filters_candidate, **sql_params_candidate}
    
    search_plan: SearchPlan = {
        'retrievers': retrievers,
        'top_k': top_k,
        'rerank': rerank,
        'rounds_budget': DEFAULT_ROUNDS_BUDGET,
        'time_budget_ms': DEFAULT_TIME_BUDGET_MS,
        'filters': combined_filters,
        'query': rewritten_query,
    }
    
    logger.info(
        f"[SearchPlan] Compiled: retrievers={retrievers}, "
        f"top_k={top_k}, rerank={rerank}, query_type={query_type}, round={search_round}"
    )
    
    return {'search_plan': search_plan}
