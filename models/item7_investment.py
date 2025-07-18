"""Item 7 - Initial Investment models using unified architecture."""

from pydantic import Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, ClassVar
from uuid import UUID

from .base_items import (
    BaseItemModel,
    BaseItemResponse,
    InvestmentBasedItem,
    ValidationStatus,
    ItemValidator,
    ItemCollection,
)
from .base import ValidationConfig


class InvestmentCategory(BaseItemModel):
    """Standardized investment categories."""

    STANDARD_CATEGORIES: ClassVar[Dict[str, str]] = {
        "REAL ESTATE": "Real Estate",
        "EQUIPMENT": "Equipment",
        "SIGNAGE": "Signage",
        "INVENTORY": "Inventory",
        "WORKING CAPITAL": "Working Capital",
        "TRAINING": "Training",
        "FRANCHISE FEE": "Initial Franchise Fee",
        "INSURANCE": "Insurance",
        "LICENSES": "Licenses and Permits",
        "PROFESSIONAL FEES": "Professional Fees",
        "MARKETING": "Grand Opening Marketing",
        "CONSTRUCTION": "Construction/Build-out",
        "FIXTURES": "Fixtures and Furniture",
        "POS": "Point of Sale System",
        "TECHNOLOGY": "Technology/Software",
        "DEPOSITS": "Security Deposits",
        "OTHER": "Other Costs",
    }

    @classmethod
    def standardize(cls, category: str) -> str:
        """Standardize category names."""
        upper = category.upper()

        # Direct match
        if upper in cls.STANDARD_CATEGORIES:
            return cls.STANDARD_CATEGORIES[upper]

        # Partial matches
        for key, value in cls.STANDARD_CATEGORIES.items():
            if key in upper or upper in key:
                return value

        # Common variations
        if any(word in upper for word in ["LEASE", "RENT", "PROPERTY"]):
            return cls.STANDARD_CATEGORIES["REAL ESTATE"]
        if any(word in upper for word in ["COMPUTER", "SOFTWARE", "IT"]):
            return cls.STANDARD_CATEGORIES["TECHNOLOGY"]
        if any(word in upper for word in ["FURNITURE", "FIXTURE", "FURNISHING"]):
            return cls.STANDARD_CATEGORIES["FIXTURES"]

        return category  # Return original if no match


class Item7Investment(InvestmentBasedItem):
    """Database storage model for Item 7 investment items."""

    # Category and description
    category: str = Field(..., min_length=1, description="Investment category")
    standardized_category: Optional[str] = Field(
        None, description="Standardized category name"
    )
    description: Optional[str] = Field(None, description="Detailed description")

    # Payment details
    when_due: Optional[str] = Field(None, description="When payment is due")
    to_whom_paid: Optional[str] = Field(None, description="Who receives payment")
    payment_method: Optional[str] = Field(None, description="Method of payment")

    # Conditions
    conditions: Optional[str] = Field(None, description="Special conditions or notes")
    is_refundable: Optional[bool] = Field(
        None, description="If investment is refundable"
    )

    @field_validator("category")
    @classmethod
    def standardize_category(cls, v):
        """Auto-standardize category on creation."""
        return InvestmentCategory.standardize(v)

    @model_validator(mode="after")
    def set_standardized_category(self):
        """Set standardized category."""
        if not self.standardized_category and self.category:
            self.standardized_category = InvestmentCategory.standardize(self.category)
        return self

    @property
    def average_investment_cents(self) -> Optional[int]:
        """Calculate average investment amount."""
        return self.average_cents


class InvestmentItem(InvestmentBasedItem):
    """Individual investment item in extraction response."""

    category: str = Field(..., description="Category of investment")
    description: Optional[str] = Field(None, description="Additional description")
    when_due: Optional[str] = Field(None, description="When payment is due")
    to_whom_paid: Optional[str] = Field(None, description="Recipient of payment")
    payment_method: Optional[str] = Field(None, description="How payment is made")
    conditions: Optional[str] = Field(None, description="Special conditions")

    def to_storage_model(self) -> Item7Investment:
        """Convert to storage model."""
        return Item7Investment(
            category=self.category,
            low_cents=self.low_cents,
            high_cents=self.high_cents,
            description=self.description,
            when_due=self.when_due,
            to_whom_paid=self.to_whom_paid,
            payment_method=self.payment_method,
            conditions=self.conditions,
            notes=self.notes,
            extraction_confidence=self.extraction_confidence,
        )


