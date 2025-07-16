"""Base web scraping framework with Playwright browser management."""

import asyncio
import hashlib
import random
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import httpx
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel

from config import get_settings
from models.scrape_metadata import ScrapeMetadata
from utils.logging import PipelineLogger


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


class ScrapingError(Exception):
    """Base exception for scraping errors."""
    pass


class NavigationError(ScrapingError):
    """Error during page navigation."""
    pass


class ExtractionError(ScrapingError):
    """Error during data extraction."""
    pass


class DownloadError(ScrapingError):
    """Error during document download."""
    pass


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
        prefect_run_id: Optional[UUID] = None
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
        self.logger = PipelineLogger(
            f"scraper.{source_name.lower()}",
            prefect_run_id=str(prefect_run_id) if prefect_run_id else None
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
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-extensions',
                    '--no-first-run',
                    '--disable-default-apps',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                ]
            )
            
            # Create browser context with random user agent
            user_agent = random.choice(self.USER_AGENTS)
            self.context = await self.browser.new_context(
                user_agent=user_agent,
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True,
            )
            
            # Create page
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            self.page.set_default_navigation_timeout(self.timeout)
            
            # Initialize HTTP client
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={'User-Agent': user_agent},
                follow_redirects=True
            )
            
            self.logger.info("scraper_initialized", user_agent=user_agent)
            
        except Exception as e:
            self.logger.error("scraper_initialization_failed", error=str(e))
            await self.cleanup()
            raise ScrapingError(f"Failed to initialize scraper: {e}")
    
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
        self,
        operation,
        operation_name: str,
        *args,
        **kwargs
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
                    max_attempts=self.max_retries
                )
                
                result = await operation(*args, **kwargs)
                
                if attempt > 0:
                    self.logger.info(
                        "operation_succeeded_after_retry",
                        operation=operation_name,
                        attempt=attempt + 1
                    )
                
                return result
                
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    "operation_attempt_failed",
                    operation=operation_name,
                    attempt=attempt + 1,
                    error=str(e)
                )
                
                if attempt < self.max_retries - 1:
                    # Calculate delay with exponential backoff and jitter
                    delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                    self.logger.debug("retrying_after_delay", delay=delay)
                    await asyncio.sleep(delay)
        
        # All attempts failed
        self.logger.error(
            "operation_failed_all_attempts",
            operation=operation_name,
            max_attempts=self.max_retries,
            final_error=str(last_exception)
        )
        raise ScrapingError(f"{operation_name} failed after {self.max_retries} attempts: {last_exception}")
    
    async def safe_navigate(self, url: str, wait_for: Optional[str] = None) -> None:
        """Safely navigate to a URL with error handling.
        
        Args:
            url: URL to navigate to
            wait_for: Optional selector to wait for after navigation
            
        Raises:
            NavigationError: If navigation fails
        """
        if not self.page:
            raise NavigationError("Page not initialized")
        
        try:
            self.logger.debug("navigating_to_url", url=url)
            
            await self.page.goto(url, wait_until='networkidle')
            
            if wait_for:
                await self.page.wait_for_selector(wait_for, timeout=self.timeout)
            
            self.logger.debug("navigation_successful", url=url)
            
        except Exception as e:
            self.logger.error("navigation_failed", url=url, error=str(e))
            raise NavigationError(f"Failed to navigate to {url}: {e}")
    
    async def safe_click(self, selector: str, timeout: Optional[int] = None) -> None:
        """Safely click an element with error handling.
        
        Args:
            selector: CSS selector for element to click
            timeout: Optional timeout override
            
        Raises:
            ExtractionError: If click fails
        """
        if not self.page:
            raise ExtractionError("Page not initialized")
        
        try:
            element = await self.page.wait_for_selector(
                selector, 
                timeout=timeout or self.timeout
            )
            if not element:
                raise ExtractionError(f"Element not found: {selector}")
            
            await element.click()
            self.logger.debug("element_clicked", selector=selector)
            
        except Exception as e:
            self.logger.error("click_failed", selector=selector, error=str(e))
            raise ExtractionError(f"Failed to click {selector}: {e}")
    
    async def safe_fill(self, selector: str, value: str, timeout: Optional[int] = None) -> None:
        """Safely fill an input field with error handling.
        
        Args:
            selector: CSS selector for input element
            value: Value to fill
            timeout: Optional timeout override
            
        Raises:
            ExtractionError: If fill fails
        """
        if not self.page:
            raise ExtractionError("Page not initialized")
        
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=timeout or self.timeout
            )
            if not element:
                raise ExtractionError(f"Element not found: {selector}")
            
            await element.fill(value)
            self.logger.debug("element_filled", selector=selector, value_length=len(value))
            
        except Exception as e:
            self.logger.error("fill_failed", selector=selector, error=str(e))
            raise ExtractionError(f"Failed to fill {selector}: {e}")
    
    async def download_document(self, url: str, expected_size: Optional[int] = None) -> bytes:
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
            raise DownloadError("HTTP client not initialized")
        
        async def _download():
            self.logger.debug("downloading_document", url=url)
            
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            content = response.content
            
            # Validate content
            if not content:
                raise DownloadError("Downloaded content is empty")
            
            if expected_size and len(content) != expected_size:
                self.logger.warning(
                    "size_mismatch",
                    expected=expected_size,
                    actual=len(content)
                )
            
            # Validate PDF header
            if not content.startswith(b'%PDF'):
                raise DownloadError("Downloaded content is not a valid PDF")
            
            self.logger.info(
                "document_downloaded",
                url=url,
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest()[:16]
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
    
    @abstractmethod
    async def discover_documents(self) -> List[DocumentMetadata]:
        """Discover available documents from the portal.
        
        Returns:
            List of document metadata
            
        Raises:
            ScrapingError: If discovery fails
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
            ExtractionError: If metadata extraction fails
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
                self.discover_documents,
                "document_discovery"
            )
            
            self.logger.info(
                "documents_discovered",
                count=len(documents),
                source=self.source_name
            )
            
            # Extract detailed metadata for each document
            enriched_documents = []
            for i, doc in enumerate(documents):
                try:
                    self.logger.debug(
                        "extracting_document_metadata",
                        document=i + 1,
                        total=len(documents),
                        franchise=doc.franchise_name
                    )
                    
                    enriched_doc = await self.retry_with_backoff(
                        self.extract_document_metadata,
                        f"metadata_extraction_{i}",
                        doc.source_url
                    )
                    enriched_documents.append(enriched_doc)
                    
                    # Add small delay between requests to be respectful
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    
                except Exception as e:
                    self.logger.error(
                        "metadata_extraction_failed",
                        document=i + 1,
                        franchise=doc.franchise_name,
                        error=str(e)
                    )
                    # Continue with basic metadata if detailed extraction fails
                    enriched_documents.append(doc)
            
            self.logger.info(
                "portal_scrape_completed",
                source=self.source_name,
                total_documents=len(enriched_documents)
            )
            
            return enriched_documents
            
        except Exception as e:
            self.logger.error("portal_scrape_failed", source=self.source_name, error=str(e))
            raise ScrapingError(f"Portal scraping failed for {self.source_name}: {e}")


@asynccontextmanager
async def create_scraper(scraper_class, *args, **kwargs):
    """Context manager for creating and managing scrapers.
    
    Args:
        scraper_class: Scraper class to instantiate
        *args: Arguments for scraper constructor
        **kwargs: Keyword arguments for scraper constructor
        
    Yields:
        Initialized scraper instance
    """
    scraper = scraper_class(*args, **kwargs)
    try:
        await scraper.initialize()
        yield scraper
    finally:
        await scraper.cleanup()