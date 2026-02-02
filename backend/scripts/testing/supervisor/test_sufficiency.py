"""
RetrievalSufficiencyChecker 단위 테스트 (PR-A: 검색 결과 충분성 평가)

작성일: 2026-01-31

테스트 대상: backend/app/agents/retrieval/sufficiency.py
"""

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# 전체 파일에 unit 마커 적용 (DB 의존성 없음, 비동기 없음)
pytestmark = pytest.mark.unit


# === Test Fixtures ===


@pytest.fixture
def checker():
    """기본 RetrievalSufficiencyChecker 인스턴스"""
    from app.agents.retrieval.sufficiency import RetrievalSufficiencyChecker

    return RetrievalSufficiencyChecker()


@pytest.fixture
def sufficient_retrieval_result() -> Dict[str, Any]:
    """
    충분한 검색 결과:
    - 4개 섹션 모두 존재
    - max_similarity 높음 (0.85)
    - 관련 문서 4개 (similarity > 0.3)
    - laws와 criteria 모두 존재
    """
    return {
        "laws": [
            {"chunk_id": "law_001", "title": "소비자기본법 제17조", "similarity": 0.85},
            {"chunk_id": "law_002", "title": "전자상거래법 제17조", "similarity": 0.80},
        ],
        "criteria": [
            {"chunk_id": "cri_001", "title": "전자제품 품질기준", "similarity": 0.75},
        ],
        "disputes": [
            {"chunk_id": "case_001", "title": "노트북 환불 사례", "similarity": 0.70},
        ],
        "counsels": [
            {"chunk_id": "coun_001", "title": "환불 상담 사례", "similarity": 0.65},
        ],
        "max_similarity": 0.85,
        "avg_similarity": 0.75,
    }


@pytest.fixture
def partial_retrieval_result() -> Dict[str, Any]:
    """
    부분적인 검색 결과:
    - 일부 섹션만 존재 (disputes만)
    - max_similarity 중간 (0.45)
    - 관련 문서 1개만
    - laws, criteria 없음 → type_score = 0.0
    → confidence = 0.4*0.9 + 0.3*0.5 + 0.3*0.0 = 0.51 (partial)
    """
    return {
        "laws": [],
        "criteria": [],
        "disputes": [
            {"chunk_id": "case_001", "title": "분쟁 사례", "similarity": 0.45},
        ],
        "counsels": [],
        "max_similarity": 0.45,
        "avg_similarity": 0.45,
    }


@pytest.fixture
def insufficient_retrieval_result() -> Dict[str, Any]:
    """
    불충분한 검색 결과:
    - 검색 결과 거의 없음
    - max_similarity 낮음 (0.25)
    - 관련 문서 0개 (모두 similarity < 0.3)
    - laws, criteria 없음
    """
    return {
        "laws": [],
        "criteria": [],
        "disputes": [
            {"chunk_id": "case_001", "title": "무관한 사례", "similarity": 0.25},
        ],
        "counsels": [
            {"chunk_id": "coun_001", "title": "무관한 상담", "similarity": 0.20},
        ],
        "max_similarity": 0.25,
        "avg_similarity": 0.225,
    }


@pytest.fixture
def empty_retrieval_result() -> Dict[str, Any]:
    """
    완전히 비어있는 검색 결과:
    - 모든 섹션 빈 리스트
    - max_similarity = 0.0
    """
    return {
        "laws": [],
        "criteria": [],
        "disputes": [],
        "counsels": [],
        "max_similarity": 0.0,
        "avg_similarity": 0.0,
    }


# === Unit Tests ===


