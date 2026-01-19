"""
똑소리 프로젝트 - ReAct 액션 노드
작성일: 2026-01-17
S2-7: ReAct 패턴 구현 - 액션(Action) 노드

ReAct 패턴의 Action 단계를 담당하는 노드.
last_action에 따라 적절한 도구(검색기)를 실행하고 결과를 기록.
"""

import os
from typing import Dict, List, Any

from ...orchestrator.state import ChatState, RetrievalResult, ReActStep


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

    user_query + onboarding + query_analysis를 조합.
    """
    user_query = state.get('user_query', '')
    onboarding = state.get('onboarding')
    query_analysis = state.get('query_analysis') or {}

    query_parts = [user_query]

    # 온보딩 정보 추가
    if onboarding:
        onboarding_dict = dict(onboarding)
        purchase_item = onboarding_dict.get('purchase_item')
        dispute_details = onboarding_dict.get('dispute_details')
        if purchase_item:
            query_parts.append(f"품목: {purchase_item}")
        if dispute_details:
            query_parts.append(f"상황: {dispute_details}")

    # 재작성된 쿼리 사용 (있을 경우)
    rewritten_query = query_analysis.get('rewritten_query')
    if rewritten_query:
        return rewritten_query

    return " ".join(query_parts)


def _execute_search_all(query: str) -> tuple[Dict[str, Any], str]:
    """
    전체 섹션 검색 (disputes, counsels, laws, criteria)

    Returns:
        (검색 결과 dict, observation 문자열)
    """
    try:
        from ..retrieval.tools.specialized_retrievers import StructuredRetriever

        db_config = _get_db_config()
        embed_api_url = _get_embed_api_url()

        retriever = StructuredRetriever(db_config, embed_api_url)
        retriever.connect()

        try:
            raw_result = retriever.search_all_sections(
                query=query,
                dispute_k=3,
                counsel_k=3,
                law_k=3,
                criteria_k=3,
            )
        finally:
            retriever.close()

        # 결과 카운트
        n_disputes = len(raw_result.get('disputes', []))
        n_counsels = len(raw_result.get('counsels', []))
        n_laws = len(raw_result.get('laws', []))
        n_criteria = len(raw_result.get('criteria', []))

        observation = (
            f"전체 검색 완료: 분쟁사례 {n_disputes}건, "
            f"상담사례 {n_counsels}건, 법령 {n_laws}건, 기준 {n_criteria}건"
        )

        return raw_result, observation

    except Exception as e:
        return {}, f"검색 실패: {str(e)}"


def _execute_search_criteria(query: str) -> tuple[List[Dict], str]:
    """
    분쟁해결기준만 검색

    Returns:
        (기준 결과 리스트, observation 문자열)
    """
    try:
        from ..retrieval.tools.specialized_retrievers import StructuredRetriever

        db_config = _get_db_config()
        embed_api_url = _get_embed_api_url()

        retriever = StructuredRetriever(db_config, embed_api_url)
        retriever.connect()

        try:
            result = retriever.search_criteria(query=query, top_k=5)
        finally:
            retriever.close()

        observation = f"분쟁해결기준 {len(result)}건 검색 완료"
        return result, observation

    except Exception as e:
        return [], f"기준 검색 실패: {str(e)}"


def _execute_search_laws(query: str) -> tuple[List[Dict], str]:
    """
    법령만 검색

    Returns:
        (법령 결과 리스트, observation 문자열)
    """
    try:
        from ..retrieval.tools.specialized_retrievers import StructuredRetriever

        db_config = _get_db_config()
        embed_api_url = _get_embed_api_url()

        retriever = StructuredRetriever(db_config, embed_api_url)
        retriever.connect()

        try:
            result = retriever.search_laws(query=query, top_k=5)
        finally:
            retriever.close()

        observation = f"법령 {len(result)}건 검색 완료"
        return result, observation

    except Exception as e:
        return [], f"법령 검색 실패: {str(e)}"


def _merge_retrieval(
    current: Dict[str, Any],
    new_data: Dict[str, Any],
    section: str = None
) -> RetrievalResult:
    """
    기존 검색 결과에 새 데이터 병합

    Args:
        current: 기존 retrieval 결과
        new_data: 새로운 검색 결과
        section: 특정 섹션만 업데이트할 경우 (criteria, laws 등)

    Returns:
        병합된 RetrievalResult
    """
    if section:
        # 특정 섹션만 업데이트
        merged = dict(current) if current else {}
        merged[section] = new_data
    else:
        # 전체 병합 (new_data로 덮어쓰기)
        merged = new_data

    # 유사도 재계산
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


def _build_sources_from_retrieval(retrieval: RetrievalResult) -> List[Dict]:
    """
    검색 결과에서 sources 리스트 생성
    """
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


def react_act_node(state: ChatState) -> Dict:
    """
    ReAct 액션 노드

    last_action에 따라 적절한 도구(검색기)를 실행하고
    결과를 state에 저장, react_steps에 기록.

    지원 액션:
    - search_all: 전체 섹션 검색
    - search_criteria: 분쟁해결기준만 검색
    - search_laws: 법령만 검색
    - ask_clarification: 사용자에게 추가 정보 요청 (미구현)

    Args:
        state: 현재 ChatState

    Returns:
        부분 상태 업데이트:
        {
            'retrieval': RetrievalResult,
            'sources': List[Dict],
            'last_observation': str,
            'react_steps': List[ReActStep],
        }
    """
    action = state.get('last_action')
    thought = state.get('last_thought', '')
    query = _build_search_query(state)
    current_retrieval = state.get('retrieval') or {}

    if action == 'search_all':
        raw_result, observation = _execute_search_all(query)
        retrieval = _merge_retrieval(current_retrieval, raw_result)
        sources = _build_sources_from_retrieval(retrieval)

        react_step: ReActStep = {
            'thought': thought,
            'action': action,
            'action_input': {'query': query},
            'observation': observation,
        }

        return {
            'retrieval': retrieval,
            'sources': sources,
            'last_observation': observation,
            'react_steps': [react_step],
        }

    elif action == 'search_criteria':
        criteria_result, observation = _execute_search_criteria(query)
        retrieval = _merge_retrieval(
            current_retrieval, criteria_result, section='criteria'
        )
        sources = _build_sources_from_retrieval(retrieval)

        react_step: ReActStep = {
            'thought': thought,
            'action': action,
            'action_input': {'query': query},
            'observation': observation,
        }

        return {
            'retrieval': retrieval,
            'sources': sources,
            'last_observation': observation,
            'react_steps': [react_step],
        }

    elif action == 'search_laws':
        laws_result, observation = _execute_search_laws(query)
        retrieval = _merge_retrieval(
            current_retrieval, laws_result, section='laws'
        )
        sources = _build_sources_from_retrieval(retrieval)

        react_step: ReActStep = {
            'thought': thought,
            'action': action,
            'action_input': {'query': query},
            'observation': observation,
        }

        return {
            'retrieval': retrieval,
            'sources': sources,
            'last_observation': observation,
            'react_steps': [react_step],
        }

    elif action == 'ask_clarification':
        observation = "사용자에게 추가 정보 요청"
        react_step: ReActStep = {
            'thought': thought,
            'action': action,
            'action_input': {},
            'observation': observation,
        }

        return {
            'last_observation': observation,
            'react_steps': [react_step],
            'awaiting_user_choice': True,
        }

    else:
        observation = f"알 수 없는 액션: {action}"
        return {
            'last_observation': observation,
            'react_steps': [{
                'thought': thought,
                'action': action or 'unknown',
                'action_input': {},
                'observation': observation,
            }],
        }
