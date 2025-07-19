# ABOUTME: Test suite for MinnesotaScraper class
# ABOUTME: Tests Minnesota CARDS portal scraping functionality with real portal

import pytest
import asyncio
from scrapers.states.minnesota import MinnesotaScraper
from scrapers.base.base_scraper import DocumentMetadata
from scrapers.base.exceptions import WebScrapingException, ElementNotFoundError


class TestMinnesotaScraper:
    """Test suite for Minnesota CARDS portal scraper using real portal."""
    
    @pytest.fixture
    async def scraper(self):
        """Create a real Minnesota scraper instance."""
        scraper = MinnesotaScraper(headless=True, timeout=30000)
        await scraper.initialize()
        yield scraper
        await scraper.cleanup()
    
    def test_initialization(self):
        """Test Minnesota scraper initialization."""
        scraper = MinnesotaScraper()
        assert scraper.source_name == "MN"
        assert scraper.BASE_URL == "https://www.cards.commerce.state.mn.us"
        assert "documentType=Clean+FDD" in scraper.SEARCH_URL
    
    @pytest.mark.asyncio
    async def test_discover_documents_real_portal(self, scraper):
        """Test document discovery from real Minnesota CARDS portal."""
        # The SEARCH_URL already has Clean FDD filter applied
        documents = await scraper.discover_documents()
        
        # Verify we got some documents
        assert isinstance(documents, list)
        assert len(documents) > 0
        
        # Check first few documents have required fields
        for doc in documents[:5]:
            assert isinstance(doc, DocumentMetadata)
            assert doc.franchise_name is not None
            assert doc.download_url is not None
            assert doc.source_url is not None
            assert doc.document_type is not None
            
            # Check additional metadata
            assert "source" in doc.additional_metadata
            assert doc.additional_metadata["source"] == "MN"
            assert "franchisor" in doc.additional_metadata
            assert "year" in doc.additional_metadata
    
    @pytest.mark.asyncio
    async def test_extract_cards_results_structure(self, scraper):
        """Test that CARDS table extraction works correctly."""
        # Navigate to the search page with Clean FDD filter
        await scraper.safe_navigate(scraper.SEARCH_URL)
        
        # Wait for results table
        await scraper.page.wait_for_selector("#results", timeout=scraper.timeout)
        
        # Extract results
        documents = await scraper._extract_cards_results()
        
        assert len(documents) > 0
        
        # Verify document structure
        first_doc = documents[0]
        assert first_doc.franchise_name
        assert first_doc.download_url
        assert first_doc.download_url.startswith("http")
        assert first_doc.additional_metadata.get("document_type") == "Clean FDD" or first_doc.document_type == "FDD"
    
    @pytest.mark.asyncio
    async def test_pagination_load_more(self, scraper):
        """Test pagination handling with Load More button."""
        # Navigate to search results
        await scraper.safe_navigate(scraper.SEARCH_URL)
        await scraper.page.wait_for_selector("#results", timeout=scraper.timeout)
        
        # Get initial count
        initial_rows = await scraper.page.query_selector_all("#results tr")
        initial_count = len(initial_rows) - 1  # Subtract header
        
        # Look for Load More button
        load_more_selectors = [
            'button:has-text("Load more")',
            "#main-content > form ul button",
            'button:has-text("Load More")',
            'button:has-text("LOAD MORE")',
        ]
        
        button_found = False
        for selector in load_more_selectors:
            try:
                button = await scraper.page.query_selector(selector)
                if button and await button.is_visible():
                    button_found = True
                    # Click load more
                    await button.click()
                    await asyncio.sleep(2)  # Wait for content to load
                    
                    # Check if more rows were added
                    new_rows = await scraper.page.query_selector_all("#results tr")
                    new_count = len(new_rows) - 1
                    
                    assert new_count > initial_count, "Load more should add more results"
                    break
            except:
                continue
        
        # It's okay if no Load More button exists (might have all results on first page)
        if button_found:
            print(f"Load More button found and tested - rows increased from {initial_count} to {new_count}")
        else:
            print("No Load More button found - all results may be on first page")
    
    @pytest.mark.asyncio
    async def test_extract_document_metadata_from_detail(self, scraper):
        """Test metadata extraction from a document detail page."""
        # First get a document from discovery
        await scraper.safe_navigate(scraper.SEARCH_URL)
        await scraper.page.wait_for_selector("#results", timeout=scraper.timeout)
        
        # Get first document link
        first_link = await scraper.page.query_selector("#results tr:nth-child(2) td:nth-child(2) a")
        if first_link:
            link_url = await first_link.get_attribute("href")
            if link_url:
                if link_url.startswith("/"):
                    link_url = scraper.BASE_URL + link_url
                
                # Extract metadata from this document
                metadata = await scraper.extract_document_metadata(link_url)
                
                assert metadata is not None
                assert metadata.franchise_name is not None
                assert metadata.download_url is not None
                assert metadata.source_url == link_url
    
    @pytest.mark.asyncio
    async def test_download_url_format(self, scraper):
        """Test that download URLs are properly formatted."""
        # Get some documents
        await scraper.safe_navigate(scraper.SEARCH_URL)
        await scraper.page.wait_for_selector("#results", timeout=scraper.timeout)
        
        documents = await scraper._extract_cards_results()
        
        # Check first few download URLs
        for doc in documents[:3]:
            assert doc.download_url.startswith("http")
            assert "documentId=" in doc.download_url or "/download" in doc.download_url
            
            # Verify document ID extraction
            if "document_id" in doc.additional_metadata:
                assert doc.additional_metadata["document_id"] is not None
    
    @pytest.mark.asyncio
    async def test_franchise_name_extraction(self, scraper):
        """Test various franchise name extraction methods."""
        # Test with a real page
        await scraper.safe_navigate(scraper.SEARCH_URL)
        
        # Get page title
        title = await scraper.page.title()
        
        # Test extraction logic
        name = await scraper._extract_franchise_name()
        assert name is not None
        assert name != "Unknown Franchise"
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_url(self, scraper):
        """Test error handling for invalid URLs."""
        with pytest.raises(WebScrapingException):
            await scraper.extract_document_metadata("http://invalid.url.com/test")
    
    @pytest.mark.asyncio
    async def test_minnesota_specific_fields(self, scraper):
        """Test Minnesota-specific data fields are captured."""
        documents = await scraper.discover_documents()
        
        # Check Minnesota-specific fields in first document
        if documents:
            doc = documents[0]
            
            # Check required Minnesota metadata
            assert doc.additional_metadata.get("source") == "MN"
            assert "discovery_method" in doc.additional_metadata
            assert doc.additional_metadata["discovery_method"] in ["cards_table", "cards_api"]
            
            # Check optional but common fields
            if "year" in doc.additional_metadata:
                year = doc.additional_metadata["year"]
                assert year.isdigit() or year == ""
            
            if "franchisor" in doc.additional_metadata:
                assert isinstance(doc.additional_metadata["franchisor"], str)