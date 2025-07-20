"""Minnesota portal scraper implementation."""

import asyncio
import json
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import logging
import time
from functools import wraps

from scrapers.base.base_scraper import (
    BaseScraper,
    DocumentMetadata,
    create_scraper,
)
from scrapers.base.exceptions import (
    ElementNotFoundError,
    WebScrapingException,
)
from utils.scraping_utils import (
    clean_text,
)

# Create module logger
logger = logging.getLogger(__name__)


def log_method_call(func):
    """Decorator to log method calls with timing."""
    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        start_time = time.time()
        method_name = func.__name__
        
        self.logger.debug(
            f"calling_{method_name}",
            args=str(args)[:200] if args else None,
            kwargs=str(kwargs)[:200] if kwargs else None
        )
        
        try:
            result = await func(self, *args, **kwargs)
            execution_time = time.time() - start_time
            
            self.logger.debug(
                f"{method_name}_completed",
                execution_time=f"{execution_time:.3f}s",
                result_type=type(result).__name__,
                result_size=len(result) if hasattr(result, '__len__') else None
            )
            
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(
                f"{method_name}_failed",
                execution_time=f"{execution_time:.3f}s",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    return async_wrapper


class MinnesotaScraper(BaseScraper):
    """Scraper for Minnesota Department of Commerce CARDS FDD portal."""

    # Minnesota CARDS portal URLs
    BASE_URL = "https://www.cards.commerce.state.mn.us"
    SEARCH_URL = "https://www.cards.commerce.state.mn.us/franchise-registrations?doSearch=true&documentTitle=&franchisor=&franchiseName=&year=&fileNumber=&documentType=Clean+FDD&content="

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        prefect_run_id: Optional[str] = None,
    ):
        """Initialize Minnesota scraper.

        Args:
            headless: Whether to run browser in headless mode
            timeout: Default timeout in milliseconds
            prefect_run_id: Optional Prefect run ID for tracking
        """
        super().__init__(
            source_name="MN",
            headless=headless,
            timeout=timeout,
            prefect_run_id=prefect_run_id,
        )
        
        # Log initialization
        self.logger.debug(
            "minnesota_scraper_initialized",
            base_url=self.BASE_URL,
            search_url=self.SEARCH_URL,
            headless=headless,
            timeout=timeout,
            prefect_run_id=prefect_run_id
        )

    @log_method_call
    async def discover_documents(self) -> List[DocumentMetadata]:
        """Discover available FDD documents from Minnesota CARDS portal.

        Returns:
            List of document metadata for discovered documents

        Raises:
            NavigationError: If navigation to portal fails
            ExtractionError: If document discovery fails
        """
        try:
            self.logger.info("starting_minnesota_cards_document_discovery")

            # Navigate to the CARDS search page (already filtered for Clean FDD)
            await self.safe_navigate(self.SEARCH_URL)

            if not self.page:
                raise WebScrapingException("Page not initialized after navigation")
                
            # Wait for the results table to load
            await self.page.wait_for_selector("#results", timeout=self.timeout)

            # Extract documents from the current page
            documents = await self._extract_cards_results()

            # Use enhanced pagination handling with Load More button
            load_more_selector = 'button:has-text("Load more")'
            alternative_selectors = [
                "#main-content > form ul button",
                'button:has-text("Load More")',
                'button:has-text("LOAD MORE")',
                'a:has-text("Load more")',
                'button[aria-label*="load more" i]',
                ".load-more-button",
                "button.load-more",
            ]

            # Try to find the load more button with various selectors
            found_selector = None
            for selector in [load_more_selector] + alternative_selectors:
                try:
                    button = await self.page.query_selector(selector)
                    if button and await button.is_visible():
                        found_selector = selector
                        self.logger.debug(
                            f"Found load more button with selector: {selector}"
                        )
                        break
                except:
                    continue

            if found_selector:
                # Handle pagination with Load More pattern
                page_num = 1
                max_pages = 20  # Reasonable limit

                while page_num < max_pages:
                    # Look for load more button
                    load_more_button = await self.page.query_selector(found_selector)
                    if not load_more_button:
                        self.logger.info(
                            "no_more_pages_available", current_page=page_num
                        )
                        break

                    # Check if button is disabled
                    is_disabled = await load_more_button.get_attribute("disabled")
                    if is_disabled:
                        self.logger.info(
                            "load_more_button_disabled", current_page=page_num
                        )
                        break

                    # Get current document count
                    current_count = len(documents)

                    # Click load more
                    self.logger.info(
                        "clicking_load_more_button", page_number=page_num + 1
                    )
                    await load_more_button.click()

                    # Wait for new content
                    await asyncio.sleep(2)

                    # Wait for new rows to appear
                    try:
                        await self.page.wait_for_function(
                            f"document.querySelectorAll('#results tr').length > {len(await self.page.query_selector_all('#results tr'))}",
                            timeout=10000,
                        )
                    except:
                        self.logger.warning("timeout_waiting_for_new_content")
                        break

                    # Extract all documents from updated table
                    all_documents = await self._extract_cards_results()

                    # Only add new documents
                    new_documents = all_documents[current_count:]
                    if not new_documents:
                        self.logger.info("no_new_documents_loaded")
                        break

                    documents.extend(new_documents)
                    self.logger.info(
                        "new_documents_loaded",
                        count=len(new_documents),
                        total=len(documents),
                    )

                    page_num += 1
                    await asyncio.sleep(1)  # Be respectful between requests

            self.logger.info(
                "minnesota_cards_document_discovery_completed",
                documents_found=len(documents),
                pages_processed=page_num,
            )

            return documents

        except Exception as e:
            self.logger.error("minnesota_cards_document_discovery_failed", error=str(e))
            raise WebScrapingException(
                f"Failed to discover documents from Minnesota CARDS portal: {e}"
            )

    @log_method_call
    async def _extract_cards_results(self) -> List[DocumentMetadata]:
        """Extract documents from CARDS results table.

        Returns:
            List of discovered documents from current page
        """
        documents = []

        try:
            if not self.page:
                raise WebScrapingException("Page not initialized")
                
            # Wait for results table to be populated
            await self.page.wait_for_selector("#results tr", timeout=self.timeout)

            # Get all table rows (skip header)
            rows = await self.page.query_selector_all("#results tr")

            for i, row in enumerate(rows):
                if i == 0:  # Skip header row
                    continue

                try:
                    # Extract data from table cells - CARDS table has 9 columns
                    cells = await row.query_selector_all("td, th")
                    if len(cells) < 9:  # CARDS table has 9 columns
                        continue

                    # Extract text from each cell based on actual structure:
                    # 0: # (row number) - this is a th element
                    # 1: Document (contains download link)
                    # 2: Franchisor
                    # 3: Franchise names
                    # 4: Document types
                    # 5: Year
                    # 6: File number
                    # 7: Notes
                    # 8: Received date/Added on

                    # Extract download link from the Document column (index 1)
                    download_link_elem = await cells[1].query_selector("a")
                    if not download_link_elem:
                        continue

                    download_url = await download_link_elem.get_attribute("href")
                    if not download_url:
                        continue

                    # Extract document title from the link
                    title = await download_link_elem.inner_text()

                    # Extract other data
                    franchisor = await cells[2].inner_text()
                    franchise_name = await cells[3].inner_text()
                    document_type = await cells[4].inner_text()
                    year = await cells[5].inner_text()
                    file_number = await cells[6].inner_text()
                    notes = await cells[7].inner_text()
                    received_date = await cells[8].inner_text()

                    # Convert relative URL to absolute
                    if download_url.startswith("/"):
                        download_url = urljoin(self.BASE_URL, download_url)
                    elif not download_url.startswith("http"):
                        download_url = urljoin(self.BASE_URL, download_url)

                    # Extract document ID from URL for tracking
                    document_id = None
                    id_match = re.search(r"documentId=%7B(.+?)%7D", download_url)
                    if id_match:
                        document_id = id_match.group(1)

                    # Create document metadata
                    document = DocumentMetadata(
                        franchise_name=franchise_name.strip(),
                        filing_date=None,  # Year is available but not specific date
                        document_type=document_type.strip(),
                        filing_number=(
                            file_number.strip() if file_number.strip() else None
                        ),
                        source_url=self.page.url,
                        download_url=download_url,
                        additional_metadata={
                            "source": "MN",
                            "discovery_method": "cards_table",
                            "title": title.strip(),
                            "franchisor": franchisor.strip(),
                            "year": year.strip(),
                            "document_id": document_id,
                        },
                    )

                    documents.append(document)

                    self.logger.debug(
                        "cards_document_discovered",
                        franchise_name=franchise_name.strip(),
                        franchisor=franchisor.strip(),
                        year=year.strip(),
                        document_id=document_id,
                    )

                except Exception as e:
                    self.logger.warning(
                        "failed_to_process_cards_row", row_index=i, error=str(e)
                    )
                    continue

        except Exception as e:
            self.logger.error("cards_results_extraction_failed", error=str(e))

        return documents

    async def _fetch_next_page(self, hx_vals: str) -> List[DocumentMetadata]:
        """Fetch next page of results using CARDS API.

        Args:
            hx_vals: The hx-vals attribute containing page token data

        Returns:
            List of documents from next page
        """
        try:
            # Parse the hx-vals JSON
            page_data = json.loads(hx_vals)

            # Prepare the POST request to the next page API
            api_url = urljoin(self.BASE_URL, "/api/documents/next-page")

            # Set up headers for the HTMX request
            if not self.page:
                raise WebScrapingException("Page not initialized")
                
            headers = {
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9",
                "content-type": "application/x-www-form-urlencoded",
                "hx-current-url": self.page.url,
                "hx-request": "true",
                "hx-target": "results",
                "origin": self.BASE_URL,
                "referer": self.page.url,
            }

            # Prepare form data
            form_data = {
                "documentClass": page_data.get(
                    "documentClass", "FRANCHISE_REGISTRATIONS"
                ),
                "pageToken": page_data.get("pageToken", ""),
                "pageNumber": page_data.get("pageNumber", 1),
            }

            # Make the API request
            if not self.http_client:
                raise WebScrapingException("HTTP client not initialized")

            response = await self.http_client.post(
                api_url, headers=headers, data=form_data
            )
            response.raise_for_status()

            # Parse the HTML response and extract documents
            html_content = response.text

            # Create a temporary page to parse the response
            temp_page = await self.context.new_page()
            try:
                # Set the HTML content
                await temp_page.set_content(html_content)

                # Extract documents from the response
                documents = []
                rows = await temp_page.query_selector_all("#results tr")

                for i, row in enumerate(rows):
                    if i == 0:  # Skip header row if present
                        continue

                    try:
                        cells = await row.query_selector_all("td, th")
                        if len(cells) < 9:
                            continue

                        # Extract data similar to _extract_cards_results
                        # Same structure as main extraction method
                        download_link_elem = await cells[1].query_selector("a")
                        if not download_link_elem:
                            continue

                        download_url = await download_link_elem.get_attribute("href")
                        if not download_url:
                            continue

                        title = await download_link_elem.inner_text()
                        franchisor = await cells[2].inner_text()
                        franchise_name = await cells[3].inner_text()
                        document_type = await cells[4].inner_text()
                        year = await cells[5].inner_text()
                        file_number = await cells[6].inner_text()

                        if download_url.startswith("/"):
                            download_url = urljoin(self.BASE_URL, download_url)

                        document_id = None
                        id_match = re.search(r"documentId=%7B(.+?)%7D", download_url)
                        if id_match:
                            document_id = id_match.group(1)

                        document = DocumentMetadata(
                            franchise_name=franchise_name.strip(),
                            filing_date=None,
                            document_type=document_type.strip(),
                            filing_number=(
                                file_number.strip() if file_number.strip() else None
                            ),
                            source_url=self.page.url,
                            download_url=download_url,
                            additional_metadata={
                                "source": "MN",
                                "discovery_method": "cards_api",
                                "title": title.strip(),
                                "franchisor": franchisor.strip(),
                                "year": year.strip(),
                                "document_id": document_id,
                            },
                        )

                        documents.append(document)

                    except Exception as e:
                        self.logger.warning(
                            "failed_to_process_api_row", row_index=i, error=str(e)
                        )
                        continue

                return documents

            finally:
                await temp_page.close()

        except Exception as e:
            self.logger.error("next_page_fetch_failed", error=str(e))
            return []

    async def _discover_via_search_form(self) -> List[DocumentMetadata]:
        """Discover documents via search form interface.

        Returns:
            List of discovered documents
        """
        documents = []

        try:
            # Look for search input field
            search_input = await self.page.query_selector(
                "input[type='text'], input[type='search']"
            )
            if not search_input:
                self.logger.warning("no_search_input_found")
                return documents

            # Try searching for "franchise" or leave empty for all results
            await search_input.fill("franchise")

            # Find and click search button
            search_button = await self.page.query_selector(
                "input[type='submit'], button[type='submit'], button:has-text('Search')"
            )
            if search_button:
                await search_button.click()
                await self.page.wait_for_load_state("networkidle")

            # Extract results from search results page
            documents = await self._extract_search_results()

        except Exception as e:
            self.logger.warning("search_form_discovery_failed", error=str(e))

        return documents

    async def _discover_via_table(self) -> List[DocumentMetadata]:
        """Discover documents via table listing.

        Returns:
            List of discovered documents
        """
        documents = []

        try:
            # Find table rows with franchise information
            rows = await self.page.query_selector_all("table tr")

            for i, row in enumerate(rows):
                if i == 0:  # Skip header row
                    continue

                try:
                    # Extract franchise name and document link from row
                    cells = await row.query_selector_all("td")
                    if len(cells) < 2:
                        continue

                    # First cell typically contains franchise name
                    franchise_name_element = cells[0]
                    franchise_name = await franchise_name_element.inner_text()
                    franchise_name = franchise_name.strip()

                    if not franchise_name:
                        continue

                    # Look for download link in any cell
                    download_link = None
                    for cell in cells:
                        link = await cell.query_selector(
                            "a[href*='.pdf'], a:has-text('Download'), a:has-text('FDD')"
                        )
                        if link:
                            download_link = await link.get_attribute("href")
                            break

                    if download_link:
                        # Convert relative URLs to absolute
                        if download_link.startswith("/"):
                            download_link = urljoin(self.BASE_URL, download_link)
                        elif not download_link.startswith("http"):
                            download_link = urljoin(self.SEARCH_URL, download_link)

                        # Extract additional metadata from row
                        filing_date = None
                        filing_number = None

                        # Try to extract date from cells (common patterns)
                        for cell in cells:
                            cell_text = await cell.inner_text()
                            date_match = re.search(
                                r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", cell_text
                            )
                            if date_match and not filing_date:
                                filing_date = date_match.group(0)

                            # Look for filing numbers
                            number_match = re.search(r"#?\s*(\d{4,})", cell_text)
                            if number_match and not filing_number:
                                filing_number = number_match.group(1)

                        document = DocumentMetadata(
                            franchise_name=franchise_name,
                            filing_date=filing_date,
                            filing_number=filing_number,
                            source_url=self.page.url,
                            download_url=download_link,
                            additional_metadata={
                                "source": "MN",
                                "discovery_method": "table",
                            },
                        )
                        documents.append(document)

                        self.logger.debug(
                            "document_discovered_from_table",
                            franchise_name=franchise_name,
                            download_url=download_link,
                        )

                except Exception as e:
                    self.logger.warning(
                        "failed_to_process_table_row", row_index=i, error=str(e)
                    )
                    continue

        except Exception as e:
            self.logger.warning("table_discovery_failed", error=str(e))

        return documents

    async def _discover_via_links(self) -> List[DocumentMetadata]:
        """Discover documents via direct links on page.

        Returns:
            List of discovered documents
        """
        documents = []

        try:
            # Look for PDF links or franchise-related links
            links = await self.page.query_selector_all(
                "a[href*='.pdf'], a:has-text('FDD'), a:has-text('Franchise'), a:has-text('Disclosure')"
            )

            for link in links:
                try:
                    href = await link.get_attribute("href")
                    if not href:
                        continue

                    # Convert relative URLs to absolute
                    if href.startswith("/"):
                        href = urljoin(self.BASE_URL, href)
                    elif not href.startswith("http"):
                        href = urljoin(self.page.url, href)

                    # Extract franchise name from link text or surrounding context
                    link_text = await link.inner_text()
                    franchise_name = link_text.strip()

                    # If link text is generic, try to get franchise name from context
                    if franchise_name.lower() in ["download", "fdd", "pdf", "view"]:
                        # Look for franchise name in parent elements
                        parent = await link.query_selector("xpath=..")
                        if parent:
                            parent_text = await parent.inner_text()
                            # Extract potential franchise name (first meaningful text)
                            lines = [
                                line.strip()
                                for line in parent_text.split("\n")
                                if line.strip()
                            ]
                            for line in lines:
                                if (
                                    line.lower()
                                    not in ["download", "fdd", "pdf", "view"]
                                    and len(line) > 3
                                ):
                                    franchise_name = line
                                    break

                    if franchise_name and len(franchise_name) > 3:
                        document = DocumentMetadata(
                            franchise_name=franchise_name,
                            source_url=self.page.url,
                            download_url=href,
                            additional_metadata={
                                "source": "MN",
                                "discovery_method": "links",
                            },
                        )
                        documents.append(document)

                        self.logger.debug(
                            "document_discovered_from_link",
                            franchise_name=franchise_name,
                            download_url=href,
                        )

                except Exception as e:
                    self.logger.warning("failed_to_process_link", error=str(e))
                    continue

        except Exception as e:
            self.logger.warning("link_discovery_failed", error=str(e))

        return documents

    async def _extract_search_results(self) -> List[DocumentMetadata]:
        """Extract documents from search results page.

        Returns:
            List of discovered documents
        """
        documents = []

        try:
            # Wait for results to load
            await self.page.wait_for_load_state("networkidle")

            # Look for results in various common formats
            # Try table format first
            table_docs = await self._discover_via_table()
            if table_docs:
                documents.extend(table_docs)

            # Try list format
            list_items = await self.page.query_selector_all(
                "li, .result, .search-result"
            )
            for item in list_items:
                try:
                    # Look for franchise name and download link within each result
                    franchise_name_elem = await item.query_selector(
                        "h1, h2, h3, h4, .title, .name, strong"
                    )
                    if franchise_name_elem:
                        franchise_name = await franchise_name_elem.inner_text()
                        franchise_name = franchise_name.strip()

                        # Look for download link
                        download_link_elem = await item.query_selector(
                            "a[href*='.pdf'], a:has-text('Download')"
                        )
                        if download_link_elem:
                            download_url = await download_link_elem.get_attribute(
                                "href"
                            )

                            if download_url:
                                # Convert relative URLs to absolute
                                if download_url.startswith("/"):
                                    download_url = urljoin(self.BASE_URL, download_url)
                                elif not download_url.startswith("http"):
                                    download_url = urljoin(self.page.url, download_url)

                                document = DocumentMetadata(
                                    franchise_name=franchise_name,
                                    source_url=self.page.url,
                                    download_url=download_url,
                                    additional_metadata={
                                        "source": "MN",
                                        "discovery_method": "search_results",
                                    },
                                )
                                documents.append(document)

                except Exception as e:
                    self.logger.warning("failed_to_process_search_result", error=str(e))
                    continue

        except Exception as e:
            self.logger.warning("search_results_extraction_failed", error=str(e))

        return documents

    @log_method_call
    async def extract_document_metadata(self, document_url: str) -> DocumentMetadata:
        """Extract detailed metadata for a specific document.

        Args:
            document_url: URL of the document detail page

        Returns:
            Enhanced document metadata

        Raises:
            ExtractionError: If metadata extraction fails
        """
        try:
            self.logger.debug(
                "extracting_minnesota_document_metadata", url=document_url
            )

            # Navigate to document detail page
            await self.safe_navigate(document_url)

            # Extract enhanced metadata
            franchise_name = await self._extract_franchise_name()
            filing_date = await self._extract_filing_date()
            filing_number = await self._extract_filing_number()
            document_type = await self._extract_document_type()

            # Find download URL
            download_url = await self._extract_download_url()

            # Get file size if available
            file_size = await self._extract_file_size()

            metadata = DocumentMetadata(
                franchise_name=franchise_name,
                filing_date=filing_date,
                document_type=document_type or "FDD",
                filing_number=filing_number,
                source_url=document_url,
                download_url=download_url,
                file_size=file_size,
                additional_metadata={
                    "source": "MN",
                    "extraction_method": "detail_page",
                },
            )

            self.logger.debug(
                "minnesota_metadata_extracted",
                franchise_name=franchise_name,
                filing_date=filing_date,
                filing_number=filing_number,
            )

            return metadata

        except Exception as e:
            self.logger.error(
                "minnesota_metadata_extraction_failed", url=document_url, error=str(e)
            )
            raise WebScrapingException(
                f"Failed to extract metadata from {document_url}: {e}"
            )

    async def _extract_franchise_name(self) -> str:
        """Extract franchise name from current page."""
        selectors = [
            "h1",
            "h2",
            ".franchise-name",
            ".company-name",
            ".title",
            "[data-franchise-name]",
            ".name",
        ]

        for selector in selectors:
            element = await self.page.query_selector(selector)
            if element:
                text = await element.inner_text()
                text = text.strip()
                if text and len(text) > 2:
                    return text

        # Fallback: extract from page title or URL
        title = await self.page.title()
        if title:
            # Clean up title
            title = re.sub(r"\s*-\s*Minnesota.*", "", title, flags=re.IGNORECASE)
            title = re.sub(r"\s*\|\s*.*", "", title)
            if title.strip():
                return title.strip()

        return "Unknown Franchise"

    async def _extract_filing_date(self) -> Optional[str]:
        """Extract filing date from current page."""
        # Look for date patterns in various elements
        selectors = [
            ".filing-date",
            ".date",
            ".effective-date",
            "[data-filing-date]",
            ".registration-date",
        ]

        for selector in selectors:
            element = await self.page.query_selector(selector)
            if element:
                text = await element.inner_text()
                date_match = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", text)
                if date_match:
                    return date_match.group(0)

        # Search in page text for date patterns
        page_text = await self.page.inner_text("body")
        date_patterns = [
            r"Filed:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Filing Date:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Effective:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Date:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    async def _extract_filing_number(self) -> Optional[str]:
        """Extract filing number from current page."""
        selectors = [
            ".filing-number",
            ".registration-number",
            ".number",
            "[data-filing-number]",
            ".file-number",
        ]

        for selector in selectors:
            element = await self.page.query_selector(selector)
            if element:
                text = await element.inner_text()
                number_match = re.search(r"#?\s*(\d{4,})", text)
                if number_match:
                    return number_match.group(1)

        # Search in page text
        page_text = await self.page.inner_text("body")
        number_patterns = [
            r"Filing Number:\s*#?\s*(\d{4,})",
            r"Registration Number:\s*#?\s*(\d{4,})",
            r"File Number:\s*#?\s*(\d{4,})",
            r"Number:\s*#?\s*(\d{4,})",
        ]

        for pattern in number_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    async def _extract_document_type(self) -> Optional[str]:
        """Extract document type from current page."""
        page_text = await self.page.inner_text("body")

        # Look for document type indicators
        if re.search(r"amendment", page_text, re.IGNORECASE):
            return "Amendment"
        elif re.search(r"renewal", page_text, re.IGNORECASE):
            return "Renewal"
        elif re.search(r"initial", page_text, re.IGNORECASE):
            return "Initial"

        return "FDD"  # Default

    async def _extract_download_url(self) -> str:
        """Extract download URL from current page."""
        # Look for download links
        selectors = [
            "a[href*='.pdf']",
            "a:has-text('Download')",
            "a:has-text('PDF')",
            "a:has-text('View Document')",
            ".download-link a",
            ".document-link a",
        ]

        for selector in selectors:
            element = await self.page.query_selector(selector)
            if element:
                href = await element.get_attribute("href")
                if href:
                    # Convert relative URLs to absolute
                    if href.startswith("/"):
                        return urljoin(self.BASE_URL, href)
                    elif not href.startswith("http"):
                        return urljoin(self.page.url, href)
                    return href

        # If no specific download link, use current page URL
        return self.page.url

    async def _extract_file_size(self) -> Optional[int]:
        """Extract file size from current page."""
        page_text = await self.page.inner_text("body")

        # Look for file size patterns
        size_patterns = [
            r"(\d+(?:\.\d+)?)\s*MB",
            r"(\d+(?:\.\d+)?)\s*KB",
            r"(\d+)\s*bytes?",
        ]

        for pattern in size_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                size_str = match.group(1)
                size_val = float(size_str)

                if "MB" in match.group(0).upper():
                    return int(size_val * 1024 * 1024)
                elif "KB" in match.group(0).upper():
                    return int(size_val * 1024)
                else:
                    return int(size_val)

        return None

    # download_and_save_document method moved to tasks.document_metadata
    # Use: from tasks.document_metadata import download_and_save_document

    # process_all_with_downloads method moved to tasks.document_metadata
    # Use: from tasks.document_metadata import process_all_documents_with_downloads

    # export_to_csv method moved to tasks.document_metadata
    # Use: from tasks.document_metadata import export_documents_to_csv
    
if __name__ == "__main__":
    import sys
    from datetime import datetime
    
    # Set up detailed logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('minnesota_scraper_debug.log')
        ]
    )
    
    async def test_minnesota_scraper():
        """Test the Minnesota scraper functionality."""
        print("\n" + "="*60)
        print("MINNESOTA SCRAPER DEBUG TEST")
        print("="*60 + "\n")
        
        # Test 1: Basic initialization
        print("Test 1: Scraper initialization")
        print("-" * 40)
        try:
            scraper = MinnesotaScraper(headless=False, timeout=15000)
            print(f"✓ Scraper created: {scraper.source_name}")
            print(f"  - Base URL: {scraper.BASE_URL}")
            print(f"  - Search URL: {scraper.SEARCH_URL[:50]}...")
            print(f"  - Timeout: {scraper.timeout}ms")
        except Exception as e:
            print(f"✗ Initialization failed: {e}")
        print()
        
        # Test 2: Browser initialization and navigation
        print("Test 2: Browser initialization and navigation")
        print("-" * 40)
        try:
            async with create_scraper(MinnesotaScraper, headless=True) as scraper:
                print("✓ Browser initialized")
                
                # Test navigation to CARDS portal
                await scraper.safe_navigate(scraper.SEARCH_URL)
                print("✓ Navigated to CARDS search page")
                
                # Get page title
                if scraper.page:
                    title = await scraper.page.title()
                    print(f"  - Page title: {title}")
                    
                    # Check for results table
                    results_table = await scraper.page.query_selector("#results")
                    if results_table:
                        print("  - Results table found")
                    else:
                        print("  - Results table not found")
        except Exception as e:
            print(f"✗ Browser test failed: {e}")
        print()
        
        # Test 3: Document discovery (limited)
        print("Test 3: Document discovery (limited to 5 documents)")
        print("-" * 40)
        try:
            async with create_scraper(MinnesotaScraper) as scraper:
                # Navigate to search page
                await scraper.safe_navigate(scraper.SEARCH_URL)
                await scraper.page.wait_for_selector("#results", timeout=10000)
                
                # Extract only first page results
                documents = await scraper._extract_cards_results()
                
                # Limit to first 5 for testing
                documents = documents[:5]
                
                print(f"✓ Discovered {len(documents)} documents:")
                for i, doc in enumerate(documents):
                    print(f"\n  {i+1}. {doc.franchise_name}")
                    print(f"     - Type: {doc.document_type}")
                    print(f"     - Filing #: {doc.filing_number or 'N/A'}")
                    print(f"     - Download URL: {doc.download_url[:60]}...")
                    if doc.additional_metadata:
                        print(f"     - Franchisor: {doc.additional_metadata.get('franchisor', 'N/A')}")
                        print(f"     - Year: {doc.additional_metadata.get('year', 'N/A')}")
        except Exception as e:
            print(f"✗ Document discovery failed: {e}")
        print()
        
        # Test 4: Metadata extraction methods
        print("Test 4: Metadata extraction helper methods")
        print("-" * 40)
        try:
            async with create_scraper(MinnesotaScraper) as scraper:
                # Create a test page with sample content
                test_html = """
                <html>
                <head><title>Test Franchise - Minnesota CARDS</title></head>
                <body>
                    <h1>Test Franchise Corporation</h1>
                    <div class="filing-date">Filed: 03/15/2024</div>
                    <div class="filing-number">Filing Number: #2024001234</div>
                    <a href="/download/test.pdf">Download FDD</a>
                    <span>File size: 2.5 MB</span>
                </body>
                </html>
                """
                
                # Navigate to a test page
                await scraper.page.goto("data:text/html," + test_html)
                
                # Test extraction methods
                franchise_name = await scraper._extract_franchise_name()
                print(f"✓ Franchise name: {franchise_name}")
                
                filing_date = await scraper._extract_filing_date()
                print(f"✓ Filing date: {filing_date}")
                
                filing_number = await scraper._extract_filing_number()
                print(f"✓ Filing number: {filing_number}")
                
                download_url = await scraper._extract_download_url()
                print(f"✓ Download URL: {download_url}")
                
                file_size = await scraper._extract_file_size()
                print(f"✓ File size: {file_size} bytes")
        except Exception as e:
            print(f"✗ Metadata extraction test failed: {e}")
        print()
        
        # Test 5: Error handling
        print("Test 5: Error handling")
        print("-" * 40)
        try:
            async with create_scraper(MinnesotaScraper) as scraper:
                # Test invalid navigation
                try:
                    await scraper.safe_navigate("https://invalid.url.test")
                except Exception as e:
                    print(f"✓ Navigation error caught: {type(e).__name__}")
                
                # Test element not found
                try:
                    await scraper.safe_click("#non-existent-element")
                except ElementNotFoundError as e:
                    print(f"✓ Element error caught: {type(e).__name__}")
        except Exception as e:
            print(f"✗ Error handling test failed: {e}")
        print()
        
        # Test 6: Pagination detection
        print("Test 6: Pagination detection")
        print("-" * 40)
        try:
            async with create_scraper(MinnesotaScraper) as scraper:
                await scraper.safe_navigate(scraper.SEARCH_URL)
                await scraper.page.wait_for_selector("#results", timeout=10000)
                
                # Check for load more button
                load_more_selectors = [
                    'button:has-text("Load more")',
                    "#main-content > form ul button",
                    'button:has-text("Load More")',
                    'button:has-text("LOAD MORE")',
                ]
                
                found_button = False
                for selector in load_more_selectors:
                    button = await scraper.page.query_selector(selector)
                    if button and await button.is_visible():
                        found_button = True
                        print(f"✓ Load more button found with selector: {selector}")
                        
                        # Check if enabled
                        is_disabled = await button.get_attribute("disabled")
                        print(f"  - Button enabled: {'No' if is_disabled else 'Yes'}")
                        break
                
                if not found_button:
                    print("✗ No load more button found")
        except Exception as e:
            print(f"✗ Pagination test failed: {e}")
        print()
        
        # Test 7: Cookie management
        print("Test 7: Cookie management")
        print("-" * 40)
        try:
            async with create_scraper(MinnesotaScraper) as scraper:
                await scraper.safe_navigate(scraper.BASE_URL)
                
                # Get cookies
                cookies = await scraper.manage_cookies()
                print(f"✓ Found {len(cookies)} cookies:")
                for name, value in list(cookies.items())[:3]:  # Show first 3
                    print(f"  - {name}: {value[:30]}...")
        except Exception as e:
            print(f"✗ Cookie test failed: {e}")
        
        # Summary
        print("\n" + "="*60)
        print("MINNESOTA SCRAPER TEST SUMMARY")
        print("="*60)
        print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("Check minnesota_scraper_debug.log for detailed logs")
        print("\nNOTE: This test uses the actual Minnesota CARDS portal.")
        print("Some tests may fail if the portal structure has changed.")
        print("="*60 + "\n")
    
    # Run the async test
    asyncio.run(test_minnesota_scraper())
