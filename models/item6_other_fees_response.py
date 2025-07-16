"""Item 6 - Other Fees response models for structured extraction."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
from enum import Enum


class FeeFrequency(str, Enum):
    """Frequency of fee payments."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    ONE_TIME = "one_time"
    AS_INCURRED = "as_incurred"
    ONGOING = "ongoing"


class CalculationBasis(str, Enum):
    """Basis for calculating fees."""
    GROSS_SALES = "gross_sales"
    NET_SALES = "net_sales"
    REVENUE = "revenue"
    FIXED_AMOUNT = "fixed_amount"
    VARIABLE = "variable"
    COST_PLUS = "cost_plus"
    OTHER = "other"


class FeeCategory(str, Enum):
    """Categories of ongoing fees."""
    ROYALTY = "royalty"
    ADVERTISING = "advertising"
    MARKETING = "marketing"
    TECHNOLOGY = "technology"
    TRAINING = "training"
    SUPPLIES = "supplies"
    INSURANCE = "insurance"
    OTHER = "other"


class OtherFeeStructure(BaseModel):
    """Structure for ongoing/other fees."""
    
    fee_name: str = Field(..., description="Name/description of the fee")
    category: Optional[FeeCategory] = Field(None, description="Category of the fee")
    
    # Amount specification - either fixed amount or percentage
    amount_cents: Optional[int] = Field(None, ge=0, description="Fixed fee amount in cents")
    percentage: Optional[float] = Field(None, ge=0, le=100, description="Percentage of sales/revenue")
    
    # Calculation details
    calculation_basis: Optional[CalculationBasis] = Field(None, description="What the percentage is calculated on")
    frequency: FeeFrequency = Field(..., description="How often the fee is paid")
    
    # Min/max amounts for percentage-based fees
    minimum_cents: Optional[int] = Field(None, ge=0, description="Minimum fee amount in cents")
    maximum_cents: Optional[int] = Field(None, ge=0, description="Maximum fee amount in cents")
    
    # Payment details
    due_date: Optional[str] = Field(None, description="When payment is due (e.g., '10th of each month')")
    payment_method: Optional[str] = Field(None, description="Required payment method")
    
    # Additional information
    conditions: Optional[str] = Field(None, description="Conditions that apply to this fee")
    exemptions: Optional[str] = Field(None, description="Any exemptions or exceptions")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    @model_validator(mode="after")
    def validate_amount_specification(self):
        """Ensure either amount_cents or percentage is specified."""
        if self.amount_cents is None and self.percentage is None:
            raise ValueError("Must specify either amount_cents or percentage")
        if self.amount_cents is not None and self.percentage is not None:
            raise ValueError("Cannot specify both amount_cents and percentage")
        return self
    
    @model_validator(mode="after")
    def validate_min_max_range(self):
        """Ensure max >= min if both specified."""
        if (self.minimum_cents is not None and 
            self.maximum_cents is not None and 
            self.maximum_cents < self.minimum_cents):
            raise ValueError("maximum_cents must be >= minimum_cents")
        return self
    
    @field_validator("percentage")
    @classmethod
    def validate_reasonable_percentage(cls, v):
        """Flag unusually high percentages."""
        if v is not None and v > 50:
            # Log warning but don't reject - some fees can be high
            pass
        return v


class RoyaltyStructure(BaseModel):
    """Specific structure for royalty fees."""
    
    percentage: float = Field(..., ge=0, le=100, description="Royalty percentage")
    calculation_basis: CalculationBasis = Field(default=CalculationBasis.GROSS_SALES)
    frequency: FeeFrequency = Field(default=FeeFrequency.MONTHLY)
    minimum_cents: Optional[int] = Field(None, ge=0)
    maximum_cents: Optional[int] = Field(None, ge=0)
    grace_period_months: Optional[int] = Field(None, ge=0, description="Grace period before royalties start")
    reduced_rate_period: Optional[Dict[str, Any]] = Field(None, description="Any reduced rate periods")


class AdvertisingFeeStructure(BaseModel):
    """Specific structure for advertising fees."""
    
    percentage: Optional[float] = Field(None, ge=0, le=100, description="Advertising fee percentage")
    amount_cents: Optional[int] = Field(None, ge=0, description="Fixed advertising fee amount")
    calculation_basis: CalculationBasis = Field(default=CalculationBasis.GROSS_SALES)
    frequency: FeeFrequency = Field(default=FeeFrequency.MONTHLY)
    
    # Advertising fund details
    fund_name: Optional[str] = Field(None, description="Name of advertising fund")
    fund_usage: Optional[str] = Field(None, description="How advertising funds are used")
    local_advertising_requirement: Optional[str] = Field(None, description="Local advertising requirements")
    
    @model_validator(mode="after")
    def validate_amount_or_percentage(self):
        """Ensure either amount or percentage is specified."""
        if self.amount_cents is None and self.percentage is None:
            raise ValueError("Must specify either amount_cents or percentage")
        return self


class Item6OtherFeesResponse(BaseModel):
    """Structured response for Item 6 - Other Fees extraction."""
    
    # Royalty fees (most common)
    royalty_fee: Optional[RoyaltyStructure] = Field(None, description="Royalty fee structure")
    
    # Advertising fees
    advertising_fee: Optional[AdvertisingFeeStructure] = Field(None, description="Advertising fee structure")
    
    # All other ongoing fees
    other_fees: List[OtherFeeStructure] = Field(
        default_factory=list,
        description="List of all other ongoing fees"
    )
    
    # Summary information
    has_royalty: bool = Field(False, description="Whether there are royalty fees")
    has_advertising_fee: bool = Field(False, description="Whether there are advertising fees")
    total_ongoing_fees_count: int = Field(0, description="Total number of ongoing fees")
    
    # Payment and reporting
    reporting_requirements: Optional[str] = Field(None, description="Financial reporting requirements")
    payment_system: Optional[str] = Field(None, description="Payment system or method")
    late_payment_penalties: Optional[str] = Field(None, description="Penalties for late payment")
    
    # Additional terms
    fee_increases: Optional[str] = Field(None, description="Information about fee increases")
    fee_waivers: Optional[str] = Field(None, description="Any fee waivers or reductions")
    
    # Extraction metadata
    extraction_confidence: Optional[float] = Field(
        None, ge=0, le=1,
        description="Confidence score for the extraction (0-1)"
    )
    
    notes: Optional[str] = Field(None, description="Additional notes or clarifications")
    
    @model_validator(mode="after")
    def update_summary_fields(self):
        """Update summary fields based on extracted data."""
        self.has_royalty = self.royalty_fee is not None
        self.has_advertising_fee = self.advertising_fee is not None
        self.total_ongoing_fees_count = len(self.other_fees)
        
        # Add royalty and advertising to count if present
        if self.has_royalty:
            self.total_ongoing_fees_count += 1
        if self.has_advertising_fee:
            self.total_ongoing_fees_count += 1
            
        return self
    
    def get_total_percentage_fees(self) -> float:
        """Calculate total percentage-based fees."""
        total = 0.0
        
        if self.royalty_fee and self.royalty_fee.percentage:
            total += self.royalty_fee.percentage
            
        if self.advertising_fee and self.advertising_fee.percentage:
            total += self.advertising_fee.percentage
            
        for fee in self.other_fees:
            if fee.percentage:
                total += fee.percentage
                
        return total
    
    def get_monthly_fixed_fees_cents(self) -> int:
        """Calculate total monthly fixed fees."""
        total = 0
        
        for fee in self.other_fees:
            if fee.amount_cents and fee.frequency == FeeFrequency.MONTHLY:
                total += fee.amount_cents
                
        return total