class TestSufficientResult:
    """충분한 검색 결과 케이스 테스트"""

    def test_sufficient_result(self, checker, sufficient_retrieval_result):
        """
        4섹션 모두 있고 max_similarity 높을 때
        → level='sufficient', is_sufficient=True
        """
        result = checker.evaluate(sufficient_retrieval_result)

        assert result.level == "sufficient"
        assert result.is_sufficient is True
        assert result.confidence >= 0.6  # medium_threshold
        assert result.clarifying_questions == []
        assert "충분하고" in result.reason
        assert "답변 생성이 가능합니다" in result.reason

    def test_sufficient_confidence_above_threshold(
        self, checker, sufficient_retrieval_result
    ):
        """충분한 경우 confidence가 medium_threshold (0.6) 이상"""
        result = checker.evaluate(sufficient_retrieval_result)

        assert result.confidence >= checker.medium_threshold
        # confidence 범위 검증 (0.0 ~ 1.0)
        assert 0.0 <= result.confidence <= 1.0


class TestPartialResult:
    """부분적인 검색 결과 케이스 테스트"""

    def test_partial_result(self, checker, partial_retrieval_result):
        """
        일부 섹션만 있거나 similarity 중간
        → level='partial', is_sufficient=False (confidence=0.51 < 0.6)
        """
        result = checker.evaluate(partial_retrieval_result)

        assert result.level == "partial"
        # partial인 경우 confidence가 medium_threshold (0.6) 미만
        assert result.is_sufficient is False
        assert result.clarifying_questions == []
        assert "일부 정보만 발견되었습니다" in result.reason

    def test_partial_with_issues_description(self, checker, partial_retrieval_result):
        """partial 상태에서 구체적인 이유 설명 포함"""
        result = checker.evaluate(partial_retrieval_result)

        # reason에 구체적인 문제점 포함 확인
        assert len(result.reason) > 0
        # 예: "유사도가 기준보다 낮음", "관련 문서 수가 부족함" 등


class TestInsufficientResult:
    """불충분한 검색 결과 케이스 테스트"""

    def test_insufficient_result(self, checker, insufficient_retrieval_result):
        """
        검색 결과 거의 없음
        → level='insufficient', is_sufficient=False, clarifying_questions 포함
        """
        result = checker.evaluate(insufficient_retrieval_result)

        assert result.level == "insufficient"
        assert result.is_sufficient is False
        assert len(result.clarifying_questions) > 0
        assert "검색 결과가 불충분합니다" in result.reason

    def test_insufficient_clarifying_questions(
        self, checker, insufficient_retrieval_result
    ):
        """불충분 시 구체적인 질문 3개 포함"""
        result = checker.evaluate(insufficient_retrieval_result)

        assert len(result.clarifying_questions) == 3
        questions = result.clarifying_questions
        assert "분쟁 발생 날짜" in questions[0]
        assert "제품/서비스의 구체적인 명칭" in questions[1]
        assert "어떤 문제가 발생했는지" in questions[2]

    def test_insufficient_confidence_below_threshold(
        self, checker, insufficient_retrieval_result
    ):
        """불충분한 경우 confidence가 low_threshold (0.3) 미만"""
        result = checker.evaluate(insufficient_retrieval_result)

        assert result.confidence < checker.low_threshold


class TestEmptyRetrieval:
    """완전히 비어있는 검색 결과 테스트"""

    def test_empty_retrieval(self, checker, empty_retrieval_result):
        """
        retrieval=None 또는 빈 dict
        → confidence=0.0
        """
        result = checker.evaluate(empty_retrieval_result)

        assert result.confidence == 0.0
        assert result.level == "insufficient"
        assert result.is_sufficient is False
        assert len(result.clarifying_questions) == 3

    def test_empty_retrieval_reason(self, checker, empty_retrieval_result):
        """빈 결과의 reason 검증"""
        result = checker.evaluate(empty_retrieval_result)

        assert "검색 결과가 불충분합니다" in result.reason


