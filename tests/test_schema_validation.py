"""Unit tests for schema validation layer."""

import pytest
import asyncio
from datetime import datetime, date
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from tasks.schema_validation import (
    SchemaValidator, ValidationBypass, ValidationReportGenerator,
    ValidationError, ValidationResult, ValidationReport,
    ValidationSeverity, ValidationCategory,
    validate_extracted_data, validate_fdd_sections
)
from models import (
    InitialFee, OtherFee, InitialInvestment, FPR, OutletSummary, 
    Financials, ValidationConfig, DueAt, FeeFrequency, CalculationBasis
)
from utils.database import DatabaseManager


@pytest.fixture
def mock_db_manager():
    """Mock database manager for testing."""
    db = AsyncMock(spec=DatabaseManager)
    return db


@pytest.fixture
def sample_initial_fee_data():
    """Sample data for initial fee validation."""
    return {
        "fee_name": "Initial Franchise Fee",
        "amount_cents": 5000000,  # $50,000
        "refundable": True,
        "refund_conditions": "Refundable within 30 days if territory not approved",
        "due_at": "Signing",
        "notes": "Standard initial fee",
        "section_id": str(uuid4())
    }


@pytest.fixture
def sample_other_fee_data():
    """Sample data for other fee validation."""
    return {
        "fee_name": "Royalty Fee",
        "amount_percentage": 6.0,
        "frequency": "Monthly",
        "calculation_basis": "Gross Sales",
        "minimum_cents": 50000,  # $500 minimum
        "remarks": "Monthly royalty based on gross sales",
        "section_id": str(uuid4())
    }


@pytest.fixture
def sample_investment_data():
    """Sample data for investment validation."""
    return {
        "category": "Initial Franchise Fee",
        "low_cents": 4500000,  # $45,000
        "high_cents": 5500000,  # $55,000
        "method_of_payment": "Lump sum",
        "when_due": "Upon signing",
        "to_whom_paid": "Franchisor",
        "section_id": str(uuid4())
    }


@pytest.fixture
def sample_outlet_data():
    """Sample data for outlet summary validation."""
    return {
        "fiscal_year": 2023,
        "count_start": 100,
        "opened": 15,
        "closed": 5,
        "transferred_in": 2,
        "transferred_out": 3,
        "count_end": 109,  # Should equal start + opened - closed + in - out
        "section_id": str(uuid4())
    }


@pytest.fixture
def sample_financials_data():
    """Sample data for financials validation."""
    return {
        "fiscal_year": 2023,
        "total_assets_cents": 1000000000,  # $10M
        "total_liabilities_cents": 600000000,  # $6M
        "total_equity_cents": 400000000,  # $4M (balances)
        "total_revenue_cents": 500000000,  # $5M
        "auditor_name": "Big Four Accounting",
        "audit_opinion": "Unqualified",
        "section_id": str(uuid4())
    }


