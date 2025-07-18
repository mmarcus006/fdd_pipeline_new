"""Base classes for all FDD item models - unified architecture."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Union, TypeVar, Generic
from datetime import datetime
from uuid import UUID
from enum import Enum
from abc import ABC, abstractmethod

from .base import ValidationConfig, cents_to_dollars, dollars_to_cents


# Common Enums used across multiple items
class FeeFrequency(str, Enum):
    """Common fee frequencies used across items."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    ONE_TIME = "one_time"
    AS_INCURRED = "as_incurred"
    UPON_SIGNING = "upon_signing"
    UPON_TRAINING = "upon_training"
    UPON_OPENING = "upon_opening"


class CalculationBasis(str, Enum):
    """How fees are calculated."""
    GROSS_SALES = "gross_sales"
    NET_SALES = "net_sales"
    FIXED = "fixed"
    PERCENTAGE = "percentage"
    VARIABLE = "variable"
    OTHER = "other"


class DiscountType(str, Enum):
    """Types of discounts available."""
    VETERAN = "veteran"
    MULTI_UNIT = "multi_unit"
    CONVERSION = "conversion"
    AREA_DEVELOPER = "area_developer"
    PROMOTIONAL = "promotional"
    OTHER = "other"


class ValidationStatus(str, Enum):
    """Status of data validation."""
    PENDING = "pending"
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"
    INVALID = "invalid"


