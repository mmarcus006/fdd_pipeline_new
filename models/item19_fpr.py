"""Item 19 - Financial Performance Representations models."""

from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, Dict, List, Any
from datetime import datetime
from uuid import UUID
from enum import Enum

from .base import ValidationConfig


class DisclosureType(str, Enum):
    HISTORICAL = "Historical"
    PROJECTED = "Projected"
    NONE = "None"
    MIXED = "Mixed"


class FPRBase(BaseModel):
    """Base model for Item 19 FPR."""
    disclosure_type: Optional[DisclosureType] = None
    methodology: Optional[str] = None
    sample_size: Optional[int] = Field(None, gt=0)
    sample_description: Optional[str] = None
    time_period: Optional[str] = None
    
    # Revenue metrics
    average_revenue_cents: Optional[int] = Field(None, ge=0)
    median_revenue_cents: Optional[int] = Field(None, ge=0)
    low_revenue_cents: Optional[int] = Field(None, ge=0)
    high_revenue_cents: Optional[int] = Field(None, ge=0)
    
    # Profit metrics
    average_profit_cents: Optional[int] = None
    median_profit_cents: Optional[int] = None
    profit_margin_percentage: Optional[float] = Field(None, ge=-100, le=100)
    
    # Complex data
    additional_metrics: Dict[str, Any] = Field(default_factory=dict)
    tables_data: List[Dict[str, Any]] = Field(default_factory=list)
    
    disclaimers: Optional[str] = None
    
    @root_validator
    def validate_revenue_range(cls, values):
        """Ensure revenue metrics are consistent."""
        low = values.get('low_revenue_cents')
        high = values.get('high_revenue_cents')
        avg = values.get('average_revenue_cents')
        median = values.get('median_revenue_cents')
        
        if all(v is not None for v in [low, high, avg]):
            if not (low <= avg <= high):
                raise ValueError("Average revenue must be between low and high")
        
        if all(v is not None for v in [low, high, median]):
            if not (low <= median <= high):
                raise ValueError("Median revenue must be between low and high")
        
        return values
    
    @validator('profit_margin_percentage')
    def validate_profit_margin(cls, v):
        """Flag unusual profit margins."""
        if v is not None:
            if v < -50:
                # Flag for review but don't reject
                pass
            if v > 50:
                # Very high margin - flag for review
                pass
        return v


class FPR(FPRBase):
    """FPR with section reference."""
    section_id: UUID
    created_at: datetime
    
    class Config:
        orm_mode = True