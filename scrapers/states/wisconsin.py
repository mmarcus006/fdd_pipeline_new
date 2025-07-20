"""Wisconsin franchise portal scraper implementation."""

import asyncio
import re
from typing import Any, Dict, List, Optional
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


class WisconsinScraper(BaseScraper):
    """Wisconsin Department of Financial Institutions franchise portal scraper.

    Handles the Wisconsin portal's multi-step workflow:
    1. Navigate to active filings table
    2. Extract franchise names from table
    3. Search for each franchise individually
    4. Navigate to detail pages for enhanced metadata
    5. Download documents with filing information
    """

    # Wisconsin portal URLs
    BASE_URL = "https://apps.dfi.wi.gov"
    ACTIVE_FILINGS_URL = f"{BASE_URL}/apps/FranchiseEFiling/activeFilings.aspx"
    SEARCH_URL = f"{BASE_URL}/apps/FranchiseSearch/MainSearch.aspx"

    def __init__(self, **kwargs):
        """Initialize Wisconsin scraper."""
        super().__init__(source_name="WI", **kwargs)
        self.discovered_franchises: List[str] = []
        
        # Log initialization
        self.logger.debug(
            "wisconsin_scraper_initialized",
            base_url=self.BASE_URL,
            active_filings_url=self.ACTIVE_FILINGS_URL,
            search_url=self.SEARCH_URL,
            kwargs=kwargs
        )

    @log_method_call
    async def discover_documents(self) -> List[DocumentMetadata]:
        """Discover available documents from Wisconsin portal.

        Returns:
            List of document metadata for all discovered franchises

        Raises:
            ScrapingError: If discovery fails
        """
        try:
            self.logger.info("starting_wisconsin_document_discovery")

            # Step 1: Get franchise names from active filings table
            self.logger.debug("starting_active_filings_extraction")
            franchise_names = await self._extract_franchise_names_from_table()
            self.discovered_franchises = franchise_names

            self.logger.info(
                "franchise_names_discovered",
                count=len(franchise_names),
                names=franchise_names[:5],  # Log first 5 for debugging
            )
            
            if not franchise_names:
                self.logger.warning("no_franchise_names_found_in_active_filings")

            # Step 2: Process each franchise to get basic document metadata
            documents = []
            for i, franchise_name in enumerate(franchise_names):
                try:
                    self.logger.debug(
                        "processing_franchise_for_discovery",
                        franchise=franchise_name,
                        index=i + 1,
                        total=len(franchise_names),
                        progress_percentage=f"{((i + 1) / len(franchise_names) * 100):.1f}%"
                    )

                    # Search for the franchise and get basic metadata
                    doc_metadata = await self._search_franchise_basic(franchise_name)
                    if doc_metadata:
                        documents.append(doc_metadata)
                        self.logger.debug(
                            "franchise_document_found",
                            franchise=franchise_name,
                            filing_number=doc_metadata.filing_number
                        )
                    else:
                        self.logger.debug(
                            "no_document_found_for_franchise",
                            franchise=franchise_name
                        )

                    # Add delay between requests to be respectful
                    await asyncio.sleep(1.0)

                except Exception as e:
                    self.logger.error(
                        "franchise_discovery_failed",
                        franchise=franchise_name,
                        error=str(e),
                    )
                    continue

            self.logger.info(
                "wisconsin_document_discovery_completed",
                total_franchises=len(franchise_names),
                documents_found=len(documents),
            )

            return documents

        except Exception as e:
            self.logger.error("wisconsin_discovery_failed", error=str(e))
            raise WebScrapingException(f"Wisconsin document discovery failed: {e}")

    @log_method_call
    async def extract_document_metadata(self, document_url: str) -> DocumentMetadata:
        """Extract detailed metadata for a specific document.

        Args:
            document_url: URL of the document detail page (search URL with franchise name)

        Returns:
            Enhanced document metadata with detailed filing information

        Raises:
            ExtractionError: If metadata extraction fails
        """
        try:
            # Extract franchise name from the document_url (which is actually the search URL)
            # The franchise name should be in the additional_metadata
            franchise_name = None
            if hasattr(self, "_current_franchise_name"):
                franchise_name = self._current_franchise_name
            else:
                # Fallback: try to extract from URL or use a default approach
                self.logger.warning("franchise_name_not_found_in_context")
                return None

            self.logger.debug("extracting_detailed_metadata", franchise=franchise_name)

            # Navigate to search page and perform detailed search
            await self.safe_navigate(self.SEARCH_URL)

            # Search for the franchise
            await self._perform_franchise_search(franchise_name)

            # Find and click the details link for registered franchise
            details_url = await self._find_registered_details_link()
            if not details_url:
                self.logger.warning(
                    "no_registered_details_found", franchise=franchise_name
                )
                return None

            # Navigate to details page
            await self.safe_navigate(details_url)

            # Extract comprehensive metadata from details page
            detailed_metadata = await self._extract_detailed_filing_info()

            # Create enhanced DocumentMetadata
            enhanced_doc = DocumentMetadata(
                franchise_name=franchise_name,
                filing_date=detailed_metadata.get("effective_date"),
                document_type=detailed_metadata.get("filing_type", "FDD"),
                filing_number=detailed_metadata.get("filing_number"),
                source_url=details_url,
                download_url=detailed_metadata.get("download_url", details_url),
                additional_metadata={
                    "franchisor_info": detailed_metadata.get("franchisor_info", {}),
                    "filing_info": detailed_metadata.get("filing_info", {}),
                    "states_filed": detailed_metadata.get("states_filed", []),
                    "legal_name": detailed_metadata.get("legal_name"),
                    "trade_name": detailed_metadata.get("trade_name"),
                    "business_address": detailed_metadata.get("business_address"),
                    "filing_status": detailed_metadata.get("filing_status"),
                },
            )

            self.logger.info(
                "detailed_metadata_extracted",
                franchise=franchise_name,
                filing_number=enhanced_doc.filing_number,
                filing_date=enhanced_doc.filing_date,
            )

            return enhanced_doc

        except Exception as e:
            self.logger.error(
                "detailed_metadata_extraction_failed",
                franchise=franchise_name if "franchise_name" in locals() else "unknown",
                error=str(e),
            )
            raise WebScrapingException(f"Failed to extract detailed metadata: {e}")

    @log_method_call
    async def _extract_franchise_names_from_table(self) -> List[str]:
        """Extract franchise names from the active filings table.

        Returns:
            List of franchise names from the first column of the table

        Raises:
            ElementNotFoundError: If table extraction fails
        """
        try:
            self.logger.debug("navigating_to_active_filings_table")
            await self.safe_navigate(self.ACTIVE_FILINGS_URL)

            # Use the new generic table extraction method
            table_selector = "#ctl00_contentPlaceholder_grdActiveFilings"
            self.logger.debug("extracting_table_data", selector=table_selector)
            table_data = await self.extract_table_data(table_selector)
            self.logger.debug(
                "table_data_extracted",
                row_count=len(table_data) if table_data else 0,
                data_type=type(table_data).__name__
            )

            # Extract franchise names from the first column
            franchise_names = []
            if isinstance(table_data, list) and table_data:
                self.logger.debug("processing_table_rows", total_rows=len(table_data))
                for idx, row in enumerate(table_data):
                    # Ensure row is a dictionary (expected format)
                    if isinstance(row, dict) and row:
                        first_value = list(row.values())[0] if row else ""
                        name = clean_text(first_value)
                        if name:
                            franchise_names.append(name)
                            self.logger.debug(
                                "franchise_name_extracted",
                                row_index=idx,
                                name=name[:50]
                            )
                    elif isinstance(row, str):
                        # Handle case where row is a string (fallback)
                        name = clean_text(row)
                        if name:
                            franchise_names.append(name)
                            self.logger.debug(
                                "franchise_name_extracted_string",
                                row_index=idx,
                                name=name[:50]
                            )

            # If table extraction failed, fall back to direct HTML parsing
            if not franchise_names:
                self.logger.debug("falling_back_to_html_parsing")

                # Wait for the table to load
                await self.page.wait_for_selector(table_selector, timeout=self.timeout)

                # Extract table HTML
                table_html = await self.page.evaluate(
                    f"document.querySelector('{table_selector}').outerHTML"
                )

                if not table_html:
                    raise ElementNotFoundError("Failed to retrieve table HTML")

                # Use regex to find table rows and extract first cell content
                rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)

                for i, row in enumerate(rows):
                    if i == 0:  # Skip header row
                        continue

                    # Extract cells from row
                    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
                    if cells:
                        # Clean up the franchise name (first cell)
                        name = clean_text(cells[0])
                        if name:
                            franchise_names.append(name)

            self.logger.info(
                "franchise_names_extracted_from_table", count=len(franchise_names)
            )

            return franchise_names

        except Exception as e:
            self.logger.error("table_extraction_failed", error=str(e))
            raise ElementNotFoundError(
                f"Failed to extract franchise names from table: {e}"
            )

    # download_and_save_document method moved to tasks.document_metadata
    # Use: from tasks.document_metadata import download_and_save_document

    @log_method_call
    async def _search_franchise_basic(
        self, franchise_name: str
    ) -> Optional[DocumentMetadata]:
        """Perform basic franchise search to get initial document metadata.

        Args:
            franchise_name: Name of franchise to search for

        Returns:
            Basic DocumentMetadata or None if not found

        Raises:
            ExtractionError: If search fails
        """
        try:
            self.logger.debug(
                "performing_basic_franchise_search", franchise=franchise_name
            )

            # Navigate to search page
            await self.safe_navigate(self.SEARCH_URL)

            # Perform search
            await self._perform_franchise_search(franchise_name)

            # Check if we have results with "Registered" status
            has_registered = await self._check_for_registered_status()

            if not has_registered:
                self.logger.debug(
                    "no_registered_franchise_found", franchise=franchise_name
                )
                return None

            # Create basic document metadata
            # Store franchise name for later detailed extraction
            self._current_franchise_name = franchise_name

            doc_metadata = DocumentMetadata(
                franchise_name=franchise_name,
                filing_date=None,  # Will be filled in detailed extraction
                document_type="FDD",
                filing_number=None,  # Will be filled in detailed extraction
                source_url=self.SEARCH_URL,  # Use search URL as source
                download_url=self.SEARCH_URL,  # Will be updated in detailed extraction
                additional_metadata={
                    "discovery_method": "active_filings_table",
                    "has_registered_status": True,
                },
            )

            return doc_metadata

        except Exception as e:
            self.logger.error(
                "basic_franchise_search_failed", franchise=franchise_name, error=str(e)
            )
            raise ElementNotFoundError(
                f"Basic franchise search failed for {franchise_name}: {e}"
            )

    @log_method_call
    async def _perform_franchise_search(self, franchise_name: str) -> None:
        """Perform franchise search on the search page.

        Args:
            franchise_name: Name of franchise to search for

        Raises:
            ElementNotFoundError: If search operation fails
        """
        try:
            # Clear any existing search first
            search_input_selector = "#ctl00_contentPlaceholder_txtSearch"
            self.logger.debug("clearing_search_input", selector=search_input_selector)
            await self.clear_search_input(search_input_selector)

            # Find and fill search input
            search_selectors = [
                "#ctl00_contentPlaceholder_txtSearch",
                'input[type="text"]',
                'input[name*="Search"]',
            ]

            search_input = None
            for selector in search_selectors:
                try:
                    search_input = await self.page.wait_for_selector(
                        selector, timeout=5000
                    )
                    if search_input:
                        break
                except:
                    continue

            if not search_input:
                raise ElementNotFoundError("Search input field not found")

            await search_input.fill(franchise_name)
            self.logger.debug("search_input_filled", franchise=franchise_name)

            # Find and click search button
            search_button_selectors = [
                "#ctl00_contentPlaceholder_btnSearch",
                'input[type="submit"]',
                'button[type="submit"]',
                'input[value*="Search"]',
            ]

            search_button = None
            for selector in search_button_selectors:
                try:
                    search_button = await self.page.wait_for_selector(
                        selector, timeout=5000
                    )
                    if search_button:
                        break
                except:
                    continue

            if not search_button:
                raise ElementNotFoundError("Search button not found")

            await search_button.click()
            self.logger.debug("search_button_clicked")

            # Wait for results to load
            await self.page.wait_for_load_state("networkidle")
            self.logger.debug("search_results_loaded")

            self.logger.debug("franchise_search_completed", franchise=franchise_name)

        except Exception as e:
            self.logger.error(
                "franchise_search_operation_failed",
                franchise=franchise_name,
                error=str(e),
            )
            raise ElementNotFoundError(f"Franchise search operation failed: {e}")

    @log_method_call
    async def _check_for_registered_status(self) -> bool:
        """Check if search results contain a franchise with 'Registered' status.

        Returns:
            True if registered franchise found, False otherwise
        """
        try:
            # Look for text containing "Registered" in the page
            page_content = await self.page.content()
            has_registered = "Registered" in page_content
            self.logger.debug(
                "registered_status_check_result",
                has_registered=has_registered,
                content_length=len(page_content)
            )
            return has_registered

        except Exception as e:
            self.logger.error("registered_status_check_failed", error=str(e))
            return False

    @log_method_call
    async def _find_registered_details_link(self) -> Optional[str]:
        """Find the details link for a registered franchise.

        Returns:
            URL of the details page or None if not found
        """
        try:
            # Look for details links
            details_links = await self.page.query_selector_all('a[href*="details"]')

            for link in details_links:
                # Check if this details link is in a row with "Registered" status
                try:
                    row_text = await self.page.evaluate(
                        '(element) => element.closest("tr").textContent', link
                    )

                    if row_text and "Registered" in row_text:
                        # Get the href attribute
                        href = await link.get_attribute("href")
                        if href:
                            # Convert relative URL to absolute
                            details_url = urljoin(self.BASE_URL, href)
                            self.logger.debug(
                                "registered_details_link_found",
                                href=href,
                                full_url=details_url
                            )
                            return details_url
                except:
                    continue

            return None

        except Exception as e:
            self.logger.error("details_link_search_failed", error=str(e))
            return None

    @log_method_call
    async def _extract_detailed_filing_info(self) -> Dict[str, Any]:
        """Extract detailed filing information from the details page.

        Returns:
            Dictionary containing detailed filing information
        """
        try:
            # Get page content for parsing
            page_content = await self.page.content()
            self.logger.debug(
                "extracting_detailed_filing_info_from_page",
                url=self.page.url,
                content_length=len(page_content)
            )

            # Initialize data containers
            franchisor_info = {}
            filing_info = {}
            states_info = []

            # Extract Franchisor Name and Address section
            franchisor_match = re.search(
                r'group "Franchisor Name and Address".*?:\n(.*?)(?=group "Filings for this Registration")',
                page_content,
                re.DOTALL,
            )

            if franchisor_match:
                section_content = franchisor_match.group(1)

                # Extract filing number
                filing_number_match = re.search(
                    r'Filing Number.*?generic.*?: "(\d+)"', section_content
                )
                if filing_number_match:
                    franchisor_info["filing_number"] = filing_number_match.group(1)

                # Extract filing status
                status_match = re.search(
                    r"Filing Status.*?generic.*?: (\w+)", section_content
                )
                if status_match:
                    franchisor_info["filing_status"] = status_match.group(1)

                # Extract legal name
                legal_name_match = re.search(
                    r"Franchise Legal Name.*?generic.*?: (.*?)\n", section_content
                )
                if legal_name_match:
                    franchisor_info["legal_name"] = legal_name_match.group(1).strip()

                # Extract trade name
                trade_name_match = re.search(
                    r"Franchise Trade Name \(DBA\).*?generic.*?: (.*?)\n",
                    section_content,
                )
                if trade_name_match:
                    franchisor_info["trade_name"] = trade_name_match.group(1).strip()

                # Extract business address (multi-line)
                # First try to get the main address line
                address_match = re.search(
                    r"Franchise Business Address.*?generic.*?: (.*?)\n", section_content
                )
                full_address = []
                if address_match:
                    full_address.append(address_match.group(1).strip())

                # Then look for additional address lines in cell structures
                additional_lines = re.findall(
                    r"^\s+- cell.*?\n\s+- cell.*?\n\s+- generic.*?: (.*?)\n",
                    section_content,
                    re.MULTILINE,
                )

                for line in additional_lines:
                    if line and line.strip():
                        full_address.append(line.strip())

                if full_address:
                    franchisor_info["business_address"] = ", ".join(full_address)

            # Extract Filings for this Registration section
            filings_match = re.search(
                r'group "Filings for this Registration".*?:\n(.*?)(?=group "States Application Filed")',
                page_content,
                re.DOTALL,
            )

            if filings_match:
                section_content = filings_match.group(1)

                # Extract filing details from table cells
                legal_name_match = re.search(
                    r'Legal Name.*?cell "(.*?)"', section_content
                )
                if legal_name_match:
                    filing_info["legal_name"] = legal_name_match.group(1).strip()

                trade_name_match = re.search(
                    r'Trade Name.*?cell "(.*?)"', section_content
                )
                if trade_name_match:
                    filing_info["trade_name"] = trade_name_match.group(1).strip()

                type_match = re.search(r'Type.*?cell "(.*?)"', section_content)
                if type_match:
                    filing_info["type"] = type_match.group(1).strip()

                status_match = re.search(r'Status.*?cell "(.*?)"', section_content)
                if status_match:
                    filing_info["status"] = status_match.group(1).strip()

                effective_match = re.search(
                    r'Effective.*?cell "(.*?)"', section_content
                )
                if effective_match:
                    filing_info["effective"] = effective_match.group(1).strip()

            # Extract States Application Filed section
            states_match = re.search(
                r'group "States Application Filed".*?:\n(.*?)(?=group "Contact Person")',
                page_content,
                re.DOTALL,
            )

            if states_match:
                section_content = states_match.group(1)
                states_list_match = re.search(
                    r"States Filed.*?generic.*?:\n(.*)", section_content, re.DOTALL
                )
                if states_list_match:
                    states_text = states_list_match.group(1)
                    states_info = [
                        s.strip() for s in re.findall(r"text: (.*?)\n", states_text)
                    ]

            # Look for download button and get download URL
            download_url = None
            try:
                download_button = await self.page.query_selector(
                    'button:has-text("Download"), input[value*="Download"]'
                )
                if download_button:
                    # If download button exists, the current page URL can be used for download
                    download_url = self.page.url
            except:
                pass

            # Combine all extracted information
            detailed_info = {
                "filing_number": franchisor_info.get("filing_number"),
                "filing_status": franchisor_info.get("filing_status"),
                "legal_name": franchisor_info.get("legal_name"),
                "trade_name": franchisor_info.get("trade_name"),
                "business_address": franchisor_info.get("business_address"),
                "filing_type": filing_info.get("type"),
                "effective_date": filing_info.get("effective"),
                "states_filed": states_info,
                "download_url": download_url,
                "franchisor_info": franchisor_info,
                "filing_info": filing_info,
            }
            
            # Log key extracted fields
            self.logger.debug(
                "detailed_info_summary",
                filing_number=detailed_info.get("filing_number"),
                legal_name=detailed_info.get("legal_name"),
                status=detailed_info.get("filing_status"),
                states_count=len(states_info),
                has_download_url=bool(download_url)
            )

            self.logger.debug(
                "detailed_filing_info_extracted",
                filing_number=detailed_info.get("filing_number"),
                legal_name=detailed_info.get("legal_name"),
            )

            return detailed_info

        except Exception as e:
            self.logger.error("detailed_info_extraction_failed", error=str(e))
            return {}

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
            logging.FileHandler('wisconsin_scraper_debug.log')
        ]
    )
    
    async def test_wisconsin_scraper():
        """Test the Wisconsin scraper functionality."""
        print("\n" + "="*60)
        print("WISCONSIN SCRAPER DEBUG TEST")
        print("="*60 + "\n")
        
        # Test 1: Basic initialization
        print("Test 1: Scraper initialization")
        print("-" * 40)
        try:
            scraper = WisconsinScraper(headless=True, timeout=15000)
            print(f"✓ Scraper created: {scraper.source_name}")
            print(f"  - Base URL: {scraper.BASE_URL}")
            print(f"  - Active Filings URL: {scraper.ACTIVE_FILINGS_URL}")
            print(f"  - Search URL: {scraper.SEARCH_URL}")
            print(f"  - Timeout: {scraper.timeout}ms")
        except Exception as e:
            print(f"✗ Initialization failed: {e}")
        print()
        
        # Test 2: Browser initialization and navigation
        print("Test 2: Browser initialization and navigation")
        print("-" * 40)
        try:
            async with create_scraper(WisconsinScraper, headless=True) as scraper:
                print("✓ Browser initialized")
                
                # Test navigation to Wisconsin DFI portal
                await scraper.safe_navigate(scraper.ACTIVE_FILINGS_URL)
                print("✓ Navigated to Active Filings page")
                
                # Get page title
                if scraper.page:
                    title = await scraper.page.title()
                    print(f"  - Page title: {title}")
                    
                    # Check for active filings table
                    table = await scraper.page.query_selector("#ctl00_contentPlaceholder_grdActiveFilings")
                    if table:
                        print("  - Active filings table found")
                    else:
                        print("  - Active filings table not found")
        except Exception as e:
            print(f"✗ Browser test failed: {e}")
        print()
        
        # Test 3: Document discovery (limited)
        print("Test 3: Document discovery (limited to 5 franchises)")
        print("-" * 40)
        try:
            async with create_scraper(WisconsinScraper) as scraper:
                # Extract franchise names from active filings table
                franchise_names = await scraper._extract_franchise_names_from_table()
                
                # Limit to first 5 for testing
                test_franchises = franchise_names[:5]
                
                print(f"✓ Found {len(franchise_names)} total franchises")
                print(f"  Testing with first {len(test_franchises)} franchises:")
                
                documents = []
                for i, franchise_name in enumerate(test_franchises):
                    print(f"\n  {i+1}. Testing franchise: {franchise_name}")
                    
                    try:
                        doc = await scraper._search_franchise_basic(franchise_name)
                        if doc:
                            documents.append(doc)
                            print(f"     ✓ Document found")
                            print(f"     - Has registered status: {doc.additional_metadata.get('has_registered_status')}")
                        else:
                            print(f"     ✗ No document found")
                    except Exception as e:
                        print(f"     ✗ Error: {e}")
                    
                    # Small delay between searches
                    await asyncio.sleep(0.5)
                
                print(f"\n✓ Total documents discovered: {len(documents)}")
        except Exception as e:
            print(f"✗ Document discovery failed: {e}")
        print()
        
        # Test 4: Metadata extraction from detail page
        print("Test 4: Detailed metadata extraction")
        print("-" * 40)
        try:
            async with create_scraper(WisconsinScraper) as scraper:
                # Get franchise names
                franchise_names = await scraper._extract_franchise_names_from_table()
                
                if franchise_names:
                    test_franchise = franchise_names[0]
                    print(f"Testing detailed extraction for: {test_franchise}")
                    
                    # Store franchise name for extraction
                    scraper._current_franchise_name = test_franchise
                    
                    # Navigate to search and perform search
                    await scraper.safe_navigate(scraper.SEARCH_URL)
                    await scraper._perform_franchise_search(test_franchise)
                    
                    # Find details link
                    details_url = await scraper._find_registered_details_link()
                    if details_url:
                        print(f"✓ Details URL found: {details_url[:60]}...")
                        
                        # Navigate and extract
                        await scraper.safe_navigate(details_url)
                        detailed_info = await scraper._extract_detailed_filing_info()
                        
                        print("✓ Detailed information extracted:")
                        print(f"  - Filing Number: {detailed_info.get('filing_number', 'N/A')}")
                        print(f"  - Legal Name: {detailed_info.get('legal_name', 'N/A')}")
                        print(f"  - Trade Name: {detailed_info.get('trade_name', 'N/A')}")
                        print(f"  - Status: {detailed_info.get('filing_status', 'N/A')}")
                        print(f"  - Effective Date: {detailed_info.get('effective_date', 'N/A')}")
                        print(f"  - States Filed: {len(detailed_info.get('states_filed', []))}")
                    else:
                        print("✗ No details link found")
                else:
                    print("✗ No franchises found for testing")
        except Exception as e:
            print(f"✗ Metadata extraction test failed: {e}")
        print()
        
        # Test 5: Error handling
        print("Test 5: Error handling")
        print("-" * 40)
        try:
            async with create_scraper(WisconsinScraper) as scraper:
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
                
                # Test search with empty franchise name
                try:
                    await scraper._search_franchise_basic("")
                except Exception as e:
                    print(f"✓ Empty search error caught: {type(e).__name__}")
        except Exception as e:
            print(f"✗ Error handling test failed: {e}")
        print()
        
        # Test 6: Cookie management
        print("Test 6: Cookie management")
        print("-" * 40)
        try:
            async with create_scraper(WisconsinScraper) as scraper:
                await scraper.safe_navigate(scraper.BASE_URL)
                
                # Get cookies
                cookies = await scraper.manage_cookies()
                print(f"✓ Found {len(cookies)} cookies:")
                for name, value in list(cookies.items())[:3]:  # Show first 3
                    print(f"  - {name}: {value[:30]}...")
        except Exception as e:
            print(f"✗ Cookie test failed: {e}")
        print()
        
        # Test 7: Table extraction capabilities
        print("Test 7: Table extraction capabilities")
        print("-" * 40)
        try:
            async with create_scraper(WisconsinScraper) as scraper:
                await scraper.safe_navigate(scraper.ACTIVE_FILINGS_URL)
                
                # Test table extraction
                table_selector = "#ctl00_contentPlaceholder_grdActiveFilings"
                table_data = await scraper.extract_table_data(table_selector)
                
                if table_data:
                    print(f"✓ Table data extracted: {len(table_data)} rows")
                    if table_data and len(table_data) > 0:
                        print("  Sample row structure:")
                        first_row = table_data[0]
                        if isinstance(first_row, dict):
                            for key in list(first_row.keys())[:3]:
                                print(f"    - {key}: {first_row[key][:30] if first_row[key] else 'None'}...")
                else:
                    print("✗ No table data extracted")
        except Exception as e:
            print(f"✗ Table extraction test failed: {e}")
        
        # Summary
        print("\n" + "="*60)
        print("WISCONSIN SCRAPER TEST SUMMARY")
        print("="*60)
        print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("Check wisconsin_scraper_debug.log for detailed logs")
        print("\nNOTE: This test uses the actual Wisconsin DFI portal.")
        print("Some tests may fail if the portal structure has changed.")
        print("="*60 + "\n")
    
    # Run the async test
    asyncio.run(test_wisconsin_scraper())
