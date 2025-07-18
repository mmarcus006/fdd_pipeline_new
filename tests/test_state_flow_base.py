"""Base test class and utilities for state flow testing."""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4

from tasks.web_scraping import DocumentMetadata
from models.scrape_metadata import ScrapeMetadata
from flows.state_configs import StateConfig


class StateFlowTestBase:
    """Base class for state flow tests with common utilities."""

    @staticmethod
    def create_test_document(
        franchise_name: str,
        state_code: str,
        filing_date: Optional[str] = None,
        filing_number: Optional[str] = None,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> DocumentMetadata:
        """Create a test document with state-specific metadata."""
        return DocumentMetadata(
            franchise_name=franchise_name,
            filing_date=filing_date or datetime.now().strftime("%Y-%m-%d"),
            document_type=kwargs.get("document_type", "FDD"),
            filing_number=filing_number,
            source_url=kwargs.get(
                "source_url",
                f"https://test.{state_code.lower()}.gov/{document_id or 'test'}",
            ),
            download_url=kwargs.get(
                "download_url",
                f"https://test.{state_code.lower()}.gov/download/{document_id or 'test'}.pdf",
            ),
            file_size=kwargs.get("file_size", 1024000),
            additional_metadata={
                "source": state_code,
                "document_id": document_id,
                **kwargs.get("additional_metadata", {}),
            },
        )

    @staticmethod
    def create_test_scrape_metadata(
        document: DocumentMetadata,
        state_code: str,
        fdd_id: Optional[str] = None,
        prefect_run_id: Optional[str] = None,
    ) -> ScrapeMetadata:
        """Create test scrape metadata from a document."""
        return ScrapeMetadata(
            id=uuid4(),
            fdd_id=fdd_id or uuid4(),
            source_name=state_code,
            source_url=document.source_url,
            filing_metadata={
                "franchise_name": document.franchise_name,
                "filing_date": document.filing_date,
                "document_type": document.document_type,
                "filing_number": document.filing_number,
                "download_url": document.download_url,
                "file_size": document.file_size,
                **document.additional_metadata,
            },
            prefect_run_id=prefect_run_id or uuid4(),
            scraped_at=datetime.utcnow(),
        )

    @staticmethod
    def create_mock_scraper(
        documents: List[DocumentMetadata],
        download_content: bytes = b"%PDF-1.4 fake pdf content",
        should_fail: bool = False,
    ) -> AsyncMock:
        """Create a mock scraper with predefined behavior."""
        mock_scraper = AsyncMock()

        if should_fail:
            mock_scraper.discover_documents.side_effect = Exception("Scraper failed")
            mock_scraper.extract_document_metadata.side_effect = Exception(
                "Extraction failed"
            )
        else:
            mock_scraper.discover_documents.return_value = documents
            mock_scraper.extract_document_metadata.side_effect = lambda url: next(
                (doc for doc in documents if doc.source_url == url), None
            )

        mock_scraper.download_file_streaming.return_value = True
        mock_scraper.compute_document_hash.return_value = "abcd1234" * 8  # 64 chars

        return mock_scraper

    @staticmethod
    def create_mock_database(
        should_fail: bool = False, partial_failure_index: Optional[int] = None
    ) -> AsyncMock:
        """Create a mock database manager."""
        mock_db = AsyncMock()

        if should_fail:
            mock_db.upsert_franchisor.side_effect = Exception("DB error")
            mock_db.upsert_fdd.side_effect = Exception("DB error")
            mock_db.create_scrape_metadata.side_effect = Exception("DB error")
        elif partial_failure_index is not None:
            # Fail on specific index
            effects = []
            for i in range(10):  # Support up to 10 calls
                if i == partial_failure_index:
                    effects.append(Exception("DB error"))
                else:
                    effects.append(MagicMock())
            mock_db.upsert_franchisor.side_effect = effects
            mock_db.upsert_fdd.side_effect = effects
        else:
            # Success case
            mock_db.upsert_franchisor.return_value = MagicMock(id=uuid4())
            mock_db.upsert_fdd.return_value = MagicMock(id=uuid4())
            mock_db.create_scrape_metadata.return_value = MagicMock()

        return mock_db

    @staticmethod
    def create_mock_drive_manager(
        should_fail: bool = False, folder_id: str = "test-folder-id"
    ) -> AsyncMock:
        """Create a mock Google Drive manager."""
        mock_drive = AsyncMock()

        if should_fail:
            mock_drive.upload_document.side_effect = Exception("Drive upload failed")
            mock_drive.get_or_create_folder.side_effect = Exception(
                "Folder creation failed"
            )
        else:
            mock_drive.upload_document.return_value = f"drive-file-{uuid4()}"
            mock_drive.get_or_create_folder.return_value = folder_id

        return mock_drive

    @staticmethod
    def assert_metrics(
        metrics: Dict[str, Any],
        expected_discovered: int,
        expected_processed: int,
        expected_downloaded: int,
        state_code: str,
    ):
        """Assert metrics are correct."""
        assert metrics["source"] == state_code
        assert metrics["documents_discovered"] == expected_discovered
        assert metrics["metadata_records_created"] == expected_processed
        assert metrics["documents_downloaded"] == expected_downloaded

        # Check calculated rates
        if expected_discovered > 0:
            assert metrics["success_rate"] == expected_processed / expected_discovered
        else:
            assert metrics["success_rate"] == 0

        if expected_processed > 0:
            assert metrics["download_rate"] == expected_downloaded / expected_processed
        else:
            assert metrics["download_rate"] == 0

        assert "duration_seconds" in metrics
        assert metrics["duration_seconds"] >= 0

    @staticmethod
    def mock_prefect_imports():
        """Mock Prefect imports to avoid server connection issues."""
        return patch.dict(
            "sys.modules",
            {
                "prefect": MagicMock(),
                "prefect.task_runners": MagicMock(),
                "prefect.deployments": MagicMock(),
                "prefect.server.schemas.schedules": MagicMock(),
            },
        )


class StateFlowTestFixtures:
    """Common fixtures for state flow tests."""

    @staticmethod
    def minnesota_documents() -> List[DocumentMetadata]:
        """Sample Minnesota documents."""
        return [
            StateFlowTestBase.create_test_document(
                franchise_name="Minnesota Test Franchise 1",
                state_code="MN",
                filing_date="2024-01-15",
                filing_number="F-2024-001",
                document_id="mn-test-1",
                additional_metadata={
                    "franchisor": "MN Test Corp 1",
                    "year": "2024",
                    "received_date": "2024-01-10",
                    "notes": "Clean FDD",
                },
            ),
            StateFlowTestBase.create_test_document(
                franchise_name="Minnesota Test Franchise 2",
                state_code="MN",
                filing_date="2024-02-20",
                filing_number="F-2024-002",
                document_id="mn-test-2",
                additional_metadata={
                    "franchisor": "MN Test Corp 2",
                    "year": "2024",
                    "received_date": "2024-02-15",
                },
            ),
        ]

    @staticmethod
    def wisconsin_documents() -> List[DocumentMetadata]:
        """Sample Wisconsin documents."""
        return [
            StateFlowTestBase.create_test_document(
                franchise_name="Wisconsin Test Franchise 1",
                state_code="WI",
                filing_date="2024-01-20",
                filing_number="WI-2024-001",
                document_id="wi-test-1",
                additional_metadata={
                    "franchisor_info": {
                        "legal_name": "WI Legal Corp 1",
                        "trade_name": "WI Trade Name 1",
                        "business_address": "123 Wisconsin Ave",
                        "filing_status": "Registered",
                    },
                    "filing_info": {"type": "Initial", "effective": "2024-01-20"},
                    "states_filed": ["WI", "IL", "MN"],
                },
            ),
            StateFlowTestBase.create_test_document(
                franchise_name="Wisconsin Test Franchise 2",
                state_code="WI",
                filing_date="2024-02-25",
                filing_number="WI-2024-002",
                document_id="wi-test-2",
                additional_metadata={
                    "franchisor_info": {
                        "legal_name": "WI Legal Corp 2",
                        "trade_name": "WI Trade Name 2",
                        "business_address": "456 Madison St",
                        "filing_status": "Registered",
                    },
                    "filing_info": {"type": "Renewal", "effective": "2024-02-25"},
                    "states_filed": ["WI"],
                },
            ),
        ]

    @staticmethod
    def create_test_state_config(
        state_code: str = "TEST", state_name: str = "Test State"
    ) -> StateConfig:
        """Create a test state configuration."""
        mock_scraper_class = MagicMock()
        mock_scraper_class.__name__ = f"{state_name.replace(' ', '')}Scraper"

        return StateConfig(
            state_code=state_code,
            state_name=state_name,
            scraper_class=mock_scraper_class,
            folder_name=f"{state_name} FDDs",
            portal_name=f"{state_code} Portal",
        )


# Common test scenarios as mixins
class StateFlowSuccessScenarios:
    """Mixin for successful flow test scenarios."""

    async def _test_successful_discovery(
        self, state_config: StateConfig, documents: List[DocumentMetadata]
    ):
        """Test successful document discovery."""
        from flows.base_state_flow import scrape_state_portal

        mock_scraper = StateFlowTestBase.create_mock_scraper(documents)

        with patch("flows.base_state_flow.create_scraper") as mock_create:
            mock_create.return_value.__aenter__.return_value = mock_scraper

            result = await scrape_state_portal(
                state_config=state_config, prefect_run_id=uuid4()
            )

            assert len(result) == len(documents)
            assert all(
                doc.additional_metadata["source"] == state_config.state_code
                for doc in result
            )
            mock_scraper.discover_documents.assert_called_once()

    async def _test_successful_processing(
        self, state_config: StateConfig, documents: List[DocumentMetadata]
    ):
        """Test successful document processing."""
        from flows.base_state_flow import process_state_documents

        mock_db = StateFlowTestBase.create_mock_database()

        with patch("flows.base_state_flow.get_database_manager") as mock_get_db:
            mock_get_db.return_value = mock_db

            result = await process_state_documents(
                documents=documents, state_config=state_config, prefect_run_id=uuid4()
            )

            assert len(result) == len(documents)
            assert mock_db.upsert_franchisor.call_count == len(documents)
            assert mock_db.upsert_fdd.call_count == len(documents)


class StateFlowFailureScenarios:
    """Mixin for failure test scenarios."""

    async def _test_discovery_failure(self, state_config: StateConfig):
        """Test document discovery failure."""
        from flows.base_state_flow import scrape_state_portal

        mock_scraper = StateFlowTestBase.create_mock_scraper([], should_fail=True)

        with patch("flows.base_state_flow.create_scraper") as mock_create:
            mock_create.return_value.__aenter__.return_value = mock_scraper

            with pytest.raises(Exception, match="Scraper failed"):
                await scrape_state_portal(
                    state_config=state_config, prefect_run_id=uuid4()
                )

    async def _test_partial_processing_failure(
        self, state_config: StateConfig, documents: List[DocumentMetadata]
    ):
        """Test partial document processing failure."""
        from flows.base_state_flow import process_state_documents

        # Fail on second document
        mock_db = StateFlowTestBase.create_mock_database(partial_failure_index=1)

        with patch("flows.base_state_flow.get_database_manager") as mock_get_db:
            mock_get_db.return_value = mock_db

            result = await process_state_documents(
                documents=documents, state_config=state_config, prefect_run_id=uuid4()
            )

            # Should process first document successfully
            assert len(result) == 1
            assert result[0].source_name == state_config.state_code
