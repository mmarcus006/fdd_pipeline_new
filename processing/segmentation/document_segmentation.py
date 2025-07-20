"""Document segmentation system for FDD Pipeline.

This module handles splitting FDD documents into individual sections,
creating section PDFs, and managing section metadata.
"""

import logging
import os
import tempfile
import time
from functools import wraps
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
from storage.google_drive import DriveManager
from models.document_models import (
    DocumentLayout,
    SectionBoundary,
    FDDSectionDetector,
)
from storage.database.manager import get_database_manager
from utils.logging import PipelineLogger

# Configure module-level logging
logger = logging.getLogger(__name__)

# Create debug logger that writes to a dedicated file
debug_handler = logging.FileHandler('document_segmentation_debug.log')
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)
debug_handler.setFormatter(debug_formatter)
logger.addHandler(debug_handler)
logger.setLevel(logging.DEBUG)

# Pipeline logger for structured logging
pipeline_logger = PipelineLogger("document_segmentation")


def timing_decorator(func):
    """Decorator to time function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        
        # Log function entry
        logger.debug(f"Entering {func_name}")
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            # Log successful completion
            logger.debug(f"Completed {func_name} in {elapsed:.3f}s")
            pipeline_logger.info(
                f"{func_name} completed",
                duration_seconds=elapsed,
                success=True
            )
            
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            
            # Log error
            logger.error(f"Failed {func_name} after {elapsed:.3f}s: {str(e)}")
            pipeline_logger.error(
                f"{func_name} failed",
                duration_seconds=elapsed,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    return wrapper


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
        logger.debug("PDFSplitter initialized")

    @timing_decorator
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
            
            logger.debug(
                f"PDF split parameters: source={source_pdf_path}, "
                f"pages={start_page}-{end_page}"
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
                        logger.debug(f"Adding page {page_num + 1} to split PDF")
                        page = pdf_reader.pages[page_num]
                        pdf_writer.add_page(page)
                        logger.debug(f"Successfully added page {page_num + 1}")
                    except Exception as e:
                        self.logger.warning(
                            "Failed to add page to split PDF",
                            page_num=page_num + 1,
                            error=str(e),
                        )
                        logger.error(f"Error adding page {page_num + 1}: {e}")
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

    @timing_decorator
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
        logger.debug("SectionMetadataManager initialized")

    @timing_decorator
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
            
            logger.debug(
                f"Section record details: id={section_id}, item={section_boundary.item_no}, "
                f"pages={section_boundary.start_page}-{section_boundary.end_page}, "
                f"quality_score={validation_result.quality_score:.2f}"
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

    def __init__(self, drive_manager=None):
        self.settings = get_settings()
        self.pdf_splitter = PDFSplitter()
        self.metadata_manager = SectionMetadataManager()
        self.drive_manager = drive_manager or DriveManager()
        self.db_manager = get_database_manager()
        self.logger = PipelineLogger("document_segmentation")
        logger.debug("DocumentSegmentationSystem initialized")

    @timing_decorator
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
                    
                    logger.debug(
                        f"Section {i+1}/{len(section_boundaries)}: "
                        f"Item {section_boundary.item_no} - {section_boundary.item_name}, "
                        f"confidence={section_boundary.confidence:.2f}"
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


# Main block for testing and demonstration
if __name__ == "__main__":
    import json
    from uuid import uuid4
    
    print("Document Segmentation System Testing")
    print("=" * 50)
    
    # Test 1: PDF Splitter functionality
    print("\n1. Testing PDF Splitter...")
    
    splitter = PDFSplitter()
    
    # Create a mock PDF for testing
    test_pdf_path = Path("test_fdd_document.pdf")
    
    try:
        # Create test PDF if PyPDF2 and reportlab are available
        from PyPDF2 import PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            c = canvas.Canvas(tmp.name, pagesize=letter)
            
            # Create a multi-page test FDD
            pages_content = [
                ("Cover Page", "Test Franchise Disclosure Document\n2025 Edition"),
                ("Table of Contents", "Item 1: The Franchisor...Page 3\nItem 2: Business Experience...Page 5"),
                ("Item 1: The Franchisor", "ABC Franchise LLC was formed in 2020..."),
                ("Item 1 continued", "Our principal business address is..."),
                ("Item 2: Business Experience", "Our key executives have the following experience..."),
                ("Item 3: Litigation", "No litigation to report."),
                ("Item 5: Initial Fees", "The initial franchise fee is $45,000..."),
                ("Item 6: Other Fees", "Royalty: 6% of gross sales...")
            ]
            
            for title, content in pages_content:
                c.drawString(100, 750, title)
                y_pos = 700
                for line in content.split('\n'):
                    c.drawString(100, y_pos, line)
                    y_pos -= 50
                c.showPage()
            
            c.save()
            
            # Copy to test location
            import shutil
            shutil.copy(tmp.name, test_pdf_path)
            Path(tmp.name).unlink()
        
        print(f"Created test PDF: {test_pdf_path} with {len(pages_content)} pages")
        
        # Test splitting pages 3-4 (Item 1)
        print("\nTesting PDF split for pages 3-4...")
        start_time = time.time()
        pdf_bytes = splitter.split_pdf_by_pages(test_pdf_path, 3, 4)
        duration = time.time() - start_time
        
        print(f"Split completed in {duration:.3f}s")
        print(f"Generated PDF size: {len(pdf_bytes)} bytes")
        
        # Validate the split PDF
        print("\nValidating split PDF...")
        validation_result = splitter.validate_pdf_content(pdf_bytes)
        
        print(f"Validation result:")
        print(f"  Valid: {validation_result.is_valid}")
        print(f"  Pages: {validation_result.page_count}")
        print(f"  Has text: {validation_result.has_text_content}")
        print(f"  Quality score: {validation_result.quality_score:.2f}")
        
    except ImportError:
        print("ReportLab not installed. Using mock data instead.")
        pdf_bytes = b"Mock PDF content"
        validation_result = SectionValidationResult(
            is_valid=True,
            page_count=2,
            file_size_bytes=len(pdf_bytes),
            has_text_content=True,
            text_sample="Item 1: The Franchisor...",
            validation_errors=[],
            quality_score=0.95
        )
    except Exception as e:
        print(f"Test setup failed: {e}")
        pdf_bytes = b""
        validation_result = None
    finally:
        if test_pdf_path.exists():
            test_pdf_path.unlink()
    
    # Test 2: Section boundaries detection
    print("\n2. Testing Section Boundary Processing...")
    
    # Create mock section boundaries
    section_boundaries = [
        SectionBoundary(
            item_no=1,
            item_name="The Franchisor and any Parents, Predecessors, and Affiliates",
            start_page=3,
            end_page=4,
            confidence=0.95
        ),
        SectionBoundary(
            item_no=2,
            item_name="Business Experience",
            start_page=5,
            end_page=5,
            confidence=0.92
        ),
        SectionBoundary(
            item_no=5,
            item_name="Initial Fees",
            start_page=7,
            end_page=7,
            confidence=0.88
        ),
        SectionBoundary(
            item_no=6,
            item_name="Other Fees",
            start_page=8,
            end_page=8,
            confidence=0.90
        )
    ]
    
    print(f"\nDetected {len(section_boundaries)} sections:")
    for sb in section_boundaries:
        page_count = sb.end_page - sb.start_page + 1
        print(f"  Item {sb.item_no}: Pages {sb.start_page}-{sb.end_page} "
              f"({page_count} page{'s' if page_count > 1 else ''}), "
              f"confidence={sb.confidence:.2f}")
    
    # Test 3: Metadata management
    print("\n3. Testing Section Metadata Management...")
    
    metadata_manager = SectionMetadataManager()
    
    # Create mock section record
    mock_fdd_id = uuid4()
    mock_section_boundary = section_boundaries[0]  # Item 1
    mock_drive_file_id = "mock_drive_file_123"
    mock_drive_path = f"processed/{mock_fdd_id}/2025/section_01.pdf"
    
    if validation_result:
        print("\nCreating section record...")
        try:
            # Note: This would normally insert into database
            # For testing, we'll just create the object
            section = FDDSection(
                id=uuid4(),
                fdd_id=mock_fdd_id,
                item_no=mock_section_boundary.item_no,
                item_name=mock_section_boundary.item_name,
                start_page=mock_section_boundary.start_page,
                end_page=mock_section_boundary.end_page,
                drive_path=mock_drive_path,
                drive_file_id=mock_drive_file_id,
                extraction_status=ExtractionStatus.PENDING,
                extraction_model=None,
                extraction_attempts=0,
                needs_review=False,
                created_at=datetime.utcnow(),
                extracted_at=None
            )
            
            print(f"Created section record:")
            print(f"  ID: {section.id}")
            print(f"  Item: {section.item_no} - {section.item_name}")
            print(f"  Pages: {section.start_page}-{section.end_page}")
            print(f"  Status: {section.extraction_status.value}")
            
        except Exception as e:
            print(f"Failed to create section record: {e}")
    
    # Test 4: Performance simulation
    print("\n4. Segmentation Performance Metrics:")
    print("-" * 30)
    
    # Simulate processing multiple sections
    processing_times = [0.234, 0.456, 0.345, 0.567, 0.432]
    section_counts = [23, 21, 25, 22, 20]
    
    for i, (proc_time, sections) in enumerate(zip(processing_times, section_counts)):
        sections_per_sec = sections / proc_time
        print(f"FDD {i+1}: {sections} sections in {proc_time:.3f}s "
              f"({sections_per_sec:.1f} sections/sec)")
    
    avg_time = sum(processing_times) / len(processing_times)
    total_sections = sum(section_counts)
    avg_sections_per_sec = total_sections / sum(processing_times)
    
    print(f"\nAverage processing time: {avg_time:.3f}s per document")
    print(f"Average speed: {avg_sections_per_sec:.1f} sections/sec")
    
    # Test 5: Progress tracking
    print("\n5. Testing Progress Tracking...")
    
    progress = SegmentationProgress(
        fdd_id=mock_fdd_id,
        total_sections=len(section_boundaries),
        completed_sections=0,
        failed_sections=0,
        start_time=datetime.utcnow(),
        status="processing"
    )
    
    print("\nSimulating section processing...")
    for i, sb in enumerate(section_boundaries):
        progress.current_section = sb.item_no
        progress.completed_sections += 1
        
        # Simulate some failures
        if i == 2:  # Fail on third section
            progress.failed_sections += 1
            progress.completed_sections -= 1
        
        completion_pct = (progress.completed_sections / progress.total_sections) * 100
        print(f"  Processing Item {sb.item_no}: {completion_pct:.0f}% complete")
        time.sleep(0.1)  # Simulate processing time
    
    progress.status = "completed" if progress.failed_sections == 0 else "partial"
    progress.estimated_completion = datetime.utcnow()
    
    print(f"\nSegmentation completed:")
    print(f"  Status: {progress.status}")
    print(f"  Completed: {progress.completed_sections}/{progress.total_sections}")
    print(f"  Failed: {progress.failed_sections}")
    print(f"  Duration: {(progress.estimated_completion - progress.start_time).total_seconds():.1f}s")
    
    print("\n" + "=" * 50)
    print("Document Segmentation testing completed!")
    print(f"Check 'document_segmentation_debug.log' for detailed debug output")


@task(name="segment_fdd_document", retries=2)
def segment_fdd_document(
    fdd_id: UUID,
    source_pdf_path: str,
    section_boundaries: List[Dict],
    use_local_drive: bool = False,
) -> Dict:
    """
    Prefect task to segment an FDD document into sections.

    Args:
        fdd_id: FDD document ID
        source_pdf_path: Path to source PDF file
        section_boundaries: List of section boundary dictionaries
        use_local_drive: If True, uses the LocalDriveManager for saving files.
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
        drive_manager = None
        if use_local_drive:
            from utils.local_drive import get_local_drive_manager

            drive_manager = get_local_drive_manager()

        segmentation_system = DocumentSegmentationSystem(drive_manager=drive_manager)

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
