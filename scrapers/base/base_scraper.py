"""Base web scraping framework with Playwright browser management."""

import asyncio
import hashlib
import random
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, AsyncIterator, Tuple
from uuid import UUID

import httpx
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from pydantic import BaseModel

from config import get_settings
from models.scrape_metadata import ScrapeMetadata
from utils.logging import PipelineLogger
from utils.scraping_utils import (
    sanitize_filename,
    get_default_headers,
    parse_date_formats,
    extract_filing_number,
    clean_text,
    normalize_url,
    calculate_retry_delay,
)
from tasks.exceptions import (
    WebScrapingException,
    BrowserInitializationError,
    NavigationTimeoutError,
    ElementNotFoundError,
    LoginFailedError,
    DownloadFailedError,
    RateLimitError,
    RetryableError,
    get_retry_delay,
)


class DocumentMetadata(BaseModel):
    """Metadata for a discovered document."""

    franchise_name: str
    filing_date: Optional[str] = None
    document_type: str = "FDD"
    filing_number: Optional[str] = None
    source_url: str
    download_url: str
    file_size: Optional[int] = None
    additional_metadata: Dict[str, Any] = {}


# Remove local exception classes - we'll use the ones from exceptions.py
# ScrapingError -> WebScrapingException
# NavigationError -> NavigationTimeoutError
# ExtractionError -> ElementNotFoundError
# DownloadError -> DownloadFailedError


