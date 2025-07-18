"""Item 5 - Initial Fees models using unified architecture."""

from pydantic import Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from .base_items import (
    BaseItemModel, BaseItemResponse, FeeBasedItem,
    FeeFrequency, DiscountType, ValidationStatus,
    ItemValidator
)
from .base import ValidationConfig


class InitialFeeDiscount(BaseItemModel):
    """Discount information for initial fees."""
    
    discount_type: DiscountType
    amount_cents: Optional[int] = Field(None, ge=0, description="Fixed discount amount in cents")
    percentage: Optional[float] = Field(None, ge=0, le=100, description="Percentage discount")
    description: str = Field(..., description="Description of the discount")
    conditions: Optional[str] = Field(None, description="Conditions that apply to the discount")
    
    @model_validator(mode="after")
    def validate_discount_amount(self):
        """Ensure either amount_cents or percentage is provided, not both."""
        if self.amount_cents is not None and self.percentage is not None:
            raise ValueError("Cannot specify both amount_cents and percentage")
        if self.amount_cents is None and self.percentage is None:
            raise ValueError("Must specify either amount_cents or percentage")
        return self


class AdditionalFee(FeeBasedItem):
    """Structure for additional initial fees beyond the primary franchise fee."""
    
    fee_name: str = Field(..., description="Name/description of the fee")
    due_at: Optional[FeeFrequency] = Field(None, description="When the fee is due")
    refundable: bool = Field(False, description="Whether the fee is refundable")
    refund_conditions: Optional[str] = Field(None, description="Conditions for refund if applicable")
    
    def to_storage_model(self) -> "Item5Fee":
        """Convert to storage model."""
        return Item5Fee(
            fee_name=self.fee_name,
            amount_cents=self.amount_cents,
            due_at=self.due_at,
            refundable=self.refundable,
            refund_conditions=self.refund_conditions,
            notes=self.notes,
            extraction_confidence=self.extraction_confidence
        )


class Item5Fee(BaseItemModel):
    """Database storage model for Item 5 fees."""
    
    # Primary fee information
    fee_name: str = Field(..., min_length=1, description="Name of the fee")
    amount_cents: int = Field(..., ge=0, description="Fee amount in cents")
    
    # Payment terms
    due_at: Optional[FeeFrequency] = Field(None, description="When the fee is due")
    refundable: bool = Field(False, description="Whether fee is refundable")
    refund_conditions: Optional[str] = Field(None, description="Conditions for refund")
    
    # Multi-unit information
    is_additional_unit_fee: bool = Field(False, description="If this is for additional units")
    additional_unit_discount_cents: Optional[int] = Field(None, ge=0)
    
    # Store as JSONB in database
    available_discounts: List[Dict[str, Any]] = Field(default_factory=list)
    
    @field_validator("amount_cents")
    @classmethod
    def validate_reasonable_amount(cls, v):
        """Ensure amount is reasonable (< $10M)."""
        if v > ValidationConfig.MAX_FEE_AMOUNT:
            raise ValueError(f"Amount exceeds reasonable maximum of ${ValidationConfig.MAX_FEE_AMOUNT / 100:,.2f}")
        return v


class Item5FeesResponse(FeeBasedItem):
    """LLM extraction response for Item 5 - Initial Fees."""
    
    # Primary franchise fee
    initial_franchise_fee_cents: int = Field(..., ge=0, description="Primary initial franchise fee in cents")
    
    # Additional fees
    additional_fees: List[AdditionalFee] = Field(
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
    due_at: FeeFrequency = Field(FeeFrequency.UPON_SIGNING, description="When the primary fee is due")
    
    # Refund information
    refundable: bool = Field(False, description="Whether the primary fee is refundable")
    refund_conditions: Optional[str] = Field(None, description="Conditions for refund")
    
    # Special circumstances
    special_circumstances: List[str] = Field(
        default_factory=list,
        description="Special circumstances that affect fees"
    )
    
    @field_validator("initial_franchise_fee_cents")
    @classmethod
    def validate_franchise_fee(cls, v):
        """Validate that the fee is within reasonable bounds."""
        if v > 100_000_000:  # $1M max
            raise ValueError("Initial franchise fee exceeds reasonable maximum of $1,000,000")
        return v
    
    @property
    def total_minimum_investment_cents(self) -> int:
        """Calculate minimum total initial investment."""
        total = self.initial_franchise_fee_cents
        for fee in self.additional_fees:
            if fee.amount_cents:
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
    
    def to_storage_model(self) -> Item5Fee:
        """Convert response to storage model for the primary fee."""
        # Create the primary fee record
        primary_fee = Item5Fee(
            fee_name="Initial Franchise Fee",
            amount_cents=self.initial_franchise_fee_cents,
            due_at=self.due_at,
            refundable=self.refundable,
            refund_conditions=self.refund_conditions,
            available_discounts=[d.to_database_dict() for d in self.discounts],
            notes=self.notes,
            extraction_confidence=self.extraction_confidence,
            raw_text=self.raw_text
        )
        
        # Set validation status based on confidence
        if self.extraction_confidence and self.extraction_confidence < 0.7:
            primary_fee.validation_status = ValidationStatus.NEEDS_REVIEW
        
        return primary_fee
    
    def to_storage_models(self) -> List[Item5Fee]:
        """Convert response to multiple storage models (primary + additional fees)."""
        models = []
        
        # Add primary fee
        models.append(self.to_storage_model())
        
        # Add additional fees
        for additional in self.additional_fees:
            fee_model = additional.to_storage_model()
            # Inherit some fields from parent
            fee_model.raw_text = self.raw_text
            fee_model.extraction_confidence = self.extraction_confidence
            models.append(fee_model)
        
        # Add additional unit fee if present
        if self.additional_unit_fee_cents:
            models.append(Item5Fee(
                fee_name="Additional Unit Fee",
                amount_cents=self.additional_unit_fee_cents,
                is_additional_unit_fee=True,
                due_at=self.due_at,
                refundable=self.refundable,
                refund_conditions=self.refund_conditions,
                notes="Fee for additional franchise units",
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text
            ))
        
        return models
    
    def validate_extraction(self) -> List[str]:
        """Validate the extracted fee data."""
        issues = super().validate_extraction()
        
        # Validate primary fee
        fee_issue = ItemValidator.validate_currency_amount(
            self.initial_franchise_fee_cents,
            "Initial franchise fee",
            min_value=0,
            max_value=100_000_000  # $1M
        )
        if fee_issue:
            issues.append(fee_issue)
        
        # Check for suspicious patterns
        if self.initial_franchise_fee_cents == 0 and not self.notes:
            issues.append("Zero franchise fee requires explanation in notes")
        
        # Validate discounts
        for i, discount in enumerate(self.discounts):
            if discount.percentage and discount.percentage > 50:
                issues.append(f"Discount {i+1} exceeds 50% - verify accuracy")
        
        # Check additional fees
        for i, fee in enumerate(self.additional_fees):
            if fee.amount_cents and fee.amount_cents > self.initial_franchise_fee_cents:
                issues.append(
                    f"Additional fee '{fee.fee_name}' exceeds primary franchise fee"
                )
        
        return issues