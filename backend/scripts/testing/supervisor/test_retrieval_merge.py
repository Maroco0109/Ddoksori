"""
Retrieval Merge Node 단위 테스트 (Phase 5: MAS Supervisor)

작성일: 2026-01-26

테스트 대상: backend/app/orchestrator/nodes/retrieval_merge.py
"""

import pytest
from typing import Dict, Any, List

# 전체 파일에 unit 마커 적용 (DB 의존성 없음)
pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# === Test Fixtures ===

@pytest.fixture
def sample_individual_results() -> List[Dict[str, Any]]:
    """4개 Agent의 샘플 개별 결과"""
    return [
        {
            'source': 'law',
            'documents': [
                {'chunk_id': 'law_001', 'title': '소비자기본법 제17조', 'content': '환불 규정', 'similarity': 0.92},
                {'chunk_id': 'law_002', 'title': '전자상거래법 제17조', 'content': '청약철회', 'similarity': 0.88},
            ],
            'max_similarity': 0.92,
            'avg_similarity': 0.90,
            'search_time_ms': 150,
        },
        {
            'source': 'criteria',
            'documents': [
                {'chunk_id': 'cri_001', 'title': '전자제품 품질기준', 'content': '노트북 환불 기준', 'similarity': 0.85},
            ],
            'max_similarity': 0.85,
            'avg_similarity': 0.85,
            'search_time_ms': 120,
        },
        {
            'source': 'case',
            'documents': [
                {'chunk_id': 'case_001', 'title': '노트북 환불 사례', 'content': '유사 분쟁 조정 사례', 'similarity': 0.78},
                {'chunk_id': 'case_002', 'title': '전자제품 하자 사례', 'content': '제품 하자 조정', 'similarity': 0.75},
            ],
            'max_similarity': 0.78,
            'avg_similarity': 0.76,
            'search_time_ms': 200,
        },
        {
            'source': 'counsel',
            'documents': [
                {'chunk_id': 'coun_001', 'title': '환불 상담 사례', 'content': '고객 문의 사례', 'similarity': 0.70},
            ],
            'max_similarity': 0.70,
            'avg_similarity': 0.70,
            'search_time_ms': 100,
        },
    ]


@pytest.fixture
def empty_results() -> List[Dict[str, Any]]:
    """빈 결과 (모든 Agent가 결과 없음)"""
    return []


@pytest.fixture
def partial_results() -> List[Dict[str, Any]]:
    """일부 Agent만 결과 반환"""
    return [
        {
            'source': 'law',
            'documents': [{'chunk_id': 'law_001', 'title': '법령', 'similarity': 0.80}],
            'max_similarity': 0.80,
            'avg_similarity': 0.80,
        },
        {
            'source': 'counsel',
            'documents': [],  # 빈 결과
            'max_similarity': 0.0,
            'avg_similarity': 0.0,
            'error': 'No documents found',
        },
    ]


@pytest.fixture
def mock_state_with_results(sample_individual_results) -> Dict[str, Any]:
    """개별 결과가 포함된 Mock ChatState"""
    return {
        'user_query': '노트북 환불이 안된다고 합니다',
        'individual_retrieval_results': sample_individual_results,
        'supervisor': {
            'current_phase': 'retrieving',
            'completed_tasks': ['query_analysis'],
            'pending_tasks': ['retrieval', 'draft', 'review'],
            'agent_messages': [],
            'supervisor_reasoning': '',
            'next_agent': None,
            'iteration_count': 1,
        },
    }


# === Unit Tests ===

class TestMergeToRetrievalResult:
    """_merge_to_retrieval_result 함수 테스트"""

    def test_merge_all_four_sources(self, sample_individual_results):
        """4개 소스 모두 정상 병합"""
        from app.supervisor.nodes.retrieval_merge import _merge_to_retrieval_result

        merged = _merge_to_retrieval_result(sample_individual_results)

        # 각 섹션에 올바른 문서 수
        assert len(merged['laws']) == 2
        assert len(merged['criteria']) == 1
        assert len(merged['disputes']) == 2  # case → disputes
        assert len(merged['counsels']) == 1

    def test_merge_preserves_document_content(self, sample_individual_results):
        """병합 시 문서 내용 보존"""
        from app.supervisor.nodes.retrieval_merge import _merge_to_retrieval_result

        merged = _merge_to_retrieval_result(sample_individual_results)

        # 법령 문서 내용 확인
        law_titles = [doc['title'] for doc in merged['laws']]
        assert '소비자기본법 제17조' in law_titles
        assert '전자상거래법 제17조' in law_titles

    def test_merge_empty_results(self, empty_results):
        """빈 결과 처리"""
        from app.supervisor.nodes.retrieval_merge import _merge_to_retrieval_result

        merged = _merge_to_retrieval_result(empty_results)

        assert len(merged['laws']) == 0
        assert len(merged['criteria']) == 0
        assert len(merged['disputes']) == 0
        assert len(merged['counsels']) == 0

    def test_merge_partial_results(self, partial_results):
        """일부 Agent만 결과 있을 때"""
        from app.supervisor.nodes.retrieval_merge import _merge_to_retrieval_result

        merged = _merge_to_retrieval_result(partial_results)

        assert len(merged['laws']) == 1
        assert len(merged['counsels']) == 0  # 빈 결과


