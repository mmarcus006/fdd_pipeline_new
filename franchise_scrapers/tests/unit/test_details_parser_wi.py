"""Unit tests for Wisconsin details parser."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from pathlib import Path

from franchise_scrapers.wi.details import (
    WIDetailsScraper,
    scrape_single_details,
    scrape_wi_details,
    export_details_to_csv,
    scrape_from_csv
)
from franchise_scrapers.models import WIRegisteredRow, WIDetailsRow


class TestWIDetailsScraper:
    """Test WIDetailsScraper class methods."""
    
    @pytest.fixture
    def mock_page(self):
        """Create a mock page object."""
        page = AsyncMock()
        page.goto = AsyncMock()
        page.content = AsyncMock()
        page.query_selector = AsyncMock()
        page.title = AsyncMock()
        page.expect_download = MagicMock()
        return page
    
    @pytest.fixture
    def scraper(self, mock_page):
        """Create a scraper instance with mock page."""
        return WIDetailsScraper(mock_page)
    
    @pytest.fixture
    def sample_registered_row(self):
        """Create a sample registered row."""
        return WIRegisteredRow(
            filing_number="12345",
            legal_name="Test Franchise LLC",
            details_url="https://apps.dfi.wi.gov/apps/Details.aspx?id=12345"
        )
    
    @pytest.mark.asyncio
    async def test_scrape_details_success(self, scraper, mock_page, sample_registered_row):
        """Test successful details scraping."""
        # Mock page content with all fields
        mock_page.content.return_value = """
        <html>
            <body>
                Filing Number: "12345"
                Filing Status: Registered
                Franchise Legal Name: "Test Franchise LLC"
                Franchise Trade Name (DBA): "Test Brand"
                Email: info@testfranchise.com
                Effective Date: 01/15/2024
            </body>
        </html>
        """
        
        # Mock successful PDF download
        mock_download = AsyncMock()
        mock_download.save_as = AsyncMock()
        
        mock_download_context = AsyncMock()
        mock_download_context.__aenter__ = AsyncMock(return_value=None)
        mock_download_context.__aexit__ = AsyncMock(return_value=None)
        mock_download_context.value = mock_download
        
        mock_page.expect_download.return_value = mock_download_context
        
        # Mock download button
        mock_button = AsyncMock()
        mock_page.query_selector.return_value = mock_button
        
        # Execute
        result = await scraper.scrape_details(sample_registered_row)
        
        # Verify
        assert result is not None
        assert result.filing_number == "12345"
        assert result.status == "Registered"
        assert result.legal_name == "Test Franchise LLC"
        assert result.trade_name == "Test Brand"
        assert result.contact_email == "info@testfranchise.com"
        assert result.pdf_status == "ok"
        assert result.pdf_path is not None
    
    @pytest.mark.asyncio
    async def test_scrape_details_error_handling(self, scraper, mock_page, sample_registered_row):
        """Test error handling during scraping."""
        # Mock page.goto to raise exception
        mock_page.goto.side_effect = Exception("Network error")
        
        # Execute
        result = await scraper.scrape_details(sample_registered_row)
        
        # Verify error row is created
        assert result is not None
        assert result.filing_number == "12345"
        assert result.status == "Error"
        assert result.legal_name == "Test Franchise LLC"
        assert result.pdf_status == "failed"
        assert result.pdf_path is None
    
    @pytest.mark.asyncio
    async def test_extract_metadata_all_fields(self, scraper, mock_page):
        """Test extracting all metadata fields."""
        mock_page.content.return_value = """
        <html>
            <body>
                <div>Filing Number: generic: "54321"</div>
                <div>Filing Status: generic: Registered</div>
                <div>Franchise Legal Name: generic: "Wisconsin Franchise Inc."</div>
                <div>Franchise Trade Name (DBA): generic: "WF Trading"</div>
                <div>Franchise Business Address: generic: "123 Main St, Madison, WI"</div>
                <div>Email: generic: "contact@wf.com"</div>
                <div>Effective Date: cell "12/31/2024"</div>
                <div>Type: cell "Initial"</div>
                <div>States Application Filed: 
                    <span>text: "WI"</span>
                    <span>text: "IL"</span>
                    <span>text: "MN"</span>
                </div>
            </body>
        </html>
        """
        
        metadata = await scraper._extract_metadata()
        
        assert metadata['filing_number'] == "54321"
        assert metadata['status'] == "Registered"
        assert metadata['legal_name'] == "Wisconsin Franchise Inc."
        assert metadata['trade_name'] == "WF Trading"
        assert metadata['business_address'] == "123 Main St, Madison, WI"
        assert metadata['contact_email'] == "contact@wf.com"
        assert metadata['effective_date'] == "12/31/2024"
        assert metadata['filing_type'] == "Initial"
        assert metadata['states_filed'] == ["WI", "IL", "MN"]
    
    @pytest.mark.asyncio
    async def test_extract_metadata_partial_fields(self, scraper, mock_page):
        """Test extracting metadata with missing fields."""
        mock_page.content.return_value = """
        <html>
            <body>
                <div>Filing Number: "12345"</div>
                <div>Filing Status: Registered</div>
                <div>Franchise Legal Name: "Test Franchise"</div>
                <!-- No trade name, email, or other optional fields -->
            </body>
        </html>
        """
        
        metadata = await scraper._extract_metadata()
        
        assert metadata['filing_number'] == "12345"
        assert metadata['status'] == "Registered"
        assert metadata['legal_name'] == "Test Franchise"
        assert 'trade_name' not in metadata
        assert 'contact_email' not in metadata
    
    @pytest.mark.asyncio
    async def test_extract_metadata_email_variations(self, scraper, mock_page):
        """Test extracting email with different formats."""
        test_cases = [
            ('Email: info@test.com', 'info@test.com'),
            ('E-mail: generic: "contact@franchise.org"', 'contact@franchise.org'),
            ('Email: support@test-franchise.co.uk', 'support@test-franchise.co.uk'),
            ('Email: user.name+tag@example.com', 'user.name+tag@example.com'),
        ]
        
        for html_snippet, expected_email in test_cases:
            mock_page.content.return_value = f"<html><body>{html_snippet}</body></html>"
            metadata = await scraper._extract_metadata()
            assert metadata.get('contact_email') == expected_email
    
    @pytest.mark.asyncio
    async def test_extract_metadata_from_title(self, scraper, mock_page):
        """Test extracting legal name from page title as fallback."""
        mock_page.content.return_value = "<html><body><!-- No legal name in content --></body></html>"
        mock_page.title.return_value = "Test Franchise LLC Details"
        
        metadata = await scraper._extract_metadata()
        
        assert metadata['legal_name'] == "Test Franchise LLC"
    
    @pytest.mark.asyncio
    async def test_download_pdf_success(self, scraper, mock_page):
        """Test successful PDF download."""
        # Mock download button
        mock_button = AsyncMock()
        mock_page.query_selector.return_value = mock_button
        
        # Mock download
        mock_download = AsyncMock()
        mock_download.save_as = AsyncMock()
        
        mock_download_context = AsyncMock()
        mock_download_context.__aenter__ = AsyncMock(return_value=None)
        mock_download_context.__aexit__ = AsyncMock(return_value=None)
        mock_download_context.value = mock_download
        
        mock_page.expect_download.return_value = mock_download_context
        
        metadata = {
            'filing_number': '12345',
            'legal_name': 'Test Franchise LLC'
        }
        
        pdf_path, status = await scraper._download_pdf(metadata)
        
        assert status == 'ok'
        assert pdf_path is not None
        assert '12345_test_franchise_llc.pdf' in pdf_path
    
    @pytest.mark.asyncio
    async def test_download_pdf_no_button(self, scraper, mock_page):
        """Test when download button is not found."""
        mock_page.query_selector.return_value = None
        
        pdf_path, status = await scraper._download_pdf({})
        
        assert pdf_path is None
        assert status == 'skipped'
    
    @pytest.mark.asyncio
    async def test_download_pdf_download_fails(self, scraper, mock_page):
        """Test when PDF download fails."""
        mock_button = AsyncMock()
        mock_page.query_selector.return_value = mock_button
        
        # Mock download failure
        mock_button.click.side_effect = Exception("Download failed")
        
        pdf_path, status = await scraper._download_pdf({})
        
        assert pdf_path is None
        assert status == 'failed'
    
    @pytest.mark.asyncio
    async def test_download_pdf_filename_sanitization(self, scraper, mock_page):
        """Test filename sanitization for PDFs."""
        mock_button = AsyncMock()
        mock_page.query_selector.return_value = mock_button
        
        mock_download = AsyncMock()
        mock_download.save_as = AsyncMock()
        
        mock_download_context = AsyncMock()
        mock_download_context.__aenter__ = AsyncMock(return_value=None)
        mock_download_context.__aexit__ = AsyncMock(return_value=None)
        mock_download_context.value = mock_download
        
        mock_page.expect_download.return_value = mock_download_context
        
        metadata = {
            'filing_number': '98765',
            'legal_name': 'Test & Franchise, Inc.'  # Special characters
        }
        
        pdf_path, status = await scraper._download_pdf(metadata)
        
        assert status == 'ok'
        assert '98765_test__franchise_inc.pdf' in pdf_path  # Special chars removed


class TestScrapeSingleDetails:
    """Test scrape_single_details function."""
    
    @pytest.mark.asyncio
    async def test_scrape_single_details_success(self):
        """Test successful single details scraping."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        
        # Mock page content
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="""
            <html><body>Filing Number: "12345"</body></html>
        """)
        mock_page.query_selector = AsyncMock(return_value=None)  # No download button
        
        with patch('franchise_scrapers.wi.details.get_context', return_value=mock_context):
            registered_row = WIRegisteredRow(
                filing_number="12345",
                legal_name="Test",
                details_url="https://example.com"
            )
            
            result = await scrape_single_details(mock_browser, registered_row)
            
            assert result is not None
            assert result.filing_number == "12345"
            assert mock_context.close.called


