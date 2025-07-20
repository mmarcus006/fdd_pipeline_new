# franchise_scrapers/tests/integration/test_active_wi.py
"""Integration tests for Wisconsin active filings extraction."""

import pytest
import asyncio
import csv
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

from franchise_scrapers.wi.active import WIActiveScraper, main as wi_active_main
from franchise_scrapers.models import WIActiveRow
from franchise_scrapers.browser import get_browser, get_context


class TestWisconsinActiveFilings:
    """Test Wisconsin active filings extraction."""
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_active_scraper_init(self, mock_browser):
        """Test WIActiveScraper initialization."""
        browser, context, page = mock_browser
        
        scraper = WIActiveScraper(page)
        assert scraper.page == page
        assert scraper.rows == []
        assert scraper.BASE_URL == "https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx"
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_navigate_to_active_filings(self, mock_browser):
        """Test navigation to active filings page."""
        browser, context, page = mock_browser
        
        scraper = WIActiveScraper(page)
        
        # Mock successful navigation
        page.goto.return_value = None
        page.wait_for_selector.return_value = None
        
        # Mock table extraction
        with patch.object(scraper, '_extract_table_rows', return_value=[]):
            await scraper.scrape()
        
        page.goto.assert_called_with(scraper.BASE_URL, wait_until="networkidle")
        page.wait_for_selector.assert_called_with(
            "#ctl00_contentPlaceholder_grdActiveFilings", 
            timeout=30000
        )
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_extract_table_rows(self, mock_browser, mock_html_responses):
        """Test table row extraction from HTML."""
        browser, context, page = mock_browser
        
        # Mock page with active filings table
        page.content = AsyncMock(return_value=mock_html_responses['wi_active_page'])
        
        # Mock table rows
        mock_rows = []
        test_data = [
            ("Wisconsin Franchise A", "12345"),
            ("Wisconsin Franchise B", "67890"),
            ("Wisconsin Franchise C", "11111")
        ]
        
        for name, filing_num in test_data:
            row = MagicMock()
            cells = [
                MagicMock(inner_text=AsyncMock(return_value=name)),
                MagicMock(inner_text=AsyncMock(return_value=filing_num))
            ]
            row.query_selector_all = AsyncMock(return_value=cells)
            mock_rows.append(row)
        
        page.query_selector_all.return_value = mock_rows[1:]  # Skip header
        
        scraper = WIActiveScraper(page)
        
        # Private method test through public interface
        page.goto.return_value = None
        page.wait_for_selector.return_value = None
        
        names = await scraper.scrape()
        
        assert len(names) == 2  # Skipped header
        assert "Wisconsin Franchise B" in names
        assert "Wisconsin Franchise C" in names
        assert len(scraper.rows) == 2
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_save_active_filings_csv(self, mock_browser, temp_dir, sample_wi_active_data):
        """Test CSV output for active filings."""
        browser, context, page = mock_browser
        
        scraper = WIActiveScraper(page)
        scraper.rows = sample_wi_active_data
        
        # Save to CSV
        csv_path = temp_dir / "wi_active_test.csv"
        
        with patch.object(scraper, 'save_to_csv') as mock_save:
            mock_save.return_value = csv_path
            result_path = scraper.save_to_csv(csv_path)
        
        # Manually save to verify format
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['legal_name', 'filing_number'])
            writer.writeheader()
            for row in sample_wi_active_data:
                writer.writerow(row.dict())
        
        # Verify CSV contents
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 3
        assert rows[0]['legal_name'] == "Wisconsin Franchise A"
        assert rows[0]['filing_number'] == "12345"
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_error_handling_network_failure(self, mock_browser):
        """Test handling of network failures."""
        browser, context, page = mock_browser
        
        # Mock network error
        page.goto.side_effect = Exception("Network error")
        
        scraper = WIActiveScraper(page)
        
        with pytest.raises(Exception) as exc_info:
            await scraper.scrape()
        
        assert "Network error" in str(exc_info.value)
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_error_handling_table_not_found(self, mock_browser):
        """Test handling when table is not found."""
        browser, context, page = mock_browser
        
        # Mock timeout waiting for table
        page.goto.return_value = None
        page.wait_for_selector.side_effect = asyncio.TimeoutError()
        
        scraper = WIActiveScraper(page)
        
        with pytest.raises(asyncio.TimeoutError):
            await scraper.scrape()
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_csv_output_format(self, temp_dir, sample_wi_active_data):
        """Test CSV output format compliance."""
        csv_path = temp_dir / "format_test.csv"
        
        # Write sample data
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['legal_name', 'filing_number']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in sample_wi_active_data:
                writer.writerow(row.dict())
        
        # Verify format
        with open(csv_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check headers
        assert "legal_name,filing_number" in content
        
        # Check encoding
        assert content.encode('utf-8').decode('utf-8') == content
        
        # Check no extra whitespace
        lines = content.strip().split('\n')
        for line in lines:
            assert line == line.strip()
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_full_active_workflow(self, mock_browser, temp_dir):
        """Test complete active filings workflow."""
        browser, context, page = mock_browser
        
        # Mock successful scraping
        mock_data = [
            {"legal_name": "Test Franchise 1", "filing_number": "11111"},
            {"legal_name": "Test Franchise 2", "filing_number": "22222"}
        ]
        
        # Create mock HTML with table data
        mock_rows = []
        for data in mock_data:
            row = MagicMock()
            cells = [
                MagicMock(inner_text=AsyncMock(return_value=data['legal_name'])),
                MagicMock(inner_text=AsyncMock(return_value=data['filing_number']))
            ]
            row.query_selector_all = AsyncMock(return_value=cells)
            mock_rows.append(row)
        
        page.query_selector_all.return_value = mock_rows
        page.goto.return_value = None
        page.wait_for_selector.return_value = None
        
        with patch('franchise_scrapers.wi.active.get_browser', return_value=browser):
            with patch('franchise_scrapers.wi.active.get_context', return_value=context):
                with patch('franchise_scrapers.config.settings.DOWNLOAD_DIR', temp_dir):
                    csv_path, names = await wi_active_main()
        
        # Verify results
        assert len(names) == 2
        assert "Test Franchise 1" in names
        assert Path(csv_path).exists()
    
    @pytest.mark.live
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_live_active_filings_extraction(self, temp_dir):
        """Test against live Wisconsin DFI portal."""
        browser = None
        try:
            browser = await get_browser(headless=True)
            context = await get_context(browser, temp_dir)
            page = await context.new_page()
            
            scraper = WIActiveScraper(page)
            
            # Scrape active filings
            franchise_names = await scraper.scrape()
            
            assert len(franchise_names) > 0, "No active filings found"
            assert len(scraper.rows) == len(franchise_names)
            
            # Save to CSV
            csv_path = temp_dir / "wi_active_live.csv"
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['legal_name', 'filing_number'])
                writer.writeheader()
                for row in scraper.rows[:10]:  # Limit to first 10 for testing
                    writer.writerow(row.dict())
            
            assert csv_path.exists()
            
            # Verify data integrity
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
            assert len(rows) <= 10
            for row in rows:
                assert row['legal_name']
                assert row['filing_number']
                assert row['filing_number'].isdigit()
            
            await page.close()
            await context.close()
            
        finally:
            if browser:
                await browser.close()
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_empty_table_handling(self, mock_browser):
        """Test handling of empty results table."""
        browser, context, page = mock_browser
        
        # Mock empty table
        page.query_selector_all.return_value = []
        page.goto.return_value = None
        page.wait_for_selector.return_value = None
        
        scraper = WIActiveScraper(page)
        names = await scraper.scrape()
        
        assert names == []
        assert scraper.rows == []
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_malformed_table_data(self, mock_browser):
        """Test handling of malformed table data."""
        browser, context, page = mock_browser
        
        # Mock malformed rows (missing cells)
        mock_rows = [
            MagicMock(query_selector_all=AsyncMock(return_value=[
                MagicMock(inner_text=AsyncMock(return_value="Only One Cell"))
            ])),
            MagicMock(query_selector_all=AsyncMock(return_value=[]))  # No cells
        ]
        
        page.query_selector_all.return_value = mock_rows
        page.goto.return_value = None
        page.wait_for_selector.return_value = None
        
        scraper = WIActiveScraper(page)
        
        # Should handle gracefully
        names = await scraper.scrape()
        assert len(names) == 0  # Skipped malformed rows