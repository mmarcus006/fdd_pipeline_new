"""Document segmentation system for FDD Pipeline.

This module handles splitting FDD documents into individual sections,
creating section PDFs, and managing section metadata.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, BinaryIO
from uuid import UUID, uuid4
from datetime import datetime

import PyPDF2
from prefect import task
from pydantic import BaseModel, Field

from config import get_settings
from models.section import FDDSection, FDDSectionBase, ExtractionStatus
from models.fdd import FDD
from tasks.drive_operations import DriveManager
from tasks.document_processing import (
    DocumentLayout,
    SectionBoundary,
    FDDSectionDetector,
)
from utils.database import get_database_manager
from utils.logging import PipelineLogger


class SectionValidationResult(BaseModel):
    """Result of section validation checks."""

    is_valid: bool
    page_count: int
    file_size_bytes: int
    has_text_content: bool
    text_sample: Optional[str] = None
    validation_errors: List[str] = Field(default_factory=list)
    quality_score: float = Field(..., ge=0.0, le=1.0)


class SegmentationProgress(BaseModel):
    """Progress tracking for document segmentation."""

    fdd_id: UUID
    total_sections: int
    completed_sections: int
    failed_sections: int
    current_section: Optional[int] = None
    start_time: datetime
    estimated_completion: Optional[datetime] = None
    status: str = "processing"  # processing, completed, failed


class DocumentSegmentationError(Exception):
    """Custom exception for document segmentation errors."""

    pass


class PDFSplitter:
    """Handles PDF splitting operations using PyPDF2."""

    def __init__(self):
        self.logger = PipelineLogger("pdf_splitter")

    def split_pdf_by_pages(
        self, source_pdf_path: Path, start_page: int, end_page: int
    ) -> bytes:
        """
        Split PDF by page range and return as bytes.

        Args:
            source_pdf_path: Path to source PDF file
            start_page: Starting page number (1-indexed)
            end_page: Ending page number (1-indexed, inclusive)

        Returns:
            PDF content as bytes

        Raises:
            DocumentSegmentationError: If splitting fails
        """
        try:
            self.logger.info(
                "Splitting PDF by page range",
                source_pdf=str(source_pdf_path),
                start_page=start_page,
                end_page=end_page,
            )

            if not source_pdf_path.exists():
                raise DocumentSegmentationError(
                    f"Source PDF not found: {source_pdf_path}"
                )

            if start_page < 1 or end_page < start_page:
                raise DocumentSegmentationError(
                    f"Invalid page range: {start_page}-{end_page}"
                )

            with open(source_pdf_path, "rb") as source_file:
                pdf_reader = PyPDF2.PdfReader(source_file)
                total_pages = len(pdf_reader.pages)

                # Validate page range
                if start_page > total_pages:
                    raise DocumentSegmentationError(
                        f"Start page {start_page} exceeds total pages {total_pages}"
                    )

                # Adjust end page if it exceeds total pages
                actual_end_page = min(end_page, total_pages)
                if actual_end_page != end_page:
                    self.logger.warning(
                        "End page adjusted to document length",
                        requested_end=end_page,
                        actual_end=actual_end_page,
                        total_pages=total_pages,
                    )

                # Create new PDF with selected pages
                pdf_writer = PyPDF2.PdfWriter()

                # Add pages (convert to 0-indexed)
                for page_num in range(start_page - 1, actual_end_page):
                    try:
                        page = pdf_reader.pages[page_num]
                        pdf_writer.add_page(page)
                    except Exception as e:
                        self.logger.warning(
                            "Failed to add page to split PDF",
                            page_num=page_num + 1,
                            error=str(e),
                        )
                        continue

                # Write to bytes
                output_buffer = BytesIO()
                pdf_writer.write(output_buffer)
                pdf_bytes = output_buffer.getvalue()
                output_buffer.close()

                pages_extracted = actual_end_page - start_page + 1

                self.logger.info(
                    "PDF splitting completed",
                    pages_extracted=pages_extracted,
                    output_size_bytes=len(pdf_bytes),
                )

                return pdf_bytes

        except Exception as e:
            self.logger.error(
                "PDF splitting failed",
                source_pdf=str(source_pdf_path),
                start_page=start_page,
                end_page=end_page,
                error=str(e),
            )
            raise DocumentSegmentationError(f"PDF splitting failed: {e}")

    def validate_pdf_content(self, pdf_bytes: bytes) -> SectionValidationResult:
        """
        Validate PDF content and extract quality metrics.

        Args:
            pdf_bytes: PDF content as bytes

        Returns:
            Validation result with quality metrics
        """
        try:
            self.logger.debug("Validating PDF content", size_bytes=len(pdf_bytes))

            validation_errors = []

            # Basic size check
            if len(pdf_bytes) < 100:  # Minimum viable PDF size
                validation_errors.append("PDF file too small (< 100 bytes)")

            # Try to read PDF structure
            try:
                pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
                page_count = len(pdf_reader.pages)

                if page_count == 0:
                    validation_errors.append("PDF contains no pages")

                # Extract text sample from first page
                text_sample = None
                has_text_content = False

                if page_count > 0:
                    try:
                        first_page = pdf_reader.pages[0]
                        text_content = first_page.extract_text()

                        if text_content and text_content.strip():
                            has_text_content = True
                            # Get first 200 characters as sample
                            text_sample = text_content.strip()[:200]
                        else:
                            validation_errors.append("No extractable text found")

                    except Exception as e:
                        validation_errors.append(f"Text extraction failed: {e}")

            except Exception as e:
                validation_errors.append(f"PDF structure invalid: {e}")
                page_count = 0
                has_text_content = False
                text_sample = None

            # Calculate quality score
            quality_score = self._calculate_quality_score(
                len(pdf_bytes), page_count, has_text_content, len(validation_errors)
            )

            is_valid = len(validation_errors) == 0

            result = SectionValidationResult(
                is_valid=is_valid,
                page_count=page_count,
                file_size_bytes=len(pdf_bytes),
                has_text_content=has_text_content,
                text_sample=text_sample,
                validation_errors=validation_errors,
                quality_score=quality_score,
            )

            self.logger.debug(
                "PDF validation completed",
                is_valid=is_valid,
                quality_score=quality_score,
                error_count=len(validation_errors),
            )

            return result

        except Exception as e:
            self.logger.error("PDF validation failed", error=str(e))
            return SectionValidationResult(
                is_valid=False,
                page_count=0,
                file_size_bytes=len(pdf_bytes),
                has_text_content=False,
                validation_errors=[f"Validation error: {e}"],
                quality_score=0.0,
            )

    def _calculate_quality_score(
        self, file_size: int, page_count: int, has_text: bool, error_count: int
    ) -> float:
        """Calculate quality score for PDF section."""
        score = 1.0

        # Penalize for errors
        score -= error_count * 0.3

        # Penalize for very small files (likely corrupted)
        if file_size < 1000:  # Less than 1KB
            score -= 0.4
        elif file_size < 5000:  # Less than 5KB
            score -= 0.2

        # Penalize for no pages
        if page_count == 0:
            score -= 0.5

        # Penalize for no text content
        if not has_text:
            score -= 0.3

        # Ensure score is between 0 and 1
        return max(0.0, min(1.0, score))


class SectionMetadataManager:
    """Manages section metadata creation and database operations."""

    def __init__(self):
        self.db_manager = get_database_manager()
        self.logger = PipelineLogger("section_metadata")

    def create_section_record(
        self,
        fdd_id: UUID,
        section_boundary: SectionBoundary,
        drive_file_id: str,
        drive_path: str,
        validation_result: SectionValidationResult,
    ) -> FDDSection:
        """
        Create a new section record in the database.

        Args:
            fdd_id: Parent FDD document ID
            section_boundary: Section boundary information
            drive_file_id: Google Drive file ID
            drive_path: Google Drive file path
            validation_result: Validation results

        Returns:
            Created FDDSection record
        """
        try:
            section_id = uuid4()
            now = datetime.utcnow()

            # Determine if section needs review based on quality
            needs_review = (
                not validation_result.is_valid or validation_result.quality_score < 0.7
            )

            section_data = {
                "id": str(section_id),
                "fdd_id": str(fdd_id),
                "item_no": section_boundary.item_no,
                "item_name": section_boundary.item_name,
                "start_page": section_boundary.start_page,
                "end_page": section_boundary.end_page,
                "drive_path": drive_path,
                "drive_file_id": drive_file_id,
                "extraction_status": ExtractionStatus.PENDING.value,
                "extraction_model": None,
                "extraction_attempts": 0,
                "needs_review": needs_review,
                "created_at": now.isoformat(),
                "extracted_at": None,
            }

            # Insert into database
            self.db_manager.execute_batch_insert("fdd_sections", [section_data])

            self.logger.info(
                "Section record created",
                section_id=str(section_id),
                fdd_id=str(fdd_id),
                item_no=section_boundary.item_no,
                needs_review=needs_review,
            )

            # Return as Pydantic model
            return FDDSection(
                id=section_id,
                fdd_id=fdd_id,
                item_no=section_boundary.item_no,
                item_name=section_boundary.item_name,
                start_page=section_boundary.start_page,
                end_page=section_boundary.end_page,
                drive_path=drive_path,
                drive_file_id=drive_file_id,
                extraction_status=ExtractionStatus.PENDING,
                extraction_model=None,
                extraction_attempts=0,
                needs_review=needs_review,
                created_at=now,
                extracted_at=None,
            )

        except Exception as e:
            self.logger.error(
                "Failed to create section record",
                fdd_id=str(fdd_id),
                item_no=section_boundary.item_no,
                error=str(e),
            )
            raise DocumentSegmentationError(f"Section record creation failed: {e}")

    def update_section_status(
        self,
        section_id: UUID,
        status: ExtractionStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update section extraction status.

        Args:
            section_id: Section ID to update
            status: New extraction status
            error_message: Optional error message

        Returns:
            True if update successful
        """
        try:
            updates = {
                "extraction_status": status.value,
                "updated_at": datetime.utcnow().isoformat(),
            }

            if status == ExtractionStatus.FAILED and error_message:
                updates["error_message"] = error_message
                updates["needs_review"] = True

            result = self.db_manager.update_record("fdd_sections", section_id, updates)

            if result:
                self.logger.info(
                    "Section status updated",
                    section_id=str(section_id),
                    status=status.value,
                )
                return True
            else:
                self.logger.warning(
                    "Section status update returned no result",
                    section_id=str(section_id),
                )
                return False

        except Exception as e:
            self.logger.error(
                "Failed to update section status",
                section_id=str(section_id),
                status=status.value,
                error=str(e),
            )
            return False

    def get_sections_by_fdd_id(self, fdd_id: UUID) -> List[FDDSection]:
        """Get all sections for an FDD document."""
        try:
            records = self.db_manager.get_records_by_filter(
                "fdd_sections", {"fdd_id": str(fdd_id)}, order_by="item_no"
            )

            sections = []
            for record in records:
                section = FDDSection(
                    id=UUID(record["id"]),
                    fdd_id=UUID(record["fdd_id"]),
                    item_no=record["item_no"],
                    item_name=record.get("item_name"),
                    start_page=record["start_page"],
                    end_page=record["end_page"],
                    drive_path=record.get("drive_path"),
                    drive_file_id=record.get("drive_file_id"),
                    extraction_status=ExtractionStatus(record["extraction_status"]),
                    extraction_model=record.get("extraction_model"),
                    extraction_attempts=record.get("extraction_attempts", 0),
                    needs_review=record.get("needs_review", False),
                    created_at=datetime.fromisoformat(record["created_at"]),
                    extracted_at=(
                        datetime.fromisoformat(record["extracted_at"])
                        if record.get("extracted_at")
                        else None
                    ),
                )
                sections.append(section)

            return sections

        except Exception as e:
            self.logger.error(
                "Failed to get sections by FDD ID", fdd_id=str(fdd_id), error=str(e)
            )
            raise


