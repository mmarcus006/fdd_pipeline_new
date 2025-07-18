"""Integration tests for Minnesota scraping flow."""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Mock Prefect imports to avoid server connection issues
with patch.dict('sys.modules', {
    'prefect': MagicMock(),
    'prefect.task_runners': MagicMock(),
}):
    from flows.scrape_minnesota import (
        scrape_minnesota_portal,
        process_minnesota_documents,
        download_minnesota_documents,
        collect_minnesota_metrics,
        scrape_minnesota_flow,
    )

from tasks.web_scraping import DocumentMetadata
from tasks.exceptions import WebScrapingException
from models.scrape_metadata import ScrapeMetadata


@pytest.fixture
def sample_documents():
    """Sample document metadata for testing."""
    return [
        DocumentMetadata(
            franchise_name="Test Franchise 1",
            filing_date="2024-01-15",
            document_type="Clean FDD",
            filing_number="F-2024-001",
            source_url="https://www.cards.commerce.state.mn.us/test1",
            download_url="https://www.cards.commerce.state.mn.us/download/test1.pdf",
            file_size=1024000,
            additional_metadata={
                "source": "MN",
                "franchisor": "Test Corp 1",
                "year": "2024",
                "document_id": "test-id-1",
            },
        ),
        DocumentMetadata(
            franchise_name="Test Franchise 2",
            filing_date="2024-02-20",
            document_type="Clean FDD",
            filing_number="F-2024-002",
            source_url="https://www.cards.commerce.state.mn.us/test2",
            download_url="https://www.cards.commerce.state.mn.us/download/test2.pdf",
            file_size=2048000,
            additional_metadata={
                "source": "MN",
                "franchisor": "Test Corp 2",
                "year": "2024",
                "document_id": "test-id-2",
            },
        ),
    ]


@pytest.fixture
def sample_scrape_metadata():
    """Sample scrape metadata for testing."""
    return [
        ScrapeMetadata(
            id=uuid4(),
            fdd_id=uuid4(),
            source_name="MN",
            source_url="https://www.cards.commerce.state.mn.us/test1",
            filing_metadata={
                "franchise_name": "Test Franchise 1",
                "filing_date": "2024-01-15",
                "document_type": "Clean FDD",
                "filing_number": "F-2024-001",
                "download_url": "https://www.cards.commerce.state.mn.us/download/test1.pdf",
                "file_size": 1024000,
            },
            prefect_run_id=uuid4(),
            scraped_at=datetime.utcnow(),
        ),
        ScrapeMetadata(
            id=uuid4(),
            fdd_id=uuid4(),
            source_name="MN",
            source_url="https://www.cards.commerce.state.mn.us/test2",
            filing_metadata={
                "franchise_name": "Test Franchise 2",
                "filing_date": "2024-02-20",
                "document_type": "Clean FDD",
                "filing_number": "F-2024-002",
                "download_url": "https://www.cards.commerce.state.mn.us/download/test2.pdf",
                "file_size": 2048000,
            },
            prefect_run_id=uuid4(),
            scraped_at=datetime.utcnow(),
        ),
    ]