class TestScrapeWIDetails:
    """Test scrape_wi_details batch processing."""
    
    @pytest.mark.asyncio
    async def test_scrape_wi_details_batch_processing(self):
        """Test batch processing of multiple franchises."""
        # Create test data
        registered_rows = [
            WIRegisteredRow(
                filing_number=str(i),
                legal_name=f"Franchise {i}",
                details_url=f"https://example.com/{i}"
            )
            for i in range(5)
        ]
        
        # Mock browser and scraping
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()
        
        # Mock individual scrapes
        async def mock_scrape_single(browser, row):
            return WIDetailsRow(
                filing_number=row.filing_number,
                status="Registered",
                legal_name=row.legal_name,
                pdf_status="ok",
                scraped_at=datetime.utcnow()
            )
        
        with patch('franchise_scrapers.wi.details.get_browser', return_value=mock_browser):
            with patch('franchise_scrapers.wi.details.scrape_single_details', side_effect=mock_scrape_single):
                with patch('franchise_scrapers.wi.details.export_details_to_csv', new_callable=AsyncMock):
                    results = await scrape_wi_details(registered_rows, max_workers=2)
        
        assert len(results) == 5
        assert all(isinstance(r, WIDetailsRow) for r in results)
        assert mock_browser.close.called
    
    @pytest.mark.asyncio
    async def test_scrape_wi_details_error_handling(self):
        """Test error handling in batch processing."""
        registered_rows = [
            WIRegisteredRow(
                filing_number="1",
                legal_name="Good Franchise",
                details_url="https://example.com/1"
            ),
            WIRegisteredRow(
                filing_number="2",
                legal_name="Bad Franchise",
                details_url="https://example.com/2"
            )
        ]
        
        mock_browser = AsyncMock()
        
        # Mock one success and one failure
        async def mock_scrape_single(browser, row):
            if row.filing_number == "1":
                return WIDetailsRow(
                    filing_number="1",
                    status="Registered",
                    legal_name="Good Franchise",
                    pdf_status="ok",
                    scraped_at=datetime.utcnow()
                )
            else:
                raise Exception("Scraping failed")
        
        with patch('franchise_scrapers.wi.details.get_browser', return_value=mock_browser):
            with patch('franchise_scrapers.wi.details.scrape_single_details', side_effect=mock_scrape_single):
                with patch('franchise_scrapers.wi.details.export_details_to_csv', new_callable=AsyncMock):
                    results = await scrape_wi_details(registered_rows, max_workers=1)
        
        # Should only have the successful result
        assert len(results) == 1
        assert results[0].filing_number == "1"


