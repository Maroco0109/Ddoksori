"""
_merge_retrieval_results 테스트 - agents/retrieval/agent.py
작성일: 2026-02-08

테스트 대상:
- _merge_retrieval_results: 여러 검색 결과를 하나로 병합
- 중복 제거 (chunk_id / doc_id 기반 dedup)
- agency 정보 병합
- 빈 입력 처리
- null/missing key 처리
"""

import sys
import types
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

# Mock the broken orchestrator module before importing agent.py
# agent.py (legacy) imports from app.orchestrator.state which doesn't exist
_mock_orchestrator = types.ModuleType("app.orchestrator")
_mock_orchestrator_state = types.ModuleType("app.orchestrator.state")
# Provide stub types that agent.py imports
_mock_orchestrator_state.ChatState = dict
_mock_orchestrator_state.RetrievalResult = dict
sys.modules.setdefault("app.orchestrator", _mock_orchestrator)
sys.modules.setdefault("app.orchestrator.state", _mock_orchestrator_state)

import pytest

pytestmark = pytest.mark.unit

from app.agents.retrieval.agent import _merge_retrieval_results

# ============================================================================
# Empty / Single input tests
# ============================================================================


class TestMergeEmpty:
    """빈 입력 및 단일 결과 테스트"""

    def test_empty_list(self):
        """빈 리스트 → 빈 결과"""
        merged = _merge_retrieval_results([])
        assert merged["agency"] == {}
        assert merged["disputes"] == []
        assert merged["counsels"] == []
        assert merged["laws"] == []
        assert merged["criteria"] == []

    def test_single_result_passthrough(self):
        """단일 결과 그대로 전달"""
        result = {
            "agency": {"name": "한국소비자원"},
            "disputes": [{"chunk_id": "d1", "content": "분쟁1"}],
            "counsels": [],
            "laws": [{"chunk_id": "l1", "text": "법률1"}],
            "criteria": [],
        }
        merged = _merge_retrieval_results([result])
        assert merged["agency"] == {"name": "한국소비자원"}
        assert len(merged["disputes"]) == 1
        assert merged["disputes"][0]["chunk_id"] == "d1"
        assert len(merged["laws"]) == 1


# ============================================================================
# Deduplication tests
# ============================================================================


