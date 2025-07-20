"""Process single PDF workflow for FDD pipeline."""

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from storage.database.manager import get_database_manager
from processing.mineru.mineru_processing import (
    process_document_with_mineru,
    extract_sections_from_mineru,
)
from processing.document_segmentation import segment_fdd_document
from processing.extraction.llm_extraction import FDDSectionExtractor
from models.section import FDDSection, ExtractionStatus
from models.document_models import SectionBoundary
from validation.schema_validation import validate_fdd_sections
from utils.logging import PipelineLogger
from tasks.document_processing_integration import (
    extract_section_content,
    extract_fdd_sections_batch,
)


@task(name="prepare_fdd_record")
async def prepare_fdd_record(
    pdf_path: Path,
    franchise_name: Optional[str] = None,
    filing_state: Optional[str] = None,
    prefect_run_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Create or update FDD record in database.
    
    Args:
        pdf_path: Path to the PDF file
        franchise_name: Optional franchise name
        filing_state: Optional filing state
        prefect_run_id: Optional Prefect run ID for tracking
        
    Returns:
        FDD record with ID
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        "prepare_fdd_record",
        prefect_run_id=str(prefect_run_id) if prefect_run_id else None
    )
    db_manager = get_database_manager()
    
    start_time = time.time()
    
    try:
        pipeline_logger.debug(
            "preparing_fdd_record",
            pdf_path=str(pdf_path),
            franchise_name=franchise_name,
            filing_state=filing_state,
        )
        
        # Check if FDD already exists based on file path
        existing_fdds = await db_manager.get_records_by_filter(
            "fdds",
            {"drive_file_id": str(pdf_path)},
            limit=1
        )
        
        if existing_fdds:
            fdd_id = existing_fdds[0]["id"]
            logger.info(f"Found existing FDD record: {fdd_id}")
            
            pipeline_logger.info(
                "existing_fdd_found",
                fdd_id=fdd_id,
                franchise_name=existing_fdds[0].get("franchise_name"),
                processing_status=existing_fdds[0].get("processing_status"),
            )
            
            # Update processing status
            await db_manager.update_record(
                "fdds",
                fdd_id,
                {"processing_status": "processing", "updated_at": datetime.utcnow()}
            )
            
            return existing_fdds[0]
        else:
            # Create new FDD record
            # First, find or create franchise
            franchise_id = uuid4()  # In production, would look up existing franchise
            
            fdd_data = {
                "id": str(uuid4()),
                "franchise_id": str(franchise_id),
                "issue_date": datetime.utcnow().date().isoformat(),
                "document_type": "Initial",
                "filing_state": filing_state or "Unknown",
                "drive_path": str(pdf_path),
                "drive_file_id": str(pdf_path),  # Using path as placeholder ID
                "is_amendment": False,
                "processing_status": "processing",
                "created_at": datetime.utcnow(),
            }
            
            result = await db_manager.create_record("fdds", fdd_data)
            logger.info(f"Created new FDD record: {result['id']}")
            
            pipeline_logger.info(
                "new_fdd_created",
                fdd_id=result["id"],
                franchise_id=str(franchise_id),
                filing_state=filing_state or "Unknown",
                elapsed_seconds=time.time() - start_time,
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Failed to prepare FDD record: {e}")
        pipeline_logger.error(
            "fdd_preparation_failed",
            error=str(e),
            error_type=type(e).__name__,
            pdf_path=str(pdf_path),
            elapsed_seconds=time.time() - start_time,
        )
        raise


@task(name="process_pdf_with_mineru")
async def process_pdf_with_mineru(
    pdf_path: Path,
    fdd_id: str,
    franchise_name: str = "Unknown",
) -> Dict[str, Any]:
    """Process PDF with MinerU for layout analysis.
    
    Args:
        pdf_path: Path to the PDF file
        fdd_id: FDD record ID
        franchise_name: Franchise name for organization
        
    Returns:
        MinerU processing results
    """
    logger = get_run_logger()
    
    try:
        # Convert local path to file URL for MinerU
        pdf_url = f"file://{pdf_path.absolute()}"
        
        result = await process_document_with_mineru(
            pdf_url=pdf_url,
            fdd_id=UUID(fdd_id),
            franchise_name=franchise_name,
            timeout_seconds=300,
        )
        
        logger.info(f"MinerU processing completed: {result['status']}")
        return result
        
    except Exception as e:
        logger.error(f"MinerU processing failed: {e}")
        raise


@task(name="detect_fdd_sections")
async def detect_fdd_sections(
    mineru_result: Dict[str, Any],
    fdd_id: str,
) -> List[SectionBoundary]:
    """Detect FDD sections from MinerU output.
    
    Args:
        mineru_result: MinerU processing results
        fdd_id: FDD record ID
        
    Returns:
        List of detected section boundaries
    """
    logger = get_run_logger()
    
    try:
        # Extract sections from MinerU JSON
        sections = await extract_sections_from_mineru(
            mineru_json_path=mineru_result["drive_files"]["json"]["path"],
            fdd_id=UUID(fdd_id),
            total_pages=mineru_result.get("total_pages", 100),
        )
        
        logger.info(f"Detected {len(sections)} sections")
        
        # Store sections in database
        db_manager = get_database_manager()
        for section in sections:
            section_data = {
                "id": str(uuid4()),
                "fdd_id": fdd_id,
                "item_no": section.item_no,
                "item_name": section.item_name,
                "start_page": section.start_page,
                "end_page": section.end_page,
                "extraction_status": "pending",
                "created_at": datetime.utcnow(),
            }
            
            await db_manager.create_record("fdd_sections", section_data)
        
        return sections
        
    except Exception as e:
        logger.error(f"Section detection failed: {e}")
        raise


@task(name="extract_fdd_data")
async def extract_fdd_data(
    pdf_path: Path,
    sections: List[SectionBoundary],
    fdd_id: str,
    extract_items: Optional[List[int]] = None,
    primary_model: str = "gemini",
) -> Dict[str, Any]:
    """Extract structured data from FDD sections.
    
    Args:
        pdf_path: Path to the PDF file
        sections: List of section boundaries
        fdd_id: FDD record ID
        extract_items: Optional list of item numbers to extract
        primary_model: Primary LLM model to use
        
    Returns:
        Extraction results by section
    """
    logger = get_run_logger()
    
    try:
        # Filter sections for extraction
        if extract_items:
            sections_to_extract = [s for s in sections if s.item_no in extract_items]
        else:
            # Default to extracting all supported sections
            supported_items = {5, 6, 7, 19, 20, 21}
            sections_to_extract = [s for s in sections if s.item_no in supported_items]
        
        logger.info(f"Extracting data from {len(sections_to_extract)} sections")
        
        # Use batch extraction
        results = await extract_fdd_sections_batch(
            fdd_id=UUID(fdd_id),
            pdf_path=pdf_path,
            sections=sections_to_extract,
            primary_model=primary_model,
        )
        
        # Update section statuses in database
        db_manager = get_database_manager()
        for item_key, result in results.get("sections", {}).items():
            item_no = int(item_key.replace("item_", ""))
            
            # Find the section record
            section_records = await db_manager.get_records_by_filter(
                "fdd_sections",
                {"fdd_id": fdd_id, "item_no": item_no},
                limit=1
            )
            
            if section_records:
                status = "completed" if result.get("status") == "success" else "failed"
                await db_manager.update_record(
                    "fdd_sections",
                    section_records[0]["id"],
                    {
                        "extraction_status": status,
                        "model_used": result.get("model_used"),
                        "extraction_error": result.get("error"),
                        "updated_at": datetime.utcnow(),
                    }
                )
        
        return results
        
    except Exception as e:
        logger.error(f"Data extraction failed: {e}")
        raise


@task(name="store_extraction_results")
async def store_extraction_results(
    fdd_id: str,
    extraction_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Store extracted data in structured tables.
    
    Args:
        fdd_id: FDD record ID
        extraction_results: Extraction results from LLM
        
    Returns:
        Storage summary
    """
    logger = get_run_logger()
    db_manager = get_database_manager()
    
    storage_summary = {
        "stored_sections": [],
        "failed_sections": [],
        "total_records": 0,
    }
    
    try:
        for section_key, section_data in extraction_results.get("sections", {}).items():
            if section_data.get("status") != "success":
                storage_summary["failed_sections"].append(section_key)
                continue
                
            item_no = int(section_key.replace("item_", ""))
            data = section_data.get("data", {})
            
            if not data:
                logger.warning(f"No data to store for {section_key}")
                continue
            
            # Store based on item type
            if item_no == 5 and "fees" in data:
                # Store Item 5 fees
                for fee in data["fees"]:
                    fee_data = {
                        "id": str(uuid4()),
                        "fdd_id": fdd_id,
                        "fee_type": fee.get("fee_type", ""),
                        "amount_min": fee.get("amount_min", 0),
                        "amount_max": fee.get("amount_max", 0),
                        "conditions": fee.get("conditions", ""),
                        "created_at": datetime.utcnow(),
                    }
                    await db_manager.create_record("item5_fees", fee_data)
                    storage_summary["total_records"] += 1
                    
            elif item_no == 6 and "other_fees" in data:
                # Store Item 6 other fees
                for fee in data["other_fees"]:
                    fee_data = {
                        "id": str(uuid4()),
                        "fdd_id": fdd_id,
                        "fee_name": fee.get("fee_name", ""),
                        "amount_min": fee.get("amount_min", 0),
                        "amount_max": fee.get("amount_max", 0),
                        "frequency": fee.get("frequency", ""),
                        "description": fee.get("description", ""),
                        "created_at": datetime.utcnow(),
                    }
                    await db_manager.create_record("item6_other_fees", fee_data)
                    storage_summary["total_records"] += 1
                    
            elif item_no == 7 and "investments" in data:
                # Store Item 7 investments
                for investment in data["investments"]:
                    inv_data = {
                        "id": str(uuid4()),
                        "fdd_id": fdd_id,
                        "category": investment.get("category", ""),
                        "amount_low": investment.get("amount_low", 0),
                        "amount_high": investment.get("amount_high", 0),
                        "description": investment.get("description", ""),
                        "created_at": datetime.utcnow(),
                    }
                    await db_manager.create_record("item7_investment", inv_data)
                    storage_summary["total_records"] += 1
                    
            # Add handlers for items 19, 20, 21 as needed
            
            storage_summary["stored_sections"].append(section_key)
            
        logger.info(f"Stored {storage_summary['total_records']} records")
        return storage_summary
        
    except Exception as e:
        logger.error(f"Failed to store extraction results: {e}")
        raise


@flow(
    name="process-single-pdf",
    description="Process a single FDD PDF through the complete pipeline",
    task_runner=ConcurrentTaskRunner(),
)
async def process_single_fdd_flow(
    pdf_path: str,
    franchise_name: Optional[str] = None,
    filing_state: Optional[str] = None,
    extract_items: Optional[List[int]] = None,
    primary_model: str = "gemini",
    skip_validation: bool = False,
) -> Dict[str, Any]:
    """Process a single FDD PDF through the complete pipeline.
    
    Args:
        pdf_path: Path to the PDF file
        franchise_name: Optional franchise name
        filing_state: Optional filing state
        extract_items: Optional list of items to extract (default: all)
        primary_model: Primary LLM model to use
        skip_validation: Whether to skip validation step
        
    Returns:
        Processing results
    """
    logger = get_run_logger()
    prefect_run_id = uuid4()
    pipeline_logger = PipelineLogger(
        "process_single_pdf", prefect_run_id=str(prefect_run_id)
    )
    
    try:
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        logger.info(f"Starting PDF processing: {pdf_path}")
        pipeline_logger.info(
            "pdf_processing_started",
            pdf_path=str(pdf_path),
            franchise_name=franchise_name,
            filing_state=filing_state,
        )
        
        # Step 1: Prepare FDD record
        logger.info("Step 1: Preparing FDD record...")
        pipeline_logger.debug("pdf_flow_step_1_starting", step="prepare_fdd_record")
        
        fdd_record = await prepare_fdd_record(
            pdf_path_obj, franchise_name, filing_state, prefect_run_id
        )
        fdd_id = fdd_record["id"]
        
        pipeline_logger.debug(
            "pdf_flow_step_1_completed",
            step="prepare_fdd_record",
            fdd_id=fdd_id,
            is_new_record="created_at" in fdd_record,
        )
        
        # Step 2: Process with MinerU
        logger.info("Step 2: Processing with MinerU...")
        pipeline_logger.debug("pdf_flow_step_2_starting", step="mineru_processing")
        
        mineru_result = await process_pdf_with_mineru(
            pdf_path_obj, fdd_id, franchise_name or "Unknown"
        )
        
        pipeline_logger.debug(
            "pdf_flow_step_2_completed",
            step="mineru_processing",
            processing_status=mineru_result.get("status"),
            total_pages=mineru_result.get("total_pages"),
        )
        
        # Step 3: Detect sections
        logger.info("Step 3: Detecting FDD sections...")
        pipeline_logger.debug("pdf_flow_step_3_starting", step="section_detection")
        
        sections = await detect_fdd_sections(mineru_result, fdd_id)
        
        pipeline_logger.debug(
            "pdf_flow_step_3_completed",
            step="section_detection",
            sections_found=len(sections),
            section_numbers=[s.item_no for s in sections],
        )
        
        # Step 4: Extract data
        logger.info("Step 4: Extracting structured data...")
        pipeline_logger.debug(
            "pdf_flow_step_4_starting",
            step="data_extraction",
            primary_model=primary_model,
            target_items=extract_items,
        )
        
        extraction_results = await extract_fdd_data(
            pdf_path_obj, sections, fdd_id, extract_items, primary_model
        )
        
        pipeline_logger.debug(
            "pdf_flow_step_4_completed",
            step="data_extraction",
            sections_extracted=len(extraction_results.get("sections", {})),
            extraction_summary=extraction_results.get("summary", {}),
        )
        
        # Step 5: Store results
        logger.info("Step 5: Storing extraction results...")
        pipeline_logger.debug("pdf_flow_step_5_starting", step="store_results")
        
        storage_summary = await store_extraction_results(fdd_id, extraction_results)
        
        pipeline_logger.debug(
            "pdf_flow_step_5_completed",
            step="store_results",
            sections_stored=len(storage_summary["stored_sections"]),
            total_records=storage_summary["total_records"],
        )
        
        # Step 6: Validate (optional)
        validation_results = {}
        if not skip_validation:
            logger.info("Step 6: Validating extracted data...")
            pipeline_logger.debug("pdf_flow_step_6_starting", step="validation")
            
            validation_results = await validate_fdd_sections(
                UUID(fdd_id), prefect_run_id
            )
            
            pipeline_logger.debug(
                "pdf_flow_step_6_completed",
                step="validation",
                validation_passed=validation_results.get("passed", False),
                validation_errors=len(validation_results.get("errors", [])),
            )
        else:
            pipeline_logger.info("validation_skipped", reason="skip_validation=True")
        
        # Update FDD status
        db_manager = get_database_manager()
        await db_manager.update_record(
            "fdds",
            fdd_id,
            {
                "processing_status": "completed",
                "processing_completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        )
        
        # Compile results
        results = {
            "success": True,
            "fdd_id": fdd_id,
            "pdf_path": str(pdf_path),
            "franchise_name": franchise_name or fdd_record.get("franchise_name"),
            "sections_detected": len(sections),
            "sections_extracted": len(storage_summary["stored_sections"]),
            "records_stored": storage_summary["total_records"],
            "validation": validation_results,
            "mineru_output": mineru_result.get("drive_files"),
        }
        
        logger.info(f"PDF processing completed successfully: {fdd_id}")
        pipeline_logger.info("pdf_processing_completed", **results)
        
        return results
        
    except Exception as e:
        logger.error(f"PDF processing failed: {e}")
        pipeline_logger.error("pdf_processing_failed", error=str(e), pdf_path=str(pdf_path))
        
        # Update FDD status to failed
        if 'fdd_id' in locals():
            try:
                db_manager = get_database_manager()
                await db_manager.update_record(
                    "fdds",
                    fdd_id,
                    {
                        "processing_status": "failed",
                        "processing_error": str(e),
                        "updated_at": datetime.utcnow(),
                    }
                )
            except:
                pass
                
        return {
            "success": False,
            "error": str(e),
            "pdf_path": str(pdf_path),
        }


if __name__ == "__main__":
    """Demonstrate the single PDF processing flow."""
    
    import argparse
    from utils.logging import configure_logging
    
    # Configure logging for demo
    configure_logging()
    
    def demonstrate_flow_structure():
        """Show the PDF processing flow structure."""
        print("\n" + "="*80)
        print("FDD Pipeline - Single PDF Processing Flow")
        print("="*80)
        print("\nFlow Steps:")
        print("1. prepare_fdd_record() - Create/update database record")
        print("   └─> Returns: FDD record with ID")
        print("2. process_pdf_with_mineru() - Layout analysis")
        print("   └─> Returns: MinerU processing results")
        print("3. detect_fdd_sections() - Find FDD sections")
        print("   └─> Returns: List[SectionBoundary]")
        print("4. extract_fdd_data() - Extract structured data")
        print("   └─> Returns: Extraction results by section")
        print("5. store_extraction_results() - Save to database")
        print("   └─> Returns: Storage summary")
        print("6. validate_fdd_sections() - Data validation (optional)")
        print("   └─> Returns: Validation results")
        print("\nSupported FDD Sections:")
        print("  - Item 5: Initial Fees")
        print("  - Item 6: Other Fees")
        print("  - Item 7: Estimated Initial Investment")
        print("  - Item 19: Financial Performance Representations")
        print("  - Item 20: Outlets and Franchisee Information")
        print("  - Item 21: Financial Statements")
    
    def demonstrate_processing_options():
        """Show processing configuration options."""
        print("\n" + "="*80)
        print("Processing Configuration")
        print("="*80)
        print("\nFlow Parameters:")
        print("  pdf_path: Path to PDF file (required)")
        print("  franchise_name: Franchise name (optional)")
        print("  filing_state: State code (optional)")
        print("  extract_items: List of item numbers (default: all)")
        print("  primary_model: LLM model (default: gemini)")
        print("  skip_validation: Skip validation step (default: False)")
        print("\nLLM Models:")
        print("  - gemini: Google Gemini (primary)")
        print("  - openai: OpenAI GPT-4 (fallback)")
        print("  - ollama: Local models (development)")
        print("\nProcessing Features:")
        print("  - MinerU layout analysis")
        print("  - Enhanced section detection with fuzzy matching")
        print("  - Multi-model LLM extraction with fallback")
        print("  - Structured data storage")
        print("  - Comprehensive validation")
    
    async def demonstrate_dry_run(pdf_path: str = "/path/to/sample.pdf"):
        """Show what the flow would do without executing."""
        print("\n" + "="*80)
        print("PDF Processing Dry Run")
        print("="*80)
        
        pipeline_logger = PipelineLogger("demo_pdf_processing")
        
        print(f"\nPlanned Processing for: {pdf_path}")
        print("\n1. Database Preparation:")
        print("   - Check for existing FDD record")
        print("   - Create/update franchisor record")
        print("   - Set processing status")
        
        print("\n2. MinerU Processing:")
        print("   - Upload to MinerU Web API")
        print("   - Perform layout analysis")
        print("   - Extract text and structure")
        print("   - Download JSON results")
        
        print("\n3. Section Detection:")
        print("   - Search for FDD item headers")
        print("   - Apply fuzzy matching")
        print("   - Determine section boundaries")
        print("   - Store in fdd_sections table")
        
        print("\n4. Data Extraction:")
        print("   - Extract text for each section")
        print("   - Send to LLM for parsing")
        print("   - Structure according to schemas")
        print("   - Handle tables and images")
        
        print("\n5. Data Storage:")
        print("   - Store in item-specific tables")
        print("   - Maintain data lineage")
        print("   - Track extraction metadata")
        
        print("\n6. Validation:")
        print("   - Schema validation")
        print("   - Business rules checks")
        print("   - Completeness verification")
        
        # Log demo
        pipeline_logger.info(
            "pdf_processing_dry_run",
            pdf_path=pdf_path,
            steps=6,
            supported_items=[5, 6, 7, 19, 20, 21],
            demo_mode=True,
        )
    
    async def demonstrate_data_flow():
        """Show the data transformation pipeline."""
        print("\n" + "="*80)
        print("Data Transformation Pipeline")
        print("="*80)
        print("\nPDF → MinerU → Sections → LLM → Structured Data")
        print("\nExample: Item 7 (Initial Investment)")
        print("\nInput (PDF text):")
        print('  "Total Initial Investment: $150,000 - $350,000"')
        print('  "Including franchise fee, equipment, inventory..."')
        
        print("\nMinerU Output:")
        print("  {")
        print('    "page": 42,')
        print('    "type": "table",')
        print('    "content": [["Category", "Low", "High"], ...]')
        print("  }")
        
        print("\nLLM Extraction:")
        print("  {")
        print('    "investments": [')
        print('      {')
        print('        "category": "Total Investment",')
        print('        "amount_low": 150000,')
        print('        "amount_high": 350000,')
        print('        "description": "Including all costs"')
        print('      }')
        print('    ]')
        print("  }")
        
        print("\nDatabase Storage (item7_investment):")
        print("  id | fdd_id | category | amount_low | amount_high")
        print("  ---|--------|----------|------------|------------")
        print("  123| abc... | Total... | 150000     | 350000")
    
    async def main():
        """Main entry point for demonstrations."""
        parser = argparse.ArgumentParser(
            description="FDD Pipeline Single PDF Processing Demo"
        )
        parser.add_argument(
            "--demo",
            choices=["structure", "options", "dry-run", "data-flow", "all"],
            default="all",
            help="Type of demonstration to run"
        )
        parser.add_argument(
            "--pdf",
            default="/path/to/sample.pdf",
            help="PDF path for dry-run demo"
        )
        
        args = parser.parse_args()
        
        if args.demo in ["structure", "all"]:
            demonstrate_flow_structure()
        
        if args.demo in ["options", "all"]:
            demonstrate_processing_options()
        
        if args.demo in ["dry-run", "all"]:
            await demonstrate_dry_run(args.pdf)
        
        if args.demo in ["data-flow", "all"]:
            await demonstrate_data_flow()
        
        print("\n" + "="*80)
        print("To process an actual PDF:")
        print("  python main.py process-pdf --path /path/to/fdd.pdf")
        print("="*80 + "\n")
    
    # Run the demo
    asyncio.run(main())