class Item7InvestmentResponse(BaseItemResponse):
    """LLM extraction response for Item 7 - Initial Investment."""

    # Investment items
    investment_items: List[InvestmentItem] = Field(
        default_factory=list,
        description="List of all investment categories and amounts",
    )

    # Summary totals
    total_investment_low_cents: Optional[int] = Field(
        None, ge=0, description="Total minimum investment"
    )
    total_investment_high_cents: Optional[int] = Field(
        None, ge=0, description="Total maximum investment"
    )

    # Additional information
    financing_available: Optional[bool] = Field(
        None, description="Whether franchisor offers financing"
    )
    financing_details: Optional[str] = Field(
        None, description="Details about available financing"
    )

    # Special notes
    includes_working_capital: bool = Field(
        True, description="Whether totals include working capital"
    )
    real_estate_included: bool = Field(
        False, description="Whether real estate purchase is included"
    )

    @model_validator(mode="after")
    def calculate_totals(self):
        """Calculate total investment if not provided."""
        if not self.investment_items:
            return self

        # Calculate totals if not set
        if self.total_investment_low_cents is None:
            total_low = sum(
                item.low_cents
                for item in self.investment_items
                if item.low_cents is not None
            )
            if total_low > 0:
                self.total_investment_low_cents = total_low

        if self.total_investment_high_cents is None:
            total_high = sum(
                item.high_cents
                for item in self.investment_items
                if item.high_cents is not None
            )
            if total_high > 0:
                self.total_investment_high_cents = total_high

        return self

    @model_validator(mode="after")
    def validate_totals_match(self):
        """Validate that totals match sum of items."""
        if not self.investment_items:
            return self

        # Calculate actual sums
        actual_low = sum(item.low_cents or 0 for item in self.investment_items)
        actual_high = sum(item.high_cents or 0 for item in self.investment_items)

        # Allow some tolerance for rounding
        tolerance = 100  # $1 tolerance

        if self.total_investment_low_cents:
            if abs(self.total_investment_low_cents - actual_low) > tolerance:
                self.extraction_warnings.append(
                    f"Total low ({self.total_investment_low_cents}) doesn't match "
                    f"sum of items ({actual_low})"
                )

        if self.total_investment_high_cents:
            if abs(self.total_investment_high_cents - actual_high) > tolerance:
                self.extraction_warnings.append(
                    f"Total high ({self.total_investment_high_cents}) doesn't match "
                    f"sum of items ({actual_high})"
                )

        return self

    def get_items_by_category(self, category: str) -> List[InvestmentItem]:
        """Get all items matching a category."""
        standardized = InvestmentCategory.standardize(category)
        return [
            item
            for item in self.investment_items
            if InvestmentCategory.standardize(item.category) == standardized
        ]

    def to_storage_model(self) -> Item7Investment:
        """Convert to storage model - returns first/primary item."""
        if not self.investment_items:
            raise ValueError("No investment items to convert")

        # Find franchise fee item or use first item
        franchise_fee_item = None
        for item in self.investment_items:
            if "franchise fee" in item.category.lower():
                franchise_fee_item = item
                break

        item_to_convert = franchise_fee_item or self.investment_items[0]
        return item_to_convert.to_storage_model()

    def to_storage_models(self) -> List[Item7Investment]:
        """Convert all items to storage models."""
        models = []

        for item in self.investment_items:
            model = item.to_storage_model()
            model.raw_text = self.raw_text
            if not model.extraction_confidence:
                model.extraction_confidence = self.extraction_confidence
            models.append(model)

        return models

    def to_investment_summary(self) -> "InvestmentSummary":
        """Create a summary object."""
        return InvestmentSummary(
            total_items=len(self.investment_items),
            total_low_cents=self.total_investment_low_cents or 0,
            total_high_cents=self.total_investment_high_cents or 0,
            items=self.to_storage_models(),
            includes_working_capital=self.includes_working_capital,
            real_estate_included=self.real_estate_included,
            financing_available=self.financing_available,
            financing_details=self.financing_details,
        )

    def validate_extraction(self) -> List[str]:
        """Validate the extracted investment data."""
        issues = super().validate_extraction()

        # Check for required categories
        categories = [
            InvestmentCategory.standardize(item.category)
            for item in self.investment_items
        ]
        required = ["Initial Franchise Fee", "Working Capital"]

        for req in required:
            if req not in categories:
                issues.append(f"Missing common investment category: {req}")

        # Validate individual items
        for i, item in enumerate(self.investment_items):
            # Check ranges
            if item.low_cents and item.high_cents:
                if item.high_cents < item.low_cents:
                    issues.append(
                        f"Item '{item.category}' has invalid range: "
                        f"high ({item.high_cents}) < low ({item.low_cents})"
                    )

            # Check for extreme values
            if (
                item.high_cents
                and item.high_cents > ValidationConfig.MAX_INVESTMENT_AMOUNT
            ):
                issues.append(
                    f"Item '{item.category}' exceeds maximum reasonable "
                    f"investment of ${ValidationConfig.MAX_INVESTMENT_AMOUNT / 100:,.2f}"
                )

        # Validate totals
        if self.total_investment_low_cents and self.total_investment_high_cents:
            if self.total_investment_high_cents < self.total_investment_low_cents:
                issues.append("Total investment high is less than low")

        return issues


class InvestmentSummary(BaseItemModel):
    """Summary of initial investment with computed totals."""

    total_items: int = Field(..., ge=0)
    total_low_cents: int = Field(..., ge=0)
    total_high_cents: int = Field(..., ge=0)
    items: List[Item7Investment] = Field(default_factory=list)

    # Additional context
    includes_working_capital: bool = True
    real_estate_included: bool = False
    financing_available: Optional[bool] = None
    financing_details: Optional[str] = None

    @field_validator("total_low_cents", "total_high_cents")
    @classmethod
    def validate_totals(cls, v):
        """Ensure totals are reasonable."""
        if v > ValidationConfig.MAX_INVESTMENT_AMOUNT:
            raise ValueError(
                f"Total exceeds reasonable maximum of ${ValidationConfig.MAX_INVESTMENT_AMOUNT / 100:,.2f}"
            )
        return v

    def get_category_breakdown(self) -> Dict[str, Dict[str, int]]:
        """Get investment breakdown by category."""
        breakdown = {}

        for item in self.items:
            category = item.standardized_category or item.category
            if category not in breakdown:
                breakdown[category] = {"low": 0, "high": 0, "count": 0}

            breakdown[category]["count"] += 1
            if item.low_cents:
                breakdown[category]["low"] += item.low_cents
            if item.high_cents:
                breakdown[category]["high"] += item.high_cents

        return breakdown
