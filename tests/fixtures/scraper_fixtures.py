"""Scraper fixtures for testing."""

from typing import List, Optional, Dict, Any
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from tasks.web_scraping import DocumentMetadata, BaseScraper


class MockScraperFactory:
    """Factory for creating mock scrapers with predefined behaviors."""

    @staticmethod
    def create_successful_scraper(
        documents: List[DocumentMetadata], source_name: str = "TEST"
    ) -> AsyncMock:
        """Create a mock scraper that successfully returns documents."""
        mock_scraper = AsyncMock(spec=BaseScraper)

        # Set basic attributes
        mock_scraper.source_name = source_name
        mock_scraper.page = AsyncMock()
        mock_scraper.context = AsyncMock()
        mock_scraper.browser = AsyncMock()
        mock_scraper.http_client = AsyncMock()

        # Mock methods
        mock_scraper.discover_documents = AsyncMock(return_value=documents)
        mock_scraper.extract_document_metadata = AsyncMock(
            side_effect=lambda url: next(
                (doc for doc in documents if doc.source_url == url), None
            )
        )
        mock_scraper.download_file_streaming = AsyncMock(return_value=True)
        mock_scraper.compute_document_hash = AsyncMock(return_value="a" * 64)
        mock_scraper.safe_navigate = AsyncMock()
        mock_scraper.manage_cookies = AsyncMock()
        mock_scraper.extract_table_data = AsyncMock(return_value=[])
        mock_scraper.clear_search_input = AsyncMock()

        # Mock context manager methods
        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock(return_value=None)

        return mock_scraper

    @staticmethod
    def create_failing_scraper(
        error_message: str = "Scraping failed", source_name: str = "TEST"
    ) -> AsyncMock:
        """Create a mock scraper that fails."""
        mock_scraper = AsyncMock(spec=BaseScraper)

        mock_scraper.source_name = source_name
        mock_scraper.discover_documents = AsyncMock(
            side_effect=Exception(error_message)
        )
        mock_scraper.extract_document_metadata = AsyncMock(
            side_effect=Exception(error_message)
        )

        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock(return_value=None)

        return mock_scraper

    @staticmethod
    def create_partial_failure_scraper(
        documents: List[DocumentMetadata],
        fail_at_index: int = 1,
        source_name: str = "TEST",
    ) -> AsyncMock:
        """Create a mock scraper that partially fails."""
        mock_scraper = AsyncMock(spec=BaseScraper)

        mock_scraper.source_name = source_name
        mock_scraper.discover_documents = AsyncMock(return_value=documents)

        # Create side effects for partial failure
        extract_effects = []
        download_effects = []

        for i, doc in enumerate(documents):
            if i == fail_at_index:
                extract_effects.append(Exception("Extraction failed"))
                download_effects.append(False)
            else:
                extract_effects.append(doc)
                download_effects.append(True)

        mock_scraper.extract_document_metadata = AsyncMock(side_effect=extract_effects)
        mock_scraper.download_file_streaming = AsyncMock(side_effect=download_effects)

        mock_scraper.compute_document_hash = AsyncMock(return_value="a" * 64)
        mock_scraper.safe_navigate = AsyncMock()
        mock_scraper.manage_cookies = AsyncMock()

        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock(return_value=None)

        return mock_scraper


class MockBrowserFactory:
    """Factory for creating mock browser components."""

    @staticmethod
    def create_page_with_content(html_content: str) -> AsyncMock:
        """Create a mock page with specific HTML content."""
        mock_page = AsyncMock()

        # Basic page methods
        mock_page.content = AsyncMock(return_value=html_content)
        mock_page.url = "https://test.example.com"
        mock_page.title = AsyncMock(return_value="Test Page")

        # Navigation methods
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        # Element interaction methods
        mock_page.query_selector = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.fill = AsyncMock()
        mock_page.click = AsyncMock()

        # Evaluation methods
        mock_page.evaluate = AsyncMock()
        mock_page.inner_text = AsyncMock(return_value="")
        mock_page.inner_html = AsyncMock(return_value=html_content)

        return mock_page

    @staticmethod
    def create_element(
        tag: str = "div", text: str = "", attributes: Dict[str, str] = None
    ) -> AsyncMock:
        """Create a mock page element."""
        mock_element = AsyncMock()

        mock_element.tag_name = AsyncMock(return_value=tag)
        mock_element.inner_text = AsyncMock(return_value=text)
        mock_element.inner_html = AsyncMock(return_value=f"<{tag}>{text}</{tag}>")

        # Attribute methods
        if attributes:
            mock_element.get_attribute = AsyncMock(
                side_effect=lambda attr: attributes.get(attr)
            )
        else:
            mock_element.get_attribute = AsyncMock(return_value=None)

        # Interaction methods
        mock_element.click = AsyncMock()
        mock_element.fill = AsyncMock()
        mock_element.is_visible = AsyncMock(return_value=True)
        mock_element.is_enabled = AsyncMock(return_value=True)

        return mock_element


class ScraperTestScenarios:
    """Common scraper test scenarios."""

    @staticmethod
    def successful_discovery_scenario(
        scraper_class: type, documents: List[DocumentMetadata]
    ) -> Dict[str, Any]:
        """Setup for successful document discovery."""
        return {
            "mock_scraper": MockScraperFactory.create_successful_scraper(
                documents, scraper_class.__name__.replace("Scraper", "").upper()[:2]
            ),
            "expected_count": len(documents),
            "should_fail": False,
        }

    @staticmethod
    def failed_discovery_scenario(
        scraper_class: type, error_message: str = "Portal unavailable"
    ) -> Dict[str, Any]:
        """Setup for failed document discovery."""
        return {
            "mock_scraper": MockScraperFactory.create_failing_scraper(
                error_message, scraper_class.__name__.replace("Scraper", "").upper()[:2]
            ),
            "expected_error": error_message,
            "should_fail": True,
        }

    @staticmethod
    def partial_failure_scenario(
        scraper_class: type, documents: List[DocumentMetadata], fail_at: int = 1
    ) -> Dict[str, Any]:
        """Setup for partial failure during processing."""
        return {
            "mock_scraper": MockScraperFactory.create_partial_failure_scraper(
                documents,
                fail_at,
                scraper_class.__name__.replace("Scraper", "").upper()[:2],
            ),
            "expected_success_count": fail_at,
            "expected_failure_count": len(documents) - fail_at,
            "should_partially_fail": True,
        }


# Export all fixture classes
__all__ = ["MockScraperFactory", "MockBrowserFactory", "ScraperTestScenarios"]
