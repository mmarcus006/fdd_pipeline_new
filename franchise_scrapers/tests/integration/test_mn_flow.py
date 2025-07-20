# franchise_scrapers/tests/integration/test_mn_flow.py
"""Integration tests for Minnesota CARDS portal scraping workflow."""

import pytest
import asyncio
import csv
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from playwright.async_api import TimeoutError as PlaywrightTimeout

from franchise_scrapers.mn.scraper import (
    navigate_to_search,
    extract_table_data,
    handle_pagination,
    save_to_csv,
    download_pdf,
    process_all_fdds,
    main as mn_main
)
from franchise_scrapers.models import CleanFDDRow
from franchise_scrapers.browser import get_browser, get_context


class TestMinnesotaFlow:
    """Test full Minnesota scraping workflow."""
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_navigate_to_search_success(self, mock_browser):
        """Test successful navigation to search page."""
        browser, context, page = mock_browser
        
        # Mock successful page load
        page.goto.return_value = None
        page.wait_for_selector.return_value = None
        
        await navigate_to_search(page)
        
        # Verify navigation
        page.goto.assert_called_once()
        assert "Clean+FDD" in page.goto.call_args[0][0]
        page.wait_for_selector.assert_called_with("#results", timeout=10000)
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_navigate_to_search_timeout(self, mock_browser):
        """Test navigation with timeout handling."""
        browser, context, page = mock_browser
        
        # Mock timeout
        page.goto.return_value = None
        page.wait_for_selector.side_effect = PlaywrightTimeout("Timeout")
        
        # Should not raise, just print warning
        await navigate_to_search(page)
        
        page.goto.assert_called_once()
        page.wait_for_selector.assert_called_once()
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_extract_table_data(self, mock_browser, sample_mn_table_data):
        """Test table data extraction."""
        browser, context, page = mock_browser
        
        # Mock table rows
        mock_rows = []
        for data in sample_mn_table_data:
            row = MagicMock()
            row.query_selector_all = AsyncMock(return_value=[
                MagicMock(inner_text=AsyncMock(return_value=data['legal_name'])),
                MagicMock(query_selector=AsyncMock(return_value=MagicMock(
                    get_attribute=AsyncMock(return_value=data['pdf_url'])
                )))
            ])
            mock_rows.append(row)
        
        page.query_selector_all.return_value = mock_rows
        
        # Extract data
        extracted = await extract_table_data(page)
        
        assert len(extracted) == 2
        assert extracted[0]['legal_name'] == 'Test Franchise Inc.'
        assert extracted[0]['document_id'] == '123456'
        assert 'scraped_at' in extracted[0]
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_pagination_handling(self, mock_browser):
        """Test pagination detection and navigation."""
        browser, context, page = mock_browser
        
        # Mock pagination scenarios
        # First call: has next page
        page.query_selector.side_effect = [
            MagicMock(),  # Next page link exists
            None          # No next page link
        ]
        page.click = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        
        # First call should return True
        has_next = await handle_pagination(page)
        assert has_next is True
        page.click.assert_called_once()
        
        # Second call should return False
        has_next = await handle_pagination(page)
        assert has_next is False
    
    @pytest.mark.mock
    def test_save_to_csv(self, temp_dir, sample_mn_table_data):
        """Test CSV output generation."""
        csv_path = temp_dir / "test_output.csv"
        
        # Convert to CleanFDDRow models
        rows = [
            CleanFDDRow(**data) 
            for data in sample_mn_table_data
        ]
        
        # Save to CSV
        save_to_csv(rows, csv_path)
        
        # Verify CSV contents
        assert csv_path.exists()
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
        
        assert len(csv_rows) == 2
        assert csv_rows[0]['legal_name'] == 'Test Franchise Inc.'
        assert csv_rows[0]['document_id'] == '123456'
        assert 'pdf_url' in csv_rows[0]
        assert 'scraped_at' in csv_rows[0]
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_pdf_download_success(self, mock_browser, mock_download, temp_dir):
        """Test successful PDF download."""
        browser, context, page = mock_browser
        
        # Mock successful download
        page.wait_for_download.return_value = mock_download
        page.goto.return_value = None
        
        row = CleanFDDRow(
            document_id="123456",
            legal_name="Test Franchise",
            pdf_url="https://example.com/fdd.pdf",
            scraped_at=datetime.utcnow()
        )
        
        # Download PDF
        result = await download_pdf(page, row, temp_dir)
        
        assert result.pdf_status == "ok"
        assert result.pdf_path is not None
        assert "123456_Test_Franchise.pdf" in result.pdf_path
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_pdf_download_failure(self, mock_browser, temp_dir):
        """Test PDF download failure handling."""
        browser, context, page = mock_browser
        
        # Mock download failure
        page.wait_for_download.side_effect = Exception("Download failed")
        page.goto.return_value = None
        
        row = CleanFDDRow(
            document_id="123456",
            legal_name="Test Franchise",
            pdf_url="https://example.com/fdd.pdf",
            scraped_at=datetime.utcnow()
        )
        
        # Download should fail gracefully
        result = await download_pdf(page, row, temp_dir)
        
        assert result.pdf_status == "failed"
        assert result.pdf_path is None
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_process_all_fdds_with_downloads(self, mock_browser, temp_dir):
        """Test processing multiple FDDs with downloads."""
        browser, context, page = mock_browser
        
        # Create test rows
        rows = [
            CleanFDDRow(
                document_id=f"{i}",
                legal_name=f"Franchise {i}",
                pdf_url=f"https://example.com/fdd{i}.pdf",
                scraped_at=datetime.utcnow()
            )
            for i in range(3)
        ]
        
        # Mock download results
        async def mock_download_pdf(p, row, download_dir):
            if row.document_id == "1":
                # Simulate failure
                row.pdf_status = "failed"
            else:
                row.pdf_status = "ok"
                row.pdf_path = f"{download_dir}/{row.document_id}_{row.legal_name}.pdf"
            return row
        
        with patch('franchise_scrapers.mn.scraper.download_pdf', side_effect=mock_download_pdf):
            updated_rows = await process_all_fdds(browser, rows, temp_dir, test_mode=True)
        
        assert len(updated_rows) == 3
        assert updated_rows[0].pdf_status == "skipped"  # Test mode
        assert updated_rows[1].pdf_status == "failed"
        assert updated_rows[2].pdf_status == "ok"
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_error_recovery(self, mock_browser):
        """Test error recovery during scraping."""
        browser, context, page = mock_browser
        
        # Mock intermittent failures
        call_count = 0
        
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")
            return []
        
        page.query_selector_all.side_effect = side_effect
        
        # Should retry and succeed
        with patch('franchise_scrapers.browser.with_retry') as mock_retry:
            mock_retry.return_value = extract_table_data
            result = await extract_table_data(page)
            assert isinstance(result, list)
    
    @pytest.mark.mock
    @pytest.mark.asyncio
    async def test_full_workflow_integration(self, mock_browser, temp_dir, mock_html_responses):
        """Test complete Minnesota scraping workflow."""
        browser, context, page = mock_browser
        
        # Mock page responses
        page.content = AsyncMock(return_value=mock_html_responses['mn_search_page'])
        
        # Mock table extraction
        mock_rows = [
            {
                'legal_name': 'Test Franchise Inc.',
                'pdf_url': 'https://example.com/fdd1.pdf',
                'document_id': '123456',
                'scraped_at': datetime.utcnow()
            }
        ]
        
        with patch('franchise_scrapers.mn.scraper.extract_table_data', return_value=mock_rows):
            with patch('franchise_scrapers.mn.scraper.handle_pagination', return_value=False):
                with patch('franchise_scrapers.mn.scraper.process_all_fdds') as mock_process:
                    mock_process.return_value = [CleanFDDRow(**row) for row in mock_rows]
                    
                    # Run main with test configuration
                    with patch('franchise_scrapers.mn.scraper.get_browser', return_value=browser):
                        with patch('franchise_scrapers.mn.scraper.get_context', return_value=context):
                            with patch('franchise_scrapers.config.settings.DOWNLOAD_DIR', temp_dir):
                                await mn_main(test_mode=True, limit=1)
        
        # Verify CSV was created
        csv_files = list(temp_dir.glob("mn_clean_fdds_*.csv"))
        assert len(csv_files) > 0
    
    @pytest.mark.live
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_live_minnesota_scraping(self, temp_dir):
        """Test against live Minnesota CARDS portal."""
        # Only run with explicit --live flag
        browser = None
        try:
            browser = await get_browser(headless=True)
            context = await get_context(browser, temp_dir)
            page = await context.new_page()
            
            # Navigate to search
            await navigate_to_search(page)
            
            # Extract first page only
            rows_data = await extract_table_data(page)
            
            assert len(rows_data) > 0, "No data found on Minnesota portal"
            
            # Convert to models
            rows = [CleanFDDRow(**data) for data in rows_data[:3]]  # Test with first 3
            
            # Save to CSV
            csv_path = temp_dir / "mn_live_test.csv"
            save_to_csv(rows, csv_path)
            
            assert csv_path.exists()
            
            # Optionally download one PDF
            if rows:
                updated_row = await download_pdf(page, rows[0], temp_dir)
                assert updated_row.pdf_status in ["ok", "failed"]
            
            await page.close()
            await context.close()
            
        finally:
            if browser:
                await browser.close()