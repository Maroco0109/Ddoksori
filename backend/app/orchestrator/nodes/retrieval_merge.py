"""
똑소리 프로젝트 - Retrieval 결과 병합 노드 (Phase 5: MAS Supervisor)

작성일: 2026-01-26

[역할]
4개 Retrieval Agent(Law, Criteria, Case, Counsel)의 병렬 실행 결과를
하나의 RetrievalResult로 병합합니다.

[워크플로우]
Supervisor → Fan-out → [Law|Criteria|Case|Counsel] → retrieval_merge → Supervisor

[병합 전략]
1. 각 Agent 결과의 documents를 해당 섹션(laws, criteria, disputes, counsels)으로 분류
2. RRF(Reciprocal Rank Fusion) 기반 점수 재계산 (옵션)
3. 최대/평균 유사도 통계 계산
4. Supervisor 상태 업데이트 (completed_tasks에 'retrieval' 추가)
"""

import logging
import time
from typing import Dict, Any, List, Optional

from ..state import ChatState, RetrievalResult, IndividualRetrievalResult

logger = logging.getLogger(__name__)


def _calculate_merged_statistics(
    individual_results: List[IndividualRetrievalResult]
) -> Dict[str, float]:
    """
    개별 결과들의 통계 계산

    Args:
        individual_results: 4개 Agent의 결과 리스트

    Returns:
        max_similarity, avg_similarity 딕셔너리
    """
    all_similarities = []
    for result in individual_results:
        if result.get('max_similarity'):
            all_similarities.append(result['max_similarity'])
        if result.get('avg_similarity'):
            all_similarities.append(result['avg_similarity'])

    if not all_similarities:
        return {'max_similarity': 0.0, 'avg_similarity': 0.0}

    return {
        'max_similarity': max(all_similarities),
        'avg_similarity': sum(all_similarities) / len(all_similarities),
    }


def _merge_to_retrieval_result(
    individual_results: List[IndividualRetrievalResult]
) -> RetrievalResult:
    """
    개별 결과를 RetrievalResult 4섹션 구조로 병합

    Args:
        individual_results: 4개 Agent의 결과 리스트

    Returns:
        병합된 RetrievalResult
    """
    # 4섹션 초기화
    merged: RetrievalResult = {
        'agency': {},
        'disputes': [],
        'counsels': [],
        'laws': [],
        'criteria': [],
        'max_similarity': 0.0,
        'avg_similarity': 0.0,
    }

    # 소스별 매핑
    source_to_section = {
        'law': 'laws',
        'criteria': 'criteria',
        'case': 'disputes',  # case → disputes 섹션
        'counsel': 'counsels',
    }

    for result in individual_results:
        source = result.get('source', '')
        section_key = source_to_section.get(source)

        if section_key and result.get('documents'):
            # 해당 섹션에 문서 추가
            merged[section_key].extend(result['documents'])

        # 에러 로깅
        if result.get('error'):
            logger.warning(f"[RetrievalMerge] {source} agent error: {result['error']}")

    # 통계 계산
    stats = _calculate_merged_statistics(individual_results)
    merged['max_similarity'] = stats['max_similarity']
    merged['avg_similarity'] = stats['avg_similarity']

    return merged


def _update_supervisor_state(
    current_supervisor: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Supervisor 상태 업데이트: completed_tasks에 'retrieval' 추가

    Args:
        current_supervisor: 현재 supervisor 상태

    Returns:
        업데이트된 supervisor 상태
    """
    if current_supervisor is None:
        # 초기 상태 생성
        return {
            'current_phase': 'drafting',
            'agent_messages': [],
            'pending_tasks': [],
            'completed_tasks': ['retrieval'],
            'supervisor_reasoning': 'Retrieval completed',
            'next_agent': None,
            'iteration_count': 0,
        }

    completed = list(current_supervisor.get('completed_tasks', []))
    if 'retrieval' not in completed:
        completed.append('retrieval')

    return {
        **current_supervisor,
        'current_phase': 'drafting',
        'completed_tasks': completed,
    }


async def retrieval_merge_node(state: ChatState) -> Dict[str, Any]:
    """
    Retrieval 결과 병합 노드 (async)

    4개 Retrieval Agent의 결과를 하나의 RetrievalResult로 병합합니다.

    Args:
        state: ChatState (individual_retrieval_results 포함)

    Returns:
        Dict with:
            - retrieval: 병합된 RetrievalResult
            - sources: 인용 출처 리스트 (추가)
            - supervisor: 업데이트된 SupervisorState
    """
    start_time = time.time()

    # 개별 결과 가져오기
    individual_results = state.get('individual_retrieval_results', [])

    logger.info(f"[RetrievalMerge] Merging {len(individual_results)} agent results")

    # 결과 병합
    merged = _merge_to_retrieval_result(individual_results)

    # 출처 목록 생성 (sources 필드용)
    sources = []
    for section_key in ['laws', 'criteria', 'disputes', 'counsels']:
        for doc in merged.get(section_key, []):
            if doc.get('chunk_id') or doc.get('doc_id'):
                sources.append({
                    'type': section_key,
                    'id': doc.get('chunk_id') or doc.get('doc_id'),
                    'title': doc.get('title', ''),
                    'similarity': doc.get('similarity', 0.0),
                })

    # Supervisor 상태 업데이트
    updated_supervisor = _update_supervisor_state(state.get('supervisor'))

    elapsed = time.time() - start_time
    logger.info(
        f"[RetrievalMerge] Completed in {elapsed*1000:.1f}ms: "
        f"laws={len(merged['laws'])}, criteria={len(merged['criteria'])}, "
        f"disputes={len(merged['disputes'])}, counsels={len(merged['counsels'])}"
    )

    return {
        'retrieval': merged,
        'sources': sources,
        'supervisor': updated_supervisor,
    }


def retrieval_merge_node_sync(state: ChatState) -> Dict[str, Any]:
    """
    Retrieval 결과 병합 노드 (sync 버전)

    LangGraph 노드로 직접 사용 가능한 동기 버전입니다.
    """
    import asyncio
    return asyncio.run(retrieval_merge_node(state))


__all__ = ['retrieval_merge_node', 'retrieval_merge_node_sync']