class TestCalculateMergedStatistics:
    """_calculate_merged_statistics 함수 테스트"""

    def test_statistics_calculation(self, sample_individual_results):
        """통계 계산 검증"""
        from app.supervisor.nodes.retrieval_merge import _calculate_merged_statistics

        stats = _calculate_merged_statistics(sample_individual_results)

        # max_similarity: 가장 높은 값 (0.92)
        assert stats['max_similarity'] == 0.92
        # avg_similarity: 모든 유사도의 평균
        assert 0.7 < stats['avg_similarity'] < 0.9

    def test_statistics_empty_results(self, empty_results):
        """빈 결과의 통계"""
        from app.supervisor.nodes.retrieval_merge import _calculate_merged_statistics

        stats = _calculate_merged_statistics(empty_results)

        assert stats['max_similarity'] == 0.0
        assert stats['avg_similarity'] == 0.0


class TestUpdateSupervisorState:
    """_update_supervisor_state 함수 테스트"""

    def test_update_existing_supervisor(self):
        """기존 Supervisor 상태 업데이트"""
        from app.supervisor.nodes.retrieval_merge import _update_supervisor_state

        current = {
            'current_phase': 'retrieving',
            'completed_tasks': ['query_analysis'],
            'pending_tasks': [],
            'agent_messages': [],
            'supervisor_reasoning': '',
            'next_agent': None,
            'iteration_count': 1,
        }

        updated = _update_supervisor_state(current)

        assert 'retrieval' in updated['completed_tasks']
        assert 'query_analysis' in updated['completed_tasks']
        assert updated['current_phase'] == 'drafting'

    def test_update_none_supervisor(self):
        """None Supervisor → 초기 상태 생성"""
        from app.supervisor.nodes.retrieval_merge import _update_supervisor_state

        updated = _update_supervisor_state(None)

        assert updated['completed_tasks'] == ['retrieval']
        assert updated['current_phase'] == 'drafting'

    def test_no_duplicate_retrieval(self):
        """retrieval 중복 추가 방지"""
        from app.supervisor.nodes.retrieval_merge import _update_supervisor_state

        current = {
            'completed_tasks': ['query_analysis', 'retrieval'],  # 이미 있음
            'current_phase': 'retrieving',
        }

        updated = _update_supervisor_state(current)

        # 'retrieval'이 한 번만 있어야 함
        assert updated['completed_tasks'].count('retrieval') == 1


class TestRetrievalMergeNode:
    """retrieval_merge_node 전체 테스트"""

    async def test_full_merge_workflow(self, mock_state_with_results):
        """전체 병합 워크플로우"""
        from app.supervisor.nodes.retrieval_merge import retrieval_merge_node

        result = await retrieval_merge_node(mock_state_with_results)

        # 필수 출력 필드 확인
        assert 'retrieval' in result
        assert 'sources' in result
        assert 'supervisor' in result

        # retrieval 구조 확인
        retrieval = result['retrieval']
        assert 'laws' in retrieval
        assert 'criteria' in retrieval
        assert 'disputes' in retrieval
        assert 'counsels' in retrieval

        # 통계 확인
        assert retrieval['max_similarity'] > 0
        assert retrieval['avg_similarity'] > 0

    async def test_sources_generation(self, mock_state_with_results):
        """출처 목록 생성 검증"""
        from app.supervisor.nodes.retrieval_merge import retrieval_merge_node

        result = await retrieval_merge_node(mock_state_with_results)

        sources = result['sources']

        # display_law=1이므로 법령 2개 중 1개만 노출 → 총 5개
        assert len(sources) == 5

        # 출처 타입 확인
        source_types = [s['type'] for s in sources]
        assert 'laws' in source_types
        assert 'criteria' in source_types
        assert 'disputes' in source_types
        assert 'counsels' in source_types

    async def test_supervisor_state_updated(self, mock_state_with_results):
        """Supervisor 상태 업데이트 확인"""
        from app.supervisor.nodes.retrieval_merge import retrieval_merge_node

        result = await retrieval_merge_node(mock_state_with_results)

        supervisor = result['supervisor']

        assert 'retrieval' in supervisor['completed_tasks']
        assert supervisor['current_phase'] == 'drafting'


class TestEdgeCases:
    """Edge cases 테스트"""

    async def test_missing_individual_results(self):
        """individual_retrieval_results 필드 없음"""
        from app.supervisor.nodes.retrieval_merge import retrieval_merge_node

        state = {'user_query': 'test', 'supervisor': None}
        result = await retrieval_merge_node(state)

        # 빈 결과지만 정상 처리
        assert result['retrieval']['laws'] == []
        assert result['sources'] == []

    async def test_agent_with_error(self):
        """에러가 있는 Agent 결과 처리"""
        from app.supervisor.nodes.retrieval_merge import retrieval_merge_node

        state = {
            'individual_retrieval_results': [
                {'source': 'law', 'documents': [], 'error': 'DB connection failed'},
                {'source': 'criteria', 'documents': [{'chunk_id': 'c1'}], 'max_similarity': 0.8},
            ],
            'supervisor': None,
        }

        # 에러 있어도 나머지 결과는 정상 처리
        result = await retrieval_merge_node(state)
        assert len(result['retrieval']['criteria']) == 1