# Base Classes
class BaseItemModel(BaseModel):
    """
    Base class for all FDD item models stored in the database.
    
    This class provides common fields and validation logic that apply
    to all FDD items. Subclasses should add item-specific fields.
    """
    
    # Database fields
    id: Optional[UUID] = None
    fdd_section_id: Optional[UUID] = None
    
    # Extraction metadata
    extracted_at: Optional[datetime] = None
    extraction_confidence: Optional[float] = Field(
        None, ge=0, le=1,
        description="Confidence score for the extraction (0-1)"
    )
    validation_status: Optional[ValidationStatus] = Field(
        default=ValidationStatus.PENDING,
        description="Current validation status"
    )
    
    # Raw data reference
    raw_text: Optional[str] = Field(
        None,
        description="Original text this data was extracted from"
    )
    
    # Common fields
    notes: Optional[str] = Field(
        None,
        description="Additional notes or clarifications"
    )
    
    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat(),
        }
    }
    
    @field_validator("extraction_confidence")
    @classmethod
    def validate_confidence(cls, v):
        """Ensure confidence is between 0 and 1."""
        if v is not None and not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v
    
    def to_database_dict(self) -> Dict[str, Any]:
        """
        Convert model to dictionary suitable for database storage.
        Handles serialization of UUIDs, datetimes, and enums.
        """
        data = self.model_dump(exclude_none=True)
        return self._serialize_for_db(data)
    
    def _serialize_for_db(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively serialize data for database storage."""
        serialized = {}
        for key, value in data.items():
            if isinstance(value, UUID):
                serialized[key] = str(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, Enum):
                serialized[key] = value.value
            elif isinstance(value, dict):
                serialized[key] = self._serialize_for_db(value)
            elif isinstance(value, list):
                serialized[key] = [
                    self._serialize_for_db(item) if isinstance(item, dict) else 
                    str(item) if isinstance(item, UUID) else
                    item.isoformat() if isinstance(item, datetime) else
                    item.value if isinstance(item, Enum) else
                    item
                    for item in value
                ]
            else:
                serialized[key] = value
        return serialized


class BaseItemResponse(BaseItemModel):
    """
    Base class for LLM extraction responses.
    
    This extends BaseItemModel with fields specific to the extraction
    process but not stored in the database. The response models are
    used during extraction and then converted to the storage models.
    """
    
    # Override to make these fields not required for extraction
    id: Optional[UUID] = None
    fdd_section_id: Optional[UUID] = None
    extracted_at: Optional[datetime] = None
    validation_status: Optional[ValidationStatus] = None
    
    # Additional extraction metadata
    extraction_warnings: List[str] = Field(
        default_factory=list,
        description="Warnings generated during extraction"
    )
    
    requires_manual_review: bool = Field(
        False,
        description="Flag indicating if manual review is needed"
    )
    
    @abstractmethod
    def to_storage_model(self) -> BaseItemModel:
        """
        Convert response model to storage model.
        Subclasses must implement this to return their specific storage model.
        """
        pass
    
    def validate_extraction(self) -> List[str]:
        """
        Validate the extracted data and return any issues.
        Subclasses should override to add specific validations.
        """
        issues = []
        
        # Check confidence if available
        if self.extraction_confidence is not None and self.extraction_confidence < 0.7:
            issues.append(f"Low extraction confidence: {self.extraction_confidence}")
        
        # Check for required fields based on the model
        for field_name, field_info in self.model_fields.items():
            value = getattr(self, field_name, None)
            if field_info.is_required() and value is None:
                issues.append(f"Missing required field: {field_name}")
        
        return issues


# Specialized base classes for common patterns
class FeeBasedItem(BaseItemResponse):
    """Base class for items that involve fees (Items 5, 6)."""
    
    amount_cents: Optional[int] = Field(None, ge=0, description="Fee amount in cents")
    amount_percentage: Optional[float] = Field(
        None, ge=0, le=100,
        description="Fee as percentage (if applicable)"
    )
    
    @model_validator(mode="after")
    def validate_amount_type(self):
        """Ensure either amount_cents OR amount_percentage is set for percentage-based fees."""
        # This validation only applies if the fee can be percentage-based
        # Subclasses can override if both are allowed
        return self
    
    @property
    def amount_dollars(self) -> Optional[float]:
        """Convert cents to dollars."""
        return cents_to_dollars(self.amount_cents)
    
    @field_validator("amount_cents")
    @classmethod
    def validate_reasonable_amount(cls, v):
        """Ensure amount is reasonable."""
        if v is not None and v > ValidationConfig.MAX_FEE_AMOUNT:
            raise ValueError(f"Amount exceeds reasonable maximum of ${ValidationConfig.MAX_FEE_AMOUNT / 100:,.2f}")
        return v


class InvestmentBasedItem(BaseItemResponse):
    """Base class for items that involve investment ranges (Item 7)."""
    
    low_cents: Optional[int] = Field(None, ge=0, description="Low end of range in cents")
    high_cents: Optional[int] = Field(None, ge=0, description="High end of range in cents")
    
    @model_validator(mode="after")
    def validate_range(self):
        """Ensure high >= low and at least one is set."""
        if self.low_cents is None and self.high_cents is None:
            raise ValueError("At least one of low_cents or high_cents must be set")
        
        if self.low_cents is not None and self.high_cents is not None:
            if self.high_cents < self.low_cents:
                raise ValueError("high_cents must be >= low_cents")
        
        return self
    
    @property
    def low_dollars(self) -> Optional[float]:
        """Convert low cents to dollars."""
        return cents_to_dollars(self.low_cents)
    
    @property
    def high_dollars(self) -> Optional[float]:
        """Convert high cents to dollars."""
        return cents_to_dollars(self.high_cents)
    
    @property
    def average_cents(self) -> Optional[int]:
        """Calculate average of range."""
        if self.low_cents is not None and self.high_cents is not None:
            return (self.low_cents + self.high_cents) // 2
        return self.low_cents or self.high_cents


class TableBasedItem(BaseItemResponse):
    """Base class for items that primarily contain tabular data (Items 19, 20, 21)."""
    
    tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted tables with headers and data"
    )
    
    summary: Optional[str] = Field(
        None,
        description="Summary of the data presented"
    )
    
    def get_table_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a table by its name."""
        for table in self.tables:
            if table.get("name") == name or table.get("table_name") == name:
                return table
        return None
    
    def validate_tables(self) -> List[str]:
        """Validate table structure."""
        issues = []
        
        for i, table in enumerate(self.tables):
            if not table.get("headers"):
                issues.append(f"Table {i} missing headers")
            if not table.get("rows"):
                issues.append(f"Table {i} has no data rows")
            
            # Validate row consistency
            if table.get("headers") and table.get("rows"):
                header_count = len(table["headers"])
                for j, row in enumerate(table["rows"]):
                    if len(row) != header_count:
                        issues.append(
                            f"Table {i} row {j} has {len(row)} columns, "
                            f"expected {header_count}"
                        )
        
        return issues


# Type variable for generic response models
T = TypeVar("T", bound=BaseItemModel)


class ItemCollection(BaseModel, Generic[T]):
    """Generic collection for multiple items of the same type."""
    
    items: List[T] = Field(default_factory=list)
    total_count: int = Field(0)
    
    def add_item(self, item: T) -> None:
        """Add an item to the collection."""
        self.items.append(item)
        self.total_count = len(self.items)
    
    def get_by_id(self, item_id: UUID) -> Optional[T]:
        """Find an item by ID."""
        for item in self.items:
            if hasattr(item, 'id') and item.id == item_id:
                return item
        return None
    
    def to_database_list(self) -> List[Dict[str, Any]]:
        """Convert all items to database-ready dictionaries."""
        return [item.to_database_dict() for item in self.items]


# Validation utilities
class ItemValidator:
    """Utilities for validating FDD item data."""
    
    @staticmethod
    def validate_percentage(value: float, field_name: str, max_value: float = 100.0) -> Optional[str]:
        """Validate percentage values."""
        if value < 0:
            return f"{field_name} cannot be negative"
        if value > max_value:
            return f"{field_name} exceeds maximum of {max_value}%"
        return None
    
    @staticmethod
    def validate_currency_amount(
        amount: int, 
        field_name: str,
        min_value: int = 0,
        max_value: Optional[int] = None
    ) -> Optional[str]:
        """Validate currency amounts in cents."""
        if amount < min_value:
            return f"{field_name} cannot be less than ${min_value/100:,.2f}"
        if max_value and amount > max_value:
            return f"{field_name} exceeds maximum of ${max_value/100:,.2f}"
        return None
    
    @staticmethod
    def validate_date_range(
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> Optional[str]:
        """Validate date ranges."""
        if start_date and end_date and start_date > end_date:
            return "Start date must be before end date"
        return None