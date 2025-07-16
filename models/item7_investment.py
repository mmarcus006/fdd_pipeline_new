"""Item 7 - Initial Investment models."""

from pydantic import BaseModel, Field, validator, root_validator
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
    
    @root_validator
    def validate_range(cls, values):
        """Ensure high >= low and at least one is set."""
        low = values.get('low_cents')
        high = values.get('high_cents')
        
        if low is None and high is None:
            raise ValueError("At least one of low_cents or high_cents must be set")
        
        if low is not None and high is not None and high < low:
            raise ValueError("high_cents must be >= low_cents")
        
        return values
    
    @validator('category')
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
    
    class Config:
        orm_mode = True


class InitialInvestmentSummary(BaseModel):
    """Computed summary of initial investment."""
    section_id: UUID
    total_items: int
    total_low_cents: int
    total_high_cents: int
    items: List[InitialInvestment]
    
    @validator('total_low_cents', 'total_high_cents')
    def validate_totals(cls, v):
        """Ensure totals are reasonable."""
        if v > ValidationConfig.MAX_INVESTMENT_AMOUNT:
            raise ValueError("Total exceeds reasonable maximum")
        return v