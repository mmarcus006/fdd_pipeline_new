"""Enhanced unit tests for schema validation layer."""

import pytest
import asyncio
from datetime import datetime, date
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# Mock the database manager to avoid import issues
class MockDatabaseManager:
    """Mock database manager for testing."""
    
    def __init__(self):
        self.execute_calls = []
        self.fetch_one_calls = []
        self.fetch_all_calls = []
    
    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return None
    
    async def fetch_one(self, query, *args):
        self.fetch_one_calls.append((query, args))
        return None
    
    async def fetch_all(self, query, *args):
        self.fetch_all_calls.append((query, args))
        return []

# Mock the logger
class MockLogger:
    def __init__(self):
        self.logs = []
    
    def info(self, msg, extra=None):
        self.logs.append(('info', msg, extra))
    
    def error(self, msg, extra=None):
        self.logs.append(('error', msg, extra))
    
    def warning(self, msg, extra=None):
        self.logs.append(('warning', msg, extra))

# Create mock instances
mock_db = MockDatabaseManager()
mock_logger = MockLogger()

# Mock the imports to avoid dependency issues
import sys
from unittest.mock import MagicMock

# Mock the modules
sys.modules['utils.database'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['utils.database'].DatabaseManager = MockDatabaseManager
sys.modules['utils.logging'].get_logger = lambda name: mock_logger

# Now import our validation classes
from tasks.schema_validation import (
    ValidationSeverity, ValidationCategory, ValidationError, ValidationResult,
    ValidationBypass, SchemaValidator, ValidationReportGenerator
)

# Import models for testing
from models.item5_fees import InitialFee
from models.item6_other_fees import OtherFee
from models.item7_investment import InitialInvestment
from models.item20_outlets import OutletSummary
from models.item21_financials import Financials
from models.base import ValidationConfig


class TestValidationEnhancements:
    """Test enhanced validation functionality."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager for testing."""
        return MockDatabaseManager()
    
    @pytest.fixture
    def sample_initial_fee_data(self):
        """Sample data for initial fee validation."""
        return {
            "fee_name": "Initial Franchise Fee",
            "amount_cents": 5000000,  # $50,000
            "refundable": True,
            "refund_conditions": "Refundable within 30 days",
            "due_at": "Signing",
            "section_id": uuid4()
        }
    
    @pytest.fixture
    def sample_other_fee_data(self):
        """Sample data for other fee validation."""
        return {
            "fee_name": "Royalty Fee",
            "amount_percentage": 6.0,
            "frequency": "Monthly",
            "calculation_basis": "Gross Sales",
            "section_id": uuid4()
        }
    
    @pytest.fixture
    def sample_outlet_data(self):
        """Sample data for outlet summary validation."""
        return {
            "fiscal_year": 2023,
            "outlet_type": "Franchised",
            "count_start": 100,
            "opened": 15,
            "closed": 5,
            "transferred_in": 2,
            "transferred_out": 3,
            "count_end": 109,
            "section_id": uuid4()
        }
    
    @pytest.mark.asyncio
    async def test_enhanced_initial_fee_validation(self, mock_db_manager, sample_initial_fee_data):
        """Test enhanced initial fee validation with business rules."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test valid fee
        result = await validator.validate_model(sample_initial_fee_data, InitialFee)
        assert result.is_valid
        assert len(result.errors) == 0
        
        # Test fee without refund conditions when refundable
        data = sample_initial_fee_data.copy()
        data["refund_conditions"] = None
        
        result = await validator.validate_model(data, InitialFee)
        assert result.is_valid  # Should still be valid
        assert len(result.warnings) > 0  # But should have warning
        assert any("refund_conditions" in w.field_name for w in result.warnings)
    
    @pytest.mark.asyncio
    async def test_enhanced_other_fee_validation(self, mock_db_manager, sample_other_fee_data):
        """Test enhanced other fee validation."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test valid percentage-based fee
        result = await validator.validate_model(sample_other_fee_data, OtherFee)
        assert result.is_valid
        
        # Test percentage fee without calculation basis
        data = sample_other_fee_data.copy()
        data["calculation_basis"] = None
        
        result = await validator.validate_model(data, OtherFee)
        assert not result.is_valid
        assert any("calculation_basis" in e.field_name for e in result.errors)
        
        # Test unusually high royalty percentage
        data = sample_other_fee_data.copy()
        data["amount_percentage"] = 60.0  # Above threshold
        
        result = await validator.validate_model(data, OtherFee)
        assert result.is_valid  # Still valid
        assert len(result.warnings) > 0  # But should have warning
    
    @pytest.mark.asyncio
    async def test_batch_validation(self, mock_db_manager):
        """Test batch validation functionality."""
        validator = SchemaValidator(mock_db_manager)
        
        # Create batch data
        batch_data = [
            {
                "fee_name": "Fee 1",
                "amount_cents": 1000000,
                "refundable": False,
                "section_id": uuid4()
            },
            {
                "fee_name": "Fee 2", 
                "amount_cents": 2000000,
                "refundable": True,
                "refund_conditions": "30 days",
                "section_id": uuid4()
            }
        ]
        
        model_classes = [InitialFee, InitialFee]
        
        results = await validator.validate_batch(batch_data, model_classes, max_concurrent=2)
        
        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)
        assert all(r.is_valid for r in results)
    
    @pytest.mark.asyncio
    async def test_cross_field_validation(self, mock_db_manager):
        """Test cross-field validation functionality."""
        validator = SchemaValidator(mock_db_manager)
        fdd_id = uuid4()
        
        # Test data with inconsistent franchise fees
        extracted_data = {
            "item5_fees": [
                {"fee_name": "Initial Franchise Fee", "amount_cents": 5000000}
            ],
            "item7_investment": [
                {"category": "Initial Franchise Fee", "low_cents": 6000000, "high_cents": 8000000}
            ]
        }
        
        errors = await validator.validate_cross_field_consistency(fdd_id, extracted_data)
        
        assert len(errors) > 0
        assert any("franchise_fee_consistency" in e.field_name for e in errors)
        assert any(e.severity == ValidationSeverity.WARNING for e in errors)
    
    @pytest.mark.asyncio
    async def test_data_completeness_validation(self, mock_db_manager):
        """Test data completeness validation."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test with minimal data (low completeness)
        minimal_data = {
            "fee_name": "Test Fee",
            "amount_cents": 1000000,
            "section_id": uuid4()
        }
        
        errors = await validator.validate_data_completeness(minimal_data, InitialFee)
        
        # Should have completeness warning
        assert len(errors) > 0
        assert any("data_completeness" in e.field_name for e in errors)
        assert any(e.severity == ValidationSeverity.WARNING for e in errors)
    
    @pytest.mark.asyncio
    async def test_temporal_consistency_validation(self, mock_db_manager):
        """Test temporal consistency validation."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test data with extreme year-over-year change
        data_by_year = {
            2022: {"count_end": 100, "total_revenue_cents": 1000000000},
            2023: {"count_end": 1000, "total_revenue_cents": 10000000000}  # 10x increase
        }
        
        errors = await validator.validate_temporal_consistency(data_by_year)
        
        assert len(errors) > 0
        assert any("temporal_consistency" in e.field_name for e in errors)
        assert any(e.severity == ValidationSeverity.WARNING for e in errors)
    
    @pytest.mark.asyncio
    async def test_validation_bypass_functionality(self, mock_db_manager):
        """Test validation bypass functionality."""
        bypass = ValidationBypass(mock_db_manager)
        entity_id = uuid4()
        
        # Initially no bypass
        is_bypassed, reason = await bypass.is_bypassed(entity_id, "InitialFee")
        assert not is_bypassed
        assert reason is None
        
        # Set bypass
        await bypass.set_bypass(entity_id, "InitialFee", "Manual review required", "user123")
        
        # Should now be bypassed (from cache)
        is_bypassed, reason = await bypass.is_bypassed(entity_id, "InitialFee")
        assert is_bypassed
        assert reason == "Cached bypass"
    
    @pytest.mark.asyncio
    async def test_validation_statistics(self, mock_db_manager):
        """Test validation statistics tracking."""
        validator = SchemaValidator(mock_db_manager)
        
        # Perform some validations
        valid_data = {
            "fee_name": "Test Fee",
            "amount_cents": 1000000,
            "refundable": False,
            "section_id": uuid4()
        }
        
        await validator.validate_model(valid_data, InitialFee)
        await validator.validate_model(valid_data, InitialFee)
        
        stats = validator.get_validation_stats()
        
        assert stats["total_validations"] == 2
        assert stats["successful_validations"] == 2
        assert stats["success_rate"] == 100.0
        assert "cache_size" in stats
    
    def test_validation_error_creation(self):
        """Test validation error object creation."""
        error = ValidationError(
            field_name="test_field",
            error_message="Test error message",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.BUSINESS_RULE,
            actual_value=100,
            expected_value=200,
            context={"test": "context"}
        )
        
        assert error.field_name == "test_field"
        assert error.severity == ValidationSeverity.ERROR
        assert error.category == ValidationCategory.BUSINESS_RULE
        assert error.actual_value == 100
        assert error.context["test"] == "context"
    
    def test_validation_result_creation(self):
        """Test validation result object creation."""
        entity_id = uuid4()
        result = ValidationResult(
            entity_id=entity_id,
            entity_type="InitialFee",
            is_valid=True
        )
        
        assert result.entity_id == entity_id
        assert result.entity_type == "InitialFee"
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert len(result.info) == 0
        assert result.validated_at is not None
    
    @pytest.mark.asyncio
    async def test_outlet_math_validation(self, mock_db_manager, sample_outlet_data):
        """Test outlet mathematics validation."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test correct math
        result = await validator.validate_model(sample_outlet_data, OutletSummary)
        assert result.is_valid
        
        # Test incorrect math
        data = sample_outlet_data.copy()
        data["count_end"] = 999  # Wrong calculation
        
        result = await validator.validate_model(data, OutletSummary)
        assert not result.is_valid
        assert any("outlet_math" in e.field_name for e in result.errors)
    
    @pytest.mark.asyncio
    async def test_financial_validation(self, mock_db_manager):
        """Test financial statement validation."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test balanced accounting equation
        balanced_data = {
            "fiscal_year": 2023,
            "total_assets_cents": 1000000000,  # $10M
            "total_liabilities_cents": 600000000,  # $6M
            "total_equity_cents": 400000000,  # $4M (balances)
            "section_id": uuid4()
        }
        
        result = await validator.validate_model(balanced_data, Financials)
        assert result.is_valid
        
        # Test imbalanced accounting equation
        imbalanced_data = balanced_data.copy()
        imbalanced_data["total_assets_cents"] = 2000000000  # $20M (doesn't balance)
        
        result = await validator.validate_model(imbalanced_data, Financials)
        assert not result.is_valid
        assert any("accounting_equation" in e.field_name for e in result.errors)
    
    @pytest.mark.asyncio
    async def test_validation_config_thresholds(self, mock_db_manager):
        """Test validation configuration thresholds."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test fee above maximum threshold
        high_fee_data = {
            "fee_name": "Very High Fee",
            "amount_cents": ValidationConfig.MAX_FEE_AMOUNT + 100,
            "refundable": False,
            "section_id": uuid4()
        }
        
        result = await validator.validate_model(high_fee_data, InitialFee)
        assert result.is_valid  # Still valid
        assert len(result.warnings) > 0  # But should have warning
        assert any("exceeds reasonable maximum" in w.error_message for w in result.warnings)
    
    @pytest.mark.asyncio
    async def test_error_handling_in_validation(self, mock_db_manager):
        """Test error handling during validation."""
        validator = SchemaValidator(mock_db_manager)
        
        # Test with invalid data that causes exception
        invalid_data = {
            "fee_name": None,  # This should cause validation error
            "amount_cents": "not_a_number",  # This should cause validation error
            "section_id": "invalid_uuid"  # This should cause validation error
        }
        
        result = await validator.validate_model(invalid_data, InitialFee)
        
        assert not result.is_valid
        assert len(result.errors) > 0
        # Should have multiple validation errors from Pydantic


def test_validation_config_constants():
    """Test validation configuration constants."""
    assert ValidationConfig.MAX_FEE_AMOUNT == 10_000_000_00  # $10M
    assert ValidationConfig.MAX_ROYALTY_PERCENTAGE == 50.0
    assert ValidationConfig.MIN_SAMPLE_SIZE_FOR_FPR == 5
    assert ValidationConfig.FLAG_NEGATIVE_EQUITY_THRESHOLD == -10_000_000_00


def test_validation_enums():
    """Test validation enums."""
    # Test ValidationSeverity
    assert ValidationSeverity.ERROR == "ERROR"
    assert ValidationSeverity.WARNING == "WARNING"
    assert ValidationSeverity.INFO == "INFO"
    
    # Test ValidationCategory
    assert ValidationCategory.SCHEMA == "SCHEMA"
    assert ValidationCategory.BUSINESS_RULE == "BUSINESS_RULE"
    assert ValidationCategory.CROSS_FIELD == "CROSS_FIELD"
    assert ValidationCategory.RANGE == "RANGE"
    assert ValidationCategory.FORMAT == "FORMAT"
    assert ValidationCategory.REFERENCE == "REFERENCE"


if __name__ == "__main__":
    # Run a simple test to verify functionality
    print("🧪 Running enhanced validation tests...")
    
    # Test basic functionality
    try:
        # Test ValidationError creation
        error = ValidationError(
            field_name="test",
            error_message="Test message",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.SCHEMA
        )
        print("✅ ValidationError creation works")
        
        # Test ValidationResult creation
        result = ValidationResult(
            entity_id=uuid4(),
            entity_type="Test",
            is_valid=True
        )
        print("✅ ValidationResult creation works")
        
        # Test validation config
        assert ValidationConfig.MAX_FEE_AMOUNT > 0
        print("✅ ValidationConfig works")
        
        print("🎉 All basic tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()