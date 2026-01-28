"""
PR-2: Intent Classifier 테스트

HybridIntentClassifier의 Fast Path 및 LLM 분류를 테스트합니다.
"""

import pytest
from app.agents.query_analysis.classifier import (
    IntentClassifier,
    HybridIntentClassifier,
    IntentClassificationResult,
)


class TestHybridIntentClassifierFastPath:
    """Fast Path (Rule-based) 분류 테스트"""

    @pytest.fixture
    def classifier(self):
        return HybridIntentClassifier(use_llm=False)

    @pytest.mark.parametrize("query,expected_type", [
        # system_meta 패턴
        ("너 누구야?", "system_meta"),
        ("어떤 모델이야?", "system_meta"),
        ("뭘 할 수 있어?", "system_meta"),
        ("누가 만들었어?", "system_meta"),
        # general (인사) 패턴 - 짧은 쿼리만
        ("안녕", "general"),
        ("감사합니다", "general"),
        # law 패턴 (법률명)
        ("소비자기본법 알려줘", "law"),
        ("전자상거래법 내용", "law"),
        ("할부거래법 조항", "law"),
    ])
    def test_fast_path_classification(self, classifier, query, expected_type):
        """Fast Path 패턴 매칭 테스트"""
        result = classifier.classify(query)
        assert result.query_type == expected_type
        assert result.confidence >= 0.9  # Fast path는 높은 신뢰도
        assert result.model_used == "rule_based"

    def test_fast_path_confidence(self, classifier):
        """Fast Path는 1.0 또는 0.9 신뢰도를 가져야 함"""
        result = classifier.classify("너 누구야?")
        assert result.confidence == 1.0
        assert result.model_used == "rule_based"

    def test_ambiguous_without_llm(self, classifier):
        """LLM 비활성화 시 알 수 없는 쿼리는 ambiguous 반환"""
        result = classifier.classify("노트북 환불해주세요")
        assert result.query_type == "ambiguous"  # LLM이 없으면 분류 불가
        assert result.confidence == 0.0


class TestIntentClassificationResult:
    """IntentClassificationResult 데이터클래스 테스트"""

    def test_default_values(self):
        """기본값 테스트"""
        result = IntentClassificationResult(query_type="dispute")
        assert result.query_type == "dispute"
        assert result.domain is None
        assert result.agency is None
        assert result.confidence == 0.0
        assert result.reasoning == ""
        assert result.from_cache is False
        assert result.model_used == ""

    def test_full_initialization(self):
        """전체 값 초기화 테스트"""
        result = IntentClassificationResult(
            query_type="restricted",
            domain="finance",
            agency=None,
            confidence=0.95,
            reasoning="금융 관련 키워드 발견",
            from_cache=False,
            model_used="gpt-4o-mini",
        )
        assert result.query_type == "restricted"
        assert result.domain == "finance"
        assert result.confidence == 0.95


class TestIntentClassifier:
    """IntentClassifier (LLM 기반) 테스트"""

    def test_classifier_initialization(self):
        """Classifier 초기화 테스트"""
        classifier = IntentClassifier(
            model="gpt-4o-mini",
            temperature=0.0,
            timeout=3.0,
            confidence_threshold=0.8,
        )
        assert classifier.model == "gpt-4o-mini"
        assert classifier.temperature == 0.0
        assert classifier.timeout == 3.0
        assert classifier.confidence_threshold == 0.8

    def test_is_confident(self):
        """is_confident 메서드 테스트"""
        classifier = IntentClassifier(confidence_threshold=0.8)

        high_conf = IntentClassificationResult(query_type="dispute", confidence=0.9)
        low_conf = IntentClassificationResult(query_type="dispute", confidence=0.5)

        assert classifier.is_confident(high_conf) is True
        assert classifier.is_confident(low_conf) is False

    @pytest.mark.skipif(
        not pytest.importorskip("openai", reason="openai package not installed"),
        reason="OpenAI package required"
    )
    @pytest.mark.llm
    def test_classify_requires_api_key(self):
        """API 키 없이 분류 시도 시 graceful failure"""
        import os
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            classifier = IntentClassifier()
            result = classifier.classify("테스트 쿼리")
            # API 키 없으면 ambiguous 반환
            assert result.query_type == "ambiguous"
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key


class TestHybridIntentClassifierWithLLM:
    """LLM 활성화 시 HybridIntentClassifier 테스트"""

    @pytest.mark.llm
    @pytest.mark.skipif(
        not pytest.importorskip("openai", reason="openai package not installed"),
        reason="OpenAI package required"
    )
    def test_llm_fallback_for_complex_queries(self):
        """복잡한 쿼리는 LLM으로 분류"""
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        classifier = HybridIntentClassifier(use_llm=True)

        # 복잡한 쿼리 (Fast Path에서 처리 불가)
        result = classifier.classify("노트북 환불이 안 돼서 너무 화가 나요")

        # LLM이 분류해야 함
        assert result.model_used == "gpt-4o-mini"
        # dispute로 분류될 가능성이 높음
        assert result.query_type in ("dispute", "ambiguous")
