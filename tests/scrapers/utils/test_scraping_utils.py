# ABOUTME: Test suite for scraping utility functions
# ABOUTME: Tests helper functions for filename sanitization, date parsing, URL normalization, etc.

import pytest
from datetime import datetime
from utils.scraping_utils import (
    sanitize_filename,
    get_default_headers,
    parse_date_formats,
    extract_filing_number,
    parse_file_size,
    normalize_url,
    extract_state_code,
    clean_text,
    format_franchise_name,
    create_document_filename,
    extract_year_from_text,
    parse_address,
    calculate_retry_delay,
)


class TestScrapingUtils:
    """Test suite for scraping utility functions."""

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Test removing invalid characters
        assert sanitize_filename("test/file:name*.pdf") == "testfilename.pdf"
        assert sanitize_filename("file<with>pipes|.txt") == "filewithpipes.txt"
        assert sanitize_filename("question?.doc") == "question.doc"

        # Test multiple spaces
        assert sanitize_filename("file   with   spaces.pdf") == "file with spaces.pdf"

        # Test leading/trailing dots and spaces
        assert sanitize_filename(" .hidden.file. ") == "hidden.file"

        # Test empty string
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("   ") == "unnamed"

        # Test max length truncation
        long_name = "a" * 250
        result = sanitize_filename(long_name)
        assert len(result) <= 200

    def test_get_default_headers(self):
        """Test default headers generation."""
        headers = get_default_headers()

        assert isinstance(headers, dict)
        assert "Accept" in headers
        assert "User-Agent" not in headers  # User-Agent added separately
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        assert headers["Cache-Control"] == "no-cache"

    def test_parse_date_formats(self):
        """Test date parsing with various formats."""
        # Test common formats
        assert parse_date_formats("12/31/2023") == datetime(2023, 12, 31)
        assert parse_date_formats("12-31-2023") == datetime(2023, 12, 31)
        assert parse_date_formats("2023-12-31") == datetime(2023, 12, 31)
        assert parse_date_formats("December 31, 2023") == datetime(2023, 12, 31)
        assert parse_date_formats("Dec 31, 2023") == datetime(2023, 12, 31)

        # Test year-only fallback
        assert parse_date_formats("Filed in 2023 somewhere") == datetime(2023, 1, 1)

        # Test invalid dates
        assert parse_date_formats("") is None
        assert parse_date_formats("not a date") is None
        assert parse_date_formats("13/45/2023") == datetime(
            2023, 1, 1
        )  # Falls back to extracting year

    def test_extract_filing_number(self):
        """Test filing number extraction."""
        # Test various patterns
        assert extract_filing_number("Filing Number: 12345") == "12345"
        assert extract_filing_number("Registration Number: #67890") == "67890"
        assert extract_filing_number("File No. 11111") == "11111"
        assert extract_filing_number("Number: 99999") == "99999"
        assert extract_filing_number("Document #54321") == "54321"

        # Test 6+ digit number extraction
        assert extract_filing_number("Random text 123456 more text") == "123456"

        # Test no match
        assert extract_filing_number("No numbers here") is None
        assert extract_filing_number("Only 123") is None  # Too short
        assert extract_filing_number("") is None

    def test_parse_file_size(self):
        """Test file size parsing."""
        # Test various units
        assert parse_file_size("2.5 MB") == 2621440  # 2.5 * 1024 * 1024
        assert parse_file_size("1024 KB") == 1048576  # 1024 * 1024
        assert parse_file_size("512 bytes") == 512
        assert parse_file_size("1 GB") == 1073741824

        # Test case insensitivity
        assert parse_file_size("2.5 mb") == 2621440
        assert parse_file_size("1024 KILOBYTES") == 1048576

        # Test invalid input
        assert parse_file_size("") is None
        assert parse_file_size("unknown") is None
        assert parse_file_size("2.5 TB") is None  # Unsupported unit

    def test_normalize_url(self):
        """Test URL normalization."""
        base = "https://example.com/path/"

        # Test absolute URLs (no change)
        assert (
            normalize_url("https://test.com/file.pdf", base)
            == "https://test.com/file.pdf"
        )
        assert (
            normalize_url("http://test.com/file.pdf", base)
            == "http://test.com/file.pdf"
        )

        # Test relative URLs
        assert (
            normalize_url("/download/file.pdf", base)
            == "https://example.com/download/file.pdf"
        )
        assert normalize_url("../file.pdf", base) == "https://example.com/file.pdf"
        assert normalize_url("file.pdf", base) == "https://example.com/path/file.pdf"

        # Test protocol-relative URLs
        assert (
            normalize_url("//cdn.example.com/file.pdf", base)
            == "https://cdn.example.com/file.pdf"
        )

        # Test empty URL
        assert normalize_url("", base) == ""

    def test_extract_state_code(self):
        """Test state code extraction."""
        # Test simple cases
        assert extract_state_code("Minneapolis, MN 55401") == "MN"
        assert extract_state_code("New York, NY") == "NY"
        assert extract_state_code("CA 90210") == "CA"

        # Test with other text
        assert extract_state_code("Located in WI near the border") == "WI"
        assert extract_state_code("TX-based company") == "TX"

        # Test DC
        assert extract_state_code("Washington, DC 20001") == "DC"

        # Test no match
        assert extract_state_code("No state here") is None
        assert extract_state_code("XX is not a state") is None
        assert extract_state_code("") is None

    def test_clean_text(self):
        """Test text cleaning."""
        # Test HTML entities
        assert clean_text("A &amp; B") == "A & B"
        assert clean_text("&lt;tag&gt;") == "<tag>"
        assert clean_text("Don&#39;t") == "Don't"
        assert clean_text("&quot;quoted&quot;") == '"quoted"'
        assert clean_text("space&nbsp;here") == "space here"

        # Test whitespace normalization
        assert clean_text("  multiple   spaces  ") == "multiple spaces"
        assert clean_text("line\nbreaks\r\nand\ttabs") == "line breaks and tabs"

        # Test empty string
        assert clean_text("") == ""
        assert clean_text("   ") == ""

    def test_format_franchise_name(self):
        """Test franchise name formatting."""
        # Test basic formatting
        assert format_franchise_name("subway restaurants") == "Subway Restaurants"
        assert format_franchise_name("MCDONALDS CORP") == "Mcdonalds Corp"

        # Test suffix removal
        assert format_franchise_name("Franchise Name, LLC") == "Franchise Name"
        assert format_franchise_name("Company Inc.") == "Company"
        assert format_franchise_name("Business Corp.") == "Business"

        # Test parentheses removal
        assert format_franchise_name("Franchise (USA)") == "Franchise"

        # Test special capitalization
        assert format_franchise_name("test llc company") == "Test LLC Company"
        assert format_franchise_name("fdd document inc") == "FDD Document Inc"

        # Test empty/unknown
        assert format_franchise_name("") == "Unknown Franchise"
        assert format_franchise_name("   ") == "Unknown Franchise"

    def test_create_document_filename(self):
        """Test document filename creation."""
        # Basic filename
        filename = create_document_filename("Test Franchise", year="2024")
        assert filename == "2024_Test Franchise.pdf"

        # With all parameters
        filename = create_document_filename(
            "Test/Franchise",
            year="2024",
            filing_number="12345",
            document_type="Amendment",
            uuid="abc123",
        )
        assert filename == "abc123_2024_TestFranchise_Amendment_#12345.pdf"

        # Different extension
        filename = create_document_filename("Test", extension=".txt")
        assert filename.endswith(".txt")

        # Default FDD type not added
        filename = create_document_filename("Test", document_type="FDD")
        assert "_FDD" not in filename

    def test_extract_year_from_text(self):
        """Test year extraction from text."""
        # Test 4-digit years
        assert extract_year_from_text("Filed in 2023") == "2023"
        assert extract_year_from_text("Document from 2024") == "2024"
        assert extract_year_from_text("Year: 2025") == "2025"

        # Test 2-digit years with context
        assert extract_year_from_text("Filed in '23") == "2023"
        assert extract_year_from_text("From 1999") == "1999"

        # Test no year
        assert extract_year_from_text("No year here") is None
        assert extract_year_from_text("") is None

    def test_parse_address(self):
        """Test address parsing."""
        # Test full address
        result = parse_address("123 Main St, Minneapolis, MN 55401")
        assert result["street"] == "123 Main St"
        assert result["city"] == "Minneapolis"
        assert result["state"] == "MN"
        assert result["zip"] == "55401"

        # Test address with ZIP+4
        result = parse_address("456 Oak Ave, Chicago, IL 60601-1234")
        assert result["zip"] == "60601-1234"

        # Test address without commas
        result = parse_address("789 Pine Rd Denver CO 80202")
        assert result["state"] == "CO"
        assert result["zip"] == "80202"

        # Test empty address
        result = parse_address("")
        assert result["full_address"] == ""
        assert result["street"] == ""

    def test_calculate_retry_delay(self):
        """Test retry delay calculation."""
        # Test exponential backoff
        assert calculate_retry_delay(0) == 1.0  # 2^0 = 1
        assert calculate_retry_delay(1) == 2.0  # 2^1 = 2
        assert calculate_retry_delay(2) == 4.0  # 2^2 = 4
        assert calculate_retry_delay(3) == 8.0  # 2^3 = 8

        # Test max delay cap
        assert calculate_retry_delay(10) == 60.0  # Capped at max_delay

        # Test custom parameters
        assert calculate_retry_delay(2, base_delay=2.0) == 8.0  # 2 * 2^2
        assert calculate_retry_delay(5, max_delay=20.0) == 20.0  # Capped at 20
