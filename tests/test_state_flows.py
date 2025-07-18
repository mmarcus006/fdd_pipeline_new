"""Consolidated tests for all state scraping flows using the base flow architecture."""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4

from test_state_flow_base import (
    StateFlowTestBase,
    StateFlowTestFixtures,
    StateFlowSuccessScenarios,
    StateFlowFailureScenarios,
)

# Mock Prefect imports
with StateFlowTestBase.mock_prefect_imports():
    from flows.base_state_flow import (
        scrape_state_portal,
        process_state_documents,
        download_state_documents,
        collect_state_metrics,
        scrape_state_flow,
    )
    from flows.state_configs import MINNESOTA_CONFIG, WISCONSIN_CONFIG, StateConfig

from tasks.web_scraping import DocumentMetadata
from models.scrape_metadata import ScrapeMetadata


class TestBaseStateFlow(StateFlowTestBase):
    """Test the base state flow with generic state configuration."""

    @pytest.fixture
    def test_state_config(self):
        """Test state configuration."""
        return StateFlowTestFixtures.create_test_state_config("TEST", "Test State")

    @pytest.fixture
    def test_documents(self):
        """Test documents for generic state."""
        return [
            self.create_test_document(
                franchise_name="Test Franchise 1",
                state_code="TEST",
                filing_number="TEST-001",
            ),
            self.create_test_document(
                franchise_name="Test Franchise 2",
                state_code="TEST",
                filing_number="TEST-002",
            ),
        ]

    @pytest.mark.asyncio
    async def test_scrape_state_portal_success(self, test_state_config, test_documents):
        """Test successful state portal scraping."""
        mock_scraper = self.create_mock_scraper(test_documents)

        with patch("flows.base_state_flow.create_scraper") as mock_create:
            mock_create.return_value.__aenter__.return_value = mock_scraper

            result = await scrape_state_portal(
                state_config=test_state_config, prefect_run_id=uuid4()
            )

            assert len(result) == 2
            assert all(doc.additional_metadata["source"] == "TEST" for doc in result)
            mock_scraper.discover_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_state_documents_success(
        self, test_state_config, test_documents
    ):
        """Test successful document processing."""
        mock_db = self.create_mock_database()
        mock_drive = self.create_mock_drive_manager()

        with (
            patch("flows.base_state_flow.get_database_manager") as mock_get_db,
            patch("flows.base_state_flow.GoogleDriveManager") as mock_drive_class,
        ):

            mock_get_db.return_value = mock_db
            mock_drive_class.return_value = mock_drive

            result = await process_state_documents(
                documents=test_documents,
                state_config=test_state_config,
                prefect_run_id=uuid4(),
            )

            assert len(result) == 2
            assert all(isinstance(r, ScrapeMetadata) for r in result)
            assert mock_db.upsert_franchisor.call_count == 2
            assert mock_db.upsert_fdd.call_count == 2

    @pytest.mark.asyncio
    async def test_download_state_documents_success(self, test_state_config):
        """Test successful document downloading."""
        # Create scrape metadata
        test_doc = self.create_test_document("Test", "TEST")
        scrape_metadata = [self.create_test_scrape_metadata(test_doc, "TEST")]

        mock_scraper = self.create_mock_scraper([test_doc])

        with (
            patch("flows.base_state_flow.create_scraper") as mock_create,
            patch(
                "tasks.document_metadata.download_and_save_document"
            ) as mock_download,
        ):

            mock_create.return_value.__aenter__.return_value = mock_scraper
            mock_download.return_value = Path("downloads/TEST/test.pdf")

            result = await download_state_documents(
                scrape_metadata_list=scrape_metadata,
                state_config=test_state_config,
                prefect_run_id=uuid4(),
            )

            assert len(result) == 1
            assert "test.pdf" in str(result[0])
            mock_download.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_state_metrics(self, test_state_config):
        """Test metrics collection."""
        metrics = await collect_state_metrics(
            documents_discovered=10,
            metadata_records_created=8,
            documents_downloaded=6,
            state_config=test_state_config,
            prefect_run_id=uuid4(),
            start_time=datetime.utcnow(),
        )

        self.assert_metrics(metrics, 10, 8, 6, "TEST")

    @pytest.mark.asyncio
    async def test_scrape_state_flow_complete(self, test_state_config, test_documents):
        """Test complete state scraping flow."""
        with (
            patch("flows.base_state_flow.scrape_state_portal") as mock_scrape,
            patch("flows.base_state_flow.process_state_documents") as mock_process,
            patch("flows.base_state_flow.download_state_documents") as mock_download,
            patch("flows.base_state_flow.collect_state_metrics") as mock_metrics,
        ):

            # Setup mocks
            mock_scrape.return_value = test_documents
            mock_process.return_value = [MagicMock() for _ in test_documents]
            mock_download.return_value = ["test1.pdf", "test2.pdf"]
            mock_metrics.return_value = {"test": "metrics"}

            result = await scrape_state_flow(
                state_config=test_state_config, download_documents=True
            )

            assert result["success"] is True
            assert result["documents_discovered"] == 2
            assert result["metadata_records_created"] == 2
            assert result["documents_downloaded"] == 2
            assert result["state"] == "TEST"

            # Verify all tasks called
            mock_scrape.assert_called_once()
            mock_process.assert_called_once()
            mock_download.assert_called_once()
            mock_metrics.assert_called_once()