class TestMinnesotaScrapingTasks:
    """Test individual tasks in the Minnesota scraping flow."""

    @pytest.mark.asyncio
    async def test_scrape_minnesota_portal_success(self, sample_documents):
        """Test successful Minnesota portal scraping."""
        prefect_run_id = uuid4()

        # Mock the scraper
        mock_scraper = AsyncMock()
        mock_scraper.scrape_portal.return_value = sample_documents

        with patch("flows.scrape_minnesota.create_scraper") as mock_create_scraper:
            mock_create_scraper.return_value.__aenter__.return_value = mock_scraper

            result = await scrape_minnesota_portal(prefect_run_id)

            assert len(result) == 2
            assert result[0].franchise_name == "Test Franchise 1"
            assert result[1].franchise_name == "Test Franchise 2"
            mock_scraper.scrape_portal.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_minnesota_portal_failure(self):
        """Test Minnesota portal scraping failure with retries."""
        prefect_run_id = uuid4()

        # Mock the scraper to raise an exception
        mock_scraper = AsyncMock()
        mock_scraper.scrape_portal.side_effect = Exception("Portal unavailable")

        with patch("flows.scrape_minnesota.create_scraper") as mock_create_scraper:
            mock_create_scraper.return_value.__aenter__.return_value = mock_scraper

            with pytest.raises(WebScrapingException):
                await scrape_minnesota_portal(prefect_run_id)

    @pytest.mark.asyncio
    async def test_process_minnesota_documents_success(self, sample_documents):
        """Test successful processing of Minnesota documents."""
        prefect_run_id = uuid4()

        # Mock database manager
        mock_db = AsyncMock()
        mock_db.create_scrape_metadata = AsyncMock()

        with patch("flows.scrape_minnesota.get_database_manager") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            result = await process_minnesota_documents(sample_documents, prefect_run_id)

            assert len(result) == 2
            assert all(isinstance(metadata, ScrapeMetadata) for metadata in result)
            assert all(metadata.source_name == "MN" for metadata in result)
            assert mock_db.create_scrape_metadata.call_count == 2

    @pytest.mark.asyncio
    async def test_process_minnesota_documents_partial_failure(self, sample_documents):
        """Test processing with some document failures."""
        prefect_run_id = uuid4()

        # Mock database manager to fail on second document
        mock_db = AsyncMock()
        mock_db.create_scrape_metadata.side_effect = [None, Exception("DB error")]

        with patch("flows.scrape_minnesota.get_database_manager") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            result = await process_minnesota_documents(sample_documents, prefect_run_id)

            # Should only have one successful result
            assert len(result) == 1
            assert result[0].source_name == "MN"

    @pytest.mark.asyncio
    async def test_download_minnesota_documents_success(self, sample_scrape_metadata):
        """Test successful downloading of Minnesota documents."""
        prefect_run_id = uuid4()

        # Mock the scraper
        mock_scraper = AsyncMock()
        mock_scraper.download_document.return_value = b"%PDF-1.4 fake pdf content"
        mock_scraper.compute_document_hash.return_value = "abcd1234" * 8  # 64 chars

        with patch("flows.scrape_minnesota.create_scraper") as mock_create_scraper:
            mock_create_scraper.return_value.__aenter__.return_value = mock_scraper

            result = await download_minnesota_documents(
                sample_scrape_metadata, prefect_run_id
            )

            assert len(result) == 2
            assert all("mn/" in path for path in result)
            assert mock_scraper.download_document.call_count == 2

    @pytest.mark.asyncio
    async def test_download_minnesota_documents_partial_failure(
        self, sample_scrape_metadata
    ):
        """Test downloading with some document failures."""
        prefect_run_id = uuid4()

        # Mock the scraper to fail on second download
        mock_scraper = AsyncMock()
        mock_scraper.download_document.side_effect = [
            b"%PDF-1.4 fake pdf content",
            Exception("Download failed"),
        ]
        mock_scraper.compute_document_hash.return_value = "abcd1234" * 8

        with patch("flows.scrape_minnesota.create_scraper") as mock_create_scraper:
            mock_create_scraper.return_value.__aenter__.return_value = mock_scraper

            result = await download_minnesota_documents(
                sample_scrape_metadata, prefect_run_id
            )

            # Should only have one successful download
            assert len(result) == 1
            assert "mn/" in result[0]

    @pytest.mark.asyncio
    async def test_collect_minnesota_metrics(self):
        """Test metrics collection for Minnesota scraping."""
        prefect_run_id = uuid4()
        start_time = datetime.utcnow()

        result = await collect_minnesota_metrics(
            documents_discovered=10,
            metadata_records_created=8,
            documents_downloaded=6,
            prefect_run_id=prefect_run_id,
            start_time=start_time,
        )

        assert result["source"] == "MN"
        assert result["documents_discovered"] == 10
        assert result["metadata_records_created"] == 8
        assert result["documents_downloaded"] == 6
        assert result["success_rate"] == 0.8  # 8/10
        assert result["download_rate"] == 0.75  # 6/8
        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0