class BaseScraper(ABC):
    """Base scraper class with common functionality for state portal scraping."""

    # User agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]

    def __init__(
        self,
        source_name: str,
        headless: bool = True,
        timeout: int = 30000,
        prefect_run_id: Optional[UUID] = None,
    ):
        """Initialize the base scraper.

        Args:
            source_name: Name of the source (e.g., 'MN', 'WI')
            headless: Whether to run browser in headless mode
            timeout: Default timeout in milliseconds
            prefect_run_id: Optional Prefect run ID for tracking
        """
        self.source_name = source_name
        self.headless = headless
        self.timeout = timeout
        self.settings = get_settings()
        self.correlation_id = str(prefect_run_id) if prefect_run_id else str(UUID())
        self.logger = PipelineLogger(
            f"scraper.{source_name.lower()}",
            prefect_run_id=self.correlation_id,
        )

        # Browser management
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # HTTP client for downloads
        self.http_client: Optional[httpx.AsyncClient] = None

        # Retry configuration
        self.max_retries = self.settings.retry_attempts
        self.base_delay = 1.0  # Base delay for exponential backoff

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    async def initialize(self) -> None:
        """Initialize browser and HTTP client."""
        try:
            self.logger.info("initializing_scraper", source=self.source_name)

            # Initialize Playwright
            self.playwright = await async_playwright().start()

            # Launch browser with optimized settings
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--no-first-run",
                    "--disable-default-apps",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                ],
            )

            # Create browser context with random user agent
            user_agent = random.choice(self.USER_AGENTS)
            self.context = await self.browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
            )

            # Create page
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            self.page.set_default_navigation_timeout(self.timeout)

            # Initialize HTTP client with enhanced headers
            headers = get_default_headers()
            headers["User-Agent"] = user_agent

            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),  # Increased timeout for large files
                headers=headers,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )

            self.logger.info("scraper_initialized", user_agent=user_agent)

        except Exception as e:
            self.logger.error(
                "scraper_initialization_failed",
                error=str(e),
                correlation_id=self.correlation_id,
            )
            await self.cleanup()
            raise BrowserInitializationError(
                f"Failed to initialize scraper: {e}",
                correlation_id=self.correlation_id,
                context={
                    "source_name": self.source_name,
                    "error_type": type(e).__name__,
                },
            )

    async def cleanup(self) -> None:
        """Clean up browser and HTTP client resources."""
        try:
            self.logger.info("cleaning_up_scraper")

            if self.http_client:
                await self.http_client.aclose()
                self.http_client = None

            if self.page:
                await self.page.close()
                self.page = None

            if self.context:
                await self.context.close()
                self.context = None

            if self.browser:
                await self.browser.close()
                self.browser = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            self.logger.info("scraper_cleanup_completed")

        except Exception as e:
            self.logger.error("scraper_cleanup_failed", error=str(e))

    async def retry_with_backoff(
        self, operation, operation_name: str, *args, **kwargs
    ) -> Any:
        """Execute operation with exponential backoff retry logic.

        Args:
            operation: Async function to execute
            operation_name: Name for logging
            *args: Arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Result of successful operation

        Raises:
            ScrapingError: If all retry attempts fail
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                self.logger.debug(
                    "attempting_operation",
                    operation=operation_name,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries,
                )

                result = await operation(*args, **kwargs)

                if attempt > 0:
                    self.logger.info(
                        "operation_succeeded_after_retry",
                        operation=operation_name,
                        attempt=attempt + 1,
                    )

                return result

            except Exception as e:
                last_exception = e
                self.logger.warning(
                    "operation_attempt_failed",
                    operation=operation_name,
                    attempt=attempt + 1,
                    error=str(e),
                )

                if attempt < self.max_retries - 1:
                    # Calculate delay with exponential backoff and jitter
                    delay = self.base_delay * (2**attempt) + random.uniform(0, 1)
                    self.logger.debug("retrying_after_delay", delay=delay)
                    await asyncio.sleep(delay)

        # All attempts failed
        self.logger.error(
            "operation_failed_all_attempts",
            operation=operation_name,
            max_attempts=self.max_retries,
            final_error=str(last_exception),
        )
        raise WebScrapingException(
            f"{operation_name} failed after {self.max_retries} attempts: {last_exception}",
            correlation_id=self.correlation_id,
            context={
                "operation": operation_name,
                "max_retries": self.max_retries,
                "last_error_type": type(last_exception).__name__,
            },
        )

    async def safe_navigate(self, url: str, wait_for: Optional[str] = None) -> None:
        """Safely navigate to a URL with error handling.

        Args:
            url: URL to navigate to
            wait_for: Optional selector to wait for after navigation

        Raises:
            NavigationError: If navigation fails
        """
        if not self.page:
            raise NavigationTimeoutError(
                "Page not initialized", correlation_id=self.correlation_id
            )

        try:
            self.logger.debug("navigating_to_url", url=url)

            await self.page.goto(url, wait_until="networkidle")

            if wait_for:
                await self.page.wait_for_selector(wait_for, timeout=self.timeout)

            self.logger.debug("navigation_successful", url=url)

        except Exception as e:
            self.logger.error(
                "navigation_failed",
                url=url,
                error=str(e),
                correlation_id=self.correlation_id,
            )
            if "timeout" in str(e).lower():
                raise NavigationTimeoutError(
                    f"Navigation timeout for {url}: {e}",
                    correlation_id=self.correlation_id,
                    context={"url": url, "timeout": self.timeout},
                )
            else:
                raise WebScrapingException(
                    f"Failed to navigate to {url}: {e}",
                    correlation_id=self.correlation_id,
                    context={"url": url, "error_type": type(e).__name__},
                )

    async def safe_click(self, selector: str, timeout: Optional[int] = None) -> None:
        """Safely click an element with error handling.

        Args:
            selector: CSS selector for element to click
            timeout: Optional timeout override

        Raises:
            ExtractionError: If click fails
        """
        if not self.page:
            raise ElementNotFoundError(
                "Page not initialized", correlation_id=self.correlation_id
            )

        try:
            element = await self.page.wait_for_selector(
                selector, timeout=timeout or self.timeout
            )
            if not element:
                raise ElementNotFoundError(
                    f"Element not found: {selector}",
                    correlation_id=self.correlation_id,
                    context={"selector": selector},
                )

            await element.click()
            self.logger.debug("element_clicked", selector=selector)

        except Exception as e:
            self.logger.error(
                "click_failed",
                selector=selector,
                error=str(e),
                correlation_id=self.correlation_id,
            )
            if "timeout" in str(e).lower():
                raise NavigationTimeoutError(
                    f"Timeout waiting for element {selector}: {e}",
                    correlation_id=self.correlation_id,
                    context={"selector": selector, "timeout": timeout or self.timeout},
                )
            else:
                raise ElementNotFoundError(
                    f"Failed to click {selector}: {e}",
                    correlation_id=self.correlation_id,
                    context={"selector": selector, "error_type": type(e).__name__},
                )

    async def safe_fill(
        self, selector: str, value: str, timeout: Optional[int] = None
    ) -> None:
        """Safely fill an input field with error handling.

        Args:
            selector: CSS selector for input element
            value: Value to fill
            timeout: Optional timeout override

        Raises:
            ExtractionError: If fill fails
        """
        if not self.page:
            raise ElementNotFoundError(
                "Page not initialized", correlation_id=self.correlation_id
            )

        try:
            element = await self.page.wait_for_selector(
                selector, timeout=timeout or self.timeout
            )
            if not element:
                raise ElementNotFoundError(
                    f"Element not found: {selector}",
                    correlation_id=self.correlation_id,
                    context={"selector": selector},
                )

            await element.fill(value)
            self.logger.debug(
                "element_filled", selector=selector, value_length=len(value)
            )

        except Exception as e:
            self.logger.error(
                "fill_failed",
                selector=selector,
                error=str(e),
                correlation_id=self.correlation_id,
            )
            if "timeout" in str(e).lower():
                raise NavigationTimeoutError(
                    f"Timeout waiting for element {selector}: {e}",
                    correlation_id=self.correlation_id,
                    context={"selector": selector, "timeout": timeout or self.timeout},
                )
            else:
                raise ElementNotFoundError(
                    f"Failed to fill {selector}: {e}",
                    correlation_id=self.correlation_id,
                    context={"selector": selector, "error_type": type(e).__name__},
                )

    async def download_document(
        self, url: str, expected_size: Optional[int] = None
    ) -> bytes:
        """Download a document with retry logic and validation.

        Args:
            url: URL to download from
            expected_size: Optional expected file size for validation

        Returns:
            Document content as bytes

        Raises:
            DownloadError: If download fails
        """
        if not self.http_client:
            raise DownloadFailedError(
                "HTTP client not initialized", correlation_id=self.correlation_id
            )

        async def _download():
            self.logger.debug(
                "downloading_document", url=url, correlation_id=self.correlation_id
            )

            try:
                response = await self.http_client.get(url)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise RateLimitError(
                        f"Rate limited while downloading: {e}",
                        retry_after=int(e.response.headers.get("Retry-After", 60)),
                        correlation_id=self.correlation_id,
                        context={"url": url, "status_code": e.response.status_code},
                    )
                elif e.response.status_code >= 500:
                    raise RetryableError(
                        f"Server error while downloading: {e}",
                        correlation_id=self.correlation_id,
                        context={"url": url, "status_code": e.response.status_code},
                    )
                else:
                    raise DownloadFailedError(
                        f"HTTP error while downloading: {e}",
                        correlation_id=self.correlation_id,
                        context={"url": url, "status_code": e.response.status_code},
                    )
            except httpx.TimeoutException as e:
                raise DownloadFailedError(
                    f"Download timeout: {e}",
                    correlation_id=self.correlation_id,
                    context={"url": url, "timeout": self.http_client.timeout},
                )
            except Exception as e:
                raise DownloadFailedError(
                    f"Download failed: {e}",
                    correlation_id=self.correlation_id,
                    context={"url": url, "error_type": type(e).__name__},
                )

            content = response.content

            # Validate content
            if not content:
                raise DownloadFailedError(
                    "Downloaded content is empty",
                    correlation_id=self.correlation_id,
                    context={"url": url},
                )

            if expected_size and len(content) != expected_size:
                self.logger.warning(
                    "size_mismatch",
                    expected=expected_size,
                    actual=len(content),
                    correlation_id=self.correlation_id,
                )

            # Validate PDF header
            if not content.startswith(b"%PDF"):
                raise DownloadFailedError(
                    "Downloaded content is not a valid PDF",
                    correlation_id=self.correlation_id,
                    context={
                        "url": url,
                        "content_preview": content[:20].hex() if content else "empty",
                    },
                )

            self.logger.info(
                "document_downloaded",
                url=url,
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest()[:16],
                correlation_id=self.correlation_id,
            )

            return content

        return await self.retry_with_backoff(_download, "document_download")

    def compute_document_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of document content.

        Args:
            content: Document content as bytes

        Returns:
            SHA256 hash as hex string
        """
        return hashlib.sha256(content).hexdigest()

    async def download_file_streaming(
        self,
        url: str,
        filepath: Path,
        chunk_size: int = 8192,
        progress_callback: Optional[callable] = None,
    ) -> bool:
        """Download file with streaming and progress tracking.

        Args:
            url: URL to download from
            filepath: Path to save file
            chunk_size: Size of chunks to download
            progress_callback: Optional callback for progress updates

        Returns:
            True if download successful

        Raises:
            DownloadFailedError: If download fails
        """
        try:
            # Ensure directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # Check if file already exists
            if filepath.exists():
                self.logger.info("file_already_exists", filepath=str(filepath))
                return True

            async def _download():
                async with self.http_client.stream("GET", url) as response:
                    response.raise_for_status()

                    # Get total size if available
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0

                    # Download with progress tracking
                    with open(filepath, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if progress_callback and total_size:
                                progress_callback(downloaded, total_size)

                    self.logger.info(
                        "file_downloaded_streaming",
                        url=url,
                        filepath=str(filepath),
                        size=downloaded,
                    )

                return True

            return await self.retry_with_backoff(_download, "streaming_download")

        except Exception as e:
            self.logger.error("streaming_download_failed", url=url, error=str(e))
            raise DownloadFailedError(
                f"Streaming download failed: {e}",
                correlation_id=self.correlation_id,
                context={"url": url, "filepath": str(filepath)},
            )

    async def manage_cookies(self) -> Dict[str, str]:
        """Extract and manage cookies between Playwright and HTTP client.

        Returns:
            Dictionary of cookies
        """
        if not self.context:
            return {}

        try:
            # Get cookies from browser context
            cookies = await self.context.cookies()

            # Convert to dict format for HTTP client
            cookie_dict = {}
            for cookie in cookies:
                cookie_dict[cookie["name"]] = cookie["value"]

            # Update HTTP client cookies
            if self.http_client:
                self.http_client.cookies.update(cookie_dict)

            self.logger.debug("cookies_synced", cookie_count=len(cookie_dict))

            return cookie_dict

        except Exception as e:
            self.logger.warning("cookie_sync_failed", error=str(e))
            return {}

    async def extract_table_data(
        self, table_selector: str, header_row_index: int = 0
    ) -> List[Dict[str, str]]:
        """Generic table data extraction.

        Args:
            table_selector: CSS selector for table
            header_row_index: Index of header row

        Returns:
            List of dictionaries with table data
        """
        if not self.page:
            raise ElementNotFoundError(
                "Page not initialized", correlation_id=self.correlation_id
            )

        try:
            # Wait for table
            await self.page.wait_for_selector(table_selector, timeout=self.timeout)

            # Extract table data
            table_data = await self.page.evaluate(
                """
                (selector, headerIndex) => {
                    const table = document.querySelector(selector);
                    if (!table) return [];
                    
                    const rows = Array.from(table.querySelectorAll('tr'));
                    if (rows.length <= headerIndex) return [];
                    
                    // Get headers
                    const headerRow = rows[headerIndex];
                    const headers = Array.from(headerRow.querySelectorAll('th, td'))
                        .map(cell => cell.textContent.trim());
                    
                    // Extract data rows
                    const data = [];
                    for (let i = headerIndex + 1; i < rows.length; i++) {
                        const row = rows[i];
                        const cells = Array.from(row.querySelectorAll('td'));
                        
                        const rowData = {};
                        headers.forEach((header, index) => {
                            if (cells[index]) {
                                rowData[header] = cells[index].textContent.trim();
                            }
                        });
                        
                        if (Object.keys(rowData).length > 0) {
                            data.push(rowData);
                        }
                    }
                    
                    return data;
                }
            """,
                table_selector,
                header_row_index,
            )

            self.logger.debug(
                "table_data_extracted",
                selector=table_selector,
                row_count=len(table_data),
            )

            return table_data

        except Exception as e:
            self.logger.error(
                "table_extraction_failed", selector=table_selector, error=str(e)
            )
            raise ElementNotFoundError(
                f"Failed to extract table data: {e}",
                correlation_id=self.correlation_id,
                context={"selector": table_selector},
            )

    async def handle_pagination(
        self,
        next_button_selector: str,
        content_selector: str,
        max_pages: Optional[int] = None,
    ) -> AsyncIterator[Page]:
        """Generic pagination handler.

        Args:
            next_button_selector: Selector for next/load more button
            content_selector: Selector to wait for after pagination
            max_pages: Maximum number of pages to process

        Yields:
            Page object after each pagination
        """
        if not self.page:
            raise ElementNotFoundError(
                "Page not initialized", correlation_id=self.correlation_id
            )

        page_count = 1

        while True:
            # Yield current page
            yield self.page

            # Check page limit
            if max_pages and page_count >= max_pages:
                self.logger.info("pagination_limit_reached", max_pages=max_pages)
                break

            try:
                # Look for next button
                next_button = await self.page.query_selector(next_button_selector)
                if not next_button:
                    self.logger.info("no_more_pages")
                    break

                # Check if button is disabled
                is_disabled = await next_button.get_attribute("disabled")
                if is_disabled:
                    self.logger.info("next_button_disabled")
                    break

                # Get current content count for comparison
                current_count = len(
                    await self.page.query_selector_all(content_selector)
                )

                # Click next button
                await next_button.click()

                # Wait for new content
                await self.page.wait_for_function(
                    f"document.querySelectorAll('{content_selector}').length > {current_count}",
                    timeout=10000,
                )

                # Additional wait for stability
                await asyncio.sleep(1)

                page_count += 1
                self.logger.debug("pagination_advanced", page=page_count)

            except Exception as e:
                self.logger.warning("pagination_ended", page=page_count, reason=str(e))
                break

    async def clear_search_input(self, selector: str) -> None:
        """Clear a search input field.

        Args:
            selector: CSS selector for input field
        """
        if not self.page:
            return

        try:
            input_element = await self.page.query_selector(selector)
            if input_element:
                # Triple-click to select all and then delete
                await input_element.click(click_count=3)
                await self.page.keyboard.press("Delete")

                # Alternative: Clear using JavaScript
                await self.page.evaluate(
                    f"document.querySelector('{selector}').value = ''"
                )

                self.logger.debug("search_input_cleared", selector=selector)

        except Exception as e:
            self.logger.warning("clear_input_failed", selector=selector, error=str(e))

    @abstractmethod
    async def discover_documents(self) -> List[DocumentMetadata]:
        """Discover available documents from the portal.

        Returns:
            List of document metadata

        Raises:
            WebScrapingException: If discovery fails
            NavigationTimeoutError: If page navigation times out
            ElementNotFoundError: If required elements are not found
        """
        pass

    @abstractmethod
    async def extract_document_metadata(self, document_url: str) -> DocumentMetadata:
        """Extract detailed metadata for a specific document.

        Args:
            document_url: URL of the document detail page

        Returns:
            Document metadata

        Raises:
            ElementNotFoundError: If metadata extraction fails
            NavigationTimeoutError: If page navigation times out
            WebScrapingException: If unexpected error occurs
        """
        pass

    async def scrape_portal(self) -> List[DocumentMetadata]:
        """Main scraping method that orchestrates the entire process.

        Returns:
            List of discovered documents with metadata

        Raises:
            ScrapingError: If scraping fails
        """
        try:
            self.logger.info("starting_portal_scrape", source=self.source_name)

            # Discover documents
            documents = await self.retry_with_backoff(
                self.discover_documents, "document_discovery"
            )

            self.logger.info(
                "documents_discovered", count=len(documents), source=self.source_name
            )

            # Extract detailed metadata for each document
            enriched_documents = []
            for i, doc in enumerate(documents):
                try:
                    self.logger.debug(
                        "extracting_document_metadata",
                        document=i + 1,
                        total=len(documents),
                        franchise=doc.franchise_name,
                    )

                    enriched_doc = await self.retry_with_backoff(
                        self.extract_document_metadata,
                        f"metadata_extraction_{i}",
                        doc.source_url,
                    )
                    enriched_documents.append(enriched_doc)

                    # Add small delay between requests to be respectful
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                except Exception as e:
                    self.logger.error(
                        "metadata_extraction_failed",
                        document=i + 1,
                        franchise=doc.franchise_name,
                        error=str(e),
                    )
                    # Continue with basic metadata if detailed extraction fails
                    enriched_documents.append(doc)

            self.logger.info(
                "portal_scrape_completed",
                source=self.source_name,
                total_documents=len(enriched_documents),
            )

            return enriched_documents

        except Exception as e:
            self.logger.error(
                "portal_scrape_failed", source=self.source_name, error=str(e)
            )
            raise WebScrapingException(
                f"Portal scraping failed for {self.source_name}: {e}",
                correlation_id=self.correlation_id,
                context={
                    "source_name": self.source_name,
                    "error_type": type(e).__name__,
                    "documents_discovered": (
                        len(documents) if "documents" in locals() else 0
                    ),
                },
            )


@asynccontextmanager
async def create_scraper(scraper_class, *args, **kwargs):
    """Context manager for creating and managing scrapers.

    Args:
        scraper_class: Scraper class to instantiate
        *args: Arguments for scraper constructor
        **kwargs: Keyword arguments for scraper constructor

    Yields:
        Initialized scraper instance

    Raises:
        BrowserInitializationError: If browser fails to start
        WebScrapingException: If scraper initialization fails
    """
    scraper = scraper_class(*args, **kwargs)
    try:
        await scraper.initialize()
        yield scraper
    except BrowserInitializationError:
        # Re-raise browser initialization errors
        raise
    except Exception as e:
        # Wrap other errors with context
        raise WebScrapingException(
            f"Scraper context manager failed: {e}",
            correlation_id=getattr(scraper, "correlation_id", None),
            context={
                "scraper_class": scraper_class.__name__,
                "error_type": type(e).__name__,
            },
        )
    finally:
        await scraper.cleanup()
