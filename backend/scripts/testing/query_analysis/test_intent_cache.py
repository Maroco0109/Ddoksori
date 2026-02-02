"""
PR-4: Intent Classification 캐싱 테스트

Redis L3 캐시를 활용한 Intent Classification 결과 캐싱을 테스트합니다.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.query_analysis.classifier import (
    HybridIntentClassifier,
    IntentClassificationResult,
)


class TestIntentClassificationCacheUnit:
    """Intent Classification 캐시 단위 테스트 (Redis 없이)"""

    @pytest.fixture
    def classifier_no_cache(self):
        """캐시 비활성화된 분류기"""
        return HybridIntentClassifier(use_llm=False, use_cache=False)

    @pytest.fixture
    def classifier_with_cache(self):
        """캐시 활성화된 분류기"""
        return HybridIntentClassifier(use_llm=False, use_cache=True)

    def test_classifier_cache_disabled(self, classifier_no_cache):
        """캐시 비활성화 시 캐시 조회 안 함"""
        with patch.object(
            classifier_no_cache, "_get_from_cache", return_value=None
        ) as mock_get:
            # Fast path query (should not check cache)
            result = classifier_no_cache.classify("너 누구야?")
            assert result.query_type == "system_meta"
            assert result.from_cache is False
            # Fast path는 캐시 체크 안 함
            mock_get.assert_not_called()

    def test_fast_path_skips_cache(self, classifier_with_cache):
        """Fast Path는 캐시 조회 건너뜀"""
        with patch.object(
            classifier_with_cache, "_get_from_cache", return_value=None
        ) as mock_get:
            result = classifier_with_cache.classify("안녕")
            assert result.query_type == "general"
            assert result.from_cache is False
            # Fast path는 캐시 체크 안 함
            mock_get.assert_not_called()

    def test_cache_hit_returns_cached_result(self, classifier_with_cache):
        """캐시 히트 시 캐시된 결과 반환"""
        cached_result = IntentClassificationResult(
            query_type="dispute",
            confidence=0.95,
            reasoning="cached",
            from_cache=True,
            model_used="gpt-4o-mini",
        )

        with patch.object(
            classifier_with_cache, "_get_from_cache", return_value=cached_result
        ):
            result = classifier_with_cache.classify("노트북 환불해줘")
            assert result.query_type == "dispute"
            assert result.from_cache is True
            assert result.confidence == 0.95


class TestIntentClassificationCacheIntegration:
    """Intent Classification 캐시 통합 테스트 (Redis 필요)"""

    @pytest.fixture
    def mock_redis(self):
        """Redis 목 설정"""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.get.return_value = None
        mock_client.setex.return_value = True
        return mock_client

    def test_cache_get_miss(self, mock_redis):
        """캐시 미스 시 None 반환"""
        with patch("app.common.cache.base.get_redis_client", return_value=mock_redis):
            from app.supervisor.cache import IntentClassificationCache

            mock_redis.get.return_value = None
            result = IntentClassificationCache.get("테스트 쿼리")
            assert result is None

    def test_cache_get_hit(self, mock_redis):
        """캐시 히트 시 저장된 데이터 반환"""
        import json

        cached_data = {
            "query_type": "dispute",
            "domain": None,
            "agency": "KCA",
            "confidence": 0.92,
            "reasoning": "test",
            "model_used": "gpt-4o-mini",
        }

        with patch("app.common.cache.base.get_redis_client", return_value=mock_redis):
            from app.supervisor.cache import IntentClassificationCache

            mock_redis.get.return_value = json.dumps(cached_data)
            result = IntentClassificationCache.get("테스트 쿼리")

            assert result is not None
            assert result["query_type"] == "dispute"
            assert (
                result["_from_cache"] is True
            )  # BaseRedisCache.get() adds _from_cache

    def test_cache_set(self, mock_redis):
        """캐시 저장 테스트"""
        with patch("app.common.cache.base.get_redis_client", return_value=mock_redis):
            from app.supervisor.cache import IntentClassificationCache

            classification = {
                "query_type": "dispute",
                "domain": None,
                "agency": "KCA",
                "confidence": 0.92,
                "reasoning": "test",
                "model_used": "gpt-4o-mini",
            }

            result = IntentClassificationCache.set("테스트 쿼리", classification)
            assert result is True
            mock_redis.setex.assert_called_once()

    def test_cache_ttl(self, mock_redis):
        """캐시 TTL 설정 확인"""
        with patch("app.common.cache.base.get_redis_client", return_value=mock_redis):
            from app.supervisor.cache import IntentClassificationCache

            classification = {
                "query_type": "dispute",
                "confidence": 0.9,
            }

            IntentClassificationCache.set("쿼리", classification)

            # setex 호출 시 TTL 확인
            call_args = mock_redis.setex.call_args
            assert call_args[0][1] == 86400 * 7  # 7일


class TestHybridClassifierWithCache:
    """HybridIntentClassifier 캐시 통합 테스트"""

    def test_cache_integration_flow(self):
        """캐시 통합 플로우 테스트"""
        classifier = HybridIntentClassifier(use_llm=False, use_cache=True)

        # 1. Fast path는 캐시 안 씀
        result1 = classifier.classify("너 누구야?")
        assert result1.query_type == "system_meta"
        assert result1.from_cache is False

        # 2. LLM 비활성화 + 캐시 미스 → ambiguous
        with patch.object(classifier, "_get_from_cache", return_value=None):
            result2 = classifier.classify("복잡한 쿼리")
            assert result2.query_type == "ambiguous"

    def test_save_to_cache_called_after_llm(self):
        """LLM 호출 후 캐시 저장 확인"""
        classifier = HybridIntentClassifier(use_llm=True, use_cache=True)

        # LLM 결과 모킹
        mock_result = IntentClassificationResult(
            query_type="dispute",
            confidence=0.9,
            reasoning="test",
            from_cache=False,
            model_used="gpt-4o-mini",
        )

        with patch.object(classifier, "_get_from_cache", return_value=None):
            with patch.object(
                classifier.llm_classifier, "classify", return_value=mock_result
            ):
                with patch.object(classifier, "_save_to_cache") as mock_save:
                    result = classifier.classify("환불 해줘")

                    assert result.query_type == "dispute"
                    mock_save.assert_called_once()