class TestValidationBypass:
    """Test validation bypass functionality."""
    
    @pytest.mark.asyncio
    async def test_no_bypass_initially(self, mock_db_manager):
        """Test that entities have no bypass initially."""
        mock_db_manager.fetch_one.return_value = None
        
        bypass = ValidationBypass(mock_db_manager)
        entity_id = uuid4()
        
        is_bypassed, reason = await bypass.is_bypassed(entity_id, "InitialFee")
        
        assert not is_bypassed
        assert reason is None
        mock_db_manager.fetch_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_set_and_check_bypass(self, mock_db_manager):
        """Test setting and checking bypass."""
        # First call returns None (no bypass), second returns bypass record
        mock_db_manager.fetch_one.side_effect = [
            None,
            {"bypass_reason": "Manual review required", "created_at": datetime.utcnow()}
        ]
        mock_db_manager.execute.return_value = None
        
        bypass = ValidationBypass(mock_db_manager)
        entity_id = uuid4()
        
        # Set bypass
        await bypass.set_bypass(entity_id, "InitialFee", "Manual review required", "user123")
        
        # Check bypass (should hit cache)
        is_bypassed, reason = await bypass.is_bypassed(entity_id, "InitialFee")
        
        assert is_bypassed
        assert reason == "Cached bypass"
        mock_db_manager.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_bypass_caching(self, mock_db_manager):
        """Test that bypass results are cached."""
        mock_db_manager.fetch_one.return_value = {
            "bypass_reason": "Test reason", 
            "created_at": datetime.utcnow()
        }
        
        bypass = ValidationBypass(mock_db_manager)
        entity_id = uuid4()
        
        # First call should hit database
        is_bypassed1, reason1 = await bypass.is_bypassed(entity_id, "InitialFee")
        
        # Second call should hit cache
        is_bypassed2, reason2 = await bypass.is_bypassed(entity_id, "InitialFee")
        
        assert is_bypassed1 and is_bypassed2
        assert reason2 == "Cached bypass"
        # Database should only be called once
        mock_db_manager.fetch_one.assert_called_once()