class TestMinnesotaFlow(
    StateFlowTestBase, StateFlowSuccessScenarios, StateFlowFailureScenarios
):
    """Test Minnesota-specific flow behavior."""

    @pytest.fixture
    def minnesota_documents(self):
        """Minnesota test documents."""
        return StateFlowTestFixtures.minnesota_documents()

    @pytest.mark.asyncio
    async def test_minnesota_discovery_success(self, minnesota_documents):
        """Test Minnesota document discovery."""
        await self._test_successful_discovery(MINNESOTA_CONFIG, minnesota_documents)

    @pytest.mark.asyncio
    async def test_minnesota_processing_success(self, minnesota_documents):
        """Test Minnesota document processing."""
        await self._test_successful_processing(MINNESOTA_CONFIG, minnesota_documents)

    @pytest.mark.asyncio
    async def test_minnesota_discovery_failure(self):
        """Test Minnesota discovery failure."""
        await self._test_discovery_failure(MINNESOTA_CONFIG)

    @pytest.mark.asyncio
    async def test_minnesota_csv_export(self, minnesota_documents):
        """Test Minnesota-specific CSV export format."""
        from tasks.document_metadata import export_documents_to_csv

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            result = export_documents_to_csv(
                documents=minnesota_documents,
                filepath=Path("test_mn.csv"),
                state_code="MN",
            )

            assert result is True
            mock_open.assert_called_once_with(
                Path("test_mn.csv"), "w", newline="", encoding="utf-8"
            )

            # Verify CSV headers include Minnesota-specific fields
            write_calls = mock_file.write.call_args_list
            header_written = any("Franchisor" in str(call) for call in write_calls)
            assert header_written


class TestWisconsinFlow(
    StateFlowTestBase, StateFlowSuccessScenarios, StateFlowFailureScenarios
):
    """Test Wisconsin-specific flow behavior."""

    @pytest.fixture
    def wisconsin_documents(self):
        """Wisconsin test documents."""
        return StateFlowTestFixtures.wisconsin_documents()

    @pytest.mark.asyncio
    async def test_wisconsin_discovery_success(self, wisconsin_documents):
        """Test Wisconsin document discovery."""
        await self._test_successful_discovery(WISCONSIN_CONFIG, wisconsin_documents)

    @pytest.mark.asyncio
    async def test_wisconsin_processing_success(self, wisconsin_documents):
        """Test Wisconsin document processing."""
        await self._test_successful_processing(WISCONSIN_CONFIG, wisconsin_documents)

    @pytest.mark.asyncio
    async def test_wisconsin_partial_failure(self, wisconsin_documents):
        """Test Wisconsin partial processing failure."""
        await self._test_partial_processing_failure(
            WISCONSIN_CONFIG, wisconsin_documents
        )

    @pytest.mark.asyncio
    async def test_wisconsin_csv_export(self, wisconsin_documents):
        """Test Wisconsin-specific CSV export format."""
        from tasks.document_metadata import export_documents_to_csv

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            result = export_documents_to_csv(
                documents=wisconsin_documents,
                filepath=Path("test_wi.csv"),
                state_code="WI",
            )

            assert result is True
            mock_open.assert_called_once_with(
                Path("test_wi.csv"), "w", newline="", encoding="utf-8"
            )

            # Verify CSV headers include Wisconsin-specific fields
            write_calls = mock_file.write.call_args_list
            header_written = any("Legal Name" in str(call) for call in write_calls)
            assert header_written


