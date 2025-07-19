"""Complete end-to-end FDD pipeline flow."""

import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from flows.base_state_flow import scrape_state_flow
from flows.state_configs import MINNESOTA_CONFIG, WISCONSIN_CONFIG
from flows.process_single_pdf import process_single_fdd_flow
from tasks.schema_validation import validate_fdd_sections
from utils.database import get_database_manager
from utils.logging import PipelineLogger


@task(name="process_scraped_documents")
async def process_scraped_documents(
    scrape_results: Dict[str, Any], max_documents: Optional[int] = None
) -> Dict[str, Any]:
    """Process documents from scraping results.

    Args:
        scrape_results: Results from state scraping flow
        max_documents: Optional limit on documents to process

    Returns:
        Processing results
    """
    logger = get_run_logger()
    results = {"total_processed": 0, "successful": 0, "failed": 0, "processed_fdds": []}

    if not scrape_results.get("success"):
        logger.error("Scraping failed, no documents to process")
        return results

    # Get FDD records that were created during scraping
    db_manager = get_database_manager()
    # Find FDDs created in the last run
    recent_fdds = await db_manager.get_records_by_filter(
        "fdds",
        {
            "processing_status": "pending",
            "created_at": {"$gte": scrape_results["timestamp"]},
        },
        limit=max_documents,
    )

    logger.info(f"Found {len(recent_fdds)} FDDs to process")

    for fdd in recent_fdds:
        try:
            fdd_id = fdd["id"]
            drive_path = fdd.get("drive_path", "")

            if not drive_path:
                logger.warning(f"No drive path for FDD {fdd_id}")
                results["failed"] += 1
                continue

            # Process the document
            logger.info(f"Processing FDD {fdd_id} from {drive_path}")

            # Update status to processing
            await db_manager.update_record(
                "fdds", fdd_id, {"processing_status": "processing"}
            )

            # Run document processing flow
            # Note: In production, this would fetch from Google Drive
            # For now, using local path stored in drive_file_id
            local_path = fdd.get("drive_file_id", "")
            if local_path:
                await process_single_fdd_flow.fn(local_path)
                results["successful"] += 1
                results["processed_fdds"].append(fdd_id)
            else:
                logger.error(f"No local path for FDD {fdd_id}")
                results["failed"] += 1

        except Exception as e:
            logger.error(f"Failed to process FDD {fdd.get('id')}: {e}")
            results["failed"] += 1

            # Update status to failed
            try:
                await db_manager.update_record(
                    "fdds",
                    fdd["id"],
                    {"processing_status": "failed", "processing_error": str(e)},
                )
            except:
                pass

        results["total_processed"] += 1

    return results