class TestSchemaValidator:
    """Test main schema validation functionality."""
    
    @pytest.mark.asyncio
    async def test_valid_initial_fee(self, mock_db_manager, sample_initial_fee_data):
        """Test validation of valid initial fee data."""
        mock_db_manager.fetch_one.return_value = None  # No bypass
        mock_db_manager.execute.return_value = None  # Store result
        
        validator = SchemaValidator(mock_db_manager)
        
        result = await validator.validate_model(
            sample_initial_fee_data, 
            InitialFee,
            uuid4()
        )
        
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.entity_type == "InitialFee"
        assert result.validation_duration_ms is not None
    
    @pytest.mark.asyncio
    async def test_invalid_initial_fee_schema(self, mock_db_manager):
        """Test validation of invalid initial fee data."""
        mock_db_manager.fetch_one.return_value = None  # No bypass
        mock_db_manager.execute.return_value = None  # Store result
        
        validator = SchemaValidator(mock_db_manager)
        
        # Invalid data - missing required fields
        invalid_data = {
            "amount_cents": -1000,  # Negative amount
            "section_id": "invalid-uuid"  # Invalid UUID
        }
        
        result = await validator.validate_model(invalid_data, InitialFee, uuid4())
        
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("fee_name" in error.field_name for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_initial_fee_business_rules(self, mock_db_manager, sample_initial_fee_data):
        """Test business rule validation for initial fees."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Test refundable fee without conditions
        data = sample_initial_fee_data.copy()
        data["refundable"] = True
        data["refund_conditions"] = None
        
        result = await validator.validate_model(data, InitialFee, uuid4())
        
        assert result.is_valid  # Should still be valid
        assert len(result.warnings) > 0  # But should have warning
        assert any("refund_conditions" in warning.field_name for warning in result.warnings)
    
    @pytest.mark.asyncio
    async def test_other_fee_validation(self, mock_db_manager, sample_other_fee_data):
        """Test validation of other fee data."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        result = await validator.validate_model(sample_other_fee_data, OtherFee, uuid4())
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    @pytest.mark.asyncio
    async def test_other_fee_missing_calculation_basis(self, mock_db_manager, sample_other_fee_data):
        """Test other fee validation when calculation basis is missing."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Remove calculation basis for percentage-based fee
        data = sample_other_fee_data.copy()
        data["calculation_basis"] = None
        
        result = await validator.validate_model(data, OtherFee, uuid4())
        
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("calculation_basis" in error.field_name for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_investment_range_validation(self, mock_db_manager, sample_investment_data):
        """Test investment range validation."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Test invalid range (high < low)
        data = sample_investment_data.copy()
        data["low_cents"] = 6000000  # $60,000
        data["high_cents"] = 4000000  # $40,000 (invalid)
        
        result = await validator.validate_model(data, InitialInvestment, uuid4())
        
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("high_cents" in error.field_name for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_outlet_math_validation(self, mock_db_manager, sample_outlet_data):
        """Test outlet mathematics validation."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Test incorrect outlet math
        data = sample_outlet_data.copy()
        data["count_end"] = 999  # Wrong calculation
        
        result = await validator.validate_model(data, OutletSummary, uuid4())
        
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("outlet_math" in error.field_name for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_financials_accounting_equation(self, mock_db_manager, sample_financials_data):
        """Test financial accounting equation validation."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Test imbalanced accounting equation
        data = sample_financials_data.copy()
        data["total_assets_cents"] = 2000000000  # $20M (doesn't balance)
        
        result = await validator.validate_model(data, Financials, uuid4())
        
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("accounting_equation" in error.field_name for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_validation_bypass(self, mock_db_manager, sample_initial_fee_data):
        """Test validation bypass functionality."""
        # Mock bypass exists
        mock_db_manager.fetch_one.return_value = {
            "bypass_reason": "Manual review approved",
            "created_at": datetime.utcnow()
        }
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        entity_id = uuid4()
        
        result = await validator.validate_model(
            sample_initial_fee_data, 
            InitialFee, 
            entity_id
        )
        
        assert result.is_valid
        assert result.bypass_reason == "Manual review approved"
        assert result.validation_duration_ms == 0
    
    @pytest.mark.asyncio
    async def test_validation_stats(self, mock_db_manager, sample_initial_fee_data):
        """Test validation statistics tracking."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Perform several validations
        await validator.validate_model(sample_initial_fee_data, InitialFee, uuid4())
        await validator.validate_model(sample_initial_fee_data, InitialFee, uuid4())
        
        stats = validator.get_validation_stats()
        
        assert stats["total_validations"] == 2
        assert stats["successful_validations"] == 2
        assert stats["success_rate"] == 100.0
    
    @pytest.mark.asyncio
    async def test_validation_error_storage(self, mock_db_manager, sample_initial_fee_data):
        """Test that validation results are stored in database."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        await validator.validate_model(sample_initial_fee_data, InitialFee, uuid4())
        
        # Should have called execute to store validation result
        assert mock_db_manager.execute.call_count >= 1
        
        # Check that the first call was to store validation result
        first_call = mock_db_manager.execute.call_args_list[0]
        query = first_call[0][0]
        assert "INSERT INTO validation_results" in query


class TestValidationReportGenerator:
    """Test validation report generation."""
    
    @pytest.mark.asyncio
    async def test_generate_fdd_report(self, mock_db_manager):
        """Test generating validation report for FDD."""
        fdd_id = uuid4()
        section_id = uuid4()
        
        # Mock database responses
        mock_db_manager.fetch_all.side_effect = [
            # Sections query
            [{"id": section_id, "item_no": 5, "extraction_status": "completed"}],
            # Errors query
            [{
                "id": uuid4(),
                "entity_id": section_id,
                "field_name": "test_field",
                "error_message": "Test error",
                "severity": "ERROR",
                "category": "SCHEMA",
                "actual_value": "test",
                "expected_value": "expected",
                "context": {"test": "context"}
            }]
        ]
        
        mock_db_manager.fetch_one.return_value = {
            "id": uuid4(),
            "entity_id": section_id,
            "entity_type": "InitialFee",
            "is_valid": False,
            "validated_at": datetime.utcnow(),
            "validation_duration_ms": 100.0,
            "bypass_reason": None,
            "error_count": 1,
            "warning_count": 0,
            "info_count": 0
        }
        
        generator = ValidationReportGenerator(mock_db_manager)
        report = await generator.generate_fdd_report(fdd_id)
        
        assert report.fdd_id == fdd_id
        assert len(report.results) == 1
        assert not report.results[0].is_valid
        assert len(report.results[0].errors) == 1
        assert report.summary["total_entities"] == 1
        assert report.summary["invalid_entities"] == 1
        assert report.total_duration_ms is not None
    
    @pytest.mark.asyncio
    async def test_empty_fdd_report(self, mock_db_manager):
        """Test generating report for FDD with no sections."""
        fdd_id = uuid4()
        
        mock_db_manager.fetch_all.return_value = []
        
        generator = ValidationReportGenerator(mock_db_manager)
        report = await generator.generate_fdd_report(fdd_id)
        
        assert report.fdd_id == fdd_id
        assert len(report.results) == 0
        assert report.summary["total_entities"] == 0


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @pytest.mark.asyncio
    async def test_validate_extracted_data(self, mock_db_manager, sample_initial_fee_data):
        """Test validate_extracted_data convenience function."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        result = await validate_extracted_data(
            sample_initial_fee_data,
            InitialFee,
            mock_db_manager
        )
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid
    
    @pytest.mark.asyncio
    async def test_validate_fdd_sections(self, mock_db_manager):
        """Test validate_fdd_sections convenience function."""
        fdd_id = uuid4()
        
        mock_db_manager.fetch_all.return_value = []
        
        report = await validate_fdd_sections(fdd_id, mock_db_manager)
        
        assert isinstance(report, ValidationReport)
        assert report.fdd_id == fdd_id


class TestValidationErrorHandling:
    """Test error handling in validation."""
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, mock_db_manager, sample_initial_fee_data):
        """Test handling of database errors during validation."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.side_effect = Exception("Database error")
        
        validator = SchemaValidator(mock_db_manager)
        
        # Should not raise exception, but log error
        result = await validator.validate_model(sample_initial_fee_data, InitialFee, uuid4())
        
        assert result.is_valid  # Validation itself succeeded
    
    @pytest.mark.asyncio
    async def test_unexpected_validation_error(self, mock_db_manager):
        """Test handling of unexpected validation errors."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Pass invalid model class to trigger unexpected error
        with patch('tasks.schema_validation.InitialFee.model_validate', side_effect=Exception("Unexpected error")):
            result = await validator.validate_model(
                {"test": "data"}, 
                InitialFee, 
                uuid4()
            )
            
            assert not result.is_valid
            assert len(result.errors) == 1
            assert "Unexpected validation error" in result.errors[0].error_message


class TestValidationConfiguration:
    """Test validation configuration and thresholds."""
    
    @pytest.mark.asyncio
    async def test_fee_amount_thresholds(self, mock_db_manager):
        """Test fee amount validation thresholds."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Test fee above info threshold but below max
        data = {
            "fee_name": "High Fee",
            "amount_cents": 1500000000,  # $15M (above info threshold)
            "refundable": False,
            "section_id": str(uuid4())
        }
        
        result = await validator.validate_model(data, InitialFee, uuid4())
        
        # Should be valid but have info message
        assert result.is_valid
        assert len(result.info) > 0
        assert any("Unusually high" in info.error_message for info in result.info)
    
    @pytest.mark.asyncio
    async def test_royalty_percentage_thresholds(self, mock_db_manager):
        """Test royalty percentage validation thresholds."""
        mock_db_manager.fetch_one.return_value = None
        mock_db_manager.execute.return_value = None
        
        validator = SchemaValidator(mock_db_manager)
        
        # Test high royalty percentage
        data = {
            "fee_name": "Royalty Fee",
            "amount_percentage": 25.0,  # Above threshold
            "frequency": "Monthly",
            "calculation_basis": "Gross Sales",
            "section_id": str(uuid4())
        }
        
        result = await validator.validate_model(data, OtherFee, uuid4())
        
        # Should be valid but have warning
        assert result.is_valid
        assert len(result.warnings) > 0
        assert any("royalty percentage" in warning.error_message.lower() for warning in result.warnings)


if __name__ == "__main__":
    pytest.main([__file__])