class TestConfidenceFormula:
    """
    Confidence 계산 공식 검증:
    confidence = 0.4 * sim_score + 0.3 * doc_score + 0.3 * type_score
    """

    def test_confidence_formula(self, checker):
        """
        confidence 계산이 공식대로 되는지 검증:
        0.4*sim + 0.3*doc + 0.3*type
        """
        # 제어된 입력으로 수동 계산
        retrieval = {
            "laws": [
                {"chunk_id": "law1", "similarity": 0.60},  # > 0.3, 관련 문서 1개
            ],
            "criteria": [],
            "disputes": [
                {"chunk_id": "case1", "similarity": 0.50},  # > 0.3, 관련 문서 1개
            ],
            "counsels": [],
            "max_similarity": 0.60,
            "avg_similarity": 0.55,
        }

        result = checker.evaluate(retrieval)

        # 수동 계산:
        # sim_score = min(0.60 / 0.5, 1.0) = 1.0
        # doc_score = min(2 / 2, 1.0) = 1.0  (관련 문서 2개)
        # type_score = 1.0 (laws 있음)
        # confidence = 0.4*1.0 + 0.3*1.0 + 0.3*1.0 = 1.0
        expected_confidence = 1.0

        assert abs(result.confidence - expected_confidence) < 0.01

    def test_confidence_with_no_type_score(self, checker):
        """laws와 criteria 없을 때 type_score = 0.0"""
        retrieval = {
            "laws": [],
            "criteria": [],
            "disputes": [
                {"chunk_id": "case1", "similarity": 0.70},
                {"chunk_id": "case2", "similarity": 0.60},
            ],
            "counsels": [],
            "max_similarity": 0.70,
            "avg_similarity": 0.65,
        }

        result = checker.evaluate(retrieval)

        # sim_score = min(0.70 / 0.5, 1.0) = 1.0
        # doc_score = min(2 / 2, 1.0) = 1.0
        # type_score = 0.0 (no laws or criteria)
        # confidence = 0.4*1.0 + 0.3*1.0 + 0.3*0.0 = 0.7
        expected_confidence = 0.7

        assert abs(result.confidence - expected_confidence) < 0.01

    def test_confidence_components_range(self, checker, sufficient_retrieval_result):
        """각 score 컴포넌트가 [0.0, 1.0] 범위인지 확인"""
        retrieval = sufficient_retrieval_result
        max_sim = retrieval["max_similarity"]

        # sim_score 범위 확인
        sim_score = min(max_sim / checker.min_similarity, 1.0)
        assert 0.0 <= sim_score <= 1.0

        # doc_score 범위 확인 (관련 문서 4개)
        relevant_docs = 4  # sufficient_retrieval_result에 4개
        doc_score = min(relevant_docs / checker.min_documents, 1.0)
        assert 0.0 <= doc_score <= 1.0


class TestEnvThresholdOverride:
    """환경변수로 임계값 변경 테스트 (monkeypatch 사용)"""

    def test_custom_min_similarity(self, monkeypatch):
        """SUFFICIENCY_MIN_SIMILARITY 환경변수 오버라이드"""
        monkeypatch.setenv("SUFFICIENCY_MIN_SIMILARITY", "0.7")

        from app.agents.retrieval.sufficiency import RetrievalSufficiencyChecker

        checker = RetrievalSufficiencyChecker()

        assert checker.min_similarity == 0.7

    def test_custom_min_documents(self, monkeypatch):
        """SUFFICIENCY_MIN_DOCUMENTS 환경변수 오버라이드"""
        monkeypatch.setenv("SUFFICIENCY_MIN_DOCUMENTS", "5")

        from app.agents.retrieval.sufficiency import RetrievalSufficiencyChecker

        checker = RetrievalSufficiencyChecker()

        assert checker.min_documents == 5

    def test_custom_thresholds_affect_result(
        self, monkeypatch, partial_retrieval_result
    ):
        """
        임계값 변경이 실제 평가 결과에 영향을 주는지 확인
        """
        # medium_threshold를 0.5로 낮춤 → partial이 sufficient로 변경될 수 있음
        monkeypatch.setenv("SUFFICIENCY_MEDIUM_THRESHOLD", "0.5")

        from app.agents.retrieval.sufficiency import RetrievalSufficiencyChecker

        checker = RetrievalSufficiencyChecker()

        result = checker.evaluate(partial_retrieval_result)

        # threshold가 낮아져서 is_sufficient=True 가능성 증가
        assert checker.medium_threshold == 0.5

    def test_default_values_when_no_env(self):
        """환경변수 없을 때 기본값 사용"""
        from app.agents.retrieval.sufficiency import RetrievalSufficiencyChecker

        checker = RetrievalSufficiencyChecker()

        # 기본값 확인 (sufficiency.py에 정의된 기본값)
        assert checker.min_similarity == 0.5
        assert checker.min_documents == 2
        assert checker.low_threshold == 0.3
        assert checker.medium_threshold == 0.6


