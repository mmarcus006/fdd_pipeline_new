"""Integration tests for Wisconsin scraper."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from tasks.wisconsin_scraper import WisconsinScraper
from tasks.web_scraping import DocumentMetadata, ExtractionError, NavigationError


@pytest.mark.asyncio
class TestWisconsinScraper:
    """Test suite for Wisconsin franchise portal scraper."""
    
    @pytest_asyncio.fixture
    async def scraper(self):
        """Create a Wisconsin scraper instance for testing."""
        scraper = WisconsinScraper(headless=True, prefect_run_id=uuid4())
        # Mock the initialization to avoid actual browser startup
        scraper.page = AsyncMock()
        scraper.http_client = AsyncMock()
        scraper.logger = MagicMock()
        return scraper
    
    @pytest.fixture
    def mock_active_filings_table_html(self):
        """Mock HTML for the active filings table."""
        return """
        <table id="ctl00_contentPlaceholder_grdActiveFilings">
            <tr>
                <th>Franchise Name</th>
                <th>Status</th>
                <th>Date</th>
            </tr>
            <tr>
                <td>McDonald's Corporation</td>
                <td>Active</td>
                <td>2024-01-15</td>
            </tr>
            <tr>
                <td>Subway &amp; Associates LLC</td>
                <td>Active</td>
                <td>2024-02-20</td>
            </tr>
            <tr>
                <td>Burger King Holdings</td>
                <td>Active</td>
                <td>2024-03-10</td>
            </tr>
        </table>
        """
    
    @pytest.fixture
    def mock_search_results_html(self):
        """Mock HTML for search results with registered franchise."""
        return """
        <table>
            <tr>
                <td>McDonald's Corporation</td>
                <td>Registered</td>
                <td><a href="/details/12345">Details</a></td>
            </tr>
        </table>
        """
    
    @pytest.fixture
    def mock_details_page_content(self):
        """Mock content for franchise details page."""
        return '''
        group "Franchisor Name and Address" [ref=e123]:
        Filing Number generic [ref=e124]: "12345"
        Filing Status generic [ref=e125]: Registered
        Franchise Legal Name generic [ref=e126]: McDonald's Corporation
        Franchise Trade Name (DBA) generic [ref=e127]: McDonald's
        Franchise Business Address generic [ref=e128]: 123 Main St
        - cell [ref=e129]:
        - cell [ref=e130]:
        - generic [ref=e131]: Chicago, IL 60601
        
        group "Filings for this Registration" [ref=e140]:
        Legal Name cell "McDonald's Corporation"
        Trade Name cell "McDonald's"
        Type cell "Initial Registration"
        Status cell "Active"
        Effective cell "2024-01-15"
        
        group "States Application Filed" [ref=e150]:
        States Filed generic [ref=e151]:
        text: Illinois
        text: Wisconsin
        text: Minnesota
        
        group "Contact Person" [ref=e160]:
        '''
    
    async def test_extract_franchise_names_from_table(self, scraper, mock_active_filings_table_html):
        """Test extraction of franchise names from active filings table."""
        # Mock page navigation and table extraction
        scraper.page.wait_for_selector = AsyncMock()
        scraper.page.evaluate = AsyncMock(return_value=mock_active_filings_table_html)
        
        # Mock safe_navigate
        scraper.safe_navigate = AsyncMock()
        
        # Execute the method
        franchise_names = await scraper._extract_franchise_names_from_table()
        
        # Verify results
        expected_names = [
            "McDonald's Corporation",
            "Subway & Associates LLC",  # Should handle HTML entities
            "Burger King Holdings"
        ]
        
        assert franchise_names == expected_names
        assert len(franchise_names) == 3
        
        # Verify method calls
        scraper.safe_navigate.assert_called_once_with(scraper.ACTIVE_FILINGS_URL)
        scraper.page.wait_for_selector.assert_called_once()
        scraper.page.evaluate.assert_called_once()
    
    async def test_perform_franchise_search(self, scraper):
        """Test franchise search functionality."""
        # Mock page elements
        search_input = AsyncMock()
        search_button = AsyncMock()
        
        scraper.page.wait_for_selector = AsyncMock(side_effect=[search_input, search_button])
        scraper.page.wait_for_load_state = AsyncMock()
        
        # Execute the method
        await scraper._perform_franchise_search("McDonald's Corporation")
        
        # Verify interactions
        search_input.fill.assert_called_once_with("McDonald's Corporation")
        search_button.click.assert_called_once()
        scraper.page.wait_for_load_state.assert_called_once_with('networkidle')
    
    async def test_check_for_registered_status(self, scraper, mock_search_results_html):
        """Test checking for registered status in search results."""
        # Mock page content
        scraper.page.content = AsyncMock(return_value=mock_search_results_html)
        
        # Execute the method
        has_registered = await scraper._check_for_registered_status()
        
        # Verify result
        assert has_registered is True
        scraper.page.content.assert_called_once()
    
    async def test_find_registered_details_link(self, scraper):
        """Test finding details link for registered franchise."""
        # Mock details link element
        mock_link = AsyncMock()
        mock_link.get_attribute = AsyncMock(return_value="/details/12345")
        
        scraper.page.query_selector_all = AsyncMock(return_value=[mock_link])
        scraper.page.evaluate = AsyncMock(return_value="McDonald's Corporation Registered Details")
        
        # Execute the method
        details_url = await scraper._find_registered_details_link()
        
        # Verify result
        expected_url = f"{scraper.BASE_URL}/details/12345"
        assert details_url == expected_url
        
        # Verify method calls
        scraper.page.query_selector_all.assert_called_once_with('a[href*="details"]')
        scraper.page.evaluate.assert_called_once()
        mock_link.get_attribute.assert_called_once_with('href')
    
    async def test_extract_detailed_filing_info(self, scraper, mock_details_page_content):
        """Test extraction of detailed filing information."""
        # Mock page content
        scraper.page.content = AsyncMock(return_value=mock_details_page_content)
        scraper.page.query_selector = AsyncMock(return_value=AsyncMock())  # Mock download button
        scraper.page.url = "https://apps.dfi.wi.gov/details/12345"
        
        # Execute the method
        detailed_info = await scraper._extract_detailed_filing_info()
        
        # Verify extracted information
        assert detailed_info['filing_number'] == '12345'
        assert detailed_info['filing_status'] == 'Registered'
        assert detailed_info['legal_name'] == "McDonald's Corporation"
        assert detailed_info['trade_name'] == "McDonald's"
        assert detailed_info['business_address'] == "123 Main St, Chicago, IL 60601"
        assert detailed_info['filing_type'] == "Initial Registration"
        assert detailed_info['effective_date'] == "2024-01-15"
        assert 'Illinois' in detailed_info['states_filed']
        assert 'Wisconsin' in detailed_info['states_filed']
        assert 'Minnesota' in detailed_info['states_filed']
        assert detailed_info['download_url'] == "https://apps.dfi.wi.gov/details/12345"
    
    async def test_search_franchise_basic_success(self, scraper):
        """Test basic franchise search with successful result."""
        franchise_name = "McDonald's Corporation"
        
        # Mock the required methods
        scraper.safe_navigate = AsyncMock()
        scraper._perform_franchise_search = AsyncMock()
        scraper._check_for_registered_status = AsyncMock(return_value=True)
        
        # Execute the method
        result = await scraper._search_franchise_basic(franchise_name)
        
        # Verify result
        assert result is not None
        assert isinstance(result, DocumentMetadata)
        assert result.franchise_name == franchise_name
        assert result.document_type == "FDD"
        assert result.source_url == scraper.SEARCH_URL
        assert result.additional_metadata['has_registered_status'] is True
        assert result.additional_metadata['discovery_method'] == 'active_filings_table'
        
        # Verify method calls
        scraper.safe_navigate.assert_called_once_with(scraper.SEARCH_URL)
        scraper._perform_franchise_search.assert_called_once_with(franchise_name)
        scraper._check_for_registered_status.assert_called_once()
    
    async def test_search_franchise_basic_no_registered(self, scraper):
        """Test basic franchise search with no registered status."""
        franchise_name = "Non-Registered Franchise"
        
        # Mock the required methods
        scraper.safe_navigate = AsyncMock()
        scraper._perform_franchise_search = AsyncMock()
        scraper._check_for_registered_status = AsyncMock(return_value=False)
        
        # Execute the method
        result = await scraper._search_franchise_basic(franchise_name)
        
        # Verify result
        assert result is None
        
        # Verify method calls
        scraper.safe_navigate.assert_called_once_with(scraper.SEARCH_URL)
        scraper._perform_franchise_search.assert_called_once_with(franchise_name)
        scraper._check_for_registered_status.assert_called_once()
    
    async def test_discover_documents_integration(self, scraper):
        """Test the complete document discovery workflow."""
        # Mock the franchise names extraction
        mock_franchise_names = ["McDonald's Corporation", "Subway LLC", "Burger King"]
        scraper._extract_franchise_names_from_table = AsyncMock(return_value=mock_franchise_names)
        
        # Mock basic search results (2 successful, 1 failed)
        mock_doc1 = DocumentMetadata(
            franchise_name="McDonald's Corporation",
            document_type="FDD",
            source_url=scraper.SEARCH_URL,
            download_url=scraper.SEARCH_URL
        )
        mock_doc2 = DocumentMetadata(
            franchise_name="Subway LLC",
            document_type="FDD",
            source_url=scraper.SEARCH_URL,
            download_url=scraper.SEARCH_URL
        )
        
        scraper._search_franchise_basic = AsyncMock(side_effect=[mock_doc1, mock_doc2, None])
        
        # Execute the method
        documents = await scraper.discover_documents()
        
        # Verify results
        assert len(documents) == 2
        assert documents[0].franchise_name == "McDonald's Corporation"
        assert documents[1].franchise_name == "Subway LLC"
        
        # Verify method calls
        scraper._extract_franchise_names_from_table.assert_called_once()
        assert scraper._search_franchise_basic.call_count == 3
    
    async def test_extract_document_metadata_success(self, scraper):
        """Test detailed metadata extraction."""
        franchise_name = "McDonald's Corporation"
        scraper._current_franchise_name = franchise_name
        
        # Mock the required methods
        scraper.safe_navigate = AsyncMock()
        scraper._perform_franchise_search = AsyncMock()
        scraper._find_registered_details_link = AsyncMock(return_value="https://apps.dfi.wi.gov/details/12345")
        scraper._extract_detailed_filing_info = AsyncMock(return_value={
            'filing_number': '12345',
            'filing_status': 'Registered',
            'legal_name': "McDonald's Corporation",
            'trade_name': "McDonald's",
            'business_address': "123 Main St, Chicago, IL",
            'filing_type': 'Initial Registration',
            'effective_date': '2024-01-15',
            'states_filed': ['Illinois', 'Wisconsin'],
            'download_url': 'https://apps.dfi.wi.gov/details/12345',
            'franchisor_info': {'filing_number': '12345'},
            'filing_info': {'type': 'Initial Registration'}
        })
        
        # Execute the method
        result = await scraper.extract_document_metadata("https://search.url")
        
        # Verify result
        assert result is not None
        assert isinstance(result, DocumentMetadata)
        assert result.franchise_name == franchise_name
        assert result.filing_number == '12345'
        assert result.filing_date == '2024-01-15'
        assert result.document_type == 'Initial Registration'
        assert result.additional_metadata['legal_name'] == "McDonald's Corporation"
        assert result.additional_metadata['states_filed'] == ['Illinois', 'Wisconsin']
    
    async def test_extract_document_metadata_no_details(self, scraper):
        """Test metadata extraction when no details are found."""
        franchise_name = "Non-Existent Franchise"
        scraper._current_franchise_name = franchise_name
        
        # Mock the required methods
        scraper.safe_navigate = AsyncMock()
        scraper._perform_franchise_search = AsyncMock()
        scraper._find_registered_details_link = AsyncMock(return_value=None)
        
        # Execute the method
        result = await scraper.extract_document_metadata("https://search.url")
        
        # Verify result
        assert result is None
    
    async def test_error_handling_navigation_failure(self, scraper):
        """Test error handling when navigation fails."""
        scraper.safe_navigate = AsyncMock(side_effect=NavigationError("Navigation failed"))
        
        # Test that the error is properly handled and re-raised
        with pytest.raises(ExtractionError):
            await scraper._extract_franchise_names_from_table()
    
    async def test_error_handling_search_failure(self, scraper):
        """Test error handling when search operation fails."""
        scraper.safe_navigate = AsyncMock()
        scraper.page.wait_for_selector = AsyncMock(side_effect=Exception("Element not found"))
        
        # Test that the error is properly handled and re-raised
        with pytest.raises(ExtractionError):
            await scraper._perform_franchise_search("Test Franchise")
    
    async def test_html_entity_decoding(self, scraper):
        """Test that HTML entities are properly decoded in franchise names."""
        mock_table_html = """
        <table id="ctl00_contentPlaceholder_grdActiveFilings">
            <tr><th>Name</th></tr>
            <tr><td>Ben &amp; Jerry&#39;s &lt;Franchise&gt;</td></tr>
        </table>
        """
        
        scraper.safe_navigate = AsyncMock()
        scraper.page.wait_for_selector = AsyncMock()
        scraper.page.evaluate = AsyncMock(return_value=mock_table_html)
        
        # Execute the method
        franchise_names = await scraper._extract_franchise_names_from_table()
        
        # Verify HTML entities are decoded
        assert len(franchise_names) == 1
        assert franchise_names[0] == "Ben & Jerry's <Franchise>"
    
    async def test_empty_table_handling(self, scraper):
        """Test handling of empty or malformed table."""
        mock_empty_table = """
        <table id="ctl00_contentPlaceholder_grdActiveFilings">
            <tr><th>Name</th></tr>
        </table>
        """
        
        scraper.safe_navigate = AsyncMock()
        scraper.page.wait_for_selector = AsyncMock()
        scraper.page.evaluate = AsyncMock(return_value=mock_empty_table)
        
        # Execute the method
        franchise_names = await scraper._extract_franchise_names_from_table()
        
        # Verify empty result
        assert franchise_names == []


@pytest.mark.asyncio
class TestWisconsinScraperIntegration:
    """Integration tests that test the scraper workflow end-to-end."""
    
    async def test_full_workflow_mock(self):
        """Test the complete scraping workflow with mocked responses."""
        # This test would require more extensive mocking but demonstrates
        # how to test the full workflow
        scraper = WisconsinScraper(headless=True)
        
        # Mock all external dependencies
        with patch.object(scraper, 'initialize') as mock_init, \
             patch.object(scraper, 'cleanup') as mock_cleanup, \
             patch.object(scraper, '_extract_franchise_names_from_table') as mock_extract, \
             patch.object(scraper, '_search_franchise_basic') as mock_search:
            
            # Setup mocks
            mock_extract.return_value = ["Test Franchise"]
            mock_search.return_value = DocumentMetadata(
                franchise_name="Test Franchise",
                document_type="FDD",
                source_url="https://test.url",
                download_url="https://test.url"
            )
            
            # Execute workflow
            async with scraper:
                documents = await scraper.discover_documents()
            
            # Verify results
            assert len(documents) == 1
            assert documents[0].franchise_name == "Test Franchise"
            
            # Verify method calls
            mock_init.assert_called_once()
            mock_cleanup.assert_called_once()
            mock_extract.assert_called_once()
            mock_search.assert_called_once_with("Test Franchise")