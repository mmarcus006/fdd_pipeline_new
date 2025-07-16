"""Item 7 - Initial Investment models."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from uuid import UUID

from .base import ValidationConfig


class InitialInvestmentBase(BaseModel):
    """Base model for initial investment items."""
    category: str = Field(..., min_length=1)
    low_cents: Optional[int] = Field(None, ge=0)
    high_cents: Optional[int] = Field(None, ge=0)
    when_due: Optional[str] = None
    to_whom: Optional[str] = None
    remarks: Optional[str] = None
    
    @model_validator(mode='after')
    def validate_range(self):
        """Ensure high >= low and at least one is set."""
        low = self.low_cents
        high = self.high_cents
        
        if low is None and high is None:
            raise ValueError("At least one of low_cents or high_cents must be set")
        
        if low is not None and high is not None and high < low:
            raise ValueError("high_cents must be >= low_cents")
        
        return self
    
    @field_validator('category')
    @classmethod
    def standardize_category(cls, v):
        """Standardize common category names."""
        category_map = {
            'REAL ESTATE': 'Real Estate',
            'EQUIPMENT': 'Equipment',
            'INVENTORY': 'Inventory',
            'WORKING CAPITAL': 'Working Capital',
            'TRAINING': 'Training',
            'FRANCHISE FEE': 'Initial Franchise Fee'
        }
        return category_map.get(v.upper(), v)


class InitialInvestment(InitialInvestmentBase):
    """Initial investment with section reference."""
    section_id: UUID
    
    model_config = {"from_attributes": True}


class InitialInvestmentSummary(BaseModel):
    """Computed summary of initial investment."""
    section_id: UUID
    total_items: int
    total_low_cents: int
    total_high_cents: int
    items: List[InitialInvestment]
    
    @field_validator('total_low_cents', 'total_high_cents')
    @classmethod
    def validate_totals(cls, v):
        """Ensure totals are reasonable."""
        if v > ValidationConfig.MAX_INVESTMENT_AMOUNT:
            raise ValueError("Total exceeds reasonable maximum")
        return v