"""Base state portal scraping flow with common functionality."""

import asyncio
import time
from datetime import datetime
from typing import List, Optional, Type, Dict, Any
from uuid import UUID, uuid4
from abc import ABC, abstractmethod

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from scrapers.base.base_scraper import BaseScraper, DocumentMetadata, create_scraper
from scrapers.base.exceptions import WebScrapingException
from models.scrape_metadata import ScrapeMetadata
from models.franchisor import Franchisor
from models.fdd import FDD, ProcessingStatus
from storage.database.manager import get_database_manager, serialize_for_db
from utils.logging import PipelineLogger


class StateConfig:
    """Configuration for a specific state's scraping flow."""

    def __init__(
        self,
        state_code: str,
        state_name: str,
        scraper_class: Type[BaseScraper],
        folder_name: str,
        portal_name: str,
    ):
        self.state_code = state_code
        self.state_name = state_name
        self.scraper_class = scraper_class
        self.folder_name = folder_name
        self.portal_name = portal_name


@task(name="scrape_state_portal", retries=3, retry_delay_seconds=60)
async def scrape_state_portal(
    state_config: StateConfig, prefect_run_id: UUID
) -> List[DocumentMetadata]:
    """Scrape a state portal for FDD documents.

    Args:
        state_config: State-specific configuration
        prefect_run_id: Prefect run ID for tracking

    Returns:
        List of discovered document metadata

    Raises:
        WebScrapingException: If scraping fails after all retries
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        f"scrape_{state_config.state_code.lower()}", prefect_run_id=str(prefect_run_id)
    )

    start_time = time.time()
    
    try:
        logger.info(
            f"Starting {state_config.state_name} {state_config.portal_name} portal scraping"
        )
        pipeline_logger.info(
            f"{state_config.state_code.lower()}_scraping_started",
            run_id=str(prefect_run_id),
            state_code=state_config.state_code,
            state_name=state_config.state_name,
            portal_name=state_config.portal_name,
            scraper_class=state_config.scraper_class.__name__,
        )
        
        # Log scraper configuration
        pipeline_logger.debug(
            "scraper_configuration",
            scraper_class=state_config.scraper_class.__name__,
            folder_name=state_config.folder_name,
            retry_attempt=0,  # Will be updated on retries
        )

        # Create and run scraper
        async with create_scraper(
            state_config.scraper_class, prefect_run_id=prefect_run_id
        ) as scraper:
            pipeline_logger.debug("scraper_created", scraper_type=type(scraper).__name__)
            documents = await scraper.scrape_portal()

        elapsed_time = time.time() - start_time
        
        logger.info(
            f"{state_config.state_name} scraping completed successfully. "
            f"Found {len(documents)} documents"
        )
        pipeline_logger.info(
            f"{state_config.state_code.lower()}_scraping_completed",
            documents_found=len(documents),
            run_id=str(prefect_run_id),
            elapsed_seconds=elapsed_time,
            documents_per_second=len(documents) / elapsed_time if elapsed_time > 0 else 0,
        )
        
        # Log sample of discovered documents for debugging
        if documents:
            pipeline_logger.debug(
                "sample_documents_discovered",
                sample_count=min(5, len(documents)),
                sample_franchises=[doc.franchise_name for doc in documents[:5]],
                total_count=len(documents),
            )

        return documents

    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"{state_config.state_name} scraping failed: {e}")
        pipeline_logger.error(
            f"{state_config.state_code.lower()}_scraping_failed",
            error=str(e),
            error_type=type(e).__name__,
            run_id=str(prefect_run_id),
            elapsed_seconds=elapsed_time,
        )
        raise WebScrapingException(
            f"{state_config.state_name} portal scraping failed: {e}"
        )


@task(name="process_state_documents", retries=2)
async def process_state_documents(
    documents: List[DocumentMetadata], state_config: StateConfig, prefect_run_id: UUID
) -> List[ScrapeMetadata]:
    """Process discovered documents and store metadata.

    Args:
        documents: List of document metadata from scraping
        state_config: State-specific configuration
        prefect_run_id: Prefect run ID for tracking

    Returns:
        List of stored scrape metadata records
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        f"process_{state_config.state_code.lower()}_docs",
        prefect_run_id=str(prefect_run_id),
    )

    start_time = time.time()
    
    try:
        logger.info(f"Processing {len(documents)} {state_config.state_name} documents")
        pipeline_logger.info(
            f"{state_config.state_code.lower()}_processing_started",
            document_count=len(documents),
            run_id=str(prefect_run_id),
            state_code=state_config.state_code,
        )

        processed_metadata = []
        skipped_count = 0
        error_count = 0

        # Get database manager
        async with get_database_manager() as db:
            pipeline_logger.debug("database_connection_established")
            
            for i, doc in enumerate(documents):
                doc_start_time = time.time()
                
                try:
                    logger.debug(
                        f"Processing document {i+1}/{len(documents)}: {doc.franchise_name}"
                    )
                    
                    pipeline_logger.debug(
                        "processing_document",
                        document_index=i+1,
                        total_documents=len(documents),
                        franchise_name=doc.franchise_name,
                        filing_number=doc.filing_number,
                        document_type=doc.document_type,
                        filing_date=str(doc.filing_date) if doc.filing_date else None,
                    )

                    # Create scrape metadata record
                    scrape_metadata = ScrapeMetadata(
                        id=uuid4(),
                        fdd_id=uuid4(),  # Will be updated when FDD record is created
                        source_name=state_config.state_code,
                        source_url=doc.source_url,
                        filing_metadata={
                            "franchise_name": doc.franchise_name,
                            "filing_date": doc.filing_date,
                            "document_type": doc.document_type,
                            "filing_number": doc.filing_number,
                            "download_url": doc.download_url,
                            "file_size": doc.file_size,
                            "additional_metadata": doc.additional_metadata,
                        },
                        prefect_run_id=prefect_run_id,
                        scraped_at=datetime.utcnow(),
                    )

                    # Store in database
                    await db.create_scrape_metadata(scrape_metadata)
                    processed_metadata.append(scrape_metadata)

                    doc_elapsed = time.time() - doc_start_time
                    
                    pipeline_logger.info(
                        f"{state_config.state_code.lower()}_document_processed",
                        franchise_name=doc.franchise_name,
                        filing_number=doc.filing_number,
                        metadata_id=str(scrape_metadata.id),
                        processing_time_seconds=doc_elapsed,
                        progress_percentage=(i+1) / len(documents) * 100,
                    )

                except Exception as e:
                    error_count += 1
                    doc_elapsed = time.time() - doc_start_time
                    
                    logger.error(
                        f"Failed to process document {doc.franchise_name}: {e}"
                    )
                    pipeline_logger.error(
                        f"{state_config.state_code.lower()}_document_processing_failed",
                        franchise_name=doc.franchise_name,
                        error=str(e),
                        error_type=type(e).__name__,
                        document_index=i+1,
                        processing_time_seconds=doc_elapsed,
                    )
                    continue

        elapsed_time = time.time() - start_time
        
        logger.info(
            f"Successfully processed {len(processed_metadata)} {state_config.state_name} documents"
        )
        pipeline_logger.info(
            f"{state_config.state_code.lower()}_processing_completed",
            processed_count=len(processed_metadata),
            total_documents=len(documents),
            error_count=error_count,
            success_rate=(len(processed_metadata) / len(documents) * 100) if documents else 0,
            run_id=str(prefect_run_id),
            elapsed_seconds=elapsed_time,
            documents_per_second=len(processed_metadata) / elapsed_time if elapsed_time > 0 else 0,
        )

        return processed_metadata

    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"{state_config.state_name} document processing failed: {e}")
        pipeline_logger.error(
            f"{state_config.state_code.lower()}_processing_failed",
            error=str(e),
            error_type=type(e).__name__,
            run_id=str(prefect_run_id),
            elapsed_seconds=elapsed_time,
        )
        raise