class TestExportDetailsToCSV:
    """Test CSV export functionality."""
    
    @pytest.mark.asyncio
    async def test_export_details_to_csv(self, tmp_path):
        """Test exporting details to CSV."""
        # Create test data
        details_rows = [
            WIDetailsRow(
                filing_number="12345",
                status="Registered",
                legal_name="Test Franchise 1",
                trade_name="TF1",
                contact_email="tf1@example.com",
                pdf_path="12345_tf1.pdf",
                pdf_status="ok",
                scraped_at=datetime(2024, 1, 15, 10, 30, 0)
            ),
            WIDetailsRow(
                filing_number="67890",
                status="Registered",
                legal_name="Test Franchise 2",
                trade_name=None,
                contact_email=None,
                pdf_path=None,
                pdf_status="failed",
                scraped_at=datetime(2024, 1, 15, 10, 45, 0)
            )
        ]
        
        # Mock settings to use temp directory
        with patch('franchise_scrapers.wi.details.settings') as mock_settings:
            mock_settings.DOWNLOAD_DIR = tmp_path
            
            await export_details_to_csv(details_rows)
            
            # Verify CSV was created
            csv_path = tmp_path / "wi_details_filings.csv"
            assert csv_path.exists()
            
            # Read and verify content
            with open(csv_path, 'r') as f:
                lines = f.readlines()
            
            assert len(lines) == 3  # Header + 2 rows
            assert "filing_number" in lines[0]
            assert "12345" in lines[1]
            assert "67890" in lines[2]
            assert "tf1@example.com" in lines[1]
            assert "TF1" in lines[1]


