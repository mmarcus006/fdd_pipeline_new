"""Item 6 - Other Fees and Costs models using unified architecture."""

from pydantic import Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from uuid import UUID

from .base_items import (
    BaseItemModel,
    BaseItemResponse,
    FeeBasedItem,
    FeeFrequency,
    CalculationBasis,
    ValidationStatus,
    ItemValidator,
)
from .base import ValidationConfig


class Item6OtherFee(BaseItemModel):
    """Database storage model for Item 6 other fees."""

    # Fee identification
    fee_name: str = Field(..., min_length=1, description="Name/type of fee")
    fee_category: Optional[str] = Field(
        None, description="Category of fee (e.g., Royalty, Marketing)"
    )

    # Amount (either fixed or percentage)
    amount_cents: Optional[int] = Field(
        None, ge=0, description="Fixed fee amount in cents"
    )
    amount_percentage: Optional[float] = Field(
        None, ge=0, le=100, description="Fee as percentage"
    )

    # Calculation details
    frequency: FeeFrequency = Field(..., description="How often fee is charged")
    calculation_basis: Optional[CalculationBasis] = Field(
        None, description="Basis for percentage fees"
    )

    # Ranges
    minimum_cents: Optional[int] = Field(None, ge=0, description="Minimum fee amount")
    maximum_cents: Optional[int] = Field(None, ge=0, description="Maximum fee amount")

    # Additional details
    when_due: Optional[str] = Field(None, description="Specific timing of payment")
    to_whom_paid: Optional[str] = Field(None, description="Recipient of payment")
    conditions: Optional[str] = Field(None, description="Conditions that apply")

    @model_validator(mode="after")
    def validate_amount_type(self):
        """Ensure either amount_cents OR amount_percentage is set."""
        if (self.amount_cents is None and self.amount_percentage is None) or (
            self.amount_cents is not None and self.amount_percentage is not None
        ):
            raise ValueError(
                "Must specify either amount_cents or amount_percentage, not both"
            )
        return self

    @model_validator(mode="after")
    def validate_min_max(self):
        """Ensure max >= min if both specified."""
        if self.minimum_cents is not None and self.maximum_cents is not None:
            if self.maximum_cents < self.minimum_cents:
                raise ValueError("maximum_cents must be >= minimum_cents")
        return self

    @field_validator("amount_percentage")
    @classmethod
    def validate_percentage(cls, v):
        """Validate percentage is reasonable."""
        if v is not None and v > ValidationConfig.MAX_ROYALTY_PERCENTAGE:
            # Flag but don't reject - some fees can be high
            pass
        return v


class OtherFeeStructure(FeeBasedItem):
    """Structure for a single ongoing/other fee in extraction response."""

    fee_name: str = Field(..., description="Name/description of the fee")
    fee_category: Optional[str] = Field(
        None, description="Category (Royalty, Marketing, etc.)"
    )

    frequency: FeeFrequency = Field(..., description="Payment frequency")
    calculation_basis: Optional[CalculationBasis] = Field(
        None, description="How fee is calculated"
    )

    minimum_cents: Optional[int] = Field(
        None, ge=0, description="Minimum fee if applicable"
    )
    maximum_cents: Optional[int] = Field(
        None, ge=0, description="Maximum fee if applicable"
    )

    when_due: Optional[str] = Field(None, description="When payment is due")
    to_whom_paid: Optional[str] = Field(None, description="Who receives payment")
    conditions: Optional[str] = Field(None, description="Special conditions")

    def to_storage_model(self) -> Item6OtherFee:
        """Convert to storage model."""
        return Item6OtherFee(
            fee_name=self.fee_name,
            fee_category=self.fee_category,
            amount_cents=self.amount_cents,
            amount_percentage=self.amount_percentage,
            frequency=self.frequency,
            calculation_basis=self.calculation_basis,
            minimum_cents=self.minimum_cents,
            maximum_cents=self.maximum_cents,
            when_due=self.when_due,
            to_whom_paid=self.to_whom_paid,
            conditions=self.conditions,
            notes=self.notes,
            extraction_confidence=self.extraction_confidence,
        )


