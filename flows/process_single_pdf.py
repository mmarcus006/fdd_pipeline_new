"""Flow to process a single FDD PDF file."""

import asyncio
from pathlib import Path
from uuid import uuid4, UUID
import json
import logging
from datetime import datetime

from prefect import flow

from tasks.mineru_processing import (
    process_document_with_mineru,
    extract_sections_from_mineru,
)
from tasks.document_segmentation import segment_fdd_document
from tasks.llm_extraction import FDDSectionExtractor
from utils.database import get_database_manager, serialize_for_db
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
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

        franchisor = Franchisor(
            id=franchisor_id,
            canonical_name=franchisor_name,
            created_at=now,
            updated_at=now,
        )
        franchisor_dict = serialize_for_db(franchisor.model_dump(by_alias=True))
        print(f"Inserting franchisor: {franchisor_dict}")
        logger.info(f"Franchisor dict: {franchisor_dict}")

        await db_manager.batch.batch_upsert(
            "franchisors", [franchisor_dict], conflict_columns=["canonical_name"]
        )
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
            drive_file_id=str(pdf_file.resolve()),
        )
        fdd_dict = serialize_for_db(fdd_record.model_dump(by_alias=True))
        print(f"Inserting FDD: {fdd_dict}")

        await db_manager.batch.batch_upsert("fdds", [fdd_dict], conflict_columns=["id"])
        print("FDD record inserted successfully")

        # Step 1: Process document with MinerU
        print("About to call process_document_with_mineru...")
        try:
            # For local file, we need to convert to a URL format
            # In production, this would be a proper URL from Google Drive or Supabase
            pdf_url = f"file://{pdf_file.resolve()}"

            mineru_results = await process_document_with_mineru.fn(
                pdf_url=pdf_url,
                fdd_id=fdd_id,
                franchise_name=franchisor_name,
                timeout_seconds=300,
            )
            print(f"MinerU processing complete: {mineru_results['task_id']}")

            # Extract sections from MinerU results
            sections = await extract_sections_from_mineru.fn(
                mineru_results=mineru_results, fdd_id=fdd_id
            )
            print(f"Sections found: {len(sections)}")
        except Exception as e:
            print(f"Error in MinerU processing: {e}")
            raise

        logger.info(
            f"Successfully processed document with MinerU. Found {len(sections)} sections."
        )
        for i, section in enumerate(sections):
            logger.info(
                f"  Section {i+1}: {section.item_name} (Pages {section.start_page}-{section.end_page})"
            )

        # Step 2: Save section boundaries to database
        print("Saving section boundaries to database...")
        for section in sections:
            section_dict = serialize_for_db(section.model_dump())
            section_dict["fdd_id"] = str(fdd_id)  # Add FDD ID to section

            # Create section record in database
            section_data = {
                "id": str(uuid4()),
                "fdd_id": str(fdd_id),
                "item_no": section_dict["item_no"],
                "item_name": section_dict["item_name"],
                "start_page": section_dict["start_page"],
                "end_page": section_dict["end_page"],
                "extraction_status": "pending",
                "extraction_attempts": 0,
                "needs_review": False,
                "created_at": datetime.utcnow().isoformat(),
            }

            await db_manager.batch.batch_upsert(
                "fdd_sections", [section_data], conflict_columns=["id"]
            )
            print(f"Saved section {section.item_no}: {section.item_name}")

        print("All sections saved to database")
        logger.info("Database operations completed successfully")

        # Step 3: Extract data from sections using LLM
        print("Starting LLM extraction for sections...")
        from tasks.llm_extraction import extract_fdd_sections_batch
        from tasks.data_storage import store_extraction_results

        # Filter sections for extraction (items 5, 6, 7, 19, 20, 21)
        extractable_items = ["5", "6", "7", "19", "20", "21"]
        sections_to_extract = [
            s for s in sections if str(s.item_no) in extractable_items
        ]

        if sections_to_extract:
            logger.info(
                f"Extracting {len(sections_to_extract)} sections: {[s.item_no for s in sections_to_extract]}"
            )

            # Extract sections
            extraction_results = await extract_fdd_sections_batch.fn(
                fdd_id=fdd_id, pdf_path=str(pdf_file), sections=sections_to_extract
            )

            logger.info(
                f"Extraction completed. Results: {list(extraction_results.keys())}"
            )

            # Step 4: Store extraction results in database
            print("Storing extraction results...")
            storage_results = await store_extraction_results.fn(
                fdd_id=fdd_id,
                extraction_results=extraction_results,
                prefect_run_id=None,  # Could pass flow run ID here
            )

            logger.info(
                f"Storage completed: {storage_results['success_count']} stored, {storage_results['failure_count']} failed"
            )

            # Update FDD processing status based on results
            if storage_results["success"]:
                processing_status = ProcessingStatus.COMPLETED
            else:
                processing_status = ProcessingStatus.PARTIALLY_COMPLETED
        else:
            logger.warning("No extractable sections found")
            processing_status = ProcessingStatus.COMPLETED

        # Step 5: Update FDD processing status
        print(f"Updating FDD status to {processing_status.value}...")
        fdd_update = {
            "processing_status": processing_status.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        await db_manager.update_record("fdds", str(fdd_id), fdd_update)
        print(f"FDD status updated to {processing_status.value}")

        # TODO: Step 6: Run validation on extracted data
        # validation_results = await validate_fdd_sections.fn(fdd_id)

        logger.info("Single FDD processing flow completed.")

    except Exception as e:
        logger.error(
            f"An error occurred during the FDD processing flow: {e}", exc_info=True
        )
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