class TestMergeDedup:
    """중복 제거 테스트"""

    def test_dedup_disputes_by_chunk_id(self):
        """disputes: chunk_id 기준 중복 제거"""
        r1 = {
            "agency": {},
            "disputes": [{"chunk_id": "d1", "content": "first"}],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        r2 = {
            "agency": {},
            "disputes": [
                {"chunk_id": "d1", "content": "duplicate"},
                {"chunk_id": "d2", "content": "second"},
            ],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert len(merged["disputes"]) == 2
        chunk_ids = [d["chunk_id"] for d in merged["disputes"]]
        assert "d1" in chunk_ids
        assert "d2" in chunk_ids

    def test_dedup_disputes_by_doc_id_fallback(self):
        """disputes: chunk_id 없으면 doc_id로 dedup"""
        r1 = {
            "agency": {},
            "disputes": [{"doc_id": "doc1", "content": "first"}],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        r2 = {
            "agency": {},
            "disputes": [{"doc_id": "doc1", "content": "dup"}],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert len(merged["disputes"]) == 1

    def test_dedup_counsels_by_chunk_id(self):
        """counsels: chunk_id 기준 중복 제거"""
        r1 = {
            "agency": {},
            "disputes": [],
            "counsels": [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
            "laws": [],
            "criteria": [],
        }
        r2 = {
            "agency": {},
            "disputes": [],
            "counsels": [{"chunk_id": "c1"}, {"chunk_id": "c3"}],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert len(merged["counsels"]) == 3

    def test_dedup_laws_by_chunk_id(self):
        """laws: chunk_id 기준 중복 제거"""
        r1 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [{"chunk_id": "l1"}],
            "criteria": [],
        }
        r2 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [{"chunk_id": "l1"}, {"chunk_id": "l2"}],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert len(merged["laws"]) == 2

    def test_dedup_criteria_by_chunk_id(self):
        """criteria: chunk_id 기준 중복 제거"""
        r1 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [{"chunk_id": "cr1"}],
        }
        r2 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [{"chunk_id": "cr1"}, {"chunk_id": "cr2"}],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert len(merged["criteria"]) == 2


# ============================================================================
# Agency info merging tests
# ============================================================================


class TestMergeAgency:
    """Agency 정보 병합 테스트"""

    def test_first_non_empty_agency(self):
        """첫 번째 비어있지 않은 agency 정보 사용"""
        r1 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        r2 = {
            "agency": {"name": "공정거래위원회"},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert merged["agency"] == {"name": "공정거래위원회"}

    def test_first_agency_wins(self):
        """여러 결과에 agency가 있으면 첫 번째가 우선"""
        r1 = {
            "agency": {"name": "한국소비자원"},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        r2 = {
            "agency": {"name": "공정거래위원회"},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert merged["agency"]["name"] == "한국소비자원"

    def test_all_empty_agency(self):
        """모든 결과에 agency가 비어있으면 빈 dict"""
        r1 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        r2 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1, r2])
        assert merged["agency"] == {}


# ============================================================================
# Null / Missing keys tests
# ============================================================================


class TestMergeNullKeys:
    """null/missing key 처리 테스트"""

    def test_missing_disputes_key(self):
        """disputes 키가 없는 결과"""
        r1 = {
            "agency": {},
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1])
        assert merged["disputes"] == []

    def test_missing_counsels_key(self):
        """counsels 키가 없는 결과"""
        r1 = {
            "agency": {},
            "disputes": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1])
        assert merged["counsels"] == []

    def test_missing_laws_key(self):
        """laws 키가 없는 결과"""
        r1 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1])
        assert merged["laws"] == []

    def test_missing_criteria_key(self):
        """criteria 키가 없는 결과"""
        r1 = {
            "agency": {},
            "disputes": [],
            "counsels": [],
            "laws": [],
        }
        merged = _merge_retrieval_results([r1])
        assert merged["criteria"] == []

    def test_no_chunk_id_or_doc_id_skipped(self):
        """chunk_id도 doc_id도 없는 항목은 추가되지 않음"""
        r1 = {
            "agency": {},
            "disputes": [{"content": "no id"}],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1])
        # The code checks: key = d.get("chunk_id") or d.get("doc_id")
        # If both are None, key is None, and "if key" is False → skip
        assert len(merged["disputes"]) == 0

    def test_none_agency_treated_as_empty(self):
        """agency가 None이면 빈 dict처럼 처리"""
        r1 = {
            "agency": None,
            "disputes": [],
            "counsels": [],
            "laws": [],
            "criteria": [],
        }
        merged = _merge_retrieval_results([r1])
        assert merged["agency"] == {}


# ============================================================================
# Multiple results merge tests
# ============================================================================


class TestMergeMultipleResults:
    """여러 결과 병합 통합 테스트"""

    def test_three_results_merged(self):
        """3개 결과 병합"""
        r1 = {
            "agency": {"name": "소비자원"},
            "disputes": [{"chunk_id": "d1"}],
            "counsels": [],
            "laws": [{"chunk_id": "l1"}],
            "criteria": [],
        }
        r2 = {
            "agency": {},
            "disputes": [{"chunk_id": "d2"}],
            "counsels": [{"chunk_id": "c1"}],
            "laws": [],
            "criteria": [{"chunk_id": "cr1"}],
        }
        r3 = {
            "agency": {},
            "disputes": [{"chunk_id": "d3"}],
            "counsels": [],
            "laws": [{"chunk_id": "l2"}],
            "criteria": [{"chunk_id": "cr2"}],
        }
        merged = _merge_retrieval_results([r1, r2, r3])
        assert merged["agency"]["name"] == "소비자원"
        assert len(merged["disputes"]) == 3
        assert len(merged["counsels"]) == 1
        assert len(merged["laws"]) == 2
        assert len(merged["criteria"]) == 2

    def test_all_sections_populated(self):
        """모든 섹션에 데이터가 있을 때"""
        r = {
            "agency": {"name": "test"},
            "disputes": [{"chunk_id": "d1"}],
            "counsels": [{"chunk_id": "c1"}],
            "laws": [{"chunk_id": "l1"}],
            "criteria": [{"chunk_id": "cr1"}],
        }
        merged = _merge_retrieval_results([r])
        assert len(merged["disputes"]) == 1
        assert len(merged["counsels"]) == 1
        assert len(merged["laws"]) == 1
        assert len(merged["criteria"]) == 1
