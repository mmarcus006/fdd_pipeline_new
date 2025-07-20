"""Unit tests for franchise_scrapers.models module."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from franchise_scrapers.models import (
    CleanFDDRow,
    WIActiveRow,
    WIRegisteredRow,
    WIDetailsRow
)


class TestCleanFDDRow:
    """Test CleanFDDRow model validation and behavior."""
    
    def test_valid_clean_fdd_row(self):
        """Test creating a valid CleanFDDRow."""
        row = CleanFDDRow(
            document_id="12345-6789-abcd",
            legal_name="Test Franchise LLC",
            pdf_url="https://example.com/doc.pdf",
            scraped_at=datetime(2024, 1, 15, 10, 30, 0)
        )
        
        assert row.document_id == "12345-6789-abcd"
        assert row.legal_name == "Test Franchise LLC"
        assert str(row.pdf_url) == "https://example.com/doc.pdf"
        assert row.scraped_at == datetime(2024, 1, 15, 10, 30, 0)
        assert row.pdf_status is None
        assert row.pdf_path is None
    
    def test_clean_fdd_row_with_optional_fields(self):
        """Test CleanFDDRow with optional fields populated."""
        row = CleanFDDRow(
            document_id="12345",
            legal_name="Test Franchise",
            pdf_url="https://example.com/doc.pdf",
            scraped_at=datetime.utcnow(),
            pdf_status="ok",
            pdf_path="/downloads/test.pdf"
        )
        
        assert row.pdf_status == "ok"
        assert row.pdf_path == "/downloads/test.pdf"
    
    def test_clean_fdd_row_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CleanFDDRow(
                legal_name="Test Franchise",
                pdf_url="https://example.com/doc.pdf",
                scraped_at=datetime.utcnow()
                # Missing document_id
            )
        
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('document_id',) for e in errors)
    
    def test_clean_fdd_row_invalid_url(self):
        """Test that invalid URL raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CleanFDDRow(
                document_id="12345",
                legal_name="Test Franchise",
                pdf_url="not-a-valid-url",  # Invalid URL
                scraped_at=datetime.utcnow()
            )
        
        errors = exc_info.value.errors()
        assert any('URL' in str(e) for e in errors)
    
    def test_clean_fdd_row_empty_strings(self):
        """Test handling of empty strings."""
        with pytest.raises(ValidationError):
            CleanFDDRow(
                document_id="",  # Empty string should fail validation
                legal_name="Test",
                pdf_url="https://example.com/doc.pdf",
                scraped_at=datetime.utcnow()
            )
    
    def test_clean_fdd_row_none_optional_fields(self):
        """Test that None values work for optional fields."""
        row = CleanFDDRow(
            document_id="12345",
            legal_name="Test Franchise",
            pdf_url="https://example.com/doc.pdf",
            scraped_at=datetime.utcnow(),
            pdf_status=None,
            pdf_path=None
        )
        
        assert row.pdf_status is None
        assert row.pdf_path is None


