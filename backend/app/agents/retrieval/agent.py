"""
똑소리 프로젝트 - 정보검색 에이전트 (Retrieval Agent)

작성일: 2026-01-14
최종 수정: 2026-01-22

[역할 및 책임]
사용자 질문 및 검색 계획(Search Plan)을 바탕으로 관련 정보를 검색합니다.
다양한 데이터 소스(분쟁사례, 상담사례, 법령, 기준)를 통합 검색하며, 
벡터 검색(Vector)과 키워드 검색(Keyword)을 혼합한 하이브리드 검색을 수행할 수 있습니다.

[지원하는 리트리버 타입]
- structured: 4개 섹션(사례/상담/법령/기준)을 모두 검색하는 기본 리트리버
- hybrid: 벡터 + 키워드 검색 결합 (RRF)
- law: 법령 전문 검색
- criteria: 분쟁조정기준 검색
- dispute/counsel: 사례 검색
- rdb: SQL 기반 정형 데이터 검색

[Output]
- RetrievalResult: 검색 결과 (유사도 점수 포함)
- sources: 출처 메타데이터 목록 (답변 생성 시 인용에 사용)
"""

import logging
import os
from typing import Dict, List, Any, Optional, Union

from ...orchestrator.state import (
    ChatState,
    ChatState_v2,
    RetrievalResult,
    SearchPlan,
)

logger = logging.getLogger(__name__)


# DB 설정 (환경변수에서 로드)
def _get_db_config() -> Dict[str, str]:
    """데이터베이스 연결 설정 반환"""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'dbname': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
    }


def _get_embed_api_url() -> str:
    return os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')


RETRIEVER_TYPE_STRUCTURED = 'structured'
RETRIEVER_TYPE_HYBRID = 'hybrid'
RETRIEVER_TYPE_LAW = 'law'
RETRIEVER_TYPE_CRITERIA = 'criteria'
RETRIEVER_TYPE_DISPUTE = 'dispute'
RETRIEVER_TYPE_COUNSEL = 'counsel'
RETRIEVER_TYPE_RDB = 'rdb'


def _build_search_query(state: Union[ChatState, ChatState_v2]) -> str:
    user_query = state.get('user_query', '')
    onboarding = state.get('onboarding')
    
    query_parts = [user_query]
    
    if onboarding:
        onboarding_dict = dict(onboarding)
        purchase_item = onboarding_dict.get('purchase_item')
        dispute_details = onboarding_dict.get('dispute_details')
        if purchase_item:
            query_parts.append(f"품목: {purchase_item}")
        if dispute_details:
            query_parts.append(f"상황: {dispute_details}")
    
    return " ".join(query_parts)


def _build_search_query_from_plan(
    state: Union[ChatState, ChatState_v2],
    search_plan: Optional[SearchPlan],
) -> str:
    if search_plan:
        query = search_plan.get('query')
        if query:
            return query
    return _build_search_query(state)


def _convert_to_retrieval_result(raw_result: Dict[str, Any]) -> RetrievalResult:
    disputes = raw_result.get('disputes', [])
    counsels = raw_result.get('counsels', [])
    
    all_similarities = []
    for d in disputes:
        all_similarities.append(d.get('similarity', 0))
    for c in counsels:
        all_similarities.append(c.get('similarity', 0))
    
    max_sim = max(all_similarities) if all_similarities else 0.0
    avg_sim = sum(all_similarities) / len(all_similarities) if all_similarities else 0.0
    
    return RetrievalResult(
        agency=raw_result.get('agency', {}),
        disputes=disputes,
        counsels=counsels,
        laws=raw_result.get('laws', []),
        criteria=raw_result.get('criteria', []),
        max_similarity=max_sim,
        avg_similarity=avg_sim,
    )