class TestStateFlowIntegration:
    """Integration tests for state flow edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_flow_with_document_limit(self):
        """Test flow respects document limits."""
        test_config = StateFlowTestFixtures.create_test_state_config()
        all_documents = [
            StateFlowTestBase.create_test_document(
                f"Franchise {i}", "TEST", document_id=f"test-{i}"
            )
            for i in range(10)
        ]

        with (
            patch("flows.base_state_flow.scrape_state_portal") as mock_scrape,
            patch("flows.base_state_flow.process_state_documents") as mock_process,
        ):

            mock_scrape.return_value = all_documents
            mock_process.return_value = [
                MagicMock() for _ in range(5)
            ]  # Process only 5

            result = await scrape_state_flow(
                state_config=test_config, download_documents=False, max_documents=5
            )

            assert result["documents_discovered"] == 5  # Limited

            # Verify process was called with limited documents
            process_call_args = mock_process.call_args[0]
            assert len(process_call_args[0]) == 5

    @pytest.mark.asyncio
    async def test_flow_error_recovery(self):
        """Test flow continues processing after individual document failures."""
        test_config = StateFlowTestFixtures.create_test_state_config()
        documents = StateFlowTestFixtures.minnesota_documents()

        # Mock database to fail on second document
        mock_db = StateFlowTestBase.create_mock_database()
        mock_db.upsert_fdd.side_effect = [MagicMock(id=uuid4()), Exception("DB error")]

        with (
            patch("flows.base_state_flow.get_database_manager") as mock_get_db,
            patch("flows.base_state_flow.GoogleDriveManager") as mock_drive,
        ):

            mock_get_db.return_value = mock_db
            mock_drive.return_value = StateFlowTestBase.create_mock_drive_manager()

            result = await process_state_documents(
                documents=documents, state_config=test_config, prefect_run_id=uuid4()
            )

            # Should have one successful result
            assert len(result) == 1
            assert result[0].source_name == "TEST"

    @pytest.mark.asyncio
    async def test_metrics_calculation_edge_cases(self):
        """Test metrics calculation with edge cases."""
        test_config = StateFlowTestFixtures.create_test_state_config()

        # Test various edge cases
        test_cases = [
            (0, 0, 0),  # No documents
            (10, 0, 0),  # All failures
            (10, 10, 0),  # No downloads
            (10, 5, 5),  # Partial success
        ]

        for discovered, processed, downloaded in test_cases:
            metrics = await collect_state_metrics(
                documents_discovered=discovered,
                metadata_records_created=processed,
                documents_downloaded=downloaded,
                state_config=test_config,
                prefect_run_id=uuid4(),
                start_time=datetime.utcnow(),
            )

            StateFlowTestBase.assert_metrics(
                metrics, discovered, processed, downloaded, "TEST"
            )

    @pytest.mark.asyncio
    async def test_flow_with_no_downloads(self):
        """Test flow behavior when download is disabled."""
        test_config = StateFlowTestFixtures.create_test_state_config()
        documents = StateFlowTestFixtures.wisconsin_documents()

        with (
            patch("flows.base_state_flow.scrape_state_portal") as mock_scrape,
            patch("flows.base_state_flow.process_state_documents") as mock_process,
            patch("flows.base_state_flow.download_state_documents") as mock_download,
        ):

            mock_scrape.return_value = documents
            mock_process.return_value = [MagicMock() for _ in documents]

            result = await scrape_state_flow(
                state_config=test_config, download_documents=False
            )

            assert result["success"] is True
            assert result["documents_downloaded"] == 0
            mock_download.assert_not_called()


class TestStateConfigValidation:
    """Test state configuration validation and error handling."""

    def test_state_config_creation(self):
        """Test creating valid state configurations."""
        config = StateConfig(
            state_code="CA",
            state_name="California",
            scraper_class=MagicMock,
            folder_name="California FDDs",
            portal_name="CA Portal",
        )

        assert config.state_code == "CA"
        assert config.state_name == "California"
        assert config.folder_name == "California FDDs"
        assert config.portal_name == "CA Portal"

    def test_state_config_validation(self):
        """Test state configuration validation."""
        # Test invalid state code (too long)
        with pytest.raises(ValueError):
            StateConfig(
                state_code="TOOLONG",
                state_name="Test",
                scraper_class=MagicMock,
                folder_name="Test",
                portal_name="Test",
            )

    def test_get_state_config(self):
        """Test retrieving state configurations."""
        from flows.state_configs import get_state_config

        # Test valid states
        mn_config = get_state_config("MN")
        assert mn_config.state_name == "Minnesota"

        wi_config = get_state_config("WI")
        assert wi_config.state_name == "Wisconsin"

        # Test invalid state
        with pytest.raises(ValueError, match="Unknown state code"):
            get_state_config("XX")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
