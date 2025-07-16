"""Tests for Wisconsin scraping flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4

# Mock Prefect modules before importing the flow
with patch.dict(
    "sys.modules",
    {
        "prefect": Mock(),
        "prefect.task_runners": Mock(),
    },
):
    # Mock the specific functions and classes we use
    mock_flow = Mock()
    mock_task = Mock()
    mock_get_run_logger = Mock()
    mock_concurrent_task_runner = Mock()

    with (
        patch("prefect.flow", mock_flow),
        patch("prefect.task", mock_task),
        patch("prefect.get_run_logger", mock_get_run_logger),
        patch("prefect.task_runners.ConcurrentTaskRunner", mock_concurrent_task_runner),
    ):

        from flows.scrape_wisconsin import (
            scrape_wisconsin_portal,
            process_wisconsin_documents,
        )

from tasks.web_scraping import DocumentMetadata
from models.scrape_metadata import ScrapeMetadata


@pytest.mark.asyncio
class TestWisconsinFlow:
    """Test suite for Wisconsin scraping flow."""

    async def test_scrape_wisconsin_portal_task(self):
        """Test the Wisconsin portal scraping task."""
        prefect_run_id = uuid4()

        # Mock the scraper and its methods
        mock_documents = [
            DocumentMetadata(
                franchise_name="Test Franchise",
                document_type="FDD",
                source_url="https://test.url",
                download_url="https://test.url/download",
            )
        ]

        with patch("flows.scrape_wisconsin.create_scraper") as mock_create_scraper:
            # Setup mock scraper context manager
            mock_scraper = AsyncMock()
            mock_scraper.scrape_portal = AsyncMock(return_value=mock_documents)

            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_scraper)
            mock_context.__aexit__ = AsyncMock(return_value=None)

            mock_create_scraper.return_value = mock_context

            # Execute the task
            result = await scrape_wisconsin_portal(prefect_run_id)

            # Verify results
            assert len(result) == 1
            assert result[0].franchise_name == "Test Franchise"
            assert result[0].document_type == "FDD"

            # Verify scraper was called correctly
            mock_create_scraper.assert_called_once()
            mock_scraper.scrape_portal.assert_called_once()

    async def test_process_wisconsin_documents_task(self):
        """Test the Wisconsin document processing task."""
        prefect_run_id = uuid4()

        # Mock input documents
        mock_documents = [
            DocumentMetadata(
                franchise_name="Test Franchise",
                filing_date="2024-01-15",
                document_type="FDD",
                filing_number="12345",
                source_url="https://test.url",
                download_url="https://test.url/download",
                additional_metadata={"test": "data"},
            )
        ]

        # Mock database manager
        mock_db = AsyncMock()
        mock_db.create_scrape_metadata = AsyncMock()

        mock_db_context = AsyncMock()
        mock_db_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_context.__aexit__ = AsyncMock(return_value=None)

        with patch("flows.scrape_wisconsin.get_database_manager") as mock_get_db:
            mock_get_db.return_value = mock_db_context

            # Execute the task
            result = await process_wisconsin_documents(mock_documents, prefect_run_id)

            # Verify results
            assert len(result) == 1
            assert isinstance(result[0], ScrapeMetadata)
            assert result[0].source_name == "WI"
            assert result[0].filing_metadata["franchise_name"] == "Test Franchise"
            assert result[0].filing_metadata["filing_number"] == "12345"
            assert result[0].prefect_run_id == prefect_run_id

            # Verify database interaction
            mock_get_db.assert_called_once()
            mock_db.create_scrape_metadata.assert_called_once()

    async def test_process_wisconsin_documents_with_errors(self):
        """Test document processing with some failures."""
        prefect_run_id = uuid4()

        # Mock input documents
        mock_documents = [
            DocumentMetadata(
                franchise_name="Good Franchise",
                document_type="FDD",
                source_url="https://test.url/good",
                download_url="https://test.url/good/download",
            ),
            DocumentMetadata(
                franchise_name="Bad Franchise",
                document_type="FDD",
                source_url="https://test.url/bad",
                download_url="https://test.url/bad/download",
            ),
        ]

        # Mock database manager that fails on second document
        mock_db = AsyncMock()
        mock_db.create_scrape_metadata = AsyncMock(
            side_effect=[None, Exception("Database error")]
        )

        mock_db_context = AsyncMock()
        mock_db_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_context.__aexit__ = AsyncMock(return_value=None)

        with patch("flows.scrape_wisconsin.get_database_manager") as mock_get_db:
            mock_get_db.return_value = mock_db_context

            # Execute the task
            result = await process_wisconsin_documents(mock_documents, prefect_run_id)

            # Verify results - should have 1 successful, 1 failed
            assert len(result) == 1
            assert result[0].filing_metadata["franchise_name"] == "Good Franchise"

            # Verify database was called twice
            assert mock_db.create_scrape_metadata.call_count == 2

    async def test_empty_document_list(self):
        """Test processing with empty document list."""
        prefect_run_id = uuid4()

        # Mock database manager
        mock_db = AsyncMock()
        mock_db_context = AsyncMock()
        mock_db_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_context.__aexit__ = AsyncMock(return_value=None)

        with patch("flows.scrape_wisconsin.get_database_manager") as mock_get_db:
            mock_get_db.return_value = mock_db_context

            # Execute the task with empty list
            result = await process_wisconsin_documents([], prefect_run_id)

            # Verify results
            assert len(result) == 0

            # Verify database manager was still called (context manager)
            mock_get_db.assert_called_once()
            # But no create operations should have been called
            mock_db.create_scrape_metadata.assert_not_called()
