"""Integration module for document processing with LLM extraction using Instructor."""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime

from prefect import task
import PyPDF2

from models.section import FDDSection, ExtractionStatus
from utils.logging import PipelineLogger
from tasks.llm_extraction import FDDSectionExtractor, extract_fdd_document
from tasks.document_processing import (
    process_document_layout,
    validate_section_boundaries,
    SectionBoundary,
)


@task(name="extract_section_content", retries=2)
async def extract_section_content(
    pdf_path: Path, section: SectionBoundary, primary_model: str = "gemini"
) -> Dict[str, Any]:
    """
    Extract structured content from a PDF section using LLM with Instructor.

    Args:
        pdf_path: Path to the PDF file
        section: Section boundary information
        primary_model: Primary LLM model to use

    Returns:
        Dict containing extraction results
    """
    logger = PipelineLogger("extract_section_content")

    try:
        logger.info(
            "Extracting section content",
            section_item=section.item_no,
            section_name=section.item_name,
            pages=f"{section.start_page}-{section.end_page}",
            model=primary_model,
        )

        # Extract text from the section pages
        text_content = ""
        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)

            # Extract pages for this section (convert to 0-indexed)
            for page_num in range(section.start_page - 1, section.end_page):
                if page_num < len(pdf_reader.pages):
                    page = pdf_reader.pages[page_num]
                    text_content += page.extract_text() + "\n\n"

        if not text_content.strip():
            logger.warning("No text content extracted from section")
            return {
                "status": "failed",
                "error": "No text content found",
                "section": section.dict(),
            }

        # Create FDDSection object for the extractor
        from uuid import uuid4
        fdd_section = FDDSection(
            id=uuid4(),  # Generate unique ID
            fdd_id=fdd_id,  # Use the actual FDD ID passed to the function
            item_no=section.item_no,
            item_name=section.item_name,
            start_page=section.start_page,
            end_page=section.end_page,
            extraction_status=ExtractionStatus.PROCESSING,
            created_at=datetime.utcnow(),
        )

        # Extract structured data using Instructor
        extractor = FDDSectionExtractor()
        result = await extractor.extract_section(
            section=fdd_section, content=text_content, primary_model=primary_model
        )

        logger.info(
            "Section extraction completed",
            status=result.get("status"),
            model_used=result.get("model_used"),
        )

        return result

    except Exception as e:
        logger.error(
            "Section extraction failed", error=str(e), section_item=section.item_no
        )
        return {"status": "failed", "error": str(e), "section": section.dict()}


@task(name="process_document_with_extraction", retries=1)
async def process_document_with_extraction(
    pdf_path: Path,
    fdd_id: UUID,
    primary_model: str = "gemini",
    extract_sections: List[int] = None,
) -> Dict[str, Any]:
    """
    Complete document processing pipeline: layout analysis, section detection, and content extraction.

    Args:
        pdf_path: Path to the PDF file
        fdd_id: FDD document ID
        primary_model: Primary LLM model for extraction
        extract_sections: List of section numbers to extract (None = all)

    Returns:
        Dict with layout analysis and extraction results
    """
    logger = PipelineLogger("process_document_with_extraction")

    try:
        logger.info(
            "Starting document processing with extraction",
            fdd_id=str(fdd_id),
            pdf_path=str(pdf_path),
        )

        # Step 1: Analyze document layout and detect sections
        layout, sections = await process_document_layout(str(pdf_path), fdd_id)

        # Step 2: Validate section boundaries
        validated_sections = validate_section_boundaries(sections, layout.total_pages)

        # Step 3: Filter sections for extraction
        if extract_sections:
            sections_to_extract = [
                s for s in validated_sections if s.item_no in extract_sections
            ]
        else:
            # Extract all sections with known models (5, 6, 7, 19, 20, 21)
            extractable_items = {5, 6, 7, 19, 20, 21}
            sections_to_extract = [
                s for s in validated_sections if s.item_no in extractable_items
            ]

        logger.info(
            "Sections selected for extraction",
            total_sections=len(validated_sections),
            extracting=len(sections_to_extract),
            section_numbers=[s.item_no for s in sections_to_extract],
        )

        # Step 4: Extract content from each section
        extraction_results = {}
        for section in sections_to_extract:
            result = await extract_section_content(
                pdf_path=pdf_path, section=section, primary_model=primary_model
            )
            extraction_results[f"item_{section.item_no}"] = result

        # Compile final results
        results = {
            "fdd_id": str(fdd_id),
            "layout_analysis": {
                "total_pages": layout.total_pages,
                "processing_time": layout.processing_time,
                "model_version": layout.model_version,
            },
            "sections_detected": [s.dict() for s in validated_sections],
            "extraction_results": extraction_results,
            "extraction_summary": {
                "total_sections": len(validated_sections),
                "sections_extracted": len(extraction_results),
                "successful_extractions": sum(
                    1
                    for r in extraction_results.values()
                    if r.get("status") == "success"
                ),
                "failed_extractions": sum(
                    1
                    for r in extraction_results.values()
                    if r.get("status") == "failed"
                ),
            },
        }

        logger.info(
            "Document processing with extraction completed",
            fdd_id=str(fdd_id),
            success_rate=results["extraction_summary"]["successful_extractions"]
            / max(1, results["extraction_summary"]["sections_extracted"]),
        )

        return results

    except Exception as e:
        logger.error(
            "Document processing with extraction failed",
            error=str(e),
            fdd_id=str(fdd_id),
        )
        raise


