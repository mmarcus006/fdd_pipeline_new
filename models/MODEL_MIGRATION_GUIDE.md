# FDD Model Migration Guide

This guide explains how to create new FDD item models using the unified architecture established in `base_items.py`.

## Overview

The unified model architecture eliminates the duplicate model/response pattern by providing base classes that handle common functionality. All FDD item models should inherit from these base classes.

## Architecture

### Base Classes

1. **`BaseItemModel`** - For database storage models
   - Contains common fields: id, fdd_section_id, timestamps, validation status
   - Provides `to_database_dict()` method for serialization
   - Handles UUID and datetime serialization automatically

2. **`BaseItemResponse`** - For LLM extraction responses
   - Extends BaseItemModel with extraction-specific fields
   - Requires implementation of `to_storage_model()` method
   - Includes `validate_extraction()` method

3. **Specialized Base Classes**:
   - `FeeBasedItem` - For fee-related items (Items 5, 6)
   - `InvestmentBasedItem` - For investment ranges (Item 7)
   - `TableBasedItem` - For table-heavy items (Items 19, 20, 21)

## Creating a New FDD Item Model

### Step 1: Create a Single Model File

Create `models/itemXX_description.py` (no separate response file needed):

```python
"""Item XX - Description models using unified architecture."""

from pydantic import Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum

from .base_items import (
    BaseItemModel, BaseItemResponse, 
    # Choose appropriate base class:
    FeeBasedItem,  # For fee-related items
    InvestmentBasedItem,  # For investment items
    TableBasedItem,  # For table-heavy items
    ValidationStatus, ItemValidator
)
```

### Step 2: Define Storage Models

Storage models inherit from `BaseItemModel`:

```python
class ItemXXData(BaseItemModel):
    """Database storage model for Item XX."""
    
    # Item-specific fields
    field_name: str = Field(..., description="Description")
    amount_cents: Optional[int] = Field(None, ge=0)
    
    # Add validators as needed
    @field_validator("field_name")
    @classmethod
    def validate_field(cls, v):
        # Custom validation logic
        return v
    
    # Add properties for calculations
    @property
    def amount_dollars(self) -> Optional[float]:
        return self.amount_cents / 100 if self.amount_cents else None
```

### Step 3: Define Response Model

Response models inherit from appropriate base class:

```python
class ItemXXResponse(BaseItemResponse):  # or FeeBasedItem, TableBasedItem, etc.
    """LLM extraction response for Item XX."""
    
    # Fields that LLM will extract
    extracted_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted data from the document"
    )
    
    # Required: Implement to_storage_model
    def to_storage_model(self) -> Union[ItemXXData, List[ItemXXData]]:
        """Convert response to storage model(s)."""
        # Single model
        return ItemXXData(
            field_name=self.extracted_data.get("name"),
            amount_cents=self._parse_amount(self.extracted_data.get("amount")),
            extraction_confidence=self.extraction_confidence,
            raw_text=self.raw_text
        )
        
        # Or multiple models
        models = []
        for data in self.extracted_data:
            model = ItemXXData(...)
            models.append(model)
        return models
    
    # Override validation if needed
    def validate_extraction(self) -> List[str]:
        """Validate the extracted data."""
        issues = super().validate_extraction()
        
        # Add custom validation
        if not self.extracted_data:
            issues.append("No data extracted")
        
        return issues
```

### Step 4: Export from Package

Add to `models/__init__.py`:

```python
from .itemXX_description import ItemXXData, ItemXXResponse
```

## Migration Examples

### Fee-Based Item (like Item 5)

```python
class AdditionalFee(FeeBasedItem):
    """Additional fee structure."""
    fee_name: str = Field(...)
    due_date: Optional[datetime] = None
    
    def to_storage_model(self) -> "ItemXXFee":
        return ItemXXFee(
            name=self.fee_name,
            amount_cents=self.amount_cents,
            due_date=self.due_date
        )

class ItemXXFeesResponse(FeeBasedItem):
    """Response for fee extraction."""
    primary_fee_cents: int = Field(..., ge=0)
    additional_fees: List[AdditionalFee] = Field(default_factory=list)
    
    def to_storage_model(self) -> List[ItemXXFee]:
        models = [ItemXXFee(
            name="Primary Fee",
            amount_cents=self.primary_fee_cents
        )]
        
        for fee in self.additional_fees:
            models.append(fee.to_storage_model())
        
        return models
```

### Table-Based Item (like Item 20)

```python
class ItemXXTableResponse(TableBasedItem):
    """Response for table-heavy items."""
    
    data_by_year: List[Dict[str, Any]] = Field(default_factory=list)
    
    def to_storage_model(self) -> List[ItemXXData]:
        models = []
        
        # Extract from tables
        for table in self.tables:
            # Process table data
            data = self._extract_from_table(table)
            models.append(ItemXXData(**data))
        
        # Extract from structured data
        for yearly_data in self.data_by_year:
            models.append(ItemXXData(**yearly_data))
        
        return models
```

## Best Practices

1. **Single File Per Item**: Keep both storage and response models in one file
2. **Inherit Properly**: Use the most specific base class available
3. **Implement Required Methods**: Always implement `to_storage_model()`
4. **Validate Data**: Override `validate_extraction()` for custom validation
5. **Use Properties**: Add calculated properties for derived values
6. **Type Everything**: Use proper type hints throughout
7. **Document Fields**: Use Field descriptions for clarity

## Common Patterns

### Amount Parsing

```python
def _parse_amount(self, value: Any) -> Optional[int]:
    """Parse various formats to cents."""
    if isinstance(value, (int, float)):
        return int(value * 100)
    # Handle string formats...
```

### Enum Parsing

```python
def _parse_enum(self, value: str, enum_class: Type[Enum]) -> Optional[Enum]:
    """Parse string to enum safely."""
    try:
        return enum_class(value.lower().replace(" ", "_"))
    except (ValueError, AttributeError):
        return None
```

### Multi-Model Response

```python
def to_storage_model(self) -> List[BaseItemModel]:
    """Return multiple models from one response."""
    models = []
    
    # Different types of models
    models.extend(self._create_summary_models())
    models.extend(self._create_detail_models())
    models.extend(self._create_table_models())
    
    return models
```

## Testing

When creating tests for new models:

```python
def test_itemXX_response_to_storage():
    """Test response model conversion."""
    response = ItemXXResponse(
        extracted_data={"field": "value"},
        extraction_confidence=0.95
    )
    
    storage = response.to_storage_model()
    assert isinstance(storage, ItemXXData)
    assert storage.field_name == "value"

def test_itemXX_validation():
    """Test validation logic."""
    response = ItemXXResponse(extracted_data={})
    issues = response.validate_extraction()
    assert "No data extracted" in issues
```

## Checklist for New Models

- [ ] Created single file `models/itemXX_description.py`
- [ ] Storage model inherits from `BaseItemModel`
- [ ] Response model inherits from appropriate base class
- [ ] Implemented `to_storage_model()` method
- [ ] Added custom validators as needed
- [ ] Added to `models/__init__.py`
- [ ] Created tests for model conversion
- [ ] Documented all fields with descriptions
- [ ] No separate `_response.py` file created