def _build_sources_from_retrieval(retrieval: RetrievalResult) -> List[Dict]:
    sources: List[Dict] = []
    
    # 분쟁조정사례
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
    
    # 상담사례
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
    
    # 법령
    for i, law in enumerate(retrieval.get('laws', [])):
        sources.append({
            'type': 'law',
            'index': i + 1,
            'unit_id': law.get('unit_id', ''),
            'law_name': law.get('law_name', ''),
            'full_path': law.get('full_path', ''),
            'similarity': law.get('similarity', 0),
        })
    
    # 기준
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


def retrieval_node(state: ChatState) -> Dict:
    """
    [정보검색 노드 (Legacy)]
    
    기본적인 StructuredRetriever를 사용하여 4개 섹션(분쟁/상담/법령/기준)을 모두 검색합니다.
    검색 계획(Search Plan) 없이 고정된 Top-K(3)로 검색합니다.
    
    Args:
        state: 현재 ChatState
        
    Returns:
        부분 상태 업데이트 dict:
        {
            'retrieval': RetrievalResult,
            'sources': List[Dict]  # operator.add로 누적됨
        }
    """
    query_analysis = state.get('query_analysis')
    if query_analysis and query_analysis.get('query_type') == 'general':
        empty_retrieval: RetrievalResult = {
            'agency': {},
            'disputes': [],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'max_similarity': 0.0,
            'avg_similarity': 0.0,
        }
        return {
            'retrieval': empty_retrieval,
            'sources': [],
        }
    
    # 검색 쿼리 구성
    search_query = _build_search_query(state)
    
    try:
        # StructuredRetriever import (지연 import로 순환 참조 방지)
        from .tools.specialized_retrievers import StructuredRetriever
        
        db_config = _get_db_config()
        embed_api_url = _get_embed_api_url()
        
        retriever = StructuredRetriever(db_config, embed_api_url)
        retriever.connect()
        
        try:
            # 4섹션 검색 수행
            raw_result = retriever.search_all_sections(
                query=search_query,
                dispute_k=3,
                counsel_k=3,
                law_k=3,
                criteria_k=3,
            )
        finally:
            retriever.close()
        
        # 결과 변환
        retrieval_result = _convert_to_retrieval_result(raw_result)
        sources = _build_sources_from_retrieval(retrieval_result)
        
        return {
            'retrieval': retrieval_result,
            'sources': sources,
        }
        
    except Exception as e:
        logger.error(f"[retrieval_node] Error: {e}")
        empty_retrieval: RetrievalResult = {
            'agency': {},
            'disputes': [],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'max_similarity': 0.0,
            'avg_similarity': 0.0,
        }
        return {
            'retrieval': empty_retrieval,
            'sources': [],
        }


def _create_empty_retrieval() -> RetrievalResult:
    return RetrievalResult(
        agency={},
        disputes=[],
        counsels=[],
        laws=[],
        criteria=[],
        max_similarity=0.0,
        avg_similarity=0.0,
    )