class TestWIActiveRow:
    """Test WIActiveRow model validation."""
    
    def test_valid_wi_active_row(self):
        """Test creating a valid WIActiveRow."""
        row = WIActiveRow(
            legal_name="Wisconsin Franchise Inc.",
            filing_number="54321"
        )
        
        assert row.legal_name == "Wisconsin Franchise Inc."
        assert row.filing_number == "54321"
    
    def test_wi_active_row_missing_fields(self):
        """Test that missing fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            WIActiveRow(legal_name="Test")  # Missing filing_number
        
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('filing_number',) for e in errors)
    
    def test_wi_active_row_empty_strings(self):
        """Test that empty strings fail validation."""
        with pytest.raises(ValidationError):
            WIActiveRow(
                legal_name="",  # Empty string
                filing_number="12345"
            )
    
    def test_wi_active_row_whitespace_handling(self):
        """Test handling of whitespace in fields."""
        row = WIActiveRow(
            legal_name="  Wisconsin Franchise  ",  # Extra whitespace
            filing_number=" 54321 "
        )
        
        # Model doesn't auto-strip, values retain whitespace
        assert row.legal_name == "  Wisconsin Franchise  "
        assert row.filing_number == " 54321 "


class TestWIRegisteredRow:
    """Test WIRegisteredRow model validation."""
    
    def test_valid_wi_registered_row(self):
        """Test creating a valid WIRegisteredRow."""
        row = WIRegisteredRow(
            filing_number="12345",
            legal_name="Registered Franchise LLC",
            details_url="https://apps.dfi.wi.gov/apps/Details.aspx?id=12345"
        )
        
        assert row.filing_number == "12345"
        assert row.legal_name == "Registered Franchise LLC"
        assert str(row.details_url) == "https://apps.dfi.wi.gov/apps/Details.aspx?id=12345"
    
    def test_wi_registered_row_invalid_url(self):
        """Test that invalid URL raises ValidationError."""
        with pytest.raises(ValidationError):
            WIRegisteredRow(
                filing_number="12345",
                legal_name="Test",
                details_url="invalid-url"
            )
    
    def test_wi_registered_row_url_normalization(self):
        """Test URL handling and normalization."""
        row = WIRegisteredRow(
            filing_number="12345",
            legal_name="Test",
            details_url="HTTP://EXAMPLE.COM/PATH"  # Uppercase protocol/domain
        )
        
        # Pydantic's HttpUrl normalizes the URL
        assert "example.com" in str(row.details_url).lower()


class TestWIDetailsRow:
    """Test WIDetailsRow model validation."""
    
    def test_valid_wi_details_row_minimal(self):
        """Test creating a valid WIDetailsRow with minimal fields."""
        row = WIDetailsRow(
            filing_number="12345",
            status="Registered",
            legal_name="Detailed Franchise Inc.",
            pdf_status="ok",
            scraped_at=datetime(2024, 1, 15, 14, 30, 0)
        )
        
        assert row.filing_number == "12345"
        assert row.status == "Registered"
        assert row.legal_name == "Detailed Franchise Inc."
        assert row.trade_name is None
        assert row.contact_email is None
        assert row.pdf_path is None
        assert row.pdf_status == "ok"
        assert row.scraped_at == datetime(2024, 1, 15, 14, 30, 0)
    
    def test_wi_details_row_all_fields(self):
        """Test WIDetailsRow with all optional fields populated."""
        row = WIDetailsRow(
            filing_number="12345",
            status="Registered",
            legal_name="Detailed Franchise Inc.",
            trade_name="DFI Trading",
            contact_email="info@dfi.com",
            pdf_path="downloads/12345_dfi.pdf",
            pdf_status="ok",
            scraped_at=datetime.utcnow()
        )
        
        assert row.trade_name == "DFI Trading"
        assert row.contact_email == "info@dfi.com"
        assert row.pdf_path == "downloads/12345_dfi.pdf"
    
    def test_wi_details_row_invalid_email(self):
        """Test email validation."""
        # Pydantic doesn't validate email format by default unless using EmailStr
        # So this will pass - the field is just Optional[str]
        row = WIDetailsRow(
            filing_number="12345",
            status="Registered",
            legal_name="Test",
            contact_email="not-an-email",  # This will be accepted
            pdf_status="ok",
            scraped_at=datetime.utcnow()
        )
        
        assert row.contact_email == "not-an-email"
    
    def test_wi_details_row_pdf_status_values(self):
        """Test different pdf_status values."""
        statuses = ["ok", "failed", "skipped", "error", "timeout"]
        
        for status in statuses:
            row = WIDetailsRow(
                filing_number="12345",
                status="Registered",
                legal_name="Test",
                pdf_status=status,
                scraped_at=datetime.utcnow()
            )
            assert row.pdf_status == status
    
    def test_wi_details_row_datetime_handling(self):
        """Test datetime field handling."""
        # Test with timezone-aware datetime
        from datetime import timezone
        
        tz_aware_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        row = WIDetailsRow(
            filing_number="12345",
            status="Registered",
            legal_name="Test",
            pdf_status="ok",
            scraped_at=tz_aware_dt
        )
        
        assert row.scraped_at == tz_aware_dt
    
    def test_wi_details_row_none_handling(self):
        """Test None values for optional fields."""
        row = WIDetailsRow(
            filing_number="12345",
            status="Registered",
            legal_name="Test",
            trade_name=None,
            contact_email=None,
            pdf_path=None,
            pdf_status="skipped",
            scraped_at=datetime.utcnow()
        )
        
        assert row.trade_name is None
        assert row.contact_email is None
        assert row.pdf_path is None


class TestModelSerialization:
    """Test model serialization and deserialization."""
    
    def test_clean_fdd_row_dict_serialization(self):
        """Test serializing CleanFDDRow to dict."""
        row = CleanFDDRow(
            document_id="12345",
            legal_name="Test Franchise",
            pdf_url="https://example.com/doc.pdf",
            scraped_at=datetime(2024, 1, 15, 10, 30, 0),
            pdf_status="ok"
        )
        
        data = row.model_dump()
        
        assert data['document_id'] == "12345"
        assert data['legal_name'] == "Test Franchise"
        assert data['pdf_url'] == "https://example.com/doc.pdf"
        assert data['pdf_status'] == "ok"
        assert data['pdf_path'] is None
    
    def test_wi_details_row_json_serialization(self):
        """Test JSON serialization of WIDetailsRow."""
        row = WIDetailsRow(
            filing_number="12345",
            status="Registered",
            legal_name="Test Franchise",
            pdf_status="ok",
            scraped_at=datetime(2024, 1, 15, 10, 30, 0)
        )
        
        json_str = row.model_dump_json()
        
        assert '"filing_number":"12345"' in json_str
        assert '"status":"Registered"' in json_str
        assert '"legal_name":"Test Franchise"' in json_str
    
    def test_model_from_dict(self):
        """Test creating models from dictionaries."""
        data = {
            'filing_number': '12345',
            'legal_name': 'Test Franchise'
        }
        
        row = WIActiveRow(**data)
        
        assert row.filing_number == '12345'
        assert row.legal_name == 'Test Franchise'
    
    def test_model_validation_on_assignment(self):
        """Test that validation occurs on field assignment."""
        row = WIActiveRow(
            legal_name="Test",
            filing_number="12345"
        )
        
        # Pydantic v2 doesn't validate on assignment by default
        # This would require model_config with validate_assignment=True
        row.filing_number = "67890"  # This will work
        assert row.filing_number == "67890"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_very_long_strings(self):
        """Test handling of very long string values."""
        long_name = "A" * 1000  # 1000 character string
        
        row = WIActiveRow(
            legal_name=long_name,
            filing_number="12345"
        )
        
        assert len(row.legal_name) == 1000
    
    def test_unicode_characters(self):
        """Test handling of unicode characters."""
        row = WIActiveRow(
            legal_name="Café Français™ LLC",
            filing_number="12345"
        )
        
        assert row.legal_name == "Café Français™ LLC"
    
    def test_special_characters_in_urls(self):
        """Test URLs with special characters."""
        row = CleanFDDRow(
            document_id="12345",
            legal_name="Test",
            pdf_url="https://example.com/doc?id=123&type=pdf#page1",
            scraped_at=datetime.utcnow()
        )
        
        assert "id=123" in str(row.pdf_url)
        assert "#page1" in str(row.pdf_url)
    
    def test_datetime_edge_cases(self):
        """Test datetime edge cases."""
        # Test with minimum datetime
        min_dt = datetime.min
        row = CleanFDDRow(
            document_id="12345",
            legal_name="Test",
            pdf_url="https://example.com/doc.pdf",
            scraped_at=min_dt
        )
        
        assert row.scraped_at == min_dt
        
        # Test with maximum datetime
        max_dt = datetime.max
        row2 = CleanFDDRow(
            document_id="12345",
            legal_name="Test",
            pdf_url="https://example.com/doc.pdf",
            scraped_at=max_dt
        )
        
        assert row2.scraped_at == max_dt