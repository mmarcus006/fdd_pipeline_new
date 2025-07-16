"""Item 5 - Initial Fees response models for structured extraction."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from enum import Enum


class DueAt(str, Enum):
    """When the fee is due."""
    SIGNING = "signing"
    TRAINING = "training"
    OPENING = "opening"
    OTHER = "other"


class DiscountType(str, Enum):
    """Types of discounts available."""
    VETERAN = "veteran"
    MULTI_UNIT = "multi_unit"
    CONVERSION = "conversion"
    PROMOTIONAL = "promotional"
    OTHER = "other"


class InitialFeeDiscount(BaseModel):
    """Discount information for initial fees."""
    
    discount_type: DiscountType
    amount_cents: Optional[int] = Field(None, ge=0, description="Fixed discount amount in cents")
    percentage: Optional[float] = Field(None, ge=0, le=100, description="Percentage discount")
    description: str = Field(..., description="Description of the discount")
    conditions: Optional[str] = Field(None, description="Conditions that apply to the discount")
    
    @field_validator("amount_cents", "percentage")
    @classmethod
    def validate_discount_amount(cls, v, info):
        """Ensure either amount_cents or percentage is provided, not both."""
        values = info.data
        amount = values.get("amount_cents")
        pct = values.get("percentage")
        
        if amount is not None and pct is not None:
            raise ValueError("Cannot specify both amount_cents and percentage")
        if amount is None and pct is None:
            raise ValueError("Must specify either amount_cents or percentage")
        return v


class InitialFeeStructure(BaseModel):
    """Structure for initial franchise fees."""
    
    fee_name: str = Field(..., description="Name/description of the fee")
    amount_cents: int = Field(..., ge=0, description="Fee amount in cents")
    due_at: Optional[DueAt] = Field(None, description="When the fee is due")
    refundable: bool = Field(False, description="Whether the fee is refundable")
    refund_conditions: Optional[str] = Field(None, description="Conditions for refund if applicable")
    notes: Optional[str] = Field(None, description="Additional notes about the fee")


class Item5FeesResponse(BaseModel):
    """Structured response for Item 5 - Initial Fees extraction."""
    
    # Primary franchise fee
    initial_franchise_fee_cents: int = Field(..., ge=0, description="Primary initial franchise fee in cents")
    
    # Additional fees
    additional_fees: List[InitialFeeStructure] = Field(
        default_factory=list,
        description="List of additional initial fees"
    )
    
    # Multi-unit pricing
    additional_unit_fee_cents: Optional[int] = Field(
        None, ge=0, 
        description="Fee for additional units/locations in cents"
    )
    
    # Discounts and special pricing
    discounts: List[InitialFeeDiscount] = Field(
        default_factory=list,
        description="Available discounts on initial fees"
    )
    
    # Payment terms
    payment_terms: Optional[str] = Field(None, description="Payment terms and schedule")
    due_at: DueAt = Field(DueAt.SIGNING, description="When the primary fee is due")
    
    # Refund information
    refundable: bool = Field(False, description="Whether the primary fee is refundable")
    refund_conditions: Optional[str] = Field(None, description="Conditions for refund")
    
    # Additional information
    special_circumstances: List[str] = Field(
        default_factory=list,
        description="Special circumstances that affect fees"
    )
    
    notes: Optional[str] = Field(None, description="Additional notes or clarifications")
    
    # Extraction metadata
    extraction_confidence: Optional[float] = Field(
        None, ge=0, le=1,
        description="Confidence score for the extraction (0-1)"
    )
    
    @field_validator("initial_franchise_fee_cents")
    @classmethod
    def validate_reasonable_fee(cls, v):
        """Validate that the fee is within reasonable bounds."""
        if v > 100_000_000:  # $1M max
            raise ValueError("Initial franchise fee exceeds reasonable maximum")
        return v
    
    @property
    def total_minimum_investment_cents(self) -> int:
        """Calculate minimum total initial investment."""
        total = self.initial_franchise_fee_cents
        for fee in self.additional_fees:
            total += fee.amount_cents
        return total
    
    def get_discounted_fee(self, discount_type: DiscountType) -> Optional[int]:
        """Calculate discounted fee for a specific discount type."""
        base_fee = self.initial_franchise_fee_cents
        
        for discount in self.discounts:
            if discount.discount_type == discount_type:
                if discount.amount_cents:
                    return max(0, base_fee - discount.amount_cents)
                elif discount.percentage:
                    return int(base_fee * (1 - discount.percentage / 100))
        
        return None