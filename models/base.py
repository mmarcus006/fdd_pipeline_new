"""Base models and common utilities for FDD Pipeline."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
import re


class Address(BaseModel):
    """Embedded address model for franchisor addresses."""
    street: str
    city: str
    state: str = Field(..., pattern="^[A-Z]{2}$")
    zip_code: str = Field(..., alias="zip")
    
    @field_validator('zip_code')
    @classmethod
    def validate_zip(cls, v):
        if not re.match(r"^\d{5}(-\d{4})?$", v):
            raise ValueError("Invalid ZIP code format")
        return v


def cents_to_dollars(cents: Optional[int]) -> Optional[float]:
    """Convert cents to dollars with proper rounding."""
    if cents is None:
        return None
    return round(cents / 100, 2)


def dollars_to_cents(dollars: Optional[float]) -> Optional[int]:
    """Convert dollars to cents."""
    if dollars is None:
        return None
    return int(round(dollars * 100))


class ValidationConfig:
    """Global validation configuration."""
    
    # Maximum amounts (in cents)
    MAX_FEE_AMOUNT = 10_000_000_00  # $10M
    MAX_INVESTMENT_AMOUNT = 100_000_000_00  # $100M
    MAX_REVENUE_AMOUNT = 10_000_000_000_00  # $10B
    
    # Percentage limits
    MAX_ROYALTY_PERCENTAGE = 50.0
    MAX_MARKETING_PERCENTAGE = 20.0
    
    # Business rules
    REQUIRE_AUDIT_ABOVE_REVENUE = 50_000_000_00  # $50M
    FLAG_NEGATIVE_EQUITY_THRESHOLD = -10_000_000_00  # -$10M
    
    # Data quality thresholds
    MIN_SAMPLE_SIZE_FOR_FPR = 5
    MAX_YEARS_HISTORICAL_DATA = 10