class TestMinnesotaScrapingFlow:
    """Test the complete Minnesota scraping flow."""

    @pytest.mark.asyncio
    async def test_scrape_minnesota_flow_success(self, sample_documents):
        """Test successful complete Minnesota scraping flow."""
        # Mock all the tasks
        with patch(
            "flows.scrape_minnesota.scrape_minnesota_portal"
        ) as mock_scrape, patch(
            "flows.scrape_minnesota.process_minnesota_documents"
        ) as mock_process, patch(
            "flows.scrape_minnesota.download_minnesota_documents"
        ) as mock_download, patch(
            "flows.scrape_minnesota.collect_minnesota_metrics"
        ) as mock_metrics:

            # Set up mock returns
            mock_scrape.return_value = sample_documents
            mock_process.return_value = [MagicMock(), MagicMock()]
            mock_download.return_value = ["mn/test1.pdf", "mn/test2.pdf"]
            mock_metrics.return_value = {"test": "metrics"}

            result = await scrape_minnesota_flow(
                download_documents=True, max_documents=None
            )

            assert result["success"] is True
            assert result["documents_discovered"] == 2
            assert result["metadata_records_created"] == 2
            assert result["documents_downloaded"] == 2
            assert "prefect_run_id" in result
            assert "timestamp" in result
            assert "metrics" in result

            # Verify all tasks were called
            mock_scrape.assert_called_once()
            mock_process.assert_called_once()
            mock_download.assert_called_once()
            mock_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_minnesota_flow_no_download(self, sample_documents):
        """Test Minnesota scraping flow without downloading documents."""
        with patch(
            "flows.scrape_minnesota.scrape_minnesota_portal"
        ) as mock_scrape, patch(
            "flows.scrape_minnesota.process_minnesota_documents"
        ) as mock_process, patch(
            "flows.scrape_minnesota.download_minnesota_documents"
        ) as mock_download, patch(
            "flows.scrape_minnesota.collect_minnesota_metrics"
        ) as mock_metrics:

            mock_scrape.return_value = sample_documents
            mock_process.return_value = [MagicMock(), MagicMock()]
            mock_metrics.return_value = {"test": "metrics"}

            result = await scrape_minnesota_flow(
                download_documents=False, max_documents=None
            )

            assert result["success"] is True
            assert result["documents_discovered"] == 2
            assert result["metadata_records_created"] == 2
            assert result["documents_downloaded"] == 0

            # Download task should not be called
            mock_download.assert_not_called()

    @pytest.mark.asyncio
    async def test_scrape_minnesota_flow_with_limit(self, sample_documents):
        """Test Minnesota scraping flow with document limit."""
        with patch(
            "flows.scrape_minnesota.scrape_minnesota_portal"
        ) as mock_scrape, patch(
            "flows.scrape_minnesota.process_minnesota_documents"
        ) as mock_process, patch(
            "flows.scrape_minnesota.download_minnesota_documents"
        ) as mock_download, patch(
            "flows.scrape_minnesota.collect_minnesota_metrics"
        ) as mock_metrics:

            mock_scrape.return_value = sample_documents
            mock_process.return_value = [MagicMock()]  # Only one processed
            mock_download.return_value = ["mn/test1.pdf"]
            mock_metrics.return_value = {"test": "metrics"}

            result = await scrape_minnesota_flow(
                download_documents=True, max_documents=1
            )

            assert result["success"] is True
            assert result["documents_discovered"] == 1  # Limited to 1
            assert result["metadata_records_created"] == 1
            assert result["documents_downloaded"] == 1

            # Verify process was called with limited documents
            mock_process.assert_called_once()
            call_args = mock_process.call_args[0]
            assert len(call_args[0]) == 1  # Only one document passed

    @pytest.mark.asyncio
    async def test_scrape_minnesota_flow_failure(self):
        """Test Minnesota scraping flow failure handling."""
        with patch(
            "flows.scrape_minnesota.scrape_minnesota_portal"
        ) as mock_scrape, patch(
            "flows.scrape_minnesota.collect_minnesota_metrics"
        ) as mock_metrics:

            # Make scraping fail
            mock_scrape.side_effect = Exception("Scraping failed")
            mock_metrics.return_value = {"partial": "metrics"}

            result = await scrape_minnesota_flow()

            assert result["success"] is False
            assert "error" in result
            assert result["documents_discovered"] == 0
            assert result["metadata_records_created"] == 0
            assert result["documents_downloaded"] == 0

            # Metrics should still be collected for failure case
            mock_metrics.assert_called_once()


class TestMinnesotaFlowIntegration:
    """Integration tests for Minnesota flow components."""

    @pytest.mark.asyncio
    async def test_flow_error_handling_and_recovery(self):
        """Test flow handles errors gracefully and continues where possible."""
        prefect_run_id = uuid4()

        # Test that processing continues even if some documents fail
        documents = [
            DocumentMetadata(
                franchise_name="Good Franchise",
                source_url="https://test.com/good",
                download_url="https://test.com/good.pdf",
            ),
            DocumentMetadata(
                franchise_name="Bad Franchise",
                source_url="https://test.com/bad",
                download_url="https://test.com/bad.pdf",
            ),
        ]

        # Mock database to fail on second document
        mock_db = AsyncMock()
        mock_db.create_scrape_metadata.side_effect = [None, Exception("DB error")]

        with patch("flows.scrape_minnesota.get_database_manager") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            result = await process_minnesota_documents(documents, prefect_run_id)

            # Should have one successful result despite one failure
            assert len(result) == 1
            assert result[0].filing_metadata["franchise_name"] == "Good Franchise"

    @pytest.mark.asyncio
    async def test_flow_metrics_accuracy(self):
        """Test that flow metrics accurately reflect processing results."""
        start_time = datetime.utcnow()
        prefect_run_id = uuid4()

        # Test various scenarios
        test_cases = [
            (10, 10, 10),  # Perfect success
            (10, 8, 6),  # Some failures
            (10, 0, 0),  # Complete failure
            (0, 0, 0),  # No documents found
        ]

        for discovered, processed, downloaded in test_cases:
            metrics = await collect_minnesota_metrics(
                documents_discovered=discovered,
                metadata_records_created=processed,
                documents_downloaded=downloaded,
                prefect_run_id=prefect_run_id,
                start_time=start_time,
            )

            expected_success_rate = processed / discovered if discovered > 0 else 0
            expected_download_rate = downloaded / processed if processed > 0 else 0

            assert metrics["success_rate"] == expected_success_rate
            assert metrics["download_rate"] == expected_download_rate
            assert metrics["documents_discovered"] == discovered
            assert metrics["metadata_records_created"] == processed
            assert metrics["documents_downloaded"] == downloaded


if __name__ == "__main__":
    pytest.main([__file__])