@task(name="download_state_documents", retries=3)
async def download_state_documents(
    metadata_list: List[ScrapeMetadata], state_config: StateConfig, prefect_run_id: UUID
) -> List[str]:
    """Download FDD documents and store in Google Drive.

    Args:
        metadata_list: List of scrape metadata records
        state_config: State-specific configuration
        prefect_run_id: Prefect run ID for tracking

    Returns:
        List of Google Drive file paths for downloaded documents
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        f"download_{state_config.state_code.lower()}_docs",
        prefect_run_id=str(prefect_run_id),
    )

    start_time = time.time()
    
    try:
        logger.info(
            f"Starting download of {len(metadata_list)} {state_config.state_name} documents"
        )
        pipeline_logger.info(
            f"{state_config.state_code.lower()}_download_started",
            document_count=len(metadata_list),
            run_id=str(prefect_run_id),
            state_code=state_config.state_code,
            folder_name=state_config.folder_name,
        )

        downloaded_files = []
        skipped_count = 0
        duplicate_count = 0
        error_count = 0
        total_bytes_downloaded = 0

        # Create scraper for downloading
        async with create_scraper(
            state_config.scraper_class, prefect_run_id=prefect_run_id
        ) as scraper:
            pipeline_logger.debug("download_scraper_created", scraper_type=type(scraper).__name__)
            
            for i, metadata in enumerate(metadata_list):
                doc_start_time = time.time()
                
                try:
                    franchise_name = metadata.filing_metadata.get(
                        "franchise_name", "unknown"
                    )
                    download_url = metadata.filing_metadata.get("download_url")
                    file_size = metadata.filing_metadata.get("file_size", 0)

                    if not download_url:
                        logger.warning(f"No download URL for {franchise_name}")
                        skipped_count += 1
                        pipeline_logger.debug(
                            "document_skipped_no_url",
                            franchise_name=franchise_name,
                            metadata_id=str(metadata.id),
                        )
                        continue

                    logger.debug(
                        f"Downloading document {i+1}/{len(metadata_list)}: {franchise_name}"
                    )
                    
                    pipeline_logger.debug(
                        "downloading_document",
                        document_index=i+1,
                        total_documents=len(metadata_list),
                        franchise_name=franchise_name,
                        download_url=download_url,
                        expected_size=file_size,
                        progress_percentage=(i / len(metadata_list) * 100),
                    )

                    # Download document content
                    content = await scraper.download_document(download_url)
                    total_bytes_downloaded += len(content)
                    
                    pipeline_logger.debug(
                        "document_downloaded",
                        franchise_name=franchise_name,
                        content_size=len(content),
                        download_time_seconds=time.time() - doc_start_time,
                    )

                    # Compute hash for deduplication
                    doc_hash = scraper.compute_document_hash(content)
                    
                    pipeline_logger.debug(
                        "document_hash_computed",
                        franchise_name=franchise_name,
                        sha256_hash=doc_hash[:16],
                    )

                    # Get database manager
                    async with get_database_manager() as db_manager:
                        # Check for duplicates in database
                        existing_fdd = await db_manager.get_records_by_filter(
                            "fdds", {"sha256_hash": doc_hash}
                        )

                        if existing_fdd:
                            duplicate_count += 1
                            logger.info(
                                f"Document already exists in database (hash: {doc_hash[:16]})"
                            )
                            pipeline_logger.info(
                                "duplicate_document_found",
                                franchise_name=franchise_name,
                                sha256_hash=doc_hash[:16],
                                existing_fdd_id=existing_fdd[0]["id"],
                                metadata_id=str(metadata.id),
                            )
                            # Update scrape metadata to point to existing FDD
                            await db_manager.update_record(
                                "scrape_metadata",
                                str(metadata.id),
                                {
                                    "fdd_id": str(existing_fdd[0]["id"]),
                                    "scrape_status": "skipped",
                                    "failure_reason": "Duplicate document",
                                },
                            )
                            continue

                        # Check if franchisor exists
                        existing_franchisor = await db_manager.get_records_by_filter(
                            "franchisors", {"canonical_name": franchise_name}
                        )

                        if existing_franchisor:
                            franchisor_id = existing_franchisor[0]["id"]
                        else:
                            # Create new franchisor
                            franchisor = Franchisor(
                                id=uuid4(),
                                canonical_name=franchise_name,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow(),
                            )
                            franchisor_dict = serialize_for_db(franchisor.model_dump())
                            await db_manager.batch.batch_upsert(
                                "franchisors",
                                [franchisor_dict],
                                conflict_columns=["canonical_name"],
                            )
                            franchisor_id = str(franchisor.id)

                        # Create FDD record
                        fdd = FDD(
                            id=metadata.fdd_id,
                            franchise_id=UUID(franchisor_id),
                            source_name=state_config.state_code,
                            processing_status=ProcessingStatus.PENDING,
                            issue_date=metadata.filing_metadata.get(
                                "filing_date", datetime.utcnow().date()
                            ),
                            document_type=metadata.filing_metadata.get(
                                "document_type", "Initial"
                            ),
                            filing_state=state_config.state_code,
                            drive_path="",  # Will be updated after upload
                            drive_file_id="",  # Will be updated after upload
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                        fdd_dict = serialize_for_db(fdd.model_dump())
                        await db_manager.batch.batch_upsert("fdds", [fdd_dict])

                    # Upload to Google Drive
                    from storage.google_drive import get_drive_manager

                    drive_manager = get_drive_manager()

                    # Create state-specific folder structure
                    root_folder_id = drive_manager.settings.gdrive_folder_id
                    state_folder_id = drive_manager.get_or_create_folder(
                        state_config.folder_name, parent_id=root_folder_id
                    )

                    # Clean franchise name for filename
                    clean_name = franchise_name.replace("/", "_").replace("\\", "_")
                    # Include UUID in filename for unique identification and tracking
                    file_name = f"{str(fdd.id)}_{clean_name}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"

                    # Upload file
                    uploaded_file_id = drive_manager.upload_file(
                        file_content=content,
                        filename=file_name,
                        parent_id=state_folder_id,
                        mime_type="application/pdf",
                    )

                    # Update FDD record with file path and hash
                    async with get_database_manager() as db_manager:
                        update_data = serialize_for_db(
                            {
                                "drive_path": f"/{state_config.folder_name}/{file_name}",
                                "drive_file_id": uploaded_file_id,
                                "sha256_hash": doc_hash,
                                "total_pages": None,  # Will be set during processing
                                "processing_status": "pending",
                                "updated_at": datetime.utcnow(),
                            }
                        )
                        await db_manager.update_record("fdds", str(fdd.id), update_data)

                        # Update scrape metadata with successful status
                        await db_manager.update_record(
                            "scrape_metadata",
                            str(metadata.id),
                            {"scrape_status": "completed", "fdd_id": str(fdd.id)},
                        )

                    doc_elapsed = time.time() - doc_start_time
                    
                    pipeline_logger.info(
                        f"{state_config.state_code.lower()}_document_downloaded",
                        franchise_name=franchise_name,
                        file_size=len(content),
                        sha256_hash=doc_hash[:16],
                        metadata_id=str(metadata.id),
                        drive_file_id=uploaded_file_id,
                        drive_path=f"/{state_config.folder_name}/{file_name}",
                        download_time_seconds=doc_elapsed,
                        download_speed_mbps=(len(content) / 1024 / 1024 / doc_elapsed) if doc_elapsed > 0 else 0,
                    )

                    downloaded_files.append(f"/{state_config.folder_name}/{file_name}")

                    # Add delay between downloads to be respectful
                    await asyncio.sleep(2.0)

                except Exception as e:
                    error_count += 1
                    doc_elapsed = time.time() - doc_start_time
                    
                    logger.error(
                        f"Failed to download document for {franchise_name}: {e}"
                    )
                    pipeline_logger.error(
                        f"{state_config.state_code.lower()}_document_download_failed",
                        franchise_name=franchise_name,
                        error=str(e),
                        error_type=type(e).__name__,
                        metadata_id=str(metadata.id),
                        document_index=i+1,
                        download_time_seconds=doc_elapsed,
                    )
                    continue

        elapsed_time = time.time() - start_time
        
        logger.info(
            f"Successfully downloaded {len(downloaded_files)} {state_config.state_name} documents"
        )
        pipeline_logger.info(
            f"{state_config.state_code.lower()}_download_completed",
            downloaded_count=len(downloaded_files),
            total_documents=len(metadata_list),
            skipped_count=skipped_count,
            duplicate_count=duplicate_count,
            error_count=error_count,
            success_rate=(len(downloaded_files) / len(metadata_list) * 100) if metadata_list else 0,
            total_bytes_downloaded=total_bytes_downloaded,
            total_mb_downloaded=total_bytes_downloaded / 1024 / 1024,
            run_id=str(prefect_run_id),
            elapsed_seconds=elapsed_time,
            average_download_speed_mbps=(total_bytes_downloaded / 1024 / 1024 / elapsed_time) if elapsed_time > 0 else 0,
        )

        return downloaded_files

    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"{state_config.state_name} document download failed: {e}")
        pipeline_logger.error(
            f"{state_config.state_code.lower()}_download_failed",
            error=str(e),
            error_type=type(e).__name__,
            run_id=str(prefect_run_id),
            elapsed_seconds=elapsed_time,
        )
        raise


@task(name="collect_state_metrics", retries=1)
async def collect_state_metrics(
    state_config: StateConfig,
    documents_discovered: int,
    metadata_records_created: int,
    documents_downloaded: int,
    prefect_run_id: UUID,
    execution_time: float,
    success: bool,
    error: Optional[str] = None,
) -> dict:
    """Collect and store metrics for state scraping workflow.

    Args:
        state_config: State-specific configuration
        documents_discovered: Number of documents found during scraping
        metadata_records_created: Number of metadata records stored
        documents_downloaded: Number of documents successfully downloaded
        prefect_run_id: Prefect run ID for tracking
        execution_time: Total execution time in seconds
        success: Whether the workflow completed successfully
        error: Error message if workflow failed

    Returns:
        Dictionary with collected metrics
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        f"{state_config.state_code.lower()}_metrics", prefect_run_id=str(prefect_run_id)
    )

    try:
        metrics = {
            "source": state_config.state_code,
            "state_name": state_config.state_name,
            "prefect_run_id": str(prefect_run_id),
            "timestamp": datetime.utcnow().isoformat(),
            "documents_discovered": documents_discovered,
            "metadata_records_created": metadata_records_created,
            "documents_downloaded": documents_downloaded,
            "execution_time_seconds": execution_time,
            "success_rate": (
                documents_downloaded / documents_discovered
                if documents_discovered > 0
                else 0
            ),
            "processing_rate": (
                metadata_records_created / documents_discovered
                if documents_discovered > 0
                else 0
            ),
            "success": success,
            "error": error,
        }

        # Log metrics for monitoring
        pipeline_logger.info(
            f"{state_config.state_code.lower()}_workflow_metrics",
            **metrics,
        )

        logger.info(f"{state_config.state_name} workflow metrics collected: {metrics}")
        return metrics

    except Exception as e:
        logger.error(f"Failed to collect {state_config.state_name} metrics: {e}")
        pipeline_logger.error(
            f"{state_config.state_code.lower()}_metrics_collection_failed",
            error=str(e),
            run_id=str(prefect_run_id),
        )
        # Return basic metrics even if collection fails
        return {
            "source": state_config.state_code,
            "state_name": state_config.state_name,
            "prefect_run_id": str(prefect_run_id),
            "timestamp": datetime.utcnow().isoformat(),
            "success": False,
            "error": f"Metrics collection failed: {e}",
        }