class TestScrapeFromCSV:
    """Test loading from CSV and scraping."""
    
    @pytest.mark.asyncio
    async def test_scrape_from_csv(self, tmp_path):
        """Test loading registered filings from CSV."""
        # Create test CSV
        csv_path = tmp_path / "wi_registered_filings.csv"
        with open(csv_path, 'w') as f:
            f.write("filing_number,legal_name,details_url\n")
            f.write("12345,Test Franchise,https://example.com/12345\n")
            f.write("67890,Another Franchise,https://example.com/67890\n")
        
        # Mock scraping function
        async def mock_scrape_wi_details(rows):
            return [
                WIDetailsRow(
                    filing_number=row.filing_number,
                    status="Registered",
                    legal_name=row.legal_name,
                    pdf_status="ok",
                    scraped_at=datetime.utcnow()
                )
                for row in rows
            ]
        
        with patch('franchise_scrapers.wi.details.settings') as mock_settings:
            mock_settings.DOWNLOAD_DIR = tmp_path
            
            with patch('franchise_scrapers.wi.details.scrape_wi_details', side_effect=mock_scrape_wi_details):
                results = await scrape_from_csv(csv_path)
        
        assert len(results) == 2
        assert results[0].filing_number == "12345"
        assert results[1].filing_number == "67890"


class TestRegexPatterns:
    """Test regex patterns used in metadata extraction."""
    
    def test_filing_number_patterns(self):
        """Test various filing number patterns."""
        import re
        pattern = r'Filing Number.*?(?:generic.*?)?:\s*"?(\d+)"?'
        
        test_cases = [
            ('Filing Number: "12345"', "12345"),
            ('Filing Number: generic: "67890"', "67890"),
            ('Filing Number: 11111', "11111"),
            ('Filing Number generic cell: "99999"', "99999"),
        ]
        
        for text, expected in test_cases:
            match = re.search(pattern, text, re.IGNORECASE)
            assert match is not None
            assert match.group(1) == expected
    
    def test_email_pattern(self):
        """Test email extraction pattern."""
        import re
        pattern = r'(?:Email|E-mail).*?(?:generic.*?)?:\s*"?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"?'
        
        test_cases = [
            ('Email: info@test.com', 'info@test.com'),
            ('E-mail: generic: "contact@franchise.org"', 'contact@franchise.org'),
            ('Email generic: user.name@example.co.uk', 'user.name@example.co.uk'),
            ('E-mail: "support+tag@test-site.com"', 'support+tag@test-site.com'),
        ]
        
        for text, expected in test_cases:
            match = re.search(pattern, text, re.IGNORECASE)
            assert match is not None
            assert match.group(1) == expected
    
    def test_states_filed_pattern(self):
        """Test states filed extraction."""
        import re
        
        # First pattern to find the states section
        section_pattern = r'States Application Filed.*?(?:States Filed.*?)?:(.*?)(?:group|Contact Person)'
        
        # Second pattern to extract state codes
        state_pattern = r'(?:text|generic):\s*"?([A-Z]{2})"?'
        
        html = """
        States Application Filed:
        <div>text: "WI"</div>
        <div>generic: "IL"</div>
        <div>text: "MN"</div>
        Contact Person: John Doe
        """
        
        section_match = re.search(section_pattern, html, re.DOTALL | re.IGNORECASE)
        assert section_match is not None
        
        states_text = section_match.group(1)
        states = re.findall(state_pattern, states_text)
        
        assert states == ["WI", "IL", "MN"]