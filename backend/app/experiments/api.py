"""
API endpoints for A/B testing framework
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from .models import (
    ExperimentCreate,
    Experiment,
    OutcomeCreate,
    ExperimentOutcome,
    VariantAssignment,
    ExperimentReport
)
from .ab_test import ABTestManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


def get_ab_manager():
    """
    Dependency for ABTestManager instance
    
    Yields:
        ABTestManager instance with connection
    """
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
        'client_encoding': 'UTF8'
    }
    
    manager = ABTestManager(db_config)
    try:
        manager.connect()
        yield manager
    finally:
        manager.close()


@router.post("/", response_model=Experiment, status_code=201)
async def create_experiment(
    experiment_data: ExperimentCreate,
    manager: ABTestManager = Depends(get_ab_manager)
):
    """
    Create a new A/B test experiment
    
    Args:
        experiment_data: Experiment configuration
    
    Returns:
        Created Experiment object
    
    Example:
        ```json
        {
          "name": "embedding_model_test",
          "description": "Compare KURE-v1 vs text-embedding-3-large",
          "variants": ["A", "B"],
          "traffic_split": {"A": 0.5, "B": 0.5},
          "metadata": {"target_metric": "retrieval_quality"}
        }
        ```
    """
    try:
        experiment = manager.create_experiment(experiment_data)
        return experiment
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating experiment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{experiment_name}/start", response_model=Experiment)
async def start_experiment(
    experiment_name: str,
    manager: ABTestManager = Depends(get_ab_manager)
):
    """
    Start an experiment (change status from draft to active)
    
    Args:
        experiment_name: Name of the experiment to start
    
    Returns:
        Updated Experiment object
    """
    try:
        experiment = manager.start_experiment(experiment_name)
        return experiment
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting experiment '{experiment_name}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{experiment_name}/assign", response_model=VariantAssignment)
async def assign_variant(
    experiment_name: str,
    subject_id: str,
    manager: ABTestManager = Depends(get_ab_manager)
):
    """
    Get variant assignment for a subject (consistent assignment)
    
    Args:
        experiment_name: Name of the experiment
        subject_id: User/session identifier
    
    Returns:
        VariantAssignment with assigned variant
    
    Example:
        GET /api/v1/experiments/embedding_model_test/assign?subject_id=session_12345
        
        Response:
        ```json
        {
          "experiment_name": "embedding_model_test",
          "subject_id": "session_12345",
          "variant": "A",
          "assigned_at": "2026-01-21T14:30:00"
        }
        ```
    """
    try:
        assignment = manager.get_variant(experiment_name, subject_id)
        return assignment
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error assigning variant for experiment '{experiment_name}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{experiment_name}/track", response_model=ExperimentOutcome, status_code=201)
async def track_outcome(
    experiment_name: str,
    outcome_data: OutcomeCreate,
    background_tasks: BackgroundTasks,
    manager: ABTestManager = Depends(get_ab_manager)
):
    """
    Record experiment outcome (async to avoid latency)
    
    Args:
        experiment_name: Name of the experiment
        outcome_data: Outcome data to record
        background_tasks: FastAPI background tasks
    
    Returns:
        Created ExperimentOutcome object
    
    Example:
        ```json
        {
          "subject_id": "session_12345",
          "variant": "A",
          "metric_name": "retrieval_quality",
          "metric_value": 0.85,
          "metric_type": "numeric",
          "metadata": {"request_id": "req_abc123"}
        }
        ```
    """
    try:
        # Record outcome immediately (for now)
        # TODO: Consider moving to BackgroundTasks for production
        outcome = manager.record_outcome(experiment_name, outcome_data)
        return outcome
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error tracking outcome for experiment '{experiment_name}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{experiment_name}/report", response_model=ExperimentReport)
async def get_experiment_report(
    experiment_name: str,
    manager: ABTestManager = Depends(get_ab_manager)
):
    """
    Get aggregated analysis report for an experiment
    
    Args:
        experiment_name: Name of the experiment
    
    Returns:
        ExperimentReport with statistics per variant
    
    Example Response:
        ```json
        {
          "experiment_name": "embedding_model_test",
          "experiment_id": 1,
          "status": "active",
          "total_subjects": 150,
          "metrics": {
            "retrieval_quality": [
              {
                "variant": "A",
                "count": 75,
                "mean": 0.82,
                "std": 0.05,
                "min": 0.70,
                "max": 0.95
              },
              {
                "variant": "B",
                "count": 75,
                "mean": 0.87,
                "std": 0.04,
                "min": 0.75,
                "max": 0.98
              }
            ]
          },
          "generated_at": "2026-01-21T14:30:00"
        }
        ```
    """
    try:
        report = manager.get_report(experiment_name)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating report for experiment '{experiment_name}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{experiment_name}", response_model=Experiment)
async def get_experiment(
    experiment_name: str,
    manager: ABTestManager = Depends(get_ab_manager)
):
    """
    Get experiment details
    
    Args:
        experiment_name: Name of the experiment
    
    Returns:
        Experiment object
    """
    try:
        experiment = manager.get_experiment(experiment_name)
        if not experiment:
            raise HTTPException(status_code=404, detail=f"Experiment '{experiment_name}' not found")
        return experiment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching experiment '{experiment_name}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