@flow(
    name="scrape-state-portal",
    description="Generic state portal scraping flow",
    task_runner=ConcurrentTaskRunner(),
    retries=1,
    retry_delay_seconds=300,
)
async def scrape_state_flow(
    state_config: StateConfig,
    download_documents: bool = True,
    max_documents: Optional[int] = None,
) -> dict:
    """Main flow for scraping any state franchise portal.

    Args:
        state_config: Configuration for the specific state
        download_documents: Whether to download document content
        max_documents: Optional limit on number of documents to process

    Returns:
        Dictionary with flow execution results and metrics
    """
    logger = get_run_logger()
    prefect_run_id = uuid4()
    start_time = datetime.utcnow()
    pipeline_logger = PipelineLogger(
        f"scrape_flow_{state_config.state_code.lower()}", 
        prefect_run_id=str(prefect_run_id)
    )

    try:
        logger.info(
            f"Starting {state_config.state_name} franchise portal scraping flow"
        )
        
        pipeline_logger.info(
            "flow_started",
            state_code=state_config.state_code,
            state_name=state_config.state_name,
            portal_name=state_config.portal_name,
            download_documents=download_documents,
            max_documents=max_documents,
            scraper_class=state_config.scraper_class.__name__,
        )

        # Step 1: Scrape portal for document metadata
        pipeline_logger.debug("flow_step_1_starting", step="scrape_portal")
        documents = await scrape_state_portal(state_config, prefect_run_id)
        pipeline_logger.debug(
            "flow_step_1_completed", 
            step="scrape_portal",
            documents_found=len(documents)
        )

        if max_documents and len(documents) > max_documents:
            logger.info(f"Limiting processing to {max_documents} documents")
            pipeline_logger.info(
                "document_limit_applied",
                original_count=len(documents),
                limited_count=max_documents
            )
            documents = documents[:max_documents]

        # Step 2: Process and store document metadata
        pipeline_logger.debug("flow_step_2_starting", step="process_metadata")
        metadata_list = await process_state_documents(
            documents, state_config, prefect_run_id
        )
        pipeline_logger.debug(
            "flow_step_2_completed",
            step="process_metadata",
            metadata_created=len(metadata_list)
        )

        # Step 3: Download documents if requested
        downloaded_files = []
        if download_documents and metadata_list:
            pipeline_logger.debug("flow_step_3_starting", step="download_documents")
            downloaded_files = await download_state_documents(
                metadata_list, state_config, prefect_run_id
            )
            pipeline_logger.debug(
                "flow_step_3_completed",
                step="download_documents",
                documents_downloaded=len(downloaded_files)
            )
        else:
            pipeline_logger.info("download_skipped", reason="download_documents=False or no metadata")

        # Step 4: Collect metrics
        pipeline_logger.debug("flow_step_4_starting", step="collect_metrics")
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        metrics = await collect_state_metrics(
            state_config=state_config,
            documents_discovered=len(documents),
            metadata_records_created=len(metadata_list),
            documents_downloaded=len(downloaded_files),
            prefect_run_id=prefect_run_id,
            execution_time=execution_time,
            success=True,
        )
        pipeline_logger.debug("flow_step_4_completed", step="collect_metrics")

        # Prepare results
        results = {
            "prefect_run_id": str(prefect_run_id),
            "state": state_config.state_code,
            "state_name": state_config.state_name,
            "documents_discovered": len(documents),
            "metadata_records_created": len(metadata_list),
            "documents_downloaded": len(downloaded_files),
            "execution_time_seconds": execution_time,
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
        }

        logger.info(
            f"{state_config.state_name} scraping flow completed successfully: {results}"
        )
        
        pipeline_logger.info(
            "flow_completed",
            **results
        )
        
        return results

    except Exception as e:
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"{state_config.state_name} scraping flow failed: {e}")
        
        pipeline_logger.error(
            "flow_failed",
            error=str(e),
            error_type=type(e).__name__,
            elapsed_seconds=execution_time,
            state_code=state_config.state_code,
        )

        # Collect failure metrics
        try:
            metrics = await collect_state_metrics(
                state_config=state_config,
                documents_discovered=0,
                metadata_records_created=0,
                documents_downloaded=0,
                prefect_run_id=prefect_run_id,
                execution_time=execution_time,
                success=False,
                error=str(e),
            )
        except Exception:
            metrics = {"error": "Failed to collect failure metrics"}

        return {
            "prefect_run_id": str(prefect_run_id),
            "state": state_config.state_code,
            "state_name": state_config.state_name,
            "documents_discovered": 0,
            "metadata_records_created": 0,
            "documents_downloaded": 0,
            "execution_time_seconds": execution_time,
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
        }


