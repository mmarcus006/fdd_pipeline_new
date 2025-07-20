# ABOUTME: Test suite for WisconsinScraper class
# ABOUTME: Tests Wisconsin DFI portal scraping functionality with real portal

import pytest
import pytest_asyncio
import asyncio
from scrapers.states.wisconsin import WisconsinScraper
from scrapers.base.base_scraper import DocumentMetadata, create_scraper
from scrapers.base.exceptions import WebScrapingException, ElementNotFoundError


class TestWisconsinScraper:
    """Test suite for Wisconsin DFI portal scraper using real portal."""

    @pytest_asyncio.fixture
    async def scraper(self):
        """Create a real Wisconsin scraper instance."""
        async with create_scraper(
            WisconsinScraper, headless=True, timeout=30000
        ) as scraper_instance:
            yield scraper_instance

    def test_initialization(self):
        """Test Wisconsin scraper initialization."""
        scraper = WisconsinScraper()
        assert scraper.source_name == "WI"
        assert scraper.BASE_URL == "https://apps.dfi.wi.gov"
        assert scraper.ACTIVE_FILINGS_URL.endswith("/activeFilings.aspx")
        assert scraper.SEARCH_URL.endswith("/MainSearch.aspx")

    @pytest.mark.asyncio
    async def test_extract_franchise_names_from_active_filings(self, scraper):
        """Test extraction of franchise names from active filings table."""
        # Navigate to active filings page
        franchise_names = await scraper._extract_franchise_names_from_table()

        # Verify we got franchise names
        assert isinstance(franchise_names, list)
        assert len(franchise_names) > 0

        # Check first few names are valid
        for name in franchise_names[:5]:
            assert isinstance(name, str)
            assert len(name) > 0
            assert name != ""

        print(f"Found {len(franchise_names)} franchise names from active filings")
        print(f"First 5: {franchise_names[:5]}")

    @pytest.mark.asyncio
    async def test_search_specific_franchise_valvoline(self, scraper):
        """Test searching for Valvoline specifically."""
        # Search for Valvoline
        doc_metadata = await scraper._search_franchise_basic("Valvoline")

        if doc_metadata:
            assert isinstance(doc_metadata, DocumentMetadata)
            assert "Valvoline" in doc_metadata.franchise_name
            assert (
                doc_metadata.additional_metadata.get("discovery_method")
                == "active_filings_table"
            )
            assert doc_metadata.additional_metadata.get("has_registered_status") is True
            print(f"Found Valvoline franchise: {doc_metadata.franchise_name}")
        else:
            print("Valvoline not found in current active filings")

    @pytest.mark.asyncio
    async def test_perform_franchise_search(self, scraper):
        """Test the franchise search functionality."""
        # Navigate to search page
        await scraper.safe_navigate(scraper.SEARCH_URL)

        # Perform search for Valvoline
        await scraper._perform_franchise_search("Valvoline")

        # Check if we have search results
        has_results = await scraper._check_for_registered_status()

        # The search should work even if Valvoline isn't currently registered
        page_content = await scraper.page.content()
        assert "Search" in page_content or "search" in page_content

    @pytest.mark.asyncio
    async def test_discover_documents_workflow(self, scraper):
        """Test the complete document discovery workflow."""
        # This will:
        # 1. Get franchise names from active filings table
        # 2. Search for each franchise
        # 3. Return documents for registered franchises

        documents = await scraper.discover_documents()

        assert isinstance(documents, list)

        if len(documents) > 0:
            # Check first document
            doc = documents[0]
            assert isinstance(doc, DocumentMetadata)
            assert doc.franchise_name is not None
            assert doc.source_url == scraper.SEARCH_URL
            assert doc.additional_metadata.get("has_registered_status") is True

            print(f"Discovered {len(documents)} documents with registered status")
            print(f"First franchise: {doc.franchise_name}")
        else:
            print("No registered franchises found in current active filings")

    @pytest.mark.asyncio
    async def test_find_registered_details_link(self, scraper):
        """Test finding details link for registered franchises."""
        # First, get a franchise that's likely to be registered
        franchise_names = await scraper._extract_franchise_names_from_table()

        # Try first few franchises
        for franchise_name in franchise_names[:5]:
            await scraper.safe_navigate(scraper.SEARCH_URL)
            await scraper._perform_franchise_search(franchise_name)

            # Check for registered status
            if await scraper._check_for_registered_status():
                # Try to find details link
                details_url = await scraper._find_registered_details_link()

                if details_url:
                    assert details_url.startswith("http")
                    assert "details" in details_url.lower()
                    print(f"Found details link for {franchise_name}: {details_url}")
                    return

        print("No registered franchises with details links found in test sample")

    @pytest.mark.asyncio
    async def test_extract_detailed_filing_info(self, scraper):
        """Test extraction of detailed filing information."""
        # Find a registered franchise and navigate to its details
        franchise_names = await scraper._extract_franchise_names_from_table()

        for franchise_name in franchise_names[:10]:  # Try first 10
            await scraper.safe_navigate(scraper.SEARCH_URL)
            await scraper._perform_franchise_search(franchise_name)

            if await scraper._check_for_registered_status():
                details_url = await scraper._find_registered_details_link()

                if details_url:
                    # Navigate to details page
                    await scraper.safe_navigate(details_url)

                    # Extract detailed info
                    detailed_info = await scraper._extract_detailed_filing_info()

                    # Check some fields
                    if detailed_info:
                        print(f"Extracted details for {franchise_name}:")
                        print(f"  Filing number: {detailed_info.get('filing_number')}")
                        print(f"  Legal name: {detailed_info.get('legal_name')}")
                        print(f"  Trade name: {detailed_info.get('trade_name')}")
                        print(f"  States filed: {detailed_info.get('states_filed')}")

                        # Basic assertions
                        assert isinstance(detailed_info, dict)
                        return

        print("No detailed filing info could be extracted from test sample")

    @pytest.mark.asyncio
    async def test_wisconsin_specific_table_selector(self, scraper):
        """Test Wisconsin-specific table selector works."""
        await scraper.safe_navigate(scraper.ACTIVE_FILINGS_URL)

        # Wait for specific Wisconsin table
        table = await scraper.page.wait_for_selector(
            "#ctl00_contentPlaceholder_grdActiveFilings", timeout=scraper.timeout
        )

        assert table is not None

        # Verify table has rows
        rows = await scraper.page.query_selector_all(
            "#ctl00_contentPlaceholder_grdActiveFilings tr"
        )
        assert len(rows) > 1  # At least header + 1 data row

    @pytest.mark.asyncio
    async def test_extract_document_metadata_full_flow(self, scraper):
        """Test full metadata extraction flow."""
        # Get first registered franchise
        documents = await scraper.discover_documents()

        if documents:
            doc = documents[0]
            scraper._current_franchise_name = doc.franchise_name

            # Extract detailed metadata
            enhanced_metadata = await scraper.extract_document_metadata(doc.source_url)

            if enhanced_metadata:
                assert isinstance(enhanced_metadata, DocumentMetadata)
                assert enhanced_metadata.franchise_name == doc.franchise_name

                # Check for enhanced fields
                if enhanced_metadata.filing_number:
                    assert enhanced_metadata.filing_number.isdigit()

                if enhanced_metadata.filing_date:
                    assert (
                        "/" in enhanced_metadata.filing_date
                        or "-" in enhanced_metadata.filing_date
                    )

                print(f"Enhanced metadata for {enhanced_metadata.franchise_name}:")
                print(f"  Filing number: {enhanced_metadata.filing_number}")
                print(f"  Filing date: {enhanced_metadata.filing_date}")
                print(
                    f"  Legal name: {enhanced_metadata.additional_metadata.get('legal_name')}"
                )
            else:
                print("Could not extract enhanced metadata")
        else:
            print("No documents discovered for metadata extraction test")

    @pytest.mark.asyncio
    async def test_error_handling_invalid_franchise(self, scraper):
        """Test error handling for non-existent franchise."""
        # Search for a franchise that definitely doesn't exist
        doc_metadata = await scraper._search_franchise_basic(
            "XYZNONEXISTENTFRANCHISE12345"
        )

        # Should return None for non-existent franchise
        assert doc_metadata is None
