"""Unit tests for web scraping base framework."""

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from playwright.async_api import Browser, BrowserContext, Page, Playwright

from tasks.web_scraping import (
    BaseScraper,
    DocumentMetadata,
    create_scraper,
)
from tasks.exceptions import (
    WebScrapingException,
    ElementNotFoundError,
    NavigationTimeoutError,
    DownloadFailedError,
)


class TestDocumentMetadata:
    """Test DocumentMetadata model."""

    def test_document_metadata_creation(self):
        """Test creating DocumentMetadata with required fields."""
        metadata = DocumentMetadata(
            franchise_name="Test Franchise",
            source_url="https://example.com/search",
            download_url="https://example.com/download.pdf",
        )

        assert metadata.franchise_name == "Test Franchise"
        assert metadata.source_url == "https://example.com/search"
        assert metadata.download_url == "https://example.com/download.pdf"
        assert metadata.document_type == "FDD"  # Default value
        assert metadata.filing_date is None
        assert metadata.filing_number is None
        assert metadata.file_size is None
        assert metadata.additional_metadata == {}

    def test_document_metadata_with_optional_fields(self):
        """Test creating DocumentMetadata with all fields."""
        metadata = DocumentMetadata(
            franchise_name="Test Franchise",
            filing_date="2024-01-15",
            document_type="Amendment",
            filing_number="12345",
            source_url="https://example.com/search",
            download_url="https://example.com/download.pdf",
            file_size=1024000,
            additional_metadata={"state": "MN", "status": "Active"},
        )

        assert metadata.filing_date == "2024-01-15"
        assert metadata.document_type == "Amendment"
        assert metadata.filing_number == "12345"
        assert metadata.file_size == 1024000
        assert metadata.additional_metadata == {"state": "MN", "status": "Active"}


