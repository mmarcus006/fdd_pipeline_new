"""Flow to process a single FDD PDF file."""

import asyncio
from pathlib import Path
from uuid import uuid4
import json

from prefect import flow, get_run_logger

from tasks.document_processing import process_document_layout
from tasks.document_segmentation import segment_fdd_document
from tasks.llm_extraction import FDDSectionExtractor
from utils.database import get_database_manager
from utils.pdf_extractor import extract_text_from_pdf
from models.fdd import FDD, FDDStatus
from models.franchisor import Franchisor
from models.section import FDDSection


@flow(name="process-single-fdd", description="Process a single FDD PDF document.")
async def process_single_fdd_flow(pdf_path: str):
    """
    Main flow to process a single FDD PDF document.

    Args:
        pdf_path: The absolute path to the PDF file.
    """
    logger = get_run_logger()
    fdd_id = uuid4()
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        logger.error(f"PDF file not found at: {pdf_path}")
        return

    logger.info(f"Starting processing for FDD at: {pdf_path} with ID: {fdd_id}")

    db_manager = get_database_manager()

    try:
        # Step 0: Create Franchisor and FDD records in the database
        # For a real pipeline, this info would come from metadata
        franchisor_name = "Valvoline Instant Oil Change"
        franchisor_id = uuid4()

        franchisor = Franchisor(
            id=franchisor_id,
            name=franchisor_name,
        )
        await db_manager.batch.batch_upsert('franchisors', [franchisor.model_dump(by_alias=True)], conflict_columns=['name'])


        fdd_record = FDD(
            id=fdd_id,
            franchise_id=franchisor_id,
            source_name="local",
            source_url=pdf_path,
            status=FDDStatus.PROCESSING,
            issue_date="2024-01-01",
            year=2024,
        )
        await db_manager.batch.batch_upsert('fdds', [fdd_record.model_dump(by_alias=True)], conflict_columns=['franchise_id', 'year'])
        

        # Step 1: Process document layout and detect sections
        layout, sections = await process_document_layout.fn(
            pdf_path=str(pdf_file), fdd_id=fdd_id
        )

        logger.info(f"Successfully processed document layout. Found {len(sections)} sections.")
        for i, section in enumerate(sections):
            logger.info(f"  Section {i+1}: {section.item_name} (Pages {section.start_page}-{section.end_page})")

        # Step 2: Segment the document based on detected sections
        if sections:
            section_boundaries_dicts = [s.model_dump() for s in sections]
            segmentation_result = await segment_fdd_document.fn(
                fdd_id=fdd_id,
                source_pdf_path=str(pdf_file),
                section_boundaries=section_boundaries_dicts,
                use_local_drive=True,
            )
            logger.info(f"Segmentation result: {segmentation_result}")

            # Step 3: Extract structured data from each section
            if segmentation_result and segmentation_result.get("created_sections"):
                section_extractor = FDDSectionExtractor()
                extracted_data = {}

                for section_info in segmentation_result["created_sections"]:
                    item_no = section_info["item_no"]
                    section_pdf_path = section_info["drive_path"] # This is the local path
                    
                    # In a real scenario, we would load the FDDSection object
                    # from the database, but for this local flow, we'll mock it.
                    mock_section = FDDSection(
                        id=uuid4(),
                        fdd_id=fdd_id,
                        item_no=item_no,
                        item_name=section_info["item_name"],
                        drive_path=section_pdf_path,
                        start_page=section_info.get('page_range', '1-1').split('-')[0],
                        end_page=section_info.get('page_range', '1-1').split('-')[1]
                    )
                    
                    # Read the content of the segmented PDF
                    pdf_content = extract_text_from_pdf(section_pdf_path)

                    logger.info(f"Extracting data from Item {item_no}...")
                    
                    extraction_result = await section_extractor.extract_section(
                        section=mock_section,
                        content=pdf_content,
                        primary_model="ollama" # Force Ollama for local processing
                    )
                    
                    extracted_data[f"item_{item_no}"] = extraction_result
                    logger.info(f"Extraction result for Item {item_no}: {extraction_result['status']}")

                logger.info("All extractions complete.")
                logger.info(f"Final extracted data: {json.dumps(extracted_data, indent=2)}")

        # The following steps would be called here, but are not yet implemented:
        # Step 4: Validate and store the extracted data
        # validation_results = await validate_and_store_data.fn(extracted_data)

        logger.info("Single FDD processing flow completed.")

    except Exception as e:
        logger.error(f"An error occurred during the FDD processing flow: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    # This allows the flow to be run directly for testing
    # Make sure to replace the path with the actual path to your PDF
    pdf_to_process = r"C:\Users\Miller\projects\fdd_pipeline_new\examples\2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf"

    async def main():
        await process_single_fdd_flow(pdf_to_process)

    asyncio.run(main()) 