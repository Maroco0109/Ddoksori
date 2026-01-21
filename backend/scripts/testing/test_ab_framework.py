"""
Integration tests for A/B testing framework
Sprint 3 - PR4

Run with: pytest backend/scripts/testing/test_ab_framework.py
"""
import pytest
import os
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.experiments import ABTestManager, ExperimentCreate, OutcomeCreate


@pytest.fixture
def db_config():
    """Database configuration for testing"""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
        'client_encoding': 'UTF8'
    }


@pytest.fixture
def ab_manager(db_config):
    """ABTestManager instance"""
    manager = ABTestManager(db_config)
    manager.connect()
    yield manager
    manager.close()
    # Clear cache after tests
    ABTestManager.clear_cache()


@pytest.fixture
def test_experiment_name():
    """Unique experiment name for testing"""
    import uuid
    return f"test_exp_{uuid.uuid4().hex[:8]}"


class TestABTestManager:
    """Test suite for ABTestManager"""
    
    def test_create_experiment(self, ab_manager, test_experiment_name):
        """Test experiment creation"""
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        
        experiment = ab_manager.create_experiment(experiment_data)
        
        assert experiment.name == test_experiment_name
        assert experiment.status == "draft"
        assert experiment.variants == ["A", "B"]
        assert experiment.traffic_split_config == {"A": 0.5, "B": 0.5}
    
    def test_create_duplicate_experiment(self, ab_manager, test_experiment_name):
        """Test that duplicate experiment names are rejected"""
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        
        # Create first experiment
        ab_manager.create_experiment(experiment_data)
        
        # Attempt to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            ab_manager.create_experiment(experiment_data)
    
    def test_start_experiment(self, ab_manager, test_experiment_name):
        """Test starting an experiment"""
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        
        # Create experiment
        experiment = ab_manager.create_experiment(experiment_data)
        assert experiment.status == "draft"
        
        # Start experiment
        started = ab_manager.start_experiment(test_experiment_name)
        assert started.status == "active"
        assert started.started_at is not None
    
    def test_consistent_variant_assignment(self, ab_manager, test_experiment_name):
        """Test that same subject_id always gets same variant"""
        # Create and start experiment
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        ab_manager.create_experiment(experiment_data)
        ab_manager.start_experiment(test_experiment_name)
        
        subject_id = "test_user_123"
        
        # Get variant assignment multiple times
        assignments = [
            ab_manager.get_variant(test_experiment_name, subject_id)
            for _ in range(10)
        ]
        
        # All assignments should be identical
        variants = [a.variant for a in assignments]
        assert len(set(variants)) == 1, "Variant assignment is not consistent"
    
    def test_traffic_split_distribution(self, ab_manager, test_experiment_name):
        """Test that traffic split approximately matches configured ratios (AC: 50/50 ±7%)"""
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        ab_manager.create_experiment(experiment_data)
        ab_manager.start_experiment(test_experiment_name)
        
        num_subjects = 1000
        assignments = [
            ab_manager.get_variant(test_experiment_name, f"subject_{i}")
            for i in range(num_subjects)
        ]
        
        variant_counts = Counter(a.variant for a in assignments)
        
        assert 430 <= variant_counts["A"] <= 570, f"Variant A count out of range: {variant_counts['A']}"
        assert 430 <= variant_counts["B"] <= 570, f"Variant B count out of range: {variant_counts['B']}"
    
    def test_record_and_retrieve_outcome(self, ab_manager, test_experiment_name):
        """Test recording and retrieving experiment outcomes"""
        # Create and start experiment
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        ab_manager.create_experiment(experiment_data)
        ab_manager.start_experiment(test_experiment_name)
        
        # Record outcomes
        outcome_data = OutcomeCreate(
            subject_id="test_user_1",
            variant="A",
            metric_name="latency",
            metric_value=120.5,
            metric_type="numeric"
        )
        
        outcome = ab_manager.record_outcome(test_experiment_name, outcome_data)
        
        assert outcome.subject_id == "test_user_1"
        assert outcome.variant == "A"
        assert outcome.metric_name == "latency"
        assert outcome.metric_value == 120.5
    
    def test_get_experiment_report(self, ab_manager, test_experiment_name):
        """Test generating experiment report with statistics"""
        # Create and start experiment
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        experiment = ab_manager.create_experiment(experiment_data)
        ab_manager.start_experiment(test_experiment_name)
        
        # Record multiple outcomes
        outcomes = [
            OutcomeCreate(subject_id=f"user_{i}", variant="A", metric_name="latency", metric_value=100 + i)
            for i in range(10)
        ] + [
            OutcomeCreate(subject_id=f"user_{i+10}", variant="B", metric_name="latency", metric_value=90 + i)
            for i in range(10)
        ]
        
        for outcome_data in outcomes:
            ab_manager.record_outcome(test_experiment_name, outcome_data)
        
        # Generate report
        report = ab_manager.get_report(test_experiment_name)
        
        assert report.experiment_name == test_experiment_name
        assert report.total_subjects == 20
        assert "latency" in report.metrics
        
        # Check variant stats
        latency_stats = report.metrics["latency"]
        assert len(latency_stats) == 2  # A and B
        
        variant_a_stats = next(s for s in latency_stats if s.variant == "A")
        variant_b_stats = next(s for s in latency_stats if s.variant == "B")
        
        assert variant_a_stats.count == 10
        assert variant_b_stats.count == 10
        assert variant_a_stats.mean is not None
        assert variant_b_stats.mean is not None
    
    def test_get_variant_inactive_experiment(self, ab_manager, test_experiment_name):
        """Test that inactive experiments cannot assign variants"""
        # Create experiment but don't start it
        experiment_data = ExperimentCreate(
            name=test_experiment_name,
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 0.5, "B": 0.5}
        )
        ab_manager.create_experiment(experiment_data)
        
        # Try to get variant (should fail)
        with pytest.raises(ValueError, match="not active"):
            ab_manager.get_variant(test_experiment_name, "test_user")
    
    def test_invalid_traffic_split(self):
        """Test that invalid traffic splits are rejected"""
        # Sum doesn't equal 1.0
        with pytest.raises(ValueError, match="must sum to 1.0"):
            ExperimentCreate(
                name="test_invalid",
                description="Test",
                variants=["A", "B"],
                traffic_split={"A": 0.6, "B": 0.6}
            )
        
        # Missing variant in split
        with pytest.raises(ValueError, match="missing in traffic_split"):
            ExperimentCreate(
                name="test_invalid",
                description="Test",
                variants=["A", "B"],
                traffic_split={"A": 1.0}
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