@task(name="validate_processed_fdds")
async def validate_processed_fdds(
    fdd_ids: List[str], prefect_run_id: UUID
) -> Dict[str, Any]:
    """Run validation on processed FDDs.

    Args:
        fdd_ids: List of FDD IDs to validate
        prefect_run_id: Prefect run ID

    Returns:
        Validation results
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        "validate_fdds", prefect_run_id=str(prefect_run_id)
    )

    results = {"total_validated": 0, "passed": 0, "failed": 0, "validation_details": {}}

    for fdd_id in fdd_ids:
        try:
            logger.info(f"Validating FDD {fdd_id}")

            # Run validation
            validation_result = await validate_fdd_sections.fn(
                UUID(fdd_id), prefect_run_id
            )

            results["total_validated"] += 1
            if validation_result.get("passed"):
                results["passed"] += 1
            else:
                results["failed"] += 1

            results["validation_details"][fdd_id] = validation_result

        except Exception as e:
            logger.error(f"Failed to validate FDD {fdd_id}: {e}")
            results["failed"] += 1
            results["validation_details"][fdd_id] = {"error": str(e), "passed": False}

    pipeline_logger.info("validation_completed", **results)

    return results


@flow(
    name="complete-fdd-pipeline",
    description="Complete end-to-end FDD processing pipeline",
    task_runner=ConcurrentTaskRunner(),
)
async def complete_fdd_pipeline(
    state: str = "WI",
    download_documents: bool = True,
    process_documents: bool = True,
    validate_documents: bool = True,
    max_documents: Optional[int] = None,
) -> Dict[str, Any]:
    """Complete FDD pipeline from scraping to validation.

    Args:
        state: State to scrape (WI or MN)
        download_documents: Whether to download documents
        process_documents: Whether to process downloaded documents
        validate_documents: Whether to validate processed documents
        max_documents: Optional limit on documents to process

    Returns:
        Pipeline execution results
    """
    logger = get_run_logger()
    prefect_run_id = uuid4()
    pipeline_logger = PipelineLogger(
        "complete_pipeline", prefect_run_id=str(prefect_run_id)
    )

    try:
        logger.info(f"Starting complete FDD pipeline for {state}")
        pipeline_logger.info(
            "pipeline_started",
            state=state,
            download_documents=download_documents,
            process_documents=process_documents,
            validate_documents=validate_documents,
            max_documents=max_documents,
        )

        # Step 1: Scrape state portal
        logger.info(f"Step 1: Scraping {state} portal...")
        if state.upper() == "WI":
            scrape_results = await scrape_state_flow(
                state_config=WISCONSIN_CONFIG,
                download_documents=download_documents,
                max_documents=max_documents,
            )
        elif state.upper() == "MN":
            scrape_results = await scrape_state_flow(
                state_config=MINNESOTA_CONFIG,
                download_documents=download_documents,
                max_documents=max_documents,
            )
        else:
            raise ValueError(f"Unsupported state: {state}")

        logger.info(f"Scraping completed: {scrape_results}")

        # Step 2: Process documents if requested
        processing_results = {}
        if process_documents and scrape_results.get("documents_downloaded", 0) > 0:
            logger.info("Step 2: Processing downloaded documents...")
            processing_results = await process_scraped_documents(
                scrape_results, max_documents
            )
            logger.info(f"Processing completed: {processing_results}")
        else:
            logger.info("Step 2: Skipping document processing")

        # Step 3: Validate documents if requested
        validation_results = {}
        if validate_documents and processing_results.get("processed_fdds"):
            logger.info("Step 3: Validating processed documents...")
            validation_results = await validate_processed_fdds(
                processing_results["processed_fdds"], prefect_run_id
            )
            logger.info(f"Validation completed: {validation_results}")
        else:
            logger.info("Step 3: Skipping validation")

        # Compile final results
        final_results = {
            "prefect_run_id": str(prefect_run_id),
            "state": state,
            "timestamp": datetime.utcnow().isoformat(),
            "success": True,
            "scraping": scrape_results,
            "processing": processing_results,
            "validation": validation_results,
            "summary": {
                "documents_discovered": scrape_results.get("documents_discovered", 0),
                "documents_downloaded": scrape_results.get("documents_downloaded", 0),
                "documents_processed": processing_results.get("successful", 0),
                "documents_validated": validation_results.get("passed", 0),
                "total_errors": (
                    processing_results.get("failed", 0)
                    + validation_results.get("failed", 0)
                ),
            },
        }

        logger.info("Complete pipeline finished successfully")
        pipeline_logger.info("pipeline_completed", **final_results["summary"])

        return final_results

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        pipeline_logger.error("pipeline_failed", error=str(e), state=state)
        return {
            "prefect_run_id": str(prefect_run_id),
            "state": state,
            "timestamp": datetime.utcnow().isoformat(),
            "success": False,
            "error": str(e),
        }


if __name__ == "__main__":
    # Test the complete pipeline
    async def main():
        result = await complete_fdd_pipeline(
            state="WI",
            download_documents=True,
            process_documents=True,
            validate_documents=True,
            max_documents=1,  # Just process one document for testing
        )
        print(f"Pipeline result: {result}")

    asyncio.run(main())