def _execute_retrieval_by_type(
    retriever_type: str,
    query: str,
    top_k: int,
    db_config: Dict[str, str],
    embed_api_url: str,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    지정된 리트리버 타입에 따라 검색을 실행합니다.
    
    - structured: 기본 4-섹션 검색
    - hybrid: 벡터 + 키워드 검색 (RRF Fusion)
    - law/criteria/dispute/counsel: 특정 도메인 전용 검색
    - rdb: SQL 쿼리 기반 정형 데이터 검색
    """
    from .tools.specialized_retrievers import (
        StructuredRetriever,
        LawRetriever,
        CriteriaRetriever,
        CaseRetriever,
        AgencyClassifier,
    )
    from .tools.hybrid_retriever import HybridRetriever
    
    result: Dict[str, Any] = {
        'agency': {},
        'disputes': [],
        'counsels': [],
        'laws': [],
        'criteria': [],
    }
    
    if retriever_type == RETRIEVER_TYPE_STRUCTURED:
        retriever = StructuredRetriever(db_config, embed_api_url)
        retriever.connect()
        try:
            raw = retriever.search_all_sections(
                query=query,
                dispute_k=top_k,
                counsel_k=top_k,
                law_k=top_k,
                criteria_k=top_k,
            )
            result.update(raw)
        finally:
            retriever.close()
    
    elif retriever_type == RETRIEVER_TYPE_HYBRID:
        retriever = HybridRetriever(db_config, embed_api_url)
        retriever.connect()
        try:
            search_results = retriever.search(query, top_k=top_k)
            disputes = []
            counsels = []
            for r in search_results:
                item = {
                    'chunk_id': r.chunk_id,
                    'doc_id': r.doc_id,
                    'content': r.content,
                    'doc_title': r.doc_title,
                    'source_org': r.source_org,
                    'similarity': r.similarity,
                }
                if r.doc_type == 'mediation_case':
                    disputes.append(item)
                elif r.doc_type == 'counsel_case':
                    counsels.append(item)
            result['disputes'] = disputes
            result['counsels'] = counsels
            classifier = AgencyClassifier()
            result['agency'] = classifier.classify(query)
        finally:
            retriever.close()
    
    elif retriever_type == RETRIEVER_TYPE_LAW:
        retriever = LawRetriever(db_config, embed_api_url)
        retriever.connect()
        try:
            law_results = retriever.search_two_stage(query, top_k)
            result['laws'] = [
                {
                    'unit_id': r.unit_id,
                    'law_name': r.law_name,
                    'full_path': r.full_path,
                    'text': r.text,
                    'similarity': r.similarity,
                }
                for r in law_results
            ]
        finally:
            retriever.close()
    
    elif retriever_type == RETRIEVER_TYPE_CRITERIA:
        retriever = CriteriaRetriever(db_config, embed_api_url)
        retriever.connect()
        try:
            criteria_results = retriever.search_two_stage(query, top_k)
            result['criteria'] = [
                {
                    'unit_id': r.unit_id,
                    'source_label': r.source_label,
                    'category': r.category,
                    'item': r.item,
                    'unit_text': r.unit_text,
                    'similarity': r.similarity,
                }
                for r in criteria_results
            ]
        finally:
            retriever.close()
    
    elif retriever_type == RETRIEVER_TYPE_DISPUTE:
        retriever = CaseRetriever(db_config, embed_api_url)
        retriever.connect()
        try:
            result['disputes'] = retriever.search_disputes(query, top_k)
            classifier = AgencyClassifier()
            result['agency'] = classifier.classify(query)
        finally:
            retriever.close()
    
    elif retriever_type == RETRIEVER_TYPE_COUNSEL:
        retriever = CaseRetriever(db_config, embed_api_url)
        retriever.connect()
        try:
            result['counsels'] = retriever.search_counsels(query, top_k)
        finally:
            retriever.close()
    
    elif retriever_type == RETRIEVER_TYPE_RDB:
        from .tools.rdb_retriever import RDBRetriever
        
        retriever = RDBRetriever(db_config)
        retriever.connect()
        try:
            sql_params = filters or {}
            rdb_results = retriever.search_from_params(sql_params, top_k=top_k)
            
            for crit in rdb_results.get('criteria', []):
                result['criteria'].append({
                    'unit_id': crit.unit_id,
                    'source_label': crit.source_label,
                    'category': crit.category,
                    'item': crit.item,
                    'unit_text': crit.unit_text,
                    'similarity': 1.0,
                })
            
            for law in rdb_results.get('laws', []):
                result['laws'].append({
                    'unit_id': law.doc_id,
                    'law_name': law.law_name,
                    'full_path': law.path,
                    'text': law.text,
                    'similarity': 1.0,
                })
        finally:
            retriever.close()
    
    return result


def _merge_retrieval_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        'agency': {},
        'disputes': [],
        'counsels': [],
        'laws': [],
        'criteria': [],
    }
    
    seen_disputes = set()
    seen_counsels = set()
    seen_laws = set()
    seen_criteria = set()
    
    for r in results:
        if r.get('agency') and not merged['agency']:
            merged['agency'] = r['agency']
        
        for d in r.get('disputes', []):
            key = d.get('chunk_id') or d.get('doc_id')
            if key and key not in seen_disputes:
                seen_disputes.add(key)
                merged['disputes'].append(d)
        
        for c in r.get('counsels', []):
            key = c.get('chunk_id') or c.get('doc_id')
            if key and key not in seen_counsels:
                seen_counsels.add(key)
                merged['counsels'].append(c)
        
        for law in r.get('laws', []):
            key = law.get('unit_id')
            if key and key not in seen_laws:
                seen_laws.add(key)
                merged['laws'].append(law)
        
        for crit in r.get('criteria', []):
            key = crit.get('unit_id')
            if key and key not in seen_criteria:
                seen_criteria.add(key)
                merged['criteria'].append(crit)
    
    return merged


def retrieval_node_v2(state: ChatState_v2) -> Dict[str, Any]:
    """
    [정보검색 노드 (V2)]
    
    ReAct Agent 또는 Search Plan이 결정한 검색 전략(retrievers, top_k, filters)에 따라
    유연하게 검색을 수행합니다. 여러 리트리버를 조합하여 실행할 수 있습니다.
    
    [동작 흐름]
    1. State에서 search_plan 확인 (없으면 Default StructuredRetriever)
    2. 지정된 리트리버들을 순차 실행
    3. 결과 병합 (Merge) 및 포맷 변환
    """
    search_plan: Optional[SearchPlan] = state.get('search_plan')
    mode = state.get('mode', 'NEED_RAG')
    
    if mode == 'NO_RETRIEVAL':
        logger.info("[retrieval_node_v2] NO_RETRIEVAL mode, skipping")
        return {
            'retrieval': _create_empty_retrieval(),
            'sources': [],
        }
    
    query = _build_search_query_from_plan(state, search_plan)
    
    if not search_plan:
        logger.warning("[retrieval_node_v2] No search_plan, using StructuredRetriever")
        retriever_types = [RETRIEVER_TYPE_STRUCTURED]
        top_k = 10
        filters = {}
    else:
        retriever_types = search_plan.get('retrievers', [RETRIEVER_TYPE_STRUCTURED])
        top_k = search_plan.get('top_k', 10) or 10
        filters = search_plan.get('filters', {})
    
    logger.info(
        f"[retrieval_node_v2] query={query[:50]}..., "
        f"retrievers={retriever_types}, top_k={top_k}"
    )
    
    db_config = _get_db_config()
    embed_api_url = _get_embed_api_url()
    
    try:
        all_results: List[Dict[str, Any]] = []
        
        for retriever_type in retriever_types:
            logger.debug(f"[retrieval_node_v2] Executing retriever: {retriever_type}")
            result = _execute_retrieval_by_type(
                retriever_type=retriever_type,
                query=query,
                top_k=top_k,
                db_config=db_config,
                embed_api_url=embed_api_url,
                filters=filters,
            )
            all_results.append(result)
        
        merged = _merge_retrieval_results(all_results)
        retrieval_result = _convert_to_retrieval_result(merged)
        sources = _build_sources_from_retrieval(retrieval_result)
        
        logger.info(
            f"[retrieval_node_v2] Results: disputes={len(retrieval_result.get('disputes', []))}, "
            f"counsels={len(retrieval_result.get('counsels', []))}, "
            f"laws={len(retrieval_result.get('laws', []))}, "
            f"criteria={len(retrieval_result.get('criteria', []))}"
        )
        
        return {
            'retrieval': retrieval_result,
            'sources': sources,
        }
        
    except Exception as e:
        logger.error(f"[retrieval_node_v2] Error: {e}", exc_info=True)
        return {
            'retrieval': _create_empty_retrieval(),
            'sources': [],
        }