class MockScraper(BaseScraper):
    """Mock scraper implementation for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.discover_documents_mock = AsyncMock()
        self.extract_document_metadata_mock = AsyncMock()

    async def discover_documents(self):
        return await self.discover_documents_mock()

    async def extract_document_metadata(self, document_url: str):
        return await self.extract_document_metadata_mock(document_url)


class TestBaseScraper:
    """Test BaseScraper functionality."""

    @pytest.fixture
    def scraper(self):
        """Create a mock scraper instance."""
        return MockScraper("TEST", headless=True, prefect_run_id=uuid4())

    def test_scraper_initialization(self, scraper):
        """Test scraper initialization with parameters."""
        assert scraper.source_name == "TEST"
        assert scraper.headless is True
        assert scraper.timeout == 30000  # Default timeout
        assert scraper.max_retries == 3  # From settings
        assert scraper.base_delay == 1.0

        # Browser components should be None initially
        assert scraper.playwright is None
        assert scraper.browser is None
        assert scraper.context is None
        assert scraper.page is None
        assert scraper.http_client is None

    @pytest.mark.asyncio
    async def test_scraper_context_manager(self, scraper):
        """Test scraper as async context manager."""
        with (
            patch.object(scraper, "initialize") as mock_init,
            patch.object(scraper, "cleanup") as mock_cleanup,
        ):

            async with scraper:
                mock_init.assert_called_once()

            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_success(self, scraper):
        """Test successful scraper initialization."""
        # Mock Playwright components
        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        with patch("tasks.web_scraping.async_playwright") as mock_pw_factory:
            mock_pw_factory.return_value.start = AsyncMock(return_value=mock_playwright)
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)

            with patch("httpx.AsyncClient") as mock_http_client:
                await scraper.initialize()

                # Verify initialization
                assert scraper.playwright == mock_playwright
                assert scraper.browser == mock_browser
                assert scraper.context == mock_context
                assert scraper.page == mock_page
                assert scraper.http_client is not None

                # Verify browser launch arguments
                mock_playwright.chromium.launch.assert_called_once()
                launch_args = mock_playwright.chromium.launch.call_args
                assert launch_args[1]["headless"] is True
                assert "--no-sandbox" in launch_args[1]["args"]

    @pytest.mark.asyncio
    async def test_initialize_failure(self, scraper):
        """Test scraper initialization failure."""
        with patch("tasks.web_scraping.async_playwright") as mock_pw_factory:
            mock_pw_factory.return_value.start = AsyncMock(
                side_effect=Exception("Playwright failed")
            )

            with pytest.raises(WebScrapingException, match="Failed to initialize scraper"):
                await scraper.initialize()

    @pytest.mark.asyncio
    async def test_cleanup_success(self, scraper):
        """Test successful cleanup."""
        # Set up mock components
        mock_http_client = AsyncMock()
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        scraper.http_client = mock_http_client
        scraper.page = mock_page
        scraper.context = mock_context
        scraper.browser = mock_browser
        scraper.playwright = mock_playwright

        await scraper.cleanup()

        # Verify cleanup calls
        mock_http_client.aclose.assert_called_once()
        mock_page.close.assert_called_once()
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

        # Verify components are reset
        assert scraper.http_client is None
        assert scraper.page is None
        assert scraper.context is None
        assert scraper.browser is None
        assert scraper.playwright is None

    @pytest.mark.asyncio
    async def test_retry_with_backoff_success_first_attempt(self, scraper):
        """Test retry logic with successful first attempt."""
        mock_operation = AsyncMock(return_value="success")

        result = await scraper.retry_with_backoff(
            mock_operation, "test_operation", "arg1", kwarg1="value1"
        )

        assert result == "success"
        mock_operation.assert_called_once_with("arg1", kwarg1="value1")

    @pytest.mark.asyncio
    async def test_retry_with_backoff_success_after_retry(self, scraper):
        """Test retry logic with success after failures."""
        mock_operation = AsyncMock(
            side_effect=[
                Exception("First failure"),
                Exception("Second failure"),
                "success",
            ]
        )

        with patch("asyncio.sleep") as mock_sleep:
            result = await scraper.retry_with_backoff(mock_operation, "test_operation")

        assert result == "success"
        assert mock_operation.call_count == 3
        assert mock_sleep.call_count == 2  # Two retries

    @pytest.mark.asyncio
    async def test_retry_with_backoff_all_attempts_fail(self, scraper):
        """Test retry logic when all attempts fail."""
        mock_operation = AsyncMock(side_effect=Exception("Persistent failure"))

        with patch("asyncio.sleep"):
            with pytest.raises(
                WebScrapingException, match="test_operation failed after 3 attempts"
            ):
                await scraper.retry_with_backoff(mock_operation, "test_operation")

        assert mock_operation.call_count == 3

    @pytest.mark.asyncio
    async def test_safe_navigate_success(self, scraper):
        """Test successful navigation."""
        mock_page = AsyncMock()
        scraper.page = mock_page

        await scraper.safe_navigate("https://example.com")

        mock_page.goto.assert_called_once_with(
            "https://example.com", wait_until="networkidle"
        )

    @pytest.mark.asyncio
    async def test_safe_navigate_with_wait_for(self, scraper):
        """Test navigation with wait_for selector."""
        mock_page = AsyncMock()
        scraper.page = mock_page

        await scraper.safe_navigate("https://example.com", wait_for="#content")

        mock_page.goto.assert_called_once()
        mock_page.wait_for_selector.assert_called_once_with(
            "#content", timeout=scraper.timeout
        )

    @pytest.mark.asyncio
    async def test_safe_navigate_failure(self, scraper):
        """Test navigation failure."""
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("Navigation failed")
        scraper.page = mock_page

        with pytest.raises(NavigationTimeoutError, match="Failed to navigate"):
            await scraper.safe_navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_safe_navigate_no_page(self, scraper):
        """Test navigation without initialized page."""
        with pytest.raises(NavigationTimeoutError, match="Page not initialized"):
            await scraper.safe_navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_safe_click_success(self, scraper):
        """Test successful element click."""
        mock_page = AsyncMock()
        mock_element = AsyncMock()
        mock_page.wait_for_selector.return_value = mock_element
        scraper.page = mock_page

        await scraper.safe_click("#button")

        mock_page.wait_for_selector.assert_called_once_with(
            "#button", timeout=scraper.timeout
        )
        mock_element.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_safe_click_element_not_found(self, scraper):
        """Test click when element is not found."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.return_value = None
        scraper.page = mock_page

        with pytest.raises(ElementNotFoundError, match="Element not found"):
            await scraper.safe_click("#button")

    @pytest.mark.asyncio
    async def test_safe_fill_success(self, scraper):
        """Test successful form field fill."""
        mock_page = AsyncMock()
        mock_element = AsyncMock()
        mock_page.wait_for_selector.return_value = mock_element
        scraper.page = mock_page

        await scraper.safe_fill("#input", "test value")

        mock_page.wait_for_selector.assert_called_once_with(
            "#input", timeout=scraper.timeout
        )
        mock_element.fill.assert_called_once_with("test value")

    @pytest.mark.asyncio
    async def test_download_document_success(self, scraper):
        """Test successful document download."""
        pdf_content = b"%PDF-1.4\n%Test PDF content"
        mock_response = MagicMock()
        mock_response.content = pdf_content
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        scraper.http_client = mock_http_client

        result = await scraper.download_document("https://example.com/test.pdf")

        assert result == pdf_content
        mock_http_client.get.assert_called_once_with("https://example.com/test.pdf")
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_document_empty_content(self, scraper):
        """Test download with empty content."""
        mock_response = MagicMock()
        mock_response.content = b""
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        scraper.http_client = mock_http_client

        with pytest.raises(WebScrapingException, match="Downloaded content is empty"):
            await scraper.download_document("https://example.com/test.pdf")

    @pytest.mark.asyncio
    async def test_download_document_invalid_pdf(self, scraper):
        """Test download with invalid PDF content."""
        mock_response = MagicMock()
        mock_response.content = b"Not a PDF file"
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        scraper.http_client = mock_http_client

        with pytest.raises(WebScrapingException, match="not a valid PDF"):
            await scraper.download_document("https://example.com/test.pdf")

    @pytest.mark.asyncio
    async def test_download_document_http_error(self, scraper):
        """Test download with HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        scraper.http_client = mock_http_client

        with pytest.raises(
            WebScrapingException, match="document_download failed after 3 attempts"
        ):
            await scraper.download_document("https://example.com/test.pdf")

    def test_compute_document_hash(self, scraper):
        """Test document hash computation."""
        content = b"%PDF-1.4\nTest content"
        expected_hash = hashlib.sha256(content).hexdigest()

        result = scraper.compute_document_hash(content)

        assert result == expected_hash

    @pytest.mark.asyncio
    async def test_scrape_portal_success(self, scraper):
        """Test successful portal scraping."""
        # Mock discovered documents
        mock_documents = [
            DocumentMetadata(
                franchise_name="Test Franchise 1",
                source_url="https://example.com/doc1",
                download_url="https://example.com/download1.pdf",
            ),
            DocumentMetadata(
                franchise_name="Test Franchise 2",
                source_url="https://example.com/doc2",
                download_url="https://example.com/download2.pdf",
            ),
        ]

        # Mock enriched documents
        enriched_doc1 = DocumentMetadata(
            franchise_name="Test Franchise 1",
            filing_date="2024-01-15",
            source_url="https://example.com/doc1",
            download_url="https://example.com/download1.pdf",
        )
        enriched_doc2 = DocumentMetadata(
            franchise_name="Test Franchise 2",
            filing_date="2024-01-20",
            source_url="https://example.com/doc2",
            download_url="https://example.com/download2.pdf",
        )

        scraper.discover_documents_mock.return_value = mock_documents
        scraper.extract_document_metadata_mock.side_effect = [
            enriched_doc1,
            enriched_doc2,
        ]

        with patch("asyncio.sleep"):  # Skip delays in tests
            result = await scraper.scrape_portal()

        assert len(result) == 2
        assert result[0].filing_date == "2024-01-15"
        assert result[1].filing_date == "2024-01-20"

        scraper.discover_documents_mock.assert_called_once()
        assert scraper.extract_document_metadata_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_scrape_portal_metadata_extraction_failure(self, scraper):
        """Test portal scraping with metadata extraction failure."""
        mock_documents = [
            DocumentMetadata(
                franchise_name="Test Franchise",
                source_url="https://example.com/doc1",
                download_url="https://example.com/download1.pdf",
            )
        ]

        scraper.discover_documents_mock.return_value = mock_documents
        scraper.extract_document_metadata_mock.side_effect = Exception(
            "Metadata extraction failed"
        )

        with patch("asyncio.sleep"):
            result = await scraper.scrape_portal()

        # Should return original document when metadata extraction fails
        assert len(result) == 1
        assert result[0].franchise_name == "Test Franchise"
        assert result[0].filing_date is None  # No enriched metadata


@pytest.mark.asyncio
async def test_create_scraper_context_manager():
    """Test create_scraper context manager."""
    mock_scraper_instance = AsyncMock()
    mock_scraper_class = MagicMock(return_value=mock_scraper_instance)

    async with create_scraper(mock_scraper_class, "TEST", headless=True) as scraper:
        assert scraper == mock_scraper_instance
        mock_scraper_instance.initialize.assert_called_once()

    mock_scraper_instance.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_create_scraper_context_manager_with_exception():
    """Test create_scraper context manager with exception."""
    mock_scraper_instance = AsyncMock()
    mock_scraper_instance.initialize.side_effect = Exception("Init failed")
    mock_scraper_class = MagicMock(return_value=mock_scraper_instance)

    with pytest.raises(Exception, match="Init failed"):
        async with create_scraper(mock_scraper_class, "TEST"):
            pass

    # Cleanup should still be called
    mock_scraper_instance.cleanup.assert_called_once()