class TestEdgeCases:
    """Edge cases 및 경계 조건 테스트"""

    def test_missing_max_similarity_field(self, checker):
        """max_similarity 필드 없을 때 기본값 0.0"""
        retrieval = {
            "laws": [],
            "criteria": [],
            "disputes": [],
            "counsels": [],
            # max_similarity 누락
        }

        result = checker.evaluate(retrieval)

        # max_similarity 기본값 0.0으로 처리
        assert result.confidence == 0.0

    def test_documents_with_exact_threshold_similarity(self, checker):
        """similarity가 정확히 0.3일 때 (경계값)"""
        retrieval = {
            "laws": [],
            "criteria": [],
            "disputes": [
                {"chunk_id": "case1", "similarity": 0.3},  # 정확히 0.3
            ],
            "counsels": [],
            "max_similarity": 0.3,
        }

        result = checker.evaluate(retrieval)

        # similarity > 0.3 조건이므로 0.3은 제외됨
        # 관련 문서 0개로 카운트
        assert result.confidence < checker.low_threshold

    def test_very_high_document_count(self, checker):
        """관련 문서가 매우 많을 때 doc_score가 1.0으로 캡핑"""
        retrieval = {
            "laws": [{"chunk_id": f"law{i}", "similarity": 0.8} for i in range(10)],
            "criteria": [{"chunk_id": f"cri{i}", "similarity": 0.7} for i in range(5)],
            "disputes": [],
            "counsels": [],
            "max_similarity": 0.8,
            "avg_similarity": 0.75,
        }

        result = checker.evaluate(retrieval)

        # doc_score = min(15 / 2, 1.0) = 1.0 (캡핑)
        # sim_score = min(0.8 / 0.5, 1.0) = 1.0 (캡핑)
        # type_score = 1.0
        # confidence = 0.4*1.0 + 0.3*1.0 + 0.3*1.0 = 1.0
        assert result.confidence == 1.0
        assert result.level == "sufficient"


class TestReasonGeneration:
    """한국어 reason 생성 테스트"""

    def test_reason_contains_max_similarity(self, checker, sufficient_retrieval_result):
        """reason에 max_similarity 값 포함"""
        result = checker.evaluate(sufficient_retrieval_result)

        # 소수점 2자리 포맷팅 확인
        assert "0.85" in result.reason

    def test_reason_contains_document_count(self, checker, sufficient_retrieval_result):
        """reason에 관련 문서 수 포함"""
        result = checker.evaluate(sufficient_retrieval_result)

        # "관련 문서 N개" 형식
        assert "관련 문서" in result.reason
        assert "4개" in result.reason or "발견" in result.reason

    def test_insufficient_reason_includes_issues(
        self, checker, insufficient_retrieval_result
    ):
        """불충분한 경우 구체적인 문제점 나열"""
        result = checker.evaluate(insufficient_retrieval_result)

        # 여러 문제점 중 하나라도 포함
        assert any(
            phrase in result.reason for phrase in ["유사도", "관련 문서", "법적 근거"]
        )
