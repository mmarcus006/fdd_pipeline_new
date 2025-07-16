"""Item 6 - Other Fees models."""

from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional
from uuid import UUID
from enum import Enum

from .base import ValidationConfig


class FeeFrequency(str, Enum):
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"
    ANNUAL = "Annual"
    ONE_TIME = "One-time"
    AS_INCURRED = "As Incurred"


class CalculationBasis(str, Enum):
    GROSS_SALES = "Gross Sales"
    NET_SALES = "Net Sales"
    FIXED = "Fixed"
    VARIABLE = "Variable"
    OTHER = "Other"


class OtherFeeBase(BaseModel):
    """Base model for ongoing/other fees."""
    fee_name: str = Field(..., min_length=1)
    amount_cents: Optional[int] = Field(None, ge=0)
    amount_percentage: Optional[float] = Field(None, ge=0, le=100)
    frequency: FeeFrequency
    calculation_basis: Optional[CalculationBasis] = None
    minimum_cents: Optional[int] = Field(None, ge=0)
    maximum_cents: Optional[int] = Field(None, ge=0)
    remarks: Optional[str] = None
    
    @root_validator
    def validate_amount_type(cls, values):
        """Ensure either amount_cents OR amount_percentage is set."""
        cents = values.get('amount_cents')
        pct = values.get('amount_percentage')
        
        if (cents is None and pct is None) or (cents is not None and pct is not None):
            raise ValueError("Must specify either amount_cents or amount_percentage, not both")
        return values
    
    @root_validator
    def validate_min_max(cls, values):
        """Ensure max >= min if both specified."""
        min_val = values.get('minimum_cents')
        max_val = values.get('maximum_cents')
        
        if min_val is not None and max_val is not None and max_val < min_val:
            raise ValueError("maximum_cents must be >= minimum_cents")
        return values
    
    @validator('amount_percentage')
    def validate_percentage(cls, v):
        """Common sense check for percentages."""
        if v is not None and v > 50:
            # Flag unusually high percentages for review
            # but don't reject - some fees can be high
            pass
        return v


class OtherFee(OtherFeeBase):
    """Other fee with section reference."""
    section_id: UUID
    
    class Config:
        orm_mode = True