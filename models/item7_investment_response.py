"""Item 7 - Initial Investment response models for structured extraction."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
from enum import Enum


class InvestmentCategory(str, Enum):
    """Categories of initial investment items."""
    INITIAL_FRANCHISE_FEE = "initial_franchise_fee"
    REAL_ESTATE = "real_estate"
    LEASEHOLD_IMPROVEMENTS = "leasehold_improvements"
    EQUIPMENT = "equipment"
    FURNITURE_FIXTURES = "furniture_fixtures"
    INVENTORY = "inventory"
    SIGNAGE = "signage"
    WORKING_CAPITAL = "working_capital"
    TRAINING = "training"
    PROFESSIONAL_FEES = "professional_fees"
    PERMITS_LICENSES = "permits_licenses"
    INSURANCE = "insurance"
    MARKETING = "marketing"
    OTHER = "other"


class PaymentTiming(str, Enum):
    """When payment is due."""
    BEFORE_OPENING = "before_opening"
    AT_SIGNING = "at_signing"
    DURING_CONSTRUCTION = "during_construction"
    AT_OPENING = "at_opening"
    AS_INCURRED = "as_incurred"
    ONGOING = "ongoing"
    OTHER = "other"


class InvestmentItem(BaseModel):
    """Individual investment item."""
    
    category: InvestmentCategory = Field(..., description="Category of investment")
    description: str = Field(..., description="Description of the investment item")
    
    # Cost range
    low_cents: Optional[int] = Field(None, ge=0, description="Low estimate in cents")
    high_cents: Optional[int] = Field(None, ge=0, description="High estimate in cents")
    
    # Payment details
    when_due: Optional[PaymentTiming] = Field(None, description="When payment is due")
    to_whom_paid: Optional[str] = Field(None, description="Who receives the payment")
    
    # Additional information
    financing_available: Optional[bool] = Field(None, description="Whether financing is available")
    refundable: Optional[bool] = Field(None, description="Whether the payment is refundable")
    conditions: Optional[str] = Field(None, description="Special conditions or requirements")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    @model_validator(mode="after")
    def validate_cost_range(self):
        """Ensure cost range is valid."""
        if self.low_cents is None and self.high_cents is None:
            raise ValueError("Must specify at least one of low_cents or high_cents")
        
        if (self.low_cents is not None and 
            self.high_cents is not None and 
            self.high_cents < self.low_cents):
            raise ValueError("high_cents must be >= low_cents")
            
        return self
    
    @property
    def estimated_cost_cents(self) -> int:
        """Get estimated cost (average of range or single value)."""
        if self.low_cents is not None and self.high_cents is not None:
            return (self.low_cents + self.high_cents) // 2
        elif self.high_cents is not None:
            return self.high_cents
        elif self.low_cents is not None:
            return self.low_cents
        return 0


class InvestmentSummary(BaseModel):
    """Summary of investment by category."""
    
    category: InvestmentCategory
    total_low_cents: int = Field(0, ge=0)
    total_high_cents: int = Field(0, ge=0)
    item_count: int = Field(0, ge=0)
    
    @property
    def average_investment_cents(self) -> int:
        """Calculate average investment for this category."""
        if self.total_low_cents > 0 and self.total_high_cents > 0:
            return (self.total_low_cents + self.total_high_cents) // 2
        return max(self.total_low_cents, self.total_high_cents)


class Item7InvestmentResponse(BaseModel):
    """Structured response for Item 7 - Initial Investment extraction."""
    
    # Individual investment items
    investment_items: List[InvestmentItem] = Field(
        default_factory=list,
        description="List of all initial investment items"
    )
    
    # Total investment range
    total_low_cents: int = Field(0, ge=0, description="Total low estimate in cents")
    total_high_cents: int = Field(0, ge=0, description="Total high estimate in cents")
    
    # Summary by category
    category_summaries: List[InvestmentSummary] = Field(
        default_factory=list,
        description="Investment summary by category"
    )
    
    # Financing information
    financing_available: Optional[bool] = Field(None, description="Whether financing is generally available")
    financing_details: Optional[str] = Field(None, description="Details about financing options")
    
    # Additional costs
    additional_funds_needed: Optional[str] = Field(None, description="Information about additional funds needed")
    working_capital_details: Optional[str] = Field(None, description="Working capital requirements")
    
    # Timing information
    investment_timeline: Optional[str] = Field(None, description="Timeline for making investments")
    pre_opening_costs_cents: Optional[int] = Field(None, ge=0, description="Costs due before opening")
    
    # Variations and conditions
    cost_variations: Optional[str] = Field(None, description="Factors that affect cost variations")
    location_factors: Optional[str] = Field(None, description="How location affects costs")
    
    # Extraction metadata
    extraction_confidence: Optional[float] = Field(
        None, ge=0, le=1,
        description="Confidence score for the extraction (0-1)"
    )
    
    notes: Optional[str] = Field(None, description="Additional notes or clarifications")
    
    @model_validator(mode="after")
    def calculate_totals_and_summaries(self):
        """Calculate totals and category summaries from investment items."""
        if not self.investment_items:
            return self
        
        # Calculate totals
        total_low = 0
        total_high = 0
        
        # Group by category
        category_data = {}
        
        for item in self.investment_items:
            # Add to totals
            if item.low_cents:
                total_low += item.low_cents
            if item.high_cents:
                total_high += item.high_cents
            
            # Group by category
            if item.category not in category_data:
                category_data[item.category] = {
                    'low': 0,
                    'high': 0,
                    'count': 0
                }
            
            if item.low_cents:
                category_data[item.category]['low'] += item.low_cents
            if item.high_cents:
                category_data[item.category]['high'] += item.high_cents
            category_data[item.category]['count'] += 1
        
        # Update totals
        self.total_low_cents = total_low
        self.total_high_cents = total_high
        
        # Create category summaries
        self.category_summaries = [
            InvestmentSummary(
                category=category,
                total_low_cents=data['low'],
                total_high_cents=data['high'],
                item_count=data['count']
            )
            for category, data in category_data.items()
        ]
        
        return self
    
    @field_validator("total_low_cents", "total_high_cents")
    @classmethod
    def validate_reasonable_totals(cls, v):
        """Validate that totals are within reasonable bounds."""
        if v > 1_000_000_000:  # $10M max
            raise ValueError("Total investment exceeds reasonable maximum")
        return v
    
    def get_category_investment(self, category: InvestmentCategory) -> Optional[InvestmentSummary]:
        """Get investment summary for a specific category."""
        for summary in self.category_summaries:
            if summary.category == category:
                return summary
        return None
    
    def get_items_by_category(self, category: InvestmentCategory) -> List[InvestmentItem]:
        """Get all investment items for a specific category."""
        return [item for item in self.investment_items if item.category == category]
    
    @property
    def estimated_total_investment_cents(self) -> int:
        """Get estimated total investment (average of range)."""
        if self.total_low_cents > 0 and self.total_high_cents > 0:
            return (self.total_low_cents + self.total_high_cents) // 2
        return max(self.total_low_cents, self.total_high_cents)
    
    def validate_against_item5_fee(self, item5_fee_cents: int) -> bool:
        """Validate that initial franchise fee matches Item 5."""
        franchise_fee_items = self.get_items_by_category(InvestmentCategory.INITIAL_FRANCHISE_FEE)
        
        if not franchise_fee_items:
            return True  # No franchise fee item to validate
        
        # Check if any franchise fee item matches Item 5
        for item in franchise_fee_items:
            if (item.low_cents and item.low_cents <= item5_fee_cents <= (item.high_cents or item.low_cents)):
                return True
            if item.high_cents == item5_fee_cents or item.low_cents == item5_fee_cents:
                return True
        
        return False