class DocumentSegmentationSystem:
    """Main document segmentation system coordinating all operations."""

    def __init__(self):
        self.settings = get_settings()
        self.pdf_splitter = PDFSplitter()
        self.metadata_manager = SectionMetadataManager()
        self.drive_manager = DriveManager()
        self.db_manager = get_database_manager()
        self.logger = PipelineLogger("document_segmentation")

    def segment_document(
        self,
        fdd_id: UUID,
        source_pdf_path: Path,
        section_boundaries: List[SectionBoundary],
    ) -> Tuple[List[FDDSection], SegmentationProgress]:
        """
        Segment a document into individual section PDFs.

        Args:
            fdd_id: FDD document ID
            source_pdf_path: Path to source PDF file
            section_boundaries: List of detected section boundaries

        Returns:
            Tuple of (created sections, progress tracking)
        """
        start_time = datetime.utcnow()
        progress = SegmentationProgress(
            fdd_id=fdd_id,
            total_sections=len(section_boundaries),
            completed_sections=0,
            failed_sections=0,
            start_time=start_time,
            status="processing",
        )

        created_sections = []

        try:
            self.logger.info(
                "Starting document segmentation",
                fdd_id=str(fdd_id),
                source_pdf=str(source_pdf_path),
                total_sections=len(section_boundaries),
            )

            # Get FDD record for folder structure
            fdd_record = self.db_manager.get_record_by_id("fdds", fdd_id)
            if not fdd_record:
                raise DocumentSegmentationError(f"FDD record not found: {fdd_id}")

            # Create base folder path for sections
            franchise_id = fdd_record["franchise_id"]
            issue_year = datetime.fromisoformat(fdd_record["issue_date"]).year
            base_folder_path = f"processed/{franchise_id}/{issue_year}"

            # Process each section
            for i, section_boundary in enumerate(section_boundaries):
                progress.current_section = section_boundary.item_no

                try:
                    self.logger.info(
                        "Processing section",
                        section_no=section_boundary.item_no,
                        section_name=section_boundary.item_name,
                        page_range=f"{section_boundary.start_page}-{section_boundary.end_page}",
                    )

                    # Split PDF for this section
                    section_pdf_bytes = self.pdf_splitter.split_pdf_by_pages(
                        source_pdf_path,
                        section_boundary.start_page,
                        section_boundary.end_page,
                    )

                    # Validate section PDF
                    validation_result = self.pdf_splitter.validate_pdf_content(
                        section_pdf_bytes
                    )

                    # Generate filename
                    section_filename = f"section_{section_boundary.item_no:02d}.pdf"

                    # Upload to Google Drive
                    drive_file_id, drive_metadata = (
                        self.drive_manager.upload_file_with_metadata_sync(
                            file_content=section_pdf_bytes,
                            filename=section_filename,
                            folder_path=base_folder_path,
                            fdd_id=fdd_id,
                            document_type="section",
                            mime_type="application/pdf",
                        )
                    )

                    # Create section record
                    section = self.metadata_manager.create_section_record(
                        fdd_id=fdd_id,
                        section_boundary=section_boundary,
                        drive_file_id=drive_file_id,
                        drive_path=drive_metadata.drive_path,
                        validation_result=validation_result,
                    )

                    created_sections.append(section)
                    progress.completed_sections += 1

                    self.logger.info(
                        "Section processed successfully",
                        section_id=str(section.id),
                        section_no=section_boundary.item_no,
                        drive_file_id=drive_file_id,
                        quality_score=validation_result.quality_score,
                    )

                except Exception as e:
                    progress.failed_sections += 1
                    self.logger.error(
                        "Section processing failed",
                        section_no=section_boundary.item_no,
                        error=str(e),
                    )
                    # Continue with next section
                    continue

            # Update final progress
            progress.status = (
                "completed" if progress.failed_sections == 0 else "partial"
            )
            progress.estimated_completion = datetime.utcnow()

            self.logger.info(
                "Document segmentation completed",
                fdd_id=str(fdd_id),
                total_sections=progress.total_sections,
                completed_sections=progress.completed_sections,
                failed_sections=progress.failed_sections,
                processing_time_seconds=(
                    progress.estimated_completion - start_time
                ).total_seconds(),
            )

            return created_sections, progress

        except Exception as e:
            progress.status = "failed"
            progress.estimated_completion = datetime.utcnow()

            self.logger.error(
                "Document segmentation failed", fdd_id=str(fdd_id), error=str(e)
            )
            raise DocumentSegmentationError(f"Document segmentation failed: {e}")

    def get_segmentation_status(self, fdd_id: UUID) -> Optional[Dict]:
        """Get current segmentation status for an FDD."""
        try:
            sections = self.metadata_manager.get_sections_by_fdd_id(fdd_id)

            if not sections:
                return None

            total_sections = len(sections)
            completed_sections = sum(
                1 for s in sections if s.extraction_status == ExtractionStatus.SUCCESS
            )
            failed_sections = sum(
                1 for s in sections if s.extraction_status == ExtractionStatus.FAILED
            )
            pending_sections = sum(
                1 for s in sections if s.extraction_status == ExtractionStatus.PENDING
            )

            return {
                "fdd_id": str(fdd_id),
                "total_sections": total_sections,
                "completed_sections": completed_sections,
                "failed_sections": failed_sections,
                "pending_sections": pending_sections,
                "sections": [
                    {
                        "id": str(s.id),
                        "item_no": s.item_no,
                        "item_name": s.item_name,
                        "status": s.extraction_status.value,
                        "needs_review": s.needs_review,
                        "page_range": f"{s.start_page}-{s.end_page}",
                    }
                    for s in sections
                ],
            }

        except Exception as e:
            self.logger.error(
                "Failed to get segmentation status", fdd_id=str(fdd_id), error=str(e)
            )
            return None