@task(name="extract_fdd_sections_batch", retries=1)
async def extract_fdd_sections_batch(
    fdd_id: UUID,
    pdf_path: Path,
    sections: List[SectionBoundary],
    content_by_section: Optional[Dict[int, str]] = None,
    primary_model: str = "gemini",
) -> Dict[str, Any]:
    """
    Extract multiple FDD sections in batch using Instructor.

    Args:
        fdd_id: FDD document ID
        pdf_path: Path to the PDF file
        sections: List of section boundaries to extract
        content_by_section: Optional pre-extracted text content by section
        primary_model: Primary model for extraction

    Returns:
        Dict with all extraction results
    """
    logger = PipelineLogger("extract_fdd_sections_batch")

    try:
        logger.info(
            "Starting batch section extraction",
            fdd_id=str(fdd_id),
            sections_count=len(sections),
        )

        # If content not provided, extract it
        if content_by_section is None:
            content_by_section = {}
            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)

                for section in sections:
                    text_content = ""
                    for page_num in range(section.start_page - 1, section.end_page):
                        if page_num < len(pdf_reader.pages):
                            page = pdf_reader.pages[page_num]
                            text_content += page.extract_text() + "\n\n"

                    if text_content.strip():
                        content_by_section[section.item_no] = text_content

        # Create FDD model
        from models.fdd import FDD

        # Get franchise_id from database or create a new one
        franchise_id = uuid4()  # In production, this should come from the actual franchise record
        
        fdd = FDD(
            id=fdd_id,
            franchise_id=franchise_id,
            issue_date=datetime.utcnow().date(),
            document_type="Initial",
            filing_state="WI",
            drive_path="/placeholder",
            drive_file_id="placeholder",
            is_amendment=False,
            created_at=datetime.utcnow(),
        )

        # Create FDDSection models
        fdd_sections = []
        for section in sections:
            if section.item_no in content_by_section:
                fdd_sections.append(
                    FDDSection(
                        id=uuid4(),  # Generate unique ID
                        fdd_id=fdd_id,
                        item_no=section.item_no,
                        item_name=section.item_name,
                        start_page=section.start_page,
                        end_page=section.end_page,
                        extraction_status=ExtractionStatus.PENDING,
                        created_at=datetime.utcnow(),
                    )
                )

        # Extract all sections
        results = await extract_fdd_document(
            fdd=fdd,
            sections=fdd_sections,
            content_by_section=content_by_section,
            primary_model=primary_model,
        )

        logger.info(
            "Batch section extraction completed",
            fdd_id=str(fdd_id),
            extracted_sections=len(results.get("sections", {})),
        )

        return results

    except Exception as e:
        logger.error(
            "Batch section extraction failed", error=str(e), fdd_id=str(fdd_id)
        )
        raise
