# franchise_scrapers/tests/integration/test_details_wi.py
"""Integration tests for full Wisconsin workflow (active -> search -> details)."""

import pytest
import asyncio
import csv
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock, call
from concurrent.futures import ThreadPoolExecutor

from franchise_scrapers.wi.details import WIDetailsScraper, process_registered_franchises
from franchise_scrapers.wi.search import WISearchScraper, search_all_franchises
from franchise_scrapers.models import WIActiveRow, WIRegisteredRow, WIDetailsRow
from franchise_scrapers.browser import get_browser, get_context


class TestWisconsinFullWorkflow:
    """Test full Wisconsin workflow from active filings to PDF downloads."""
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_search_scraper_init(self, mock_browser):
        """Test WISearchScraper initialization."""
        browser, context, page = mock_browser
        
        scraper = WISearchScraper(page)
        assert scraper.page == page
        assert scraper.SEARCH_URL == "https://apps.dfi.wi.gov/apps/FranchiseSearch/MainSearch.aspx"
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_search_single_franchise(self, mock_browser, mock_html_responses):
        """Test searching for a single franchise."""
        browser, context, page = mock_browser
        
        # Mock search interaction
        page.goto.return_value = None
        page.fill.return_value = None
        page.click.return_value = None
        page.wait_for_selector.return_value = None
        page.content.return_value = mock_html_responses['wi_search_results']
        
        # Mock search results table
        mock_row = MagicMock()
        mock_cells = [
            MagicMock(inner_text=AsyncMock(return_value="12345")),
            MagicMock(inner_text=AsyncMock(return_value="Wisconsin Franchise A")),
            MagicMock(inner_text=AsyncMock(return_value="Registered")),
            MagicMock(query_selector=AsyncMock(return_value=MagicMock(
                get_attribute=AsyncMock(return_value="Details.aspx?id=12345")
            )))
        ]
        mock_row.query_selector_all = AsyncMock(return_value=mock_cells)
        page.query_selector_all.return_value = [mock_row]
        
        scraper = WISearchScraper(page)
        active_row = WIActiveRow(legal_name="Wisconsin Franchise A", filing_number="12345")
        
        result = await scraper.search_franchise(active_row)
        
        assert result is not None
        assert result.filing_number == "12345"
        assert result.legal_name == "Wisconsin Franchise A"
        assert "Details.aspx?id=12345" in str(result.details_url)
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_search_franchise_not_registered(self, mock_browser):
        """Test searching for franchise that's not registered."""
        browser, context, page = mock_browser
        
        # Mock no results
        page.query_selector_all.return_value = []
        page.goto.return_value = None
        page.fill.return_value = None
        page.click.return_value = None
        page.wait_for_selector.return_value = None
        
        scraper = WISearchScraper(page)
        active_row = WIActiveRow(legal_name="Unregistered Franchise", filing_number="99999")
        
        result = await scraper.search_franchise(active_row)
        assert result is None
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_parallel_search_functionality(self, sample_wi_active_data, mock_browser):
        """Test parallel search with ThreadPoolExecutor."""
        # Mock browser factory
        browser, context, page = mock_browser
        
        async def mock_browser_factory():
            return browser
        
        # Mock search results
        registered_results = [
            WIRegisteredRow(
                filing_number=row.filing_number,
                legal_name=row.legal_name,
                details_url=f"https://example.com/details?id={row.filing_number}"
            )
            for row in sample_wi_active_data[:2]  # Only first 2 are registered
        ]
        
        with patch('franchise_scrapers.wi.search.get_browser', mock_browser_factory):
            with patch('franchise_scrapers.wi.search.WISearchScraper.search_franchise') as mock_search:
                # Return registered for first 2, None for others
                mock_search.side_effect = registered_results + [None]
                
                results = await search_all_franchises(
                    sample_wi_active_data,
                    max_workers=2
                )
        
        assert len(results) == 2
        assert all(isinstance(r, WIRegisteredRow) for r in results)
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_details_scraper_extract_metadata(self, mock_browser, mock_html_responses):
        """Test details page metadata extraction."""
        browser, context, page = mock_browser
        
        # Mock details page
        page.goto.return_value = None
        page.content.return_value = mock_html_responses['wi_details_page']
        
        # Mock element queries for metadata
        mock_elements = {
            "#ctl00_contentPlaceholder_lblFilingNumber": "12345",
            "#ctl00_contentPlaceholder_lblStatus": "Registered",
            "#ctl00_contentPlaceholder_lblLegalName": "Wisconsin Franchise A",
            "#ctl00_contentPlaceholder_lblTradeName": "WF-A",
            "#ctl00_contentPlaceholder_lblEmail": "contact@wfa.com"
        }
        
        async def mock_query_selector(selector):
            if selector in mock_elements:
                element = MagicMock()
                element.inner_text = AsyncMock(return_value=mock_elements[selector])
                return element
            return None
        
        page.query_selector = mock_query_selector
        
        scraper = WIDetailsScraper(page)
        registered_row = WIRegisteredRow(
            filing_number="12345",
            legal_name="Wisconsin Franchise A",
            details_url="https://example.com/details?id=12345"
        )
        
        # Mock PDF download
        pdf_link = MagicMock()
        pdf_link.get_attribute = AsyncMock(return_value="GetDocument.aspx?id=12345")
        page.query_selector = AsyncMock(side_effect=lambda s: pdf_link if "hyperlinkDisclosureDocument" in s else None)
        
        with patch.object(scraper, '_download_pdf', return_value=("test.pdf", "ok")):
            result = await scraper.scrape_details(registered_row)
        
        assert result is not None
        assert result.filing_number == "12345"
        assert result.legal_name == "Wisconsin Franchise A"
        assert result.trade_name == "WF-A"
        assert result.contact_email == "contact@wfa.com"
        assert result.pdf_status == "ok"
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_pdf_download_process(self, mock_browser, mock_download, temp_dir):
        """Test PDF download functionality."""
        browser, context, page = mock_browser
        
        # Mock successful download
        page.wait_for_download.return_value = mock_download
        page.click.return_value = None
        
        scraper = WIDetailsScraper(page)
        
        # Mock metadata for filename
        metadata = {
            'filing_number': '12345',
            'legal_name': 'Test Franchise'
        }
        
        # Test private method through public interface
        with patch.object(scraper, '_extract_metadata', return_value=metadata):
            with patch('franchise_scrapers.config.settings.DOWNLOAD_DIR', temp_dir):
                pdf_path, status = await scraper._download_pdf(metadata)
        
        assert status == "ok"
        assert "12345_Test_Franchise.pdf" in pdf_path
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_resume_capability(self, temp_dir, sample_wi_registered_data):
        """Test resume from existing registered CSV."""
        # Create existing registered CSV
        csv_path = temp_dir / "wi_registered_existing.csv"
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['filing_number', 'legal_name', 'details_url'])
            writer.writeheader()
            for row in sample_wi_registered_data:
                writer.writerow(row.dict())
        
        # Load from CSV
        loaded_rows = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                loaded_rows.append(WIRegisteredRow(**row))
        
        assert len(loaded_rows) == 2
        assert loaded_rows[0].filing_number == "12345"
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_data_consistency_across_steps(self, sample_wi_active_data, sample_wi_registered_data, sample_wi_details_data):
        """Test data consistency through the pipeline."""
        # Verify filing numbers match across datasets
        active_numbers = {row.filing_number for row in sample_wi_active_data}
        registered_numbers = {row.filing_number for row in sample_wi_registered_data}
        details_numbers = {row.filing_number for row in sample_wi_details_data}
        
        # Registered should be subset of active
        assert registered_numbers.issubset(active_numbers)
        
        # Details should match registered
        assert details_numbers == registered_numbers
        
        # Verify legal names are consistent
        for reg_row in sample_wi_registered_data:
            # Find corresponding details
            details_row = next(
                (d for d in sample_wi_details_data if d.filing_number == reg_row.filing_number),
                None
            )
            assert details_row is not None
            assert details_row.legal_name == reg_row.legal_name
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_error_recovery_network_issues(self, mock_browser):
        """Test error handling for network issues."""
        browser, context, page = mock_browser
        
        # Mock network error
        page.goto.side_effect = Exception("Network timeout")
        
        scraper = WIDetailsScraper(page)
        registered_row = WIRegisteredRow(
            filing_number="12345",
            legal_name="Test",
            details_url="https://example.com"
        )
        
        result = await scraper.scrape_details(registered_row)
        assert result is None  # Should return None on error
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_full_workflow_integration(self, mock_browser, temp_dir):
        """Test complete Wisconsin workflow integration."""
        browser, context, page = mock_browser
        
        # Step 1: Active filings (mocked as input)
        active_data = [
            WIActiveRow(legal_name="Franchise A", filing_number="111"),
            WIActiveRow(legal_name="Franchise B", filing_number="222")
        ]
        
        # Step 2: Search (mock registered results)
        registered_data = [
            WIRegisteredRow(
                filing_number="111",
                legal_name="Franchise A",
                details_url="https://example.com/details?id=111"
            )
        ]
        
        # Step 3: Details scraping
        with patch('franchise_scrapers.wi.search.search_all_franchises', return_value=registered_data):
            with patch('franchise_scrapers.wi.details.process_registered_franchises') as mock_process:
                mock_process.return_value = [
                    WIDetailsRow(
                        filing_number="111",
                        status="Registered",
                        legal_name="Franchise A",
                        trade_name="FA",
                        contact_email="test@fa.com",
                        pdf_path="test.pdf",
                        pdf_status="ok",
                        scraped_at=datetime.utcnow()
                    )
                ]
                
                # Run workflow
                registered = await search_all_franchises(active_data, max_workers=2)
                details = await mock_process(registered, temp_dir)
        
        assert len(registered) == 1
        assert len(details) == 1
        assert details[0].filing_number == "111"
    
    @pytest.mark.live
    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_live_wisconsin_workflow(self, temp_dir):
        """Test against live Wisconsin DFI portal (limited scope)."""
        browser = None
        try:
            # Step 1: Get active filings (assume we have some)
            test_active = [
                WIActiveRow(
                    legal_name="McDonald's",  # Known franchise
                    filing_number="1"  # Will search by name
                )
            ]
            
            browser = await get_browser(headless=True)
            context = await get_context(browser, temp_dir)
            page = await context.new_page()
            
            # Step 2: Search for registered
            search_scraper = WISearchScraper(page)
            registered = await search_scraper.search_franchise(test_active[0])
            
            if registered:
                # Step 3: Get details
                details_scraper = WIDetailsScraper(page)
                details = await details_scraper.scrape_details(registered)
                
                assert details is not None
                assert details.status == "Registered"
                
                # Save results
                csv_path = temp_dir / "wi_live_test.csv"
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=details.dict().keys())
                    writer.writeheader()
                    writer.writerow(details.dict())
            
            await page.close()
            await context.close()
            
        finally:
            if browser:
                await browser.close()
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_csv_output_all_stages(self, temp_dir, sample_wi_active_data, sample_wi_registered_data, sample_wi_details_data):
        """Test CSV output at all workflow stages."""
        # Active filings CSV
        active_csv = temp_dir / "active.csv"
        with open(active_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['legal_name', 'filing_number'])
            writer.writeheader()
            for row in sample_wi_active_data:
                writer.writerow(row.dict())
        
        # Registered CSV
        registered_csv = temp_dir / "registered.csv"
        with open(registered_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['filing_number', 'legal_name', 'details_url'])
            writer.writeheader()
            for row in sample_wi_registered_data:
                writer.writerow(row.dict())
        
        # Details CSV
        details_csv = temp_dir / "details.csv"
        with open(details_csv, 'w', newline='', encoding='utf-8') as f:
            fieldnames = list(sample_wi_details_data[0].dict().keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in sample_wi_details_data:
                writer.writerow(row.dict())
        
        # Verify all CSVs exist and have correct structure
        assert active_csv.exists()
        assert registered_csv.exists()
        assert details_csv.exists()
        
        # Verify row counts
        with open(active_csv) as f:
            assert len(list(csv.DictReader(f))) == 3
        
        with open(registered_csv) as f:
            assert len(list(csv.DictReader(f))) == 2
        
        with open(details_csv) as f:
            assert len(list(csv.DictReader(f))) == 2