"""Unit tests for franchise_scrapers.mn.parsers module."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from franchise_scrapers.mn.parsers import (
    parse_row,
    extract_document_id,
    sanitize_filename,
    clean_text,
    parse_year,
    parse_date,
    is_valid_fdd
)


class TestParseRow:
    """Test parse_row function with various HTML structures."""
    
    @pytest.fixture
    def mock_cell(self):
        """Create a mock cell element."""
        def _mock_cell(text):
            cell = AsyncMock()
            cell.inner_text = AsyncMock(return_value=text)
            return cell
        return _mock_cell
    
    @pytest.fixture
    def mock_download_link(self):
        """Create a mock download link element."""
        link = AsyncMock()
        link.get_attribute = AsyncMock(return_value="https://example.com/download?documentId=%7B12345%7D")
        link.inner_text = AsyncMock(return_value="2024 FDD Document")
        return link
    
    @pytest.mark.asyncio
    async def test_parse_valid_clean_fdd_row(self, mock_cell, mock_download_link):
        """Test parsing a valid Clean FDD row."""
        # Create mock cells for a valid row
        cells = [
            mock_cell("1"),  # Row number
            AsyncMock(),  # Document cell (with link)
            mock_cell("Test Franchise LLC"),  # Franchisor
            mock_cell("Test Brand"),  # Franchise names
            mock_cell("Clean FDD"),  # Document types
            mock_cell("2024"),  # Year
            mock_cell("FN-12345"),  # File number
            mock_cell("Initial filing"),  # Notes
            mock_cell("01/15/2024"),  # Received date
        ]
        
        # Set up document cell with download link
        cells[1].query_selector = AsyncMock(return_value=mock_download_link)
        cells[1].inner_text = AsyncMock(return_value="Download")
        
        # Create mock row
        row = AsyncMock()
        row.query_selector_all = AsyncMock(return_value=cells)
        
        # Parse the row
        result = await parse_row(row)
        
        # Verify result
        assert result is not None
        assert result['download_url'] == "https://example.com/download?documentId=%7B12345%7D"
        assert result['document_title'] == "2024 FDD Document"
        assert result['franchisor'] == "Test Franchise LLC"
        assert result['franchise_names'] == "Test Brand"
        assert result['document_types'] == "Clean FDD"
        assert result['year'] == "2024"
        assert result['file_number'] == "FN-12345"
        assert result['notes'] == "Initial filing"
        assert result['received_date'] == "01/15/2024"
    
    @pytest.mark.asyncio
    async def test_parse_row_skip_non_clean_fdd(self, mock_cell, mock_download_link):
        """Test that non-Clean FDD rows are skipped."""
        cells = [
            mock_cell("1"),
            AsyncMock(),
            mock_cell("Test Franchise"),
            mock_cell("Test Brand"),
            mock_cell("Amendment"),  # Not a Clean FDD
            mock_cell("2024"),
            mock_cell("FN-12345"),
            mock_cell(""),
            mock_cell("01/15/2024"),
        ]
        
        cells[1].query_selector = AsyncMock(return_value=mock_download_link)
        
        row = AsyncMock()
        row.query_selector_all = AsyncMock(return_value=cells)
        
        result = await parse_row(row)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_parse_row_skip_header(self, mock_cell):
        """Test that header rows are skipped."""
        cells = [
            mock_cell("#"),  # Header indicator
            mock_cell("Document"),
            mock_cell("Franchisor"),
            mock_cell("Franchise names"),
            mock_cell("Document types"),
            mock_cell("Year"),
            mock_cell("File number"),
            mock_cell("Notes"),
            mock_cell("Received date"),
        ]
        
        row = AsyncMock()
        row.query_selector_all = AsyncMock(return_value=cells)
        
        result = await parse_row(row)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_parse_row_insufficient_cells(self):
        """Test that rows with insufficient cells are skipped."""
        cells = [AsyncMock() for _ in range(5)]  # Only 5 cells instead of 9
        
        row = AsyncMock()
        row.query_selector_all = AsyncMock(return_value=cells)
        
        result = await parse_row(row)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_parse_row_no_download_link(self, mock_cell):
        """Test that rows without download links are skipped."""
        cells = [mock_cell(str(i)) for i in range(9)]
        cells[4] = mock_cell("Clean FDD")
        
        # Document cell has no link
        cells[1].query_selector = AsyncMock(return_value=None)
        
        row = AsyncMock()
        row.query_selector_all = AsyncMock(return_value=cells)
        
        result = await parse_row(row)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_parse_row_whitespace_handling(self, mock_cell, mock_download_link):
        """Test that whitespace is properly stripped."""
        cells = [
            mock_cell("1"),
            AsyncMock(),
            mock_cell("  Test Franchise LLC  "),  # Extra whitespace
            mock_cell("\nTest Brand\t"),  # Newlines and tabs
            mock_cell("Clean FDD"),
            mock_cell(" 2024 "),
            mock_cell("FN-12345"),
            mock_cell("   "),  # Only whitespace
            mock_cell("01/15/2024"),
        ]
        
        cells[1].query_selector = AsyncMock(return_value=mock_download_link)
        
        row = AsyncMock()
        row.query_selector_all = AsyncMock(return_value=cells)
        
        result = await parse_row(row)
        
        assert result['franchisor'] == "Test Franchise LLC"
        assert result['franchise_names'] == "Test Brand"
        assert result['year'] == "2024"
        assert result['notes'] == ""
    
    @pytest.mark.asyncio
    async def test_parse_row_exception_handling(self):
        """Test that exceptions are handled gracefully."""
        row = AsyncMock()
        row.query_selector_all = AsyncMock(side_effect=Exception("Test error"))
        
        result = await parse_row(row)
        
        assert result is None


class TestExtractDocumentId:
    """Test extract_document_id function."""
    
    def test_extract_encoded_document_id(self):
        """Test extracting document ID from URL with encoded brackets."""
        url = "https://example.com/download?documentId=%7B550e8400-e29b-41d4-a716-446655440000%7D"
        result = extract_document_id(url)
        assert result == "550e8400-e29b-41d4-a716-446655440000"
    
    def test_extract_unencoded_document_id(self):
        """Test extracting document ID from URL with unencoded brackets."""
        url = "https://example.com/download?documentId={550e8400-e29b-41d4-a716-446655440000}"
        result = extract_document_id(url)
        assert result == "550e8400-e29b-41d4-a716-446655440000"
    
    def test_extract_document_id_with_other_params(self):
        """Test extraction when URL has multiple parameters."""
        url = "https://example.com/download?type=pdf&documentId=%7B12345-67890%7D&format=clean"
        result = extract_document_id(url)
        assert result == "12345-67890"
    
    def test_extract_document_id_url_decoded(self):
        """Test extraction after URL decoding."""
        url = "https://example.com/download?documentId=%7B12345%7D&name=Test%20Document"
        result = extract_document_id(url)
        assert result == "12345"
    
    def test_extract_document_id_not_found(self):
        """Test when document ID is not found."""
        url = "https://example.com/download?id=12345"
        result = extract_document_id(url)
        assert result is None
    
    def test_extract_document_id_malformed_url(self):
        """Test with malformed URL."""
        url = "not-a-valid-url"
        result = extract_document_id(url)
        assert result is None
    
    def test_extract_document_id_empty_url(self):
        """Test with empty URL."""
        result = extract_document_id("")
        assert result is None
    
    def test_extract_document_id_exception_handling(self):
        """Test exception handling."""
        # URL that might cause regex issues
        url = "https://example.com/download?documentId=%7B[invalid-regex"
        result = extract_document_id(url)
        # Should handle gracefully and return None
        assert result is None


class TestSanitizeFilename:
    """Test sanitize_filename function."""
    
    def test_sanitize_basic_text(self):
        """Test sanitizing basic text."""
        result = sanitize_filename("Test Franchise LLC")
        assert result == "Test_Franchise_LLC"
    
    def test_sanitize_special_characters(self):
        """Test removing special characters."""
        result = sanitize_filename("Test & Franchise, Inc.")
        assert result == "Test__Franchise_Inc"
    
    def test_sanitize_multiple_spaces(self):
        """Test replacing multiple spaces."""
        result = sanitize_filename("Test    Franchise     LLC")
        assert result == "Test_Franchise_LLC"
    
    def test_sanitize_leading_trailing_spaces(self):
        """Test removing leading/trailing spaces."""
        result = sanitize_filename("  Test Franchise  ")
        assert result == "Test_Franchise"
    
    def test_sanitize_max_length(self):
        """Test truncation to max length."""
        long_name = "A" * 150
        result = sanitize_filename(long_name)
        assert len(result) == 100
    
    def test_sanitize_max_length_custom(self):
        """Test custom max length."""
        result = sanitize_filename("Test Franchise LLC", max_length=10)
        assert result == "Test_Franc"
    
    def test_sanitize_unicode_characters(self):
        """Test handling of unicode characters."""
        result = sanitize_filename("Café Français™")
        assert result == "Caf_Franais"
    
    def test_sanitize_only_special_characters(self):
        """Test when input has only special characters."""
        result = sanitize_filename("@#$%^&*()")
        assert result == "unknown_franchise"
    
    def test_sanitize_empty_string(self):
        """Test empty string input."""
        result = sanitize_filename("")
        assert result == "unknown_franchise"
    
    def test_sanitize_numbers_and_hyphens(self):
        """Test that numbers and hyphens are preserved."""
        result = sanitize_filename("Test-123 Franchise-456")
        assert result == "Test-123_Franchise-456"


class TestCleanText:
    """Test clean_text function."""
    
    def test_clean_basic_text(self):
        """Test cleaning basic text."""
        result = clean_text("Test Franchise")
        assert result == "Test Franchise"
    
    def test_clean_extra_whitespace(self):
        """Test removing extra whitespace."""
        result = clean_text("Test    Franchise\n\nLLC\t\tInc")
        assert result == "Test Franchise LLC Inc"
    
    def test_clean_leading_trailing_whitespace(self):
        """Test removing leading/trailing whitespace."""
        result = clean_text("  \n\tTest Franchise\t\n  ")
        assert result == "Test Franchise"
    
    def test_clean_non_printable_characters(self):
        """Test removing non-printable characters."""
        result = clean_text("Test\x00Franchise\x01LLC")
        assert result == "TestFranchiseLLC"
    
    def test_clean_preserve_normal_spaces(self):
        """Test that normal spaces are preserved."""
        result = clean_text("Test Franchise LLC")
        assert result == "Test Franchise LLC"
    
    def test_clean_empty_string(self):
        """Test empty string."""
        result = clean_text("")
        assert result == ""
    
    def test_clean_only_whitespace(self):
        """Test string with only whitespace."""
        result = clean_text("   \n\t   ")
        assert result == ""
    
    def test_clean_mixed_whitespace_types(self):
        """Test various types of whitespace."""
        result = clean_text("Test\r\nFranchise\vLLC\fInc")
        assert result == "Test Franchise LLC Inc"


class TestParseYear:
    """Test parse_year function."""
    
    def test_parse_year_simple(self):
        """Test parsing simple year."""
        assert parse_year("2024") == 2024
    
    def test_parse_year_in_text(self):
        """Test extracting year from text."""
        assert parse_year("Year: 2024") == 2024
        assert parse_year("FDD 2024 Document") == 2024
    
    def test_parse_year_multiple_years(self):
        """Test when multiple years present (takes first)."""
        assert parse_year("2023-2024 FDD") == 2023
    
    def test_parse_year_with_whitespace(self):
        """Test year with whitespace."""
        assert parse_year(" 2024 ") == 2024
    
    def test_parse_year_invalid(self):
        """Test invalid year values."""
        assert parse_year("1999") is None  # Too old
        assert parse_year("2150") is None  # Too far future
        assert parse_year("24") is None    # Not 4 digits
    
    def test_parse_year_no_year(self):
        """Test when no year is found."""
        assert parse_year("No year here") is None
        assert parse_year("") is None
    
    def test_parse_year_edge_cases(self):
        """Test edge case years."""
        assert parse_year("2000") == 2000  # Minimum valid
        assert parse_year("2100") == 2100  # Maximum valid
    
    def test_parse_year_non_numeric(self):
        """Test non-numeric input."""
        assert parse_year("Twenty Twenty Four") is None


class TestParseDate:
    """Test parse_date function."""
    
    def test_parse_date_mm_dd_yyyy_slash(self):
        """Test MM/DD/YYYY format."""
        assert parse_date("01/15/2024") == "2024-01-15"
        assert parse_date("12/31/2024") == "2024-12-31"
    
    def test_parse_date_mm_dd_yyyy_dash(self):
        """Test MM-DD-YYYY format."""
        assert parse_date("01-15-2024") == "2024-01-15"
    
    def test_parse_date_single_digit_month_day(self):
        """Test single digit month/day."""
        assert parse_date("1/5/2024") == "2024-01-05"
        assert parse_date("12/5/2024") == "2024-12-05"
    
    def test_parse_date_yyyy_mm_dd(self):
        """Test YYYY-MM-DD format."""
        assert parse_date("2024-01-15") == "2024-01-15"
        assert parse_date("2024/01/15") == "2024-01-15"
    
    def test_parse_date_month_name(self):
        """Test month name format."""
        assert parse_date("Jan 15, 2024") == "2024-01-15"
        assert parse_date("December 31, 2024") == "2024-12-31"
        assert parse_date("Feb 5 2024") == "2024-02-05"  # No comma
    
    def test_parse_date_with_extra_text(self):
        """Test date extraction from text."""
        assert parse_date("Received on 01/15/2024") == "2024-01-15"
        assert parse_date("Date: Jan 15, 2024 (Monday)") == "2024-01-15"
    
    def test_parse_date_invalid(self):
        """Test invalid dates."""
        assert parse_date("13/32/2024") is None  # Invalid month/day
        assert parse_date("not a date") is None
        assert parse_date("") is None
    
    def test_parse_date_edge_cases(self):
        """Test edge case dates."""
        assert parse_date("12/31/2024") == "2024-12-31"  # End of year
        assert parse_date("01/01/2024") == "2024-01-01"  # Start of year
    
    def test_parse_date_case_insensitive_months(self):
        """Test case insensitive month names."""
        assert parse_date("JAN 15, 2024") == "2024-01-15"
        assert parse_date("jan 15, 2024") == "2024-01-15"


class TestIsValidFDD:
    """Test is_valid_fdd function."""
    
    def test_valid_clean_fdd(self):
        """Test valid Clean FDD document."""
        assert is_valid_fdd("Clean FDD", "") is True
        assert is_valid_fdd("Clean FDD", "Initial filing") is True
    
    def test_not_clean_fdd(self):
        """Test document that's not a Clean FDD."""
        assert is_valid_fdd("Amendment", "") is False
        assert is_valid_fdd("FDD", "") is False  # Missing "Clean"
    
    def test_skip_amendments(self):
        """Test skipping amendments."""
        assert is_valid_fdd("Clean FDD", "Amendment to 2023 FDD") is False
        assert is_valid_fdd("Clean FDD", "This is an AMENDMENT") is False
    
    def test_skip_supplements(self):
        """Test skipping supplements."""
        assert is_valid_fdd("Clean FDD", "Supplement dated 01/15/2024") is False
    
    def test_skip_addendums(self):
        """Test skipping addendums."""
        assert is_valid_fdd("Clean FDD", "Addendum for CA") is False
    
    def test_skip_corrections(self):
        """Test skipping corrections."""
        assert is_valid_fdd("Clean FDD", "Correction to Item 7") is False
    
    def test_case_insensitive_notes(self):
        """Test case insensitive keyword matching."""
        assert is_valid_fdd("Clean FDD", "AMENDMENT") is False
        assert is_valid_fdd("Clean FDD", "Supplement") is False
    
    def test_valid_with_other_notes(self):
        """Test valid FDD with non-skip notes."""
        assert is_valid_fdd("Clean FDD", "Reviewed by legal") is True
        assert is_valid_fdd("Clean FDD", "New franchise system") is True
    
    def test_empty_notes(self):
        """Test with empty notes."""
        assert is_valid_fdd("Clean FDD", "") is True
    
    def test_multiple_document_types(self):
        """Test when Clean FDD is part of multiple types."""
        assert is_valid_fdd("Clean FDD, Receipt", "") is True
        assert is_valid_fdd("Receipt, Clean FDD", "") is True