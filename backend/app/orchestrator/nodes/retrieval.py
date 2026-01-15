"""
똑소리 프로젝트 - 정보검색 노드
작성일: 2026-01-14
S2-3: StructuredRetriever를 활용한 4섹션 검색

검색 노드의 역할:
1. query_analysis 결과를 활용하여 검색 쿼리 구성
2. StructuredRetriever.search_all_sections() 호출
3. 검색 결과를 RetrievalResult로 변환하여 상태에 저장
"""

import os
from typing import Dict, List, Any

from ..state import ChatState, RetrievalResult


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
    """임베딩 API URL 반환"""
    return os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')


def _build_search_query(state: ChatState) -> str:
    """
    검색 쿼리 구성
    
    user_query + onboarding 정보를 조합하여 검색 쿼리 생성.
    query_analysis의 keywords를 활용할 수도 있음.
    """
    user_query = state.get('user_query', '')
    onboarding = state.get('onboarding')
    
    # 기본 쿼리
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


def _convert_to_retrieval_result(raw_result: Dict[str, Any]) -> RetrievalResult:
    """
    StructuredRetriever 결과를 RetrievalResult로 변환
    """
    return RetrievalResult(
        agency=raw_result.get('agency', {}),
        disputes=raw_result.get('disputes', []),
        counsels=raw_result.get('counsels', []),
        laws=raw_result.get('laws', []),
        criteria=raw_result.get('criteria', []),
    )


def _build_sources_from_retrieval(retrieval: RetrievalResult) -> List[Dict]:
    """
    검색 결과에서 sources 리스트 생성
    
    각 섹션의 결과를 통합하여 출처 정보 생성.
    """
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
    정보검색 노드 함수
    
    StructuredRetriever를 사용하여 4개 섹션 검색 수행.
    DB 연결 실패 시 빈 결과 반환.
    
    Args:
        state: 현재 ChatState
        
    Returns:
        부분 상태 업데이트 dict:
        {
            'retrieval': RetrievalResult,
            'sources': List[Dict]  # operator.add로 누적됨
        }
    """
    # query_analysis가 general이면 검색 스킵
    query_analysis = state.get('query_analysis')
    if query_analysis and query_analysis.get('query_type') == 'general':
        empty_retrieval: RetrievalResult = {
            'agency': {},
            'disputes': [],
            'counsels': [],
            'laws': [],
            'criteria': [],
        }
        return {
            'retrieval': empty_retrieval,
            'sources': [],
        }
    
    # 검색 쿼리 구성
    search_query = _build_search_query(state)
    
    try:
        # StructuredRetriever import (지연 import로 순환 참조 방지)
        from rag.specialized_retrievers import StructuredRetriever
        
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
        # DB 연결 실패 등 예외 시 빈 결과
        print(f"[retrieval_node] Error: {e}")
        empty_retrieval: RetrievalResult = {
            'agency': {},
            'disputes': [],
            'counsels': [],
            'laws': [],
            'criteria': [],
        }
        return {
            'retrieval': empty_retrieval,
            'sources': [],
        }
