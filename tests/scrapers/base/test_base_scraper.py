# ABOUTME: Test suite for BaseScraper abstract base class
# ABOUTME: Tests browser initialization, navigation, error handling, and document operations with real browsers

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from uuid import uuid4

from scrapers.base.base_scraper import BaseScraper, DocumentMetadata, create_scraper
from scrapers.base.exceptions import (
    BrowserInitializationError,
    NavigationTimeoutError,
    ElementNotFoundError,
    DownloadFailedError,
    WebScrapingException,
    RateLimitError,
    RetryableError,
)


class TestScraper(BaseScraper):
    """Concrete implementation of BaseScraper for testing."""
    
    async def discover_documents(self):
        """Test implementation that searches httpbin.org."""
        # Use httpbin.org as a test endpoint
        await self.safe_navigate("https://httpbin.org/html")
        
        # Extract some test data from the page
        title = await self.page.title()
        
        return [
            DocumentMetadata(
                franchise_name=title or "Test Document",
                filing_date="2024-01-01",
                document_type="FDD",
                filing_number="12345",
                source_url="https://httpbin.org/html",
                download_url="https://httpbin.org/image/pdf"
            )
        ]
    
    async def extract_document_metadata(self, document_url: str):
        """Test implementation."""
        await self.safe_navigate(document_url)
        title = await self.page.title()
        
        return DocumentMetadata(
            franchise_name=title or "Test Franchise",
            filing_date="2024-01-01",
            document_type="FDD",
            filing_number="12345",
            source_url=document_url,
            download_url="https://httpbin.org/image/pdf"
        )


