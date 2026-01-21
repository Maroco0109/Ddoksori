"""
A/B Test Manager
Core logic for experiment management, variant assignment, and outcome tracking
"""
import hashlib
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

from .models import (
    Experiment,
    ExperimentCreate,
    ExperimentOutcome,
    OutcomeCreate,
    VariantAssignment,
    ExperimentReport,
    VariantStats
)

logger = logging.getLogger(__name__)


class ABTestManager:
    """
    A/B Test Manager for experiment management and variant assignment
    
    Features:
    - Consistent variant assignment using hash-based bucketing
    - In-memory experiment cache for performance
    - DB persistence for outcomes
    """
    
    # Class-level cache for active experiments
    _experiment_cache: Dict[str, Experiment] = {}
    
    def __init__(self, db_config: Dict[str, Any]):
        """
        Initialize ABTestManager with database configuration
        
        Args:
            db_config: Database connection parameters
        """
        self.db_config = db_config
        self.conn: Optional[Any] = None
    
    def connect(self):
        """Establish database connection"""
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(**self.db_config)
    
    def close(self):
        """Close database connection"""
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    def _hash_subject(self, experiment_name: str, subject_id: str) -> float:
        """
        Generate consistent hash for subject assignment
        
        Args:
            experiment_name: Name of the experiment
            subject_id: User/session identifier
        
        Returns:
            Float between 0.0 and 1.0
        """
        # Combine experiment name and subject ID for consistent hashing
        hash_input = f"{experiment_name}:{subject_id}"
        hash_bytes = hashlib.md5(hash_input.encode('utf-8')).digest()
        # Convert first 8 bytes to integer, normalize to [0, 1)
        hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
        return hash_int / (2 ** 64)
    
    def _assign_variant(self, experiment: Experiment, subject_id: str) -> str:
        """
        Assign variant based on traffic split configuration
        
        Args:
            experiment: Experiment object
            subject_id: User/session identifier
        
        Returns:
            Assigned variant name
        """
        hash_value = self._hash_subject(experiment.name, subject_id)
        
        # Cumulative distribution function
        cumulative = 0.0
        for variant, ratio in experiment.traffic_split_config.items():
            cumulative += ratio
            if hash_value < cumulative:
                return variant
        
        # Fallback to last variant (should not happen if ratios sum to 1.0)
        return experiment.variants[-1]
    
    def create_experiment(self, experiment_data: ExperimentCreate) -> Experiment:
        """
        Create a new experiment
        
        Args:
            experiment_data: Experiment creation data
        
        Returns:
            Created Experiment object
        """
        self.connect()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO experiments 
                    (name, description, status, traffic_split_config, variants, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    experiment_data.name,
                    experiment_data.description,
                    'draft',
                    json.dumps(experiment_data.traffic_split),
                    json.dumps(experiment_data.variants),
                    json.dumps(experiment_data.metadata) if experiment_data.metadata else None
                ))
                
                row = cur.fetchone()
                self.conn.commit()
                
                experiment = Experiment(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    status=row['status'],
                    traffic_split_config=row['traffic_split_config'],
                    variants=row['variants'],
                    metadata=row['metadata'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    started_at=row['started_at'],
                    ended_at=row['ended_at']
                )
                
                logger.info(f"Created experiment: {experiment.name} (ID: {experiment.id})")
                return experiment
                
        except psycopg2.IntegrityError as e:
            self.conn.rollback()
            raise ValueError(f"Experiment with name '{experiment_data.name}' already exists") from e
        except Exception as e:
            self.conn.rollback()
            raise
    
    def get_experiment(self, experiment_name: str) -> Optional[Experiment]:
        """
        Get experiment by name (with caching)
        
        Args:
            experiment_name: Name of the experiment
        
        Returns:
            Experiment object or None if not found
        """
        # Check cache first
        if experiment_name in self._experiment_cache:
            return self._experiment_cache[experiment_name]
        
        self.connect()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM experiments 
                    WHERE name = %s
                """, (experiment_name,))
                
                row = cur.fetchone()
                if not row:
                    return None
                
                experiment = Experiment(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    status=row['status'],
                    traffic_split_config=row['traffic_split_config'],
                    variants=row['variants'],
                    metadata=row['metadata'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    started_at=row['started_at'],
                    ended_at=row['ended_at']
                )
                
                # Cache active experiments
                if experiment.status == 'active':
                    self._experiment_cache[experiment_name] = experiment
                
                return experiment
                
        except Exception as e:
            logger.error(f"Error fetching experiment '{experiment_name}': {e}")
            raise
    
    def start_experiment(self, experiment_name: str) -> Experiment:
        """
        Start an experiment (change status to active)
        
        Args:
            experiment_name: Name of the experiment
        
        Returns:
            Updated Experiment object
        """
        self.connect()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    UPDATE experiments 
                    SET status = 'active', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE name = %s AND status = 'draft'
                    RETURNING *
                """, (experiment_name,))
                
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Experiment '{experiment_name}' not found or already started")
                
                self.conn.commit()
                
                experiment = Experiment(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    status=row['status'],
                    traffic_split_config=row['traffic_split_config'],
                    variants=row['variants'],
                    metadata=row['metadata'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    started_at=row['started_at'],
                    ended_at=row['ended_at']
                )
                
                # Update cache
                self._experiment_cache[experiment_name] = experiment
                logger.info(f"Started experiment: {experiment_name}")
                
                return experiment
                
        except Exception as e:
            self.conn.rollback()
            raise
    
    def get_variant(self, experiment_name: str, subject_id: str) -> VariantAssignment:
        """
        Get assigned variant for a subject (consistent assignment)
        
        Args:
            experiment_name: Name of the experiment
            subject_id: User/session identifier
        
        Returns:
            VariantAssignment object
        
        Raises:
            ValueError: If experiment not found or not active
        """
        experiment = self.get_experiment(experiment_name)
        
        if not experiment:
            raise ValueError(f"Experiment '{experiment_name}' not found")
        
        if experiment.status != 'active':
            raise ValueError(f"Experiment '{experiment_name}' is not active (status: {experiment.status})")
        
        variant = self._assign_variant(experiment, subject_id)
        
        return VariantAssignment(
            experiment_name=experiment_name,
            subject_id=subject_id,
            variant=variant
        )
    
    def record_outcome(self, experiment_name: str, outcome_data: OutcomeCreate) -> ExperimentOutcome:
        """
        Record experiment outcome
        
        Args:
            experiment_name: Name of the experiment
            outcome_data: Outcome data to record
        
        Returns:
            Created ExperimentOutcome object
        """
        experiment = self.get_experiment(experiment_name)
        
        if not experiment:
            raise ValueError(f"Experiment '{experiment_name}' not found")
        
        self.connect()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO experiment_outcomes 
                    (experiment_id, subject_id, variant, metric_name, metric_value, metric_type, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    experiment.id,
                    outcome_data.subject_id,
                    outcome_data.variant,
                    outcome_data.metric_name,
                    outcome_data.metric_value,
                    outcome_data.metric_type,
                    json.dumps(outcome_data.metadata) if outcome_data.metadata else None
                ))
                
                row = cur.fetchone()
                self.conn.commit()
                
                return ExperimentOutcome(
                    id=row['id'],
                    experiment_id=row['experiment_id'],
                    subject_id=row['subject_id'],
                    variant=row['variant'],
                    metric_name=row['metric_name'],
                    metric_value=row['metric_value'],
                    metric_type=row['metric_type'],
                    metadata=row['metadata'],
                    created_at=row['created_at']
                )
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error recording outcome for experiment '{experiment_name}': {e}")
            raise
    
    def get_report(self, experiment_name: str) -> ExperimentReport:
        """
        Generate analysis report for an experiment
        
        Args:
            experiment_name: Name of the experiment
        
        Returns:
            ExperimentReport object with aggregated statistics
        """
        experiment = self.get_experiment(experiment_name)
        
        if not experiment:
            raise ValueError(f"Experiment '{experiment_name}' not found")
        
        self.connect()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get aggregated statistics per variant per metric
                cur.execute("""
                    SELECT 
                        metric_name,
                        variant,
                        COUNT(*) as count,
                        AVG(metric_value) as mean,
                        STDDEV(metric_value) as std,
                        MIN(metric_value) as min,
                        MAX(metric_value) as max
                    FROM experiment_outcomes
                    WHERE experiment_id = %s
                    GROUP BY metric_name, variant
                    ORDER BY metric_name, variant
                """, (experiment.id,))
                
                rows = cur.fetchall()
                
                # Get total unique subjects
                cur.execute("""
                    SELECT COUNT(DISTINCT subject_id) as total
                    FROM experiment_outcomes
                    WHERE experiment_id = %s
                """, (experiment.id,))
                
                total_subjects = cur.fetchone()['total']
                
                # Organize by metric name
                metrics: Dict[str, List[VariantStats]] = {}
                for row in rows:
                    metric_name = row['metric_name']
                    if metric_name not in metrics:
                        metrics[metric_name] = []
                    
                    metrics[metric_name].append(VariantStats(
                        variant=row['variant'],
                        count=row['count'],
                        mean=float(row['mean']) if row['mean'] is not None else None,
                        std=float(row['std']) if row['std'] is not None else None,
                        min=float(row['min']) if row['min'] is not None else None,
                        max=float(row['max']) if row['max'] is not None else None
                    ))
                
                return ExperimentReport(
                    experiment_name=experiment.name,
                    experiment_id=experiment.id,
                    status=experiment.status,
                    total_subjects=total_subjects,
                    metrics=metrics
                )
                
        except Exception as e:
            logger.error(f"Error generating report for experiment '{experiment_name}': {e}")
            raise
    
    @classmethod
    def clear_cache(cls):
        """Clear the experiment cache (useful for testing)"""
        cls._experiment_cache.clear()
