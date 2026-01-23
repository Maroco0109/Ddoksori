"""
Unit tests for A/B testing framework (no DB dependency)
PR-T6: Mock 기반 순수 로직 테스트

Run with: pytest backend/scripts/testing/test_ab_framework_unit.py -v
"""
import pytest
import sys
from pathlib import Path
from collections import Counter
from unittest.mock import MagicMock

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.experiments import ABTestManager, ExperimentCreate
from app.experiments.models import Experiment


# Unit 테스트 마커 - DB 의존성 없음
pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def skip_db_fixtures(request):
    """
    Unit 테스트에서는 DB 관련 세션 fixture를 건너뜀

    conftest.py의 ensure_test_data(autouse=True)로 인한 skip 방지
    """
    # 이 fixture는 아무 작업도 하지 않음
    # 단지 unit 마커가 있는 테스트임을 표시
    pass


class TestABTestManagerUnit:
    """DB 의존성 없는 순수 로직 테스트"""

    def test_hash_subject_consistency(self):
        """동일 입력에 동일 해시값 반환 검증"""
        # ABTestManager를 DB 연결 없이 생성
        manager = ABTestManager.__new__(ABTestManager)

        # 동일한 실험명 + subject_id로 여러 번 호출
        h1 = manager._hash_subject("exp_test", "user123")
        h2 = manager._hash_subject("exp_test", "user123")
        h3 = manager._hash_subject("exp_test", "user123")

        # 모든 해시값이 동일해야 함
        assert h1 == h2 == h3, "Hash should be consistent for same input"

        # 해시값 범위 검증 (0.0 ~ 1.0)
        assert 0.0 <= h1 < 1.0, "Hash value should be in [0, 1) range"

    def test_hash_subject_different_experiments(self):
        """다른 실험명은 다른 해시값 생성 검증"""
        manager = ABTestManager.__new__(ABTestManager)

        same_user = "user_abc"

        h1 = manager._hash_subject("experiment_A", same_user)
        h2 = manager._hash_subject("experiment_B", same_user)

        # 다른 실험명은 다른 해시값을 생성해야 함
        assert h1 != h2, "Different experiment names should produce different hashes"

    def test_hash_subject_different_users(self):
        """다른 사용자는 다른 해시값 생성 검증"""
        manager = ABTestManager.__new__(ABTestManager)

        same_exp = "same_experiment"

        h1 = manager._hash_subject(same_exp, "user_1")
        h2 = manager._hash_subject(same_exp, "user_2")

        # 다른 사용자는 다른 해시값을 생성해야 함
        assert h1 != h2, "Different users should produce different hashes"

    def test_assign_variant_distribution(self):
        """트래픽 분배 로직 검증 (50/50 ±5%)"""
        manager = ABTestManager.__new__(ABTestManager)

        # Mock Experiment 객체 생성
        mock_experiment = MagicMock(spec=Experiment)
        mock_experiment.name = "test_distribution"
        mock_experiment.variants = ["A", "B"]
        mock_experiment.traffic_split_config = {"A": 0.5, "B": 0.5}

        # 1000개 subject에 대해 variant 할당
        num_subjects = 1000
        variants = [
            manager._assign_variant(mock_experiment, f"subject_{i}")
            for i in range(num_subjects)
        ]

        variant_counts = Counter(variants)

        # 50/50 분배 (±5% 허용)
        assert 450 <= variant_counts["A"] <= 550, f"Variant A out of range: {variant_counts['A']}"
        assert 450 <= variant_counts["B"] <= 550, f"Variant B out of range: {variant_counts['B']}"

    def test_assign_variant_70_30_distribution(self):
        """트래픽 분배 로직 검증 (70/30 ±5%)"""
        manager = ABTestManager.__new__(ABTestManager)

        # Mock Experiment 객체 생성 (70% A, 30% B)
        mock_experiment = MagicMock(spec=Experiment)
        mock_experiment.name = "test_70_30"
        mock_experiment.variants = ["A", "B"]
        mock_experiment.traffic_split_config = {"A": 0.7, "B": 0.3}

        # 1000개 subject에 대해 variant 할당
        num_subjects = 1000
        variants = [
            manager._assign_variant(mock_experiment, f"subject_{i}")
            for i in range(num_subjects)
        ]

        variant_counts = Counter(variants)

        # 70/30 분배 (±5% 허용)
        assert 650 <= variant_counts["A"] <= 750, f"Variant A out of range: {variant_counts['A']}"
        assert 250 <= variant_counts["B"] <= 350, f"Variant B out of range: {variant_counts['B']}"

    def test_assign_variant_consistency(self):
        """동일 사용자는 항상 동일 variant에 할당 검증"""
        manager = ABTestManager.__new__(ABTestManager)

        mock_experiment = MagicMock(spec=Experiment)
        mock_experiment.name = "test_consistency"
        mock_experiment.variants = ["A", "B"]
        mock_experiment.traffic_split_config = {"A": 0.5, "B": 0.5}

        subject_id = "consistent_user_123"

        # 동일 사용자에게 10번 variant 할당
        assignments = [
            manager._assign_variant(mock_experiment, subject_id)
            for _ in range(10)
        ]

        # 모든 할당이 동일해야 함
        assert len(set(assignments)) == 1, "Same user should always get same variant"


class TestExperimentCreateValidation:
    """Pydantic 모델 검증 테스트 (DB 불필요)"""

    def test_traffic_split_sum_to_one(self):
        """트래픽 비율 합계가 1.0이어야 함"""
        # 정상 케이스
        valid = ExperimentCreate(
            name="valid_exp",
            description="Test",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        assert valid.traffic_split == {"A": 0.5, "B": 0.5}

        # 합계가 1.0이 아닌 경우 - 실패해야 함
        with pytest.raises(ValueError, match="must sum to 1.0"):
            ExperimentCreate(
                name="invalid_exp",
                description="Test",
                variants=["A", "B"],
                traffic_split={"A": 0.6, "B": 0.6}
            )

    def test_traffic_split_missing_variant(self):
        """모든 variant가 traffic_split에 포함되어야 함"""
        with pytest.raises(ValueError, match="missing in traffic_split"):
            ExperimentCreate(
                name="missing_variant",
                description="Test",
                variants=["A", "B"],
                traffic_split={"A": 1.0}  # B 누락
            )

    def test_traffic_split_positive_ratios(self):
        """모든 비율은 양수여야 함"""
        # 0 또는 음수 비율 - 실패해야 함
        with pytest.raises(ValueError, match="must be positive"):
            ExperimentCreate(
                name="zero_ratio",
                description="Test",
                variants=["A", "B"],
                traffic_split={"A": 0.0, "B": 1.0}
            )

    def test_valid_three_way_split(self):
        """3-way 분배 검증"""
        valid = ExperimentCreate(
            name="three_way",
            description="Test",
            variants=["A", "B", "C"],
            traffic_split={"A": 0.33, "B": 0.33, "C": 0.34}
        )
        assert len(valid.variants) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