class Item6OtherFeesResponse(BaseItemResponse):
    """LLM extraction response for Item 6 - Other Fees and Costs."""

    # Royalty fees (most common)
    royalty_percentage: Optional[float] = Field(
        None, ge=0, le=100, description="Ongoing royalty fee percentage"
    )
    royalty_frequency: FeeFrequency = Field(
        FeeFrequency.MONTHLY, description="How often royalty is paid"
    )
    royalty_basis: CalculationBasis = Field(
        CalculationBasis.GROSS_SALES, description="Basis for royalty calculation"
    )

    # Marketing/advertising fees
    marketing_fee_percentage: Optional[float] = Field(
        None, ge=0, le=100, description="Marketing/advertising fee percentage"
    )
    marketing_fee_cents: Optional[int] = Field(
        None, ge=0, description="Fixed marketing fee if not percentage"
    )
    marketing_frequency: FeeFrequency = Field(
        FeeFrequency.MONTHLY, description="Marketing fee frequency"
    )

    # All other fees
    other_fees: List[OtherFeeStructure] = Field(
        default_factory=list, description="List of all other ongoing fees"
    )

    # Summary information
    total_fee_types: Optional[int] = Field(
        None, description="Total number of different fee types"
    )
    estimated_monthly_total_cents: Optional[int] = Field(
        None, ge=0, description="Estimated total monthly fees (if calculable)"
    )

    @model_validator(mode="after")
    def calculate_totals(self):
        """Calculate summary totals."""
        if self.total_fee_types is None:
            count = len(self.other_fees)
            if self.royalty_percentage is not None:
                count += 1
            if (
                self.marketing_fee_percentage is not None
                or self.marketing_fee_cents is not None
            ):
                count += 1
            self.total_fee_types = count
        return self

    def to_storage_model(self) -> Item6OtherFee:
        """Convert to storage model - returns primary royalty fee."""
        if self.royalty_percentage is not None:
            return Item6OtherFee(
                fee_name="Royalty Fee",
                fee_category="Royalty",
                amount_percentage=self.royalty_percentage,
                frequency=self.royalty_frequency,
                calculation_basis=self.royalty_basis,
                notes=self.notes,
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text,
            )
        elif self.other_fees:
            # Return first fee if no royalty
            return self.other_fees[0].to_storage_model()
        else:
            raise ValueError("No fees found to convert")

    def to_storage_models(self) -> List[Item6OtherFee]:
        """Convert response to multiple storage models."""
        models = []

        # Add royalty fee
        if self.royalty_percentage is not None:
            models.append(
                Item6OtherFee(
                    fee_name="Royalty Fee",
                    fee_category="Royalty",
                    amount_percentage=self.royalty_percentage,
                    frequency=self.royalty_frequency,
                    calculation_basis=self.royalty_basis,
                    notes=self.notes,
                    extraction_confidence=self.extraction_confidence,
                    raw_text=self.raw_text,
                )
            )

        # Add marketing fee
        if (
            self.marketing_fee_percentage is not None
            or self.marketing_fee_cents is not None
        ):
            marketing_fee = Item6OtherFee(
                fee_name="Marketing/Advertising Fee",
                fee_category="Marketing",
                frequency=self.marketing_frequency,
                notes=self.notes,
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text,
            )
            if self.marketing_fee_percentage is not None:
                marketing_fee.amount_percentage = self.marketing_fee_percentage
                marketing_fee.calculation_basis = CalculationBasis.GROSS_SALES
            else:
                marketing_fee.amount_cents = self.marketing_fee_cents
            models.append(marketing_fee)

        # Add all other fees
        for fee in self.other_fees:
            fee_model = fee.to_storage_model()
            fee_model.raw_text = self.raw_text
            if not fee_model.extraction_confidence:
                fee_model.extraction_confidence = self.extraction_confidence
            models.append(fee_model)

        return models

    def validate_extraction(self) -> List[str]:
        """Validate the extracted fee data."""
        issues = super().validate_extraction()

        # Validate royalty
        if self.royalty_percentage is not None:
            royalty_issue = ItemValidator.validate_percentage(
                self.royalty_percentage,
                "Royalty percentage",
                max_value=ValidationConfig.MAX_ROYALTY_PERCENTAGE,
            )
            if royalty_issue:
                issues.append(royalty_issue)

        # Validate marketing fee
        if self.marketing_fee_percentage is not None:
            marketing_issue = ItemValidator.validate_percentage(
                self.marketing_fee_percentage,
                "Marketing fee percentage",
                max_value=ValidationConfig.MAX_MARKETING_PERCENTAGE,
            )
            if marketing_issue:
                issues.append(marketing_issue)

        # Check for missing common fees
        fee_names = [f.fee_name.lower() for f in self.other_fees]
        if self.royalty_percentage is None and not any(
            "royalty" in name for name in fee_names
        ):
            issues.append("No royalty fee found - verify if this is correct")

        # Validate other fees
        for i, fee in enumerate(self.other_fees):
            if fee.amount_percentage and fee.amount_percentage > 20:
                issues.append(
                    f"Fee '{fee.fee_name}' has unusually high percentage: {fee.amount_percentage}%"
                )

        return issues