# Import BytesIO here to avoid circular imports
from io import BytesIO


@task(name="segment_fdd_document", retries=2)
def segment_fdd_document(
    fdd_id: UUID, source_pdf_path: str, section_boundaries: List[Dict]
) -> Dict:
    """
    Prefect task to segment an FDD document into sections.

    Args:
        fdd_id: FDD document ID
        source_pdf_path: Path to source PDF file
        section_boundaries: List of section boundary dictionaries

    Returns:
        Segmentation results dictionary
    """
    logger = PipelineLogger("segment_fdd_document").bind(fdd_id=str(fdd_id))

    try:
        logger.info(
            "Starting FDD document segmentation task",
            source_pdf=source_pdf_path,
            section_count=len(section_boundaries),
        )

        # Convert dictionaries to SectionBoundary objects
        boundaries = [
            SectionBoundary(
                item_no=b["item_no"],
                item_name=b["item_name"],
                start_page=b["start_page"],
                end_page=b["end_page"],
                confidence=b.get("confidence", 0.8),
            )
            for b in section_boundaries
        ]

        # Initialize segmentation system
        segmentation_system = DocumentSegmentationSystem()

        # Perform segmentation
        created_sections, progress = segmentation_system.segment_document(
            fdd_id=fdd_id,
            source_pdf_path=Path(source_pdf_path),
            section_boundaries=boundaries,
        )

        # Prepare results
        results = {
            "fdd_id": str(fdd_id),
            "status": progress.status,
            "total_sections": progress.total_sections,
            "completed_sections": progress.completed_sections,
            "failed_sections": progress.failed_sections,
            "processing_time_seconds": (
                (progress.estimated_completion - progress.start_time).total_seconds()
                if progress.estimated_completion
                else None
            ),
            "created_sections": [
                {
                    "id": str(section.id),
                    "item_no": section.item_no,
                    "item_name": section.item_name,
                    "drive_file_id": section.drive_file_id,
                    "drive_path": section.drive_path,
                    "page_range": f"{section.start_page}-{section.end_page}",
                    "needs_review": section.needs_review,
                }
                for section in created_sections
            ],
        }

        logger.info(
            "FDD document segmentation task completed",
            status=progress.status,
            completed_sections=progress.completed_sections,
            failed_sections=progress.failed_sections,
        )

        return results

    except Exception as e:
        logger.error("FDD document segmentation task failed", error=str(e))
        raise


