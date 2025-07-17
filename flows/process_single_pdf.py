"""Flow to process a single FDD PDF file."""

import asyncio
from pathlib import Path
from uuid import uuid4, UUID
import json
import logging
from datetime import datetime

from prefect import flow

from tasks.document_processing import process_document_layout
from tasks.document_segmentation import segment_fdd_document
from tasks.llm_extraction import FDDSectionExtractor
from utils.database import get_database_manager
from utils.pdf_extractor import extract_text_from_pdf
from models.fdd import FDD, ProcessingStatus
from models.franchisor import Franchisor
from models.section import FDDSection


@flow(name="process-single-fdd", description="Process a single FDD PDF document.")
async def process_single_fdd_flow(pdf_path: str):
    """
    Main flow to process a single FDD PDF document.

    Args:
        pdf_path: The absolute path to the PDF file.
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    fdd_id = uuid4()
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        logger.error(f"PDF file not found at: {pdf_path}")
        return

    print(f"Starting processing for FDD at: {pdf_path} with ID: {fdd_id}")
    logger.info(f"Starting processing for FDD at: {pdf_path} with ID: {fdd_id}")

    db_manager = get_database_manager()

    try:
        # Step 0: Create Franchisor and FDD records in the database
        # For a real pipeline, this info would come from metadata
        franchisor_name = "Valvoline Instant Oil Change"
        franchisor_id = uuid4()
        now = datetime.utcnow()

        # Helper function to serialize data for database
        def serialize_for_db(data: dict) -> dict:
            """Convert UUID and datetime objects to strings for JSON serialization."""
            serialized = {}
            for key, value in data.items():
                if isinstance(value, UUID):
                    serialized[key] = str(value)
                elif isinstance(value, datetime):
                    serialized[key] = value.isoformat()
                elif isinstance(value, dict):
                    serialized[key] = serialize_for_db(value)
                elif isinstance(value, list):
                    serialized[key] = [serialize_for_db(item) if isinstance(item, dict) else item for item in value]
                else:
                    serialized[key] = value
            return serialized

        franchisor = Franchisor(
            id=franchisor_id,
            canonical_name=franchisor_name,
            created_at=now,
            updated_at=now,
        )
        franchisor_dict = serialize_for_db(franchisor.model_dump(by_alias=True))
        print(f"Inserting franchisor: {franchisor_dict}")
        logger.info(f"Franchisor dict: {franchisor_dict}")
        
        await db_manager.batch.batch_upsert('franchisors', [franchisor_dict], conflict_columns=['canonical_name'])
        print("Franchisor inserted successfully")

        fdd_record = FDD(
            id=fdd_id,
            franchise_id=franchisor_id,
            source_name="local",
            source_url=pdf_path,
            processing_status=ProcessingStatus.PROCESSING,
            issue_date="2024-01-01",
            is_amendment=False,
            document_type="Initial",
            filing_state="WI",
            drive_path="/local/",
            drive_file_id=str(pdf_file.resolve())
        )
        fdd_dict = serialize_for_db(fdd_record.model_dump(by_alias=True))
        print(f"Inserting FDD: {fdd_dict}")
        
        await db_manager.batch.batch_upsert('fdds', [fdd_dict], conflict_columns=['id'])
        print("FDD record inserted successfully")
        

        # Step 1: Process document layout and detect sections
        print("About to call process_document_layout...")
        try:
            layout, sections = await process_document_layout.fn(
                pdf_path=str(pdf_file), fdd_id=fdd_id
            )
            print(f"Layout result: {layout}")
            print(f"Sections found: {len(sections)}")
        except Exception as e:
            print(f"Error in process_document_layout: {e}")
            raise

        logger.info(f"Successfully processed document layout. Found {len(sections)} sections.")
        for i, section in enumerate(sections):
            logger.info(f"  Section {i+1}: {section.item_name} (Pages {section.start_page}-{section.end_page})")

        # Step 2: Save section boundaries to database
        print("Saving section boundaries to database...")
        for section in sections:
            section_dict = serialize_for_db(section.model_dump())
            section_dict['fdd_id'] = str(fdd_id)  # Add FDD ID to section
            
            # Create section record in database
            section_data = {
                'id': str(uuid4()),
                'fdd_id': str(fdd_id),
                'item_no': section_dict['item_no'],
                'item_name': section_dict['item_name'],
                'start_page': section_dict['start_page'],
                'end_page': section_dict['end_page'],
                'extraction_status': 'pending',
                'extraction_attempts': 0,
                'needs_review': False,
                'created_at': datetime.utcnow().isoformat()
            }
            
            await db_manager.batch.batch_upsert('fdd_sections', [section_data], conflict_columns=['id'])
            print(f"Saved section {section.item_no}: {section.item_name}")
        
        print("All sections saved to database")
        logger.info("Database operations completed successfully")
        
        # Step 3: Update FDD processing status to completed
        print("Updating FDD status to completed...")
        fdd_update = {
            'processing_status': ProcessingStatus.COMPLETED.value,
            'updated_at': datetime.utcnow().isoformat()
        }
        await db_manager.update_record('fdds', str(fdd_id), fdd_update)
        print("FDD status updated to completed")

        # The following steps would be called here, but are not yet implemented:
        # Step 4: Validate and store the extracted data
        # validation_results = await validate_and_store_data.fn(extracted_data)

        logger.info("Single FDD processing flow completed.")

    except Exception as e:
        logger.error(f"An error occurred during the FDD processing flow: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    # This allows the flow to be run directly for testing
    # Use WSL path format
    pdf_to_process = "/mnt/c/Users/Miller/projects/fdd_pipeline_new/examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf"
    
    print("Starting PDF processing...")
    print(f"PDF path: {pdf_to_process}")

    async def main():
        print("Running async main...")
        await process_single_fdd_flow.fn(pdf_to_process)
        print("Completed!")

    asyncio.run(main()) 