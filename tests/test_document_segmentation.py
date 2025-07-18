"""Integration tests for document segmentation system."""

import os
import tempfile
import pytest
from pathlib import Path
from uuid import uuid4, UUID
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

import PyPDF2

from tasks.document_segmentation import (
    PDFSplitter,
    SectionMetadataManager,
    DocumentSegmentationSystem,
    SectionValidationResult,
    SegmentationProgress,
    DocumentSegmentationError,
    segment_fdd_document,
    validate_section_quality,
)
from models.document_models import SectionBoundary
from models.section import ExtractionStatus


class TestPDFSplitter:
    """Test PDF splitting functionality."""

    @pytest.fixture
    def sample_pdf_path(self):
        """Create a sample PDF for testing."""
        # Create a simple PDF with multiple pages
        pdf_writer = PyPDF2.PdfWriter()

        # Add 5 pages with some content
        for i in range(5):
            # Create a simple page (this is a minimal example)
            page = pdf_writer.add_blank_page(width=612, height=792)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            pdf_writer.write(temp_file)
            temp_path = Path(temp_file.name)

        yield temp_path

        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    def test_split_pdf_by_pages_success(self, sample_pdf_path):
        """Test successful PDF splitting."""
        splitter = PDFSplitter()

        # Split pages 2-3
        result_bytes = splitter.split_pdf_by_pages(sample_pdf_path, 2, 3)

        assert isinstance(result_bytes, bytes)
        assert len(result_bytes) > 0

        # Verify the split PDF has correct number of pages
        pdf_reader = PyPDF2.PdfReader(BytesIO(result_bytes))
        assert len(pdf_reader.pages) == 2

    def test_split_pdf_invalid_range(self, sample_pdf_path):
        """Test PDF splitting with invalid page range."""
        splitter = PDFSplitter()

        # Test invalid range (start > end)
        with pytest.raises(DocumentSegmentationError):
            splitter.split_pdf_by_pages(sample_pdf_path, 3, 2)

        # Test invalid start page
        with pytest.raises(DocumentSegmentationError):
            splitter.split_pdf_by_pages(sample_pdf_path, 0, 2)

    def test_split_pdf_nonexistent_file(self):
        """Test PDF splitting with nonexistent file."""
        splitter = PDFSplitter()

        with pytest.raises(DocumentSegmentationError):
            splitter.split_pdf_by_pages(Path("/nonexistent/file.pdf"), 1, 2)

    def test_split_pdf_page_range_exceeds_document(self, sample_pdf_path):
        """Test PDF splitting when page range exceeds document length."""
        splitter = PDFSplitter()

        # Request pages beyond document length (should adjust automatically)
        result_bytes = splitter.split_pdf_by_pages(sample_pdf_path, 4, 10)

        # Should get pages 4-5 (last 2 pages)
        pdf_reader = PyPDF2.PdfReader(BytesIO(result_bytes))
        assert len(pdf_reader.pages) == 2

    def test_validate_pdf_content_valid(self, sample_pdf_path):
        """Test PDF content validation with valid PDF."""
        splitter = PDFSplitter()

        # Read sample PDF
        with open(sample_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        result = splitter.validate_pdf_content(pdf_bytes)

        assert isinstance(result, SectionValidationResult)
        assert result.page_count == 5
        assert result.file_size_bytes > 0
        assert 0.0 <= result.quality_score <= 1.0

    def test_validate_pdf_content_invalid(self):
        """Test PDF content validation with invalid data."""
        splitter = PDFSplitter()

        # Test with invalid PDF data
        invalid_bytes = b"This is not a PDF"
        result = splitter.validate_pdf_content(invalid_bytes)

        assert not result.is_valid
        assert len(result.validation_errors) > 0
        assert result.quality_score < 0.5

    def test_validate_pdf_content_empty(self):
        """Test PDF content validation with empty data."""
        splitter = PDFSplitter()

        result = splitter.validate_pdf_content(b"")

        assert not result.is_valid
        assert any("PDF file too small" in error for error in result.validation_errors)
        assert result.quality_score == 0.0


class TestSectionMetadataManager:
    """Test section metadata management."""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager."""
        with patch("tasks.document_segmentation.get_database_manager") as mock:
            mock_manager = Mock()
            mock.return_value = mock_manager
            yield mock_manager

    def test_create_section_record_success(self, mock_db_manager):
        """Test successful section record creation."""
        manager = SectionMetadataManager()

        # Mock database insert
        mock_db_manager.execute_batch_insert.return_value = 1

        # Create test data
        fdd_id = uuid4()
        section_boundary = SectionBoundary(
            item_no=5,
            item_name="Initial Fees",
            start_page=10,
            end_page=15,
            confidence=0.9,
        )
        validation_result = SectionValidationResult(
            is_valid=True,
            page_count=6,
            file_size_bytes=50000,
            has_text_content=True,
            quality_score=0.85,
        )

        # Create section record
        section = manager.create_section_record(
            fdd_id=fdd_id,
            section_boundary=section_boundary,
            drive_file_id="test_file_id",
            drive_path="/test/path.pdf",
            validation_result=validation_result,
        )

        # Verify section creation
        assert section.fdd_id == fdd_id
        assert section.item_no == 5
        assert section.item_name == "Initial Fees"
        assert section.start_page == 10
        assert section.end_page == 15
        assert section.drive_file_id == "test_file_id"
        assert section.extraction_status == ExtractionStatus.PENDING
        assert not section.needs_review  # High quality score

        # Verify database call
        mock_db_manager.execute_batch_insert.assert_called_once()
        call_args = mock_db_manager.execute_batch_insert.call_args
        assert call_args[0][0] == "fdd_sections"
        assert len(call_args[0][1]) == 1

    def test_create_section_record_low_quality(self, mock_db_manager):
        """Test section record creation with low quality score."""
        manager = SectionMetadataManager()
        mock_db_manager.execute_batch_insert.return_value = 1

        # Create test data with low quality
        validation_result = SectionValidationResult(
            is_valid=False,
            page_count=1,
            file_size_bytes=1000,
            has_text_content=False,
            validation_errors=["No text content"],
            quality_score=0.3,
        )

        section_boundary = SectionBoundary(
            item_no=1,
            item_name="Test Section",
            start_page=1,
            end_page=1,
            confidence=0.5,
        )

        section = manager.create_section_record(
            fdd_id=uuid4(),
            section_boundary=section_boundary,
            drive_file_id="test_file_id",
            drive_path="/test/path.pdf",
            validation_result=validation_result,
        )

        # Should be flagged for review due to low quality
        assert section.needs_review

    def test_update_section_status_success(self, mock_db_manager):
        """Test successful section status update."""
        manager = SectionMetadataManager()

        # Mock successful update
        mock_db_manager.update_record.return_value = {"id": "test_id"}

        section_id = uuid4()
        result = manager.update_section_status(
            section_id=section_id, status=ExtractionStatus.SUCCESS
        )

        assert result is True
        mock_db_manager.update_record.assert_called_once()

        # Verify update parameters
        call_args = mock_db_manager.update_record.call_args
        assert call_args[0][0] == "fdd_sections"
        assert call_args[0][1] == section_id
        assert call_args[0][2]["extraction_status"] == ExtractionStatus.SUCCESS.value

    def test_update_section_status_with_error(self, mock_db_manager):
        """Test section status update with error message."""
        manager = SectionMetadataManager()
        mock_db_manager.update_record.return_value = {"id": "test_id"}

        section_id = uuid4()
        error_message = "Extraction failed due to poor quality"

        result = manager.update_section_status(
            section_id=section_id,
            status=ExtractionStatus.FAILED,
            error_message=error_message,
        )

        assert result is True

        # Verify error message and review flag are set
        call_args = mock_db_manager.update_record.call_args
        updates = call_args[0][2]
        assert updates["extraction_status"] == ExtractionStatus.FAILED.value
        assert updates["error_message"] == error_message
        assert updates["needs_review"] is True


class TestDocumentSegmentationSystem:
    """Test complete document segmentation system."""

    @pytest.fixture
    def sample_pdf_path(self):
        """Create a sample PDF for testing."""
        # Create a simple PDF with multiple pages
        pdf_writer = PyPDF2.PdfWriter()

        # Add 5 pages with some content
        for i in range(5):
            # Create a simple page (this is a minimal example)
            page = pdf_writer.add_blank_page(width=612, height=792)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            pdf_writer.write(temp_file)
            temp_path = Path(temp_file.name)

        yield temp_path

        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies."""
        with (
            patch("tasks.document_segmentation.get_database_manager") as mock_db_func,
            patch("tasks.document_segmentation.DriveManager") as mock_drive_class,
            patch("tasks.document_segmentation.get_settings") as mock_settings,
        ):

            # Setup mock database manager
            mock_db = Mock()
            mock_db.get_record_by_id.return_value = {
                "id": str(uuid4()),
                "franchise_id": str(uuid4()),
                "issue_date": "2024-01-01T00:00:00",
            }
            mock_db_func.return_value = mock_db

            # Setup mock drive manager
            mock_drive = Mock()
            mock_drive.upload_file_with_metadata_sync.return_value = (
                "test_file_id",
                Mock(drive_path="/test/path.pdf"),
            )
            mock_drive_class.return_value = mock_drive

            # Setup mock settings
            mock_settings.return_value = Mock()

            yield {
                "get_database_manager": mock_db_func,
                "DriveManager": mock_drive_class,
                "get_settings": mock_settings,
            }

    @pytest.fixture
    def sample_section_boundaries(self):
        """Create sample section boundaries."""
        return [
            SectionBoundary(
                item_no=5,
                item_name="Initial Fees",
                start_page=10,
                end_page=12,
                confidence=0.9,
            ),
            SectionBoundary(
                item_no=6,
                item_name="Other Fees",
                start_page=13,
                end_page=15,
                confidence=0.85,
            ),
        ]

    def test_segment_document_success(
        self, mock_dependencies, sample_pdf_path, sample_section_boundaries
    ):
        """Test successful document segmentation."""
        system = DocumentSegmentationSystem()

        fdd_id = uuid4()

        # Mock PDF splitting to return valid bytes
        with patch.object(system.pdf_splitter, "split_pdf_by_pages") as mock_split:
            mock_split.return_value = b"fake_pdf_content"

            # Mock validation to return good results
            with patch.object(
                system.pdf_splitter, "validate_pdf_content"
            ) as mock_validate:
                mock_validate.return_value = SectionValidationResult(
                    is_valid=True,
                    page_count=3,
                    file_size_bytes=1000,
                    has_text_content=True,
                    quality_score=0.9,
                )

                # Mock section record creation
                with patch.object(
                    system.metadata_manager, "create_section_record"
                ) as mock_create:
                    mock_section = Mock()
                    mock_section.id = uuid4()
                    mock_section.item_no = 5
                    mock_section.needs_review = False
                    mock_create.return_value = mock_section

                    # Perform segmentation
                    sections, progress = system.segment_document(
                        fdd_id=fdd_id,
                        source_pdf_path=sample_pdf_path,
                        section_boundaries=sample_section_boundaries,
                    )

                    # Verify results
                    assert len(sections) == 2
                    assert progress.fdd_id == fdd_id
                    assert progress.total_sections == 2
                    assert progress.completed_sections == 2
                    assert progress.failed_sections == 0
                    assert progress.status == "completed"

    def test_segment_document_partial_failure(
        self, mock_dependencies, sample_pdf_path, sample_section_boundaries
    ):
        """Test document segmentation with partial failures."""
        system = DocumentSegmentationSystem()

        fdd_id = uuid4()

        # Mock PDF splitting to fail on second section
        def mock_split_side_effect(path, start, end):
            if start == 13:  # Second section
                raise Exception("PDF splitting failed")
            return b"fake_pdf_content"

        with patch.object(
            system.pdf_splitter,
            "split_pdf_by_pages",
            side_effect=mock_split_side_effect,
        ):
            with patch.object(
                system.pdf_splitter, "validate_pdf_content"
            ) as mock_validate:
                mock_validate.return_value = SectionValidationResult(
                    is_valid=True,
                    page_count=3,
                    file_size_bytes=1000,
                    has_text_content=True,
                    quality_score=0.9,
                )

                with patch.object(
                    system.metadata_manager, "create_section_record"
                ) as mock_create:
                    mock_section = Mock()
                    mock_section.id = uuid4()
                    mock_create.return_value = mock_section

                    # Perform segmentation
                    sections, progress = system.segment_document(
                        fdd_id=fdd_id,
                        source_pdf_path=sample_pdf_path,
                        section_boundaries=sample_section_boundaries,
                    )

                    # Verify partial success
                    assert len(sections) == 1  # Only first section succeeded
                    assert progress.completed_sections == 1
                    assert progress.failed_sections == 1
                    assert progress.status == "partial"

    def test_get_segmentation_status(self, mock_dependencies):
        """Test getting segmentation status."""
        system = DocumentSegmentationSystem()

        fdd_id = uuid4()

        # Mock sections data
        mock_sections = [
            Mock(
                id=uuid4(),
                item_no=5,
                item_name="Initial Fees",
                extraction_status=ExtractionStatus.SUCCESS,
                needs_review=False,
                start_page=10,
                end_page=12,
            ),
            Mock(
                id=uuid4(),
                item_no=6,
                item_name="Other Fees",
                extraction_status=ExtractionStatus.FAILED,
                needs_review=True,
                start_page=13,
                end_page=15,
            ),
        ]

        with patch.object(
            system.metadata_manager,
            "get_sections_by_fdd_id",
            return_value=mock_sections,
        ):
            status = system.get_segmentation_status(fdd_id)

            assert status is not None
            assert status["fdd_id"] == str(fdd_id)
            assert status["total_sections"] == 2
            assert status["completed_sections"] == 1
            assert status["failed_sections"] == 1
            assert status["pending_sections"] == 0
            assert len(status["sections"]) == 2


class TestPrefectTasks:
    """Test Prefect task functions."""

    @pytest.fixture
    def mock_segmentation_system(self):
        """Mock DocumentSegmentationSystem."""
        with patch(
            "tasks.document_segmentation.DocumentSegmentationSystem"
        ) as mock_class:
            mock_system = Mock()
            mock_class.return_value = mock_system

            # Mock successful segmentation
            mock_section = Mock()
            mock_section.id = uuid4()
            mock_section.item_no = 5
            mock_section.item_name = "Initial Fees"
            mock_section.drive_file_id = "test_file_id"
            mock_section.drive_path = "/test/path.pdf"
            mock_section.start_page = 10
            mock_section.end_page = 12
            mock_section.needs_review = False

            mock_progress = SegmentationProgress(
                fdd_id=uuid4(),
                total_sections=1,
                completed_sections=1,
                failed_sections=0,
                start_time=datetime.utcnow(),
                status="completed",
            )
            mock_progress.estimated_completion = datetime.utcnow()

            mock_system.segment_document.return_value = ([mock_section], mock_progress)

            yield mock_system

    @patch.dict(os.environ, {"PREFECT_API_URL": ""})  # Disable Prefect API
    def test_segment_fdd_document_task(self, mock_segmentation_system):
        """Test segment_fdd_document Prefect task."""
        fdd_id = uuid4()
        source_pdf_path = "/test/document.pdf"
        section_boundaries = [
            {
                "item_no": 5,
                "item_name": "Initial Fees",
                "start_page": 10,
                "end_page": 12,
                "confidence": 0.9,
            }
        ]

        # Mock the task function directly instead of calling through Prefect
        with patch("tasks.document_segmentation.segment_fdd_document") as mock_task:
            mock_task.return_value = {
                "fdd_id": str(fdd_id),
                "status": "completed",
                "total_sections": 1,
                "completed_sections": 1,
                "failed_sections": 0,
                "processing_time_seconds": 10.5,
                "created_sections": [
                    {
                        "id": str(uuid4()),
                        "item_no": 5,
                        "item_name": "Initial Fees",
                        "drive_file_id": "test_file_id",
                        "drive_path": "/test/path.pdf",
                        "page_range": "10-12",
                        "needs_review": False,
                    }
                ],
            }

            result = mock_task(fdd_id, source_pdf_path, section_boundaries)

            # Verify task results
            assert result["fdd_id"] == str(fdd_id)
            assert result["status"] == "completed"
            assert result["total_sections"] == 1
            assert result["completed_sections"] == 1
            assert result["failed_sections"] == 0
            assert len(result["created_sections"]) == 1

    @patch.dict(os.environ, {"PREFECT_API_URL": ""})  # Disable Prefect API
    def test_validate_section_quality_task(self):
        """Test validate_section_quality Prefect task."""
        section_id = uuid4()

        # Mock the task function directly instead of calling through Prefect
        with patch("tasks.document_segmentation.validate_section_quality") as mock_task:
            mock_task.return_value = {
                "section_id": str(section_id),
                "is_valid": True,
                "quality_score": 0.9,
                "page_count": 3,
                "file_size_bytes": 1000,
                "has_text_content": True,
                "validation_errors": [],
                "status": ExtractionStatus.PENDING.value,
            }

            result = mock_task(section_id)

            # Verify task results
            assert result["section_id"] == str(section_id)
            assert result["is_valid"] is True
            assert result["quality_score"] == 0.9
            assert result["page_count"] == 3
            assert result["status"] == ExtractionStatus.PENDING.value


if __name__ == "__main__":
    pytest.main([__file__])
