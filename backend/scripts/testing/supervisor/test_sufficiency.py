"""
RetrievalSufficiencyChecker 단위 테스트 (PR-A: 검색 결과 충분성 평가)

작성일: 2026-01-31
수정일: 2026-02-02

테스트 대상: backend/app/agents/retrieval/sufficiency.py

현재 구현은 RRF top-k 방식으로:
  - 결과 1건 이상 + max_similarity >= min_quality → sufficient (confidence=1.0)
  - 결과 1건 이상 + max_similarity < min_quality → marginal (confidence=0.5)
  - 결과 0건 → insufficient (confidence=0.0)
"""

from typing import Any, Dict

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
    - 총 5건 문서
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
def low_similarity_retrieval_result() -> Dict[str, Any]:
    """
    결과는 있지만 max_similarity가 매우 낮은 경우 (min_quality 미만):
    - 문서 존재하지만 유사도 극히 낮음
    - max_similarity < sufficiency_min_score (0.01)
    → marginal 판정
    """
    return {
        "laws": [],
        "criteria": [],
        "disputes": [
            {"chunk_id": "case_001", "title": "분쟁 사례", "similarity": 0.005},
        ],
        "counsels": [],
        "max_similarity": 0.005,
        "avg_similarity": 0.005,
    }


@pytest.fixture
def partial_retrieval_result() -> Dict[str, Any]:
    """
    일부 섹션만 존재하지만 결과가 있는 경우:
    - disputes만 1건
    - max_similarity 0.45 (> min_quality 0.01)
    → RRF 방식에서는 결과가 있으므로 sufficient
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
    - 결과는 있지만 유사도 낮음 (0.25)
    - RRF 방식에서는 결과가 있으므로 여전히 sufficient
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
    """충분한 검색 결과 케이스 테스트 (RRF top-k: 결과 있으면 sufficient)"""

    def test_sufficient_result(self, checker, sufficient_retrieval_result):
        """
        4섹션 모두 있고 max_similarity 높을 때
        → level='sufficient', is_sufficient=True, confidence=1.0
        """
        result = checker.evaluate(sufficient_retrieval_result)

        assert result.level == "sufficient"
        assert result.is_sufficient is True
        assert result.confidence == 1.0
        assert result.clarifying_questions == []
        assert "답변 생성이 가능합니다" in result.reason
        assert "5건" in result.reason

    def test_sufficient_confidence_is_one(self, checker, sufficient_retrieval_result):
        """충분한 경우 confidence가 항상 1.0"""
        result = checker.evaluate(sufficient_retrieval_result)

        assert result.confidence == 1.0
        assert 0.0 <= result.confidence <= 1.0


class TestMarginalResult:
    """결과는 있지만 유사도가 극히 낮은 경우 marginal 판정 테스트"""

    def test_marginal_result(self, checker, low_similarity_retrieval_result):
        """
        결과 1건 이상이지만 max_similarity < min_quality
        → level='marginal', is_sufficient=True, confidence=0.5
        """
        result = checker.evaluate(low_similarity_retrieval_result)

        assert result.level == "marginal"
        assert result.is_sufficient is True
        assert result.confidence == 0.5
        assert "유사도가 낮음" in result.reason
        assert len(result.clarifying_questions) == 1

    def test_marginal_has_clarifying_suggestion(
        self, checker, low_similarity_retrieval_result
    ):
        """marginal일 때 더 구체적인 정보를 요청하는 안내 포함"""
        result = checker.evaluate(low_similarity_retrieval_result)

        assert len(result.clarifying_questions) == 1
        assert "구체적" in result.clarifying_questions[0]


class TestNonEmptyResultsAreSufficient:
    """RRF 방식에서 결과가 있으면 모두 sufficient인지 테스트"""

    def test_partial_sections_are_sufficient(self, checker, partial_retrieval_result):
        """
        일부 섹션만 있어도 결과가 있으면 sufficient
        (이전의 partial 판정은 RRF 방식에서 제거됨)
        """
        result = checker.evaluate(partial_retrieval_result)

        assert result.level == "sufficient"
        assert result.is_sufficient is True
        assert result.confidence == 1.0
        assert result.clarifying_questions == []

    def test_low_similarity_docs_are_sufficient(
        self, checker, insufficient_retrieval_result
    ):
        """
        유사도가 낮아도 결과가 있으면 sufficient
        (이전의 insufficient 판정은 결과가 0건일 때만 적용)
        """
        result = checker.evaluate(insufficient_retrieval_result)

        assert result.level == "sufficient"
        assert result.is_sufficient is True
        assert result.confidence == 1.0
        assert result.clarifying_questions == []

    def test_reason_contains_document_count(
        self, checker, insufficient_retrieval_result
    ):
        """sufficient인 경우 reason에 문서 건수 포함"""
        result = checker.evaluate(insufficient_retrieval_result)

        # total docs: 1 dispute + 1 counsel = 2
        assert "2건" in result.reason
        assert "답변 생성이 가능합니다" in result.reason


class TestInsufficientResult:
    """완전히 비어있는 검색 결과만 insufficient"""

    def test_empty_retrieval_is_insufficient(self, checker, empty_retrieval_result):
        """
        결과가 0건일 때만 insufficient
        → confidence=0.0, is_sufficient=False
        """
        result = checker.evaluate(empty_retrieval_result)

        assert result.level == "insufficient"
        assert result.is_sufficient is False
        assert result.confidence == 0.0

    def test_insufficient_clarifying_questions(self, checker, empty_retrieval_result):
        """insufficient 시 구체적인 질문 3개 포함"""
        result = checker.evaluate(empty_retrieval_result)

        assert len(result.clarifying_questions) == 3
        questions = result.clarifying_questions
        assert "분쟁 발생 날짜" in questions[0]
        assert "제품/서비스의 구체적인 명칭" in questions[1]
        assert "어떤 문제가 발생했는지" in questions[2]

    def test_empty_retrieval_reason(self, checker, empty_retrieval_result):
        """빈 결과의 reason 검증"""
        result = checker.evaluate(empty_retrieval_result)

        assert "검색 결과가 없습니다" in result.reason
        assert "구체적으로" in result.reason


class TestConfidenceValues:
    """
    RRF 방식에서의 confidence 값 검증:
    - sufficient: 1.0
    - marginal: 0.5
    - insufficient: 0.0
    """

    def test_sufficient_confidence(self, checker):
        """결과가 있고 품질이 충분하면 confidence = 1.0"""
        retrieval = {
            "laws": [
                {"chunk_id": "law1", "similarity": 0.60},
            ],
            "criteria": [],
            "disputes": [
                {"chunk_id": "case1", "similarity": 0.50},
            ],
            "counsels": [],
            "max_similarity": 0.60,
            "avg_similarity": 0.55,
        }

        result = checker.evaluate(retrieval)

        assert result.confidence == 1.0
        assert result.level == "sufficient"

    def test_insufficient_confidence(self, checker):
        """결과가 0건이면 confidence = 0.0"""
        retrieval = {
            "laws": [],
            "criteria": [],
            "disputes": [],
            "counsels": [],
            "max_similarity": 0.0,
            "avg_similarity": 0.0,
        }

        result = checker.evaluate(retrieval)

        assert result.confidence == 0.0
        assert result.level == "insufficient"

    def test_no_type_score_still_sufficient(self, checker):
        """laws와 criteria 없어도 결과가 있으면 sufficient (confidence=1.0)"""
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

        # RRF 방식: 결과가 있으면 항상 sufficient
        assert result.confidence == 1.0
        assert result.level == "sufficient"

    def test_confidence_range(self, checker, sufficient_retrieval_result):
        """confidence는 항상 [0.0, 1.0] 범위"""
        result = checker.evaluate(sufficient_retrieval_result)
        assert 0.0 <= result.confidence <= 1.0


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

    def test_custom_thresholds_affect_checker(
        self, monkeypatch, partial_retrieval_result
    ):
        """
        임계값 변경이 체커 인스턴스에 반영되는지 확인
        """
        monkeypatch.setenv("SUFFICIENCY_MEDIUM_THRESHOLD", "0.5")

        from app.agents.retrieval.sufficiency import RetrievalSufficiencyChecker

        checker = RetrievalSufficiencyChecker()

        assert checker.medium_threshold == 0.5

        # RRF 방식에서는 결과가 있으면 항상 sufficient
        result = checker.evaluate(partial_retrieval_result)
        assert result.is_sufficient is True

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
        """max_similarity 필드 없을 때 기본값 0.0 → 결과 0건이면 insufficient"""
        retrieval = {
            "laws": [],
            "criteria": [],
            "disputes": [],
            "counsels": [],
            # max_similarity 누락
        }

        result = checker.evaluate(retrieval)

        assert result.confidence == 0.0
        assert result.level == "insufficient"

    def test_documents_with_exact_threshold_similarity(self, checker):
        """similarity가 정확히 0.3일 때 - RRF 방식에서는 결과가 있으면 sufficient"""
        retrieval = {
            "laws": [],
            "criteria": [],
            "disputes": [
                {"chunk_id": "case1", "similarity": 0.3},
            ],
            "counsels": [],
            "max_similarity": 0.3,
        }

        result = checker.evaluate(retrieval)

        # RRF 방식: 결과 1건 있으므로 sufficient
        assert result.level == "sufficient"
        assert result.confidence == 1.0

    def test_very_high_document_count(self, checker):
        """관련 문서가 매우 많을 때도 confidence = 1.0"""
        retrieval = {
            "laws": [{"chunk_id": f"law{i}", "similarity": 0.8} for i in range(10)],
            "criteria": [{"chunk_id": f"cri{i}", "similarity": 0.7} for i in range(5)],
            "disputes": [],
            "counsels": [],
            "max_similarity": 0.8,
            "avg_similarity": 0.75,
        }

        result = checker.evaluate(retrieval)

        assert result.confidence == 1.0
        assert result.level == "sufficient"


class TestReasonGeneration:
    """reason 생성 테스트"""

    def test_sufficient_reason_format(self, checker, sufficient_retrieval_result):
        """sufficient일 때 reason 형식: '검색된 문서 N건으로 답변 생성이 가능합니다.'"""
        result = checker.evaluate(sufficient_retrieval_result)

        assert "검색된 문서" in result.reason
        assert "5건" in result.reason
        assert "답변 생성이 가능합니다" in result.reason

    def test_insufficient_reason_format(self, checker, empty_retrieval_result):
        """insufficient일 때 reason 형식"""
        result = checker.evaluate(empty_retrieval_result)

        assert "검색 결과가 없습니다" in result.reason

    def test_marginal_reason_includes_similarity(
        self, checker, low_similarity_retrieval_result
    ):
        """marginal일 때 reason에 유사도 정보 포함"""
        result = checker.evaluate(low_similarity_retrieval_result)

        assert "유사도가 낮음" in result.reason
        assert "0.0050" in result.reason