if __name__ == "__main__":
    """Demonstrate and test the base state flow functionality."""
    
    import argparse
    from workflows.state_configs import get_state_config, STATE_CONFIGS
    from utils.logging import configure_logging
    
    # Configure logging for demo
    configure_logging()
    
    def demonstrate_flow_structure():
        """Show the flow structure and dependencies."""
        print("\n" + "="*80)
        print("FDD Pipeline - Base State Scraping Flow")
        print("="*80)
        print("\nFlow Structure:")
        print("1. scrape_state_portal() - Discovers documents from state portal")
        print("   └─> Returns: List[DocumentMetadata]")
        print("2. process_state_documents() - Stores metadata in database")
        print("   └─> Returns: List[ScrapeMetadata]")
        print("3. download_state_documents() - Downloads PDFs to Google Drive")
        print("   └─> Returns: List[str] (file paths)")
        print("4. collect_state_metrics() - Gathers execution metrics")
        print("   └─> Returns: dict")
        print("\nSupported States:")
        for key, config in STATE_CONFIGS.items():
            if key == config.state_code.lower():  # Skip duplicates
                print(f"  - {config.state_name} ({config.state_code}): {config.portal_name} portal")
        
    def demonstrate_state_config():
        """Show state configuration details."""
        print("\n" + "="*80)
        print("State Configuration Details")
        print("="*80)
        
        for state_code in ["MN", "WI"]:
            config = get_state_config(state_code)
            print(f"\n{config.state_name} Configuration:")
            print(f"  State Code: {config.state_code}")
            print(f"  Portal Name: {config.portal_name}")
            print(f"  Scraper Class: {config.scraper_class.__name__}")
            print(f"  Google Drive Folder: {config.folder_name}")
    
    async def demonstrate_dry_run(state: str = "WI", limit: int = 5):
        """Demonstrate a dry run without actual execution."""
        print("\n" + "="*80)
        print(f"Dry Run Demo - {state} Portal Scraping")
        print("="*80)
        
        config = get_state_config(state)
        pipeline_logger = PipelineLogger(f"demo_{state.lower()}")
        
        print(f"\nConfiguration for {config.state_name}:")
        print(f"  - Scraper: {config.scraper_class.__name__}")
        print(f"  - Portal: {config.portal_name}")
        print(f"  - Drive Folder: {config.folder_name}")
        
        print("\nFlow Parameters:")
        print(f"  - download_documents: True")
        print(f"  - max_documents: {limit}")
        
        print("\nExpected Flow Execution:")
        print("1. Initialize Playwright browser")
        print(f"2. Navigate to {config.state_name} {config.portal_name} portal")
        print("3. Search for franchise documents")
        print(f"4. Extract metadata for up to {limit} documents")
        print("5. Store metadata in 'scrape_metadata' table")
        print("6. Download PDF files")
        print("7. Check for duplicates using SHA256 hash")
        print("8. Create/update franchisor records")
        print("9. Create FDD records")
        print(f"10. Upload PDFs to Google Drive/{config.folder_name}/")
        print("11. Collect and log execution metrics")
        
        # Log demo execution
        pipeline_logger.info(
            "dry_run_demo",
            state=state,
            state_config=config.state_name,
            max_documents=limit,
            demo_mode=True
        )
    
    async def main():
        """Main entry point for demonstrations."""
        parser = argparse.ArgumentParser(
            description="FDD Pipeline Base State Flow Demo"
        )
        parser.add_argument(
            "--demo",
            choices=["structure", "config", "dry-run", "all"],
            default="all",
            help="Type of demonstration to run"
        )
        parser.add_argument(
            "--state",
            choices=["MN", "WI", "mn", "wi"],
            default="WI",
            help="State to use for dry-run demo"
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Document limit for dry-run demo"
        )
        
        args = parser.parse_args()
        
        if args.demo in ["structure", "all"]:
            demonstrate_flow_structure()
        
        if args.demo in ["config", "all"]:
            demonstrate_state_config()
        
        if args.demo in ["dry-run", "all"]:
            await demonstrate_dry_run(args.state.upper(), args.limit)
        
        print("\n" + "="*80)
        print("To run actual flow, use main.py or deploy to Prefect")
        print("Example: python main.py scrape --state wisconsin --limit 10")
        print("="*80 + "\n")
    
    # Run the demo
    asyncio.run(main())