@task(name="validate_section_quality", retries=1)
def validate_section_quality(section_id: UUID) -> Dict:
    """
    Prefect task to validate section quality and update status.

    Args:
        section_id: Section ID to validate

    Returns:
        Validation results dictionary
    """
    logger = PipelineLogger("validate_section_quality").bind(section_id=str(section_id))

    try:
        logger.info("Starting section quality validation")

        # Get section record
        db_manager = get_database_manager()
        section_record = db_manager.get_record_by_id("fdd_sections", section_id)

        if not section_record:
            raise ValueError(f"Section not found: {section_id}")

        # Download section PDF from Google Drive
        drive_manager = DriveManager()
        pdf_bytes = drive_manager.download_file(section_record["drive_file_id"])

        # Validate PDF content
        pdf_splitter = PDFSplitter()
        validation_result = pdf_splitter.validate_pdf_content(pdf_bytes)

        # Update section status based on validation
        metadata_manager = SectionMetadataManager()

        if validation_result.is_valid and validation_result.quality_score >= 0.7:
            status = ExtractionStatus.PENDING  # Ready for extraction
        else:
            status = ExtractionStatus.FAILED
            error_msg = "; ".join(validation_result.validation_errors)
            metadata_manager.update_section_status(section_id, status, error_msg)

        results = {
            "section_id": str(section_id),
            "is_valid": validation_result.is_valid,
            "quality_score": validation_result.quality_score,
            "page_count": validation_result.page_count,
            "file_size_bytes": validation_result.file_size_bytes,
            "has_text_content": validation_result.has_text_content,
            "validation_errors": validation_result.validation_errors,
            "status": status.value,
        }

        logger.info(
            "Section quality validation completed",
            is_valid=validation_result.is_valid,
            quality_score=validation_result.quality_score,
            status=status.value,
        )

        return results

    except Exception as e:
        logger.error("Section quality validation failed", error=str(e))
        raise
