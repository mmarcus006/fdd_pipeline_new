"""Data storage tasks for saving extraction results to database."""

from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime
import json

from prefect import task, get_run_logger

from utils.database import get_database_manager, serialize_for_db
from utils.logging import PipelineLogger
from models.base import ExtractionStatus


@task(name="store_extraction_results", retries=2)
async def store_extraction_results(
    fdd_id: UUID,
    extraction_results: Dict[str, Any],
    prefect_run_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """Store LLM extraction results in appropriate database tables.
    
    Args:
        fdd_id: FDD document ID
        extraction_results: Dictionary of extraction results by item number
        prefect_run_id: Optional Prefect run ID for tracking
        
    Returns:
        Dictionary with storage status and statistics
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        "store_extraction_results", 
        prefect_run_id=str(prefect_run_id) if prefect_run_id else None
    )
    
    try:
        logger.info(f"Storing extraction results for FDD {fdd_id}")
        pipeline_logger.info(
            "extraction_storage_started",
            fdd_id=str(fdd_id),
            items_to_store=list(extraction_results.keys())
        )
        
        stored_items = []
        failed_items = []
        
        async with get_database_manager() as db_manager:
            for item_number, result in extraction_results.items():
                try:
                    # Determine the table based on item number
                    table_name = get_table_for_item(item_number)
                    if not table_name:
                        logger.warning(f"No table mapping for item {item_number}")
                        continue
                    
                    # Check if extraction was successful
                    if result.get("status") == "success" and result.get("data"):
                        # Prepare data for storage
                        data = result["data"]
                        if isinstance(data, dict):
                            # Add FDD reference and metadata
                            data["fdd_id"] = str(fdd_id)
                            data["created_at"] = datetime.utcnow()
                            data["updated_at"] = datetime.utcnow()
                            
                            # Serialize for database
                            serialized_data = serialize_for_db(data)
                            
                            # Store in appropriate table
                            await db_manager.batch.batch_upsert(
                                table_name,
                                [serialized_data],
                                conflict_columns=['fdd_id']  # Update if exists
                            )
                            
                            stored_items.append(item_number)
                            
                            # Update section status
                            await update_section_status(
                                db_manager,
                                fdd_id,
                                item_number,
                                ExtractionStatus.COMPLETED,
                                result.get("token_usage", {})
                            )
                        else:
                            logger.error(f"Invalid data format for item {item_number}")
                            failed_items.append(item_number)
                    else:
                        # Extraction failed
                        failed_items.append(item_number)
                        await update_section_status(
                            db_manager,
                            fdd_id,
                            item_number,
                            ExtractionStatus.FAILED,
                            error=result.get("error", "Unknown error")
                        )
                        
                except Exception as e:
                    logger.error(f"Failed to store item {item_number}: {e}")
                    failed_items.append(item_number)
                    pipeline_logger.error(
                        "item_storage_failed",
                        fdd_id=str(fdd_id),
                        item_number=item_number,
                        error=str(e)
                    )
        
        # Prepare results
        results = {
            "fdd_id": str(fdd_id),
            "stored_items": stored_items,
            "failed_items": failed_items,
            "success_count": len(stored_items),
            "failure_count": len(failed_items),
            "success": len(failed_items) == 0
        }
        
        logger.info(
            f"Extraction storage completed for FDD {fdd_id}: "
            f"{len(stored_items)} stored, {len(failed_items)} failed"
        )
        pipeline_logger.info(
            "extraction_storage_completed",
            **results
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to store extraction results: {e}")
        pipeline_logger.error(
            "extraction_storage_failed",
            fdd_id=str(fdd_id),
            error=str(e)
        )
        raise


@task(name="store_validation_results")
async def store_validation_results(
    fdd_id: UUID,
    validation_results: Dict[str, Any],
    prefect_run_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """Store validation results in the database.
    
    Args:
        fdd_id: FDD document ID
        validation_results: Validation results from schema/business rule checks
        prefect_run_id: Optional Prefect run ID
        
    Returns:
        Dictionary with storage status
    """
    logger = get_run_logger()
    
    try:
        async with get_database_manager() as db_manager:
            # Store validation results
            validation_record = {
                "id": str(UUID()),
                "fdd_id": str(fdd_id),
                "validation_type": validation_results.get("validation_type", "combined"),
                "passed": validation_results.get("passed", False),
                "total_checks": validation_results.get("total_checks", 0),
                "passed_checks": validation_results.get("passed_checks", 0),
                "failed_checks": validation_results.get("failed_checks", 0),
                "validation_details": json.dumps(validation_results.get("details", {})),
                "created_at": datetime.utcnow().isoformat()
            }
            
            await db_manager.batch.batch_insert(
                "validation_results",
                [validation_record]
            )
            
            # Store individual errors if any
            if validation_results.get("errors"):
                error_records = []
                for error in validation_results["errors"]:
                    error_records.append({
                        "id": str(UUID()),
                        "validation_result_id": validation_record["id"],
                        "fdd_id": str(fdd_id),
                        "section": error.get("section", "unknown"),
                        "field": error.get("field", ""),
                        "error_type": error.get("type", "unknown"),
                        "error_message": error.get("message", ""),
                        "severity": error.get("severity", "error"),
                        "created_at": datetime.utcnow().isoformat()
                    })
                
                if error_records:
                    await db_manager.batch.batch_insert(
                        "validation_errors",
                        error_records
                    )
            
            logger.info(f"Stored validation results for FDD {fdd_id}")
            return {
                "success": True,
                "validation_result_id": validation_record["id"],
                "errors_stored": len(validation_results.get("errors", []))
            }
            
    except Exception as e:
        logger.error(f"Failed to store validation results: {e}")
        raise


def get_table_for_item(item_number: str) -> Optional[str]:
    """Map item numbers to database tables.
    
    Args:
        item_number: FDD item number (e.g., "5", "19", "20")
        
    Returns:
        Table name or None if no mapping exists
    """
    table_mapping = {
        "5": "item5_fees",
        "6": "item6_other_fees", 
        "7": "item7_investment",
        "19": "item19_fpr",
        "20": "item20_outlets",
        "21": "item21_financials"
    }
    
    # Handle both "Item 5" and "5" formats
    item_num = str(item_number).lower().replace("item", "").strip()
    return table_mapping.get(item_num)


async def update_section_status(
    db_manager,
    fdd_id: UUID,
    item_number: str,
    status: ExtractionStatus,
    token_usage: Optional[Dict] = None,
    error: Optional[str] = None
) -> None:
    """Update the extraction status of a section.
    
    Args:
        db_manager: Database manager instance
        fdd_id: FDD document ID
        item_number: Item number
        status: New extraction status
        token_usage: Optional token usage statistics
        error: Optional error message
    """
    try:
        # Find the section record
        sections = await db_manager.get_records_by_filter(
            "fdd_sections",
            {
                "fdd_id": str(fdd_id),
                "item_no": int(item_number) if item_number.isdigit() else 0
            }
        )
        
        if sections:
            section_id = sections[0]["id"]
            
            # Prepare update data
            update_data = {
                "extraction_status": status.value,
                "extraction_attempts": sections[0].get("extraction_attempts", 0) + 1,
                "last_extraction_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if token_usage:
                update_data["extraction_metadata"] = json.dumps({
                    "token_usage": token_usage,
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            if error:
                update_data["extraction_error"] = error
                update_data["needs_review"] = True
            
            # Update section
            await db_manager.update_record(
                "fdd_sections",
                section_id,
                update_data
            )
            
    except Exception as e:
        logger = get_run_logger()
        logger.error(f"Failed to update section status: {e}")