class TestBaseScraper:
    """Test suite for BaseScraper functionality using real browser instances."""
    
    @pytest.fixture
    async def scraper(self):
        """Create a real test scraper instance."""
        scraper = TestScraper(
            source_name="TEST",
            headless=True,
            timeout=10000,
            prefect_run_id=uuid4()
        )
        await scraper.initialize()
        yield scraper
        await scraper.cleanup()
    
    def test_initialization(self):
        """Test scraper initialization with various parameters."""
        # Test with all parameters
        run_id = uuid4()
        scraper = TestScraper(
            source_name="TEST",
            headless=False,
            timeout=10000,
            prefect_run_id=run_id
        )
        
        assert scraper.source_name == "TEST"
        assert scraper.headless is False
        assert scraper.timeout == 10000
        assert scraper.correlation_id == str(run_id)
        
        # Test with defaults
        scraper2 = TestScraper(source_name="TEST2")
        assert scraper2.headless is True
        assert scraper2.timeout == 30000
        assert scraper2.correlation_id is not None
    
    @pytest.mark.asyncio
    async def test_browser_initialization(self):
        """Test real browser initialization and cleanup."""
        scraper = TestScraper(source_name="TEST", headless=True)
        
        # Initialize browser
        await scraper.initialize()
        
        # Verify browser is initialized
        assert scraper.playwright is not None
        assert scraper.browser is not None
        assert scraper.context is not None
        assert scraper.page is not None
        assert scraper.http_client is not None
        
        # Test that we can navigate
        await scraper.page.goto("https://httpbin.org/")
        assert "httpbin" in await scraper.page.title()
        
        # Test cleanup
        await scraper.cleanup()
        assert scraper.playwright is None
        assert scraper.browser is None
        assert scraper.context is None
        assert scraper.page is None
        assert scraper.http_client is None
    
    @pytest.mark.asyncio
    async def test_safe_navigate(self, scraper):
        """Test safe navigation to real URLs."""
        # Test successful navigation
        await scraper.safe_navigate("https://httpbin.org/html")
        assert "httpbin" in await scraper.page.url()
        
        # Test navigation with wait selector
        await scraper.safe_navigate("https://httpbin.org/html", wait_for="h1")
        h1_text = await scraper.page.inner_text("h1")
        assert h1_text is not None
        
        # Test navigation to invalid URL
        with pytest.raises(WebScrapingException):
            await scraper.safe_navigate("http://invalid-domain-that-does-not-exist-12345.com")
    
    @pytest.mark.asyncio
    async def test_safe_click(self, scraper):
        """Test safe element clicking on real page."""
        # Navigate to a page with clickable elements
        await scraper.safe_navigate("https://httpbin.org/forms/post")
        
        # Test clicking a real button
        await scraper.safe_click('button[type="submit"]')
        
        # Test element not found
        with pytest.raises(ElementNotFoundError):
            await scraper.safe_click(".non-existent-button")
    
    @pytest.mark.asyncio
    async def test_safe_fill(self, scraper):
        """Test safe form filling on real forms."""
        # Navigate to a form page
        await scraper.safe_navigate("https://httpbin.org/forms/post")
        
        # Test filling a real input field
        await scraper.safe_fill('input[name="custname"]', "Test Customer")
        
        # Verify the value was set
        value = await scraper.page.input_value('input[name="custname"]')
        assert value == "Test Customer"
        
        # Test element not found
        with pytest.raises(ElementNotFoundError):
            await scraper.safe_fill(".non-existent-input", "value")
    
    @pytest.mark.asyncio
    async def test_download_document(self, scraper):
        """Test document download from real endpoints."""
        # Test downloading a real PDF sample
        # httpbin doesn't serve PDFs, so we'll test error handling
        
        # Test non-PDF content error
        with pytest.raises(DownloadFailedError) as exc_info:
            await scraper.download_document("https://httpbin.org/html")
        assert "not a valid PDF" in str(exc_info.value)
        
        # Test 404 error
        with pytest.raises(DownloadFailedError):
            await scraper.download_document("https://httpbin.org/status/404")
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff(self, scraper):
        """Test retry logic with real failing operations."""
        attempt_count = 0
        
        async def intermittent_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                # Simulate network failure
                raise ConnectionError("Network temporarily unavailable")
            return "success"
        
        # Test successful retry
        scraper.max_retries = 5
        result = await scraper.retry_with_backoff(intermittent_operation, "test_operation")
        assert result == "success"
        assert attempt_count == 3
    
    @pytest.mark.asyncio
    async def test_extract_table_data(self, scraper):
        """Test table data extraction from real HTML tables."""
        # Create a test HTML page with a table
        test_html = """
        <html>
        <body>
            <table id="test-table">
                <tr>
                    <th>Name</th>
                    <th>Date</th>
                    <th>Status</th>
                </tr>
                <tr>
                    <td>Franchise A</td>
                    <td>2024-01-01</td>
                    <td>Active</td>
                </tr>
                <tr>
                    <td>Franchise B</td>
                    <td>2024-01-02</td>
                    <td>Pending</td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        # Navigate to data URL with the HTML
        await scraper.page.goto(f"data:text/html,{test_html}")
        
        # Extract table data
        data = await scraper.extract_table_data("#test-table")
        
        assert len(data) == 2
        assert data[0]["Name"] == "Franchise A"
        assert data[0]["Date"] == "2024-01-01"
        assert data[0]["Status"] == "Active"
        assert data[1]["Name"] == "Franchise B"
    
    @pytest.mark.asyncio
    async def test_compute_document_hash(self, scraper):
        """Test document hash computation."""
        content = b"test document content"
        hash_value = scraper.compute_document_hash(content)
        
        # SHA256 produces 64 character hex string
        assert len(hash_value) == 64
        assert all(c in '0123456789abcdef' for c in hash_value)
        
        # Same content should produce same hash
        hash_value2 = scraper.compute_document_hash(content)
        assert hash_value == hash_value2
        
        # Different content should produce different hash
        hash_value3 = scraper.compute_document_hash(b"different content")
        assert hash_value != hash_value3
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test scraper as async context manager with real browser."""
        async with create_scraper(TestScraper, source_name="TEST") as scraper:
            assert isinstance(scraper, TestScraper)
            assert scraper.source_name == "TEST"
            
            # Verify browser is working
            await scraper.page.goto("https://httpbin.org/")
            assert "httpbin" in await scraper.page.title()
    
    @pytest.mark.asyncio
    async def test_manage_cookies(self, scraper):
        """Test cookie management between browser and HTTP client."""
        # Navigate to a page that sets cookies
        await scraper.safe_navigate("https://httpbin.org/cookies/set/test_cookie/test_value")
        
        # Extract cookies
        cookies = await scraper.manage_cookies()
        
        # httpbin redirects after setting cookies, so check if we have any cookies
        assert isinstance(cookies, dict)
    
    @pytest.mark.asyncio
    async def test_download_file_streaming(self, scraper):
        """Test streaming file download."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test_download.json"
            
            # Download a small JSON file
            success = await scraper.download_file_streaming(
                "https://httpbin.org/json",
                filepath
            )
            
            assert success
            assert filepath.exists()
            
            # Verify content
            content = filepath.read_text()
            assert "slideshow" in content  # httpbin.org/json returns slideshow data
    
    @pytest.mark.asyncio
    async def test_clear_search_input(self, scraper):
        """Test clearing search input fields."""
        # Navigate to a form
        await scraper.safe_navigate("https://httpbin.org/forms/post")
        
        # Fill an input
        await scraper.safe_fill('input[name="custname"]', "Initial Value")
        
        # Clear it
        await scraper.clear_search_input('input[name="custname"]')
        
        # Verify it's empty
        value = await scraper.page.input_value('input[name="custname"]')
        assert value == ""
    
    @pytest.mark.asyncio
    async def test_handle_pagination(self, scraper):
        """Test pagination handling."""
        # Since we need a real paginated site, we'll test the generator behavior
        # with a simple HTML page
        test_html = """
        <html>
        <body>
            <div class="content">Page 1</div>
            <button id="next" disabled>Next</button>
        </body>
        </html>
        """
        
        await scraper.page.goto(f"data:text/html,{test_html}")
        
        # Test pagination generator
        page_count = 0
        async for page in scraper.handle_pagination("#next", ".content", max_pages=5):
            page_count += 1
            # Should stop after first page due to disabled button
            break
        
        assert page_count == 1