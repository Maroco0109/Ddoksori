"""
Pydantic models for A/B testing framework
"""
from datetime import datetime
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


class ExperimentCreate(BaseModel):
    """Request model for creating a new experiment"""
    name: str = Field(..., min_length=1, max_length=255, description="Unique experiment name")
    description: Optional[str] = Field(None, description="Experiment description")
    variants: List[str] = Field(..., min_length=2, description="List of variant names (e.g., ['A', 'B'])")
    traffic_split: Dict[str, float] = Field(..., description="Traffic split config (e.g., {'A': 0.5, 'B': 0.5})")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")

    @field_validator('traffic_split')
    @classmethod
    def validate_traffic_split(cls, v, info):
        """Validate that traffic split sums to 1.0"""
        variants = info.data.get('variants', [])
        
        # Check all variants have split ratios
        for variant in variants:
            if variant not in v:
                raise ValueError(f"Variant '{variant}' missing in traffic_split")
        
        # Check sum equals 1.0 (with tolerance)
        total = sum(v.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Traffic split must sum to 1.0, got {total}")
        
        # Check all ratios are positive
        for variant, ratio in v.items():
            if ratio <= 0:
                raise ValueError(f"Traffic ratio for '{variant}' must be positive")
        
        return v


class Experiment(BaseModel):
    """Experiment model (database representation)"""
    id: int
    name: str
    description: Optional[str] = None
    status: Literal['draft', 'active', 'paused', 'completed'] = 'draft'
    traffic_split_config: Dict[str, float]
    variants: List[str]
    metadata: Optional[Dict] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OutcomeCreate(BaseModel):
    """Request model for recording an outcome"""
    subject_id: str = Field(..., description="User/session ID")
    variant: str = Field(..., description="Assigned variant")
    metric_name: str = Field(..., description="Metric name (e.g., 'latency', 'success')")
    metric_value: float = Field(..., description="Metric value")
    metric_type: Literal['numeric', 'boolean', 'string'] = Field(default='numeric')
    metadata: Optional[Dict] = Field(default=None, description="Additional context")


class ExperimentOutcome(BaseModel):
    """Experiment outcome model (database representation)"""
    id: int
    experiment_id: int
    subject_id: str
    variant: str
    metric_name: str
    metric_value: float
    metric_type: str = 'numeric'
    metadata: Optional[Dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class VariantAssignment(BaseModel):
    """Response model for variant assignment"""
    experiment_name: str
    subject_id: str
    variant: str
    assigned_at: datetime = Field(default_factory=datetime.now)


class VariantStats(BaseModel):
    """Statistics for a single variant"""
    variant: str
    count: int
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class ExperimentReport(BaseModel):
    """Report model for experiment analysis"""
    experiment_name: str
    experiment_id: int
    status: str
    total_subjects: int
    metrics: Dict[str, List[VariantStats]]  # metric_name -> [VariantStats]
    generated_at: datetime = Field(default_factory=datetime.now)
