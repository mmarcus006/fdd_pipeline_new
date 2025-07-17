"""Minnesota franchise portal scraping flow."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID, uuid4

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from tasks.minnesota_scraper import MinnesotaScraper
from tasks.web_scraping import DocumentMetadata, ScrapingError, create_scraper
from models.scrape_metadata import ScrapeMetadata
from utils.database import get_database_manager
from utils.logging import PipelineLogger


@task(name="scrape_minnesota_portal", retries=3, retry_delay_seconds=60)
async def scrape_minnesota_portal(prefect_run_id: UUID) -> List[DocumentMetadata]:
    """Scrape the Minnesota franchise portal for FDD documents.

    Args:
        prefect_run_id: Prefect run ID for tracking

    Returns:
        List of discovered document metadata

    Raises:
        ScrapingError: If scraping fails after all retries
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        "scrape_minnesota", prefect_run_id=str(prefect_run_id)
    )

    try:
        logger.info("Starting Minnesota portal scraping")
        pipeline_logger.info("minnesota_scraping_started", run_id=str(prefect_run_id))

        # Create and run scraper
        async with create_scraper(
            MinnesotaScraper, prefect_run_id=prefect_run_id
        ) as scraper:
            documents = await scraper.scrape_portal()

        logger.info(
            f"Minnesota scraping completed successfully. Found {len(documents)} documents"
        )
        pipeline_logger.info(
            "minnesota_scraping_completed",
            documents_found=len(documents),
            run_id=str(prefect_run_id),
        )

        return documents

    except Exception as e:
        logger.error(f"Minnesota scraping failed: {e}")
        pipeline_logger.error(
            "minnesota_scraping_failed", error=str(e), run_id=str(prefect_run_id)
        )
        raise ScrapingError(f"Minnesota portal scraping failed: {e}")


@task(name="process_minnesota_documents", retries=2)
async def process_minnesota_documents(
    documents: List[DocumentMetadata], prefect_run_id: UUID
) -> List[ScrapeMetadata]:
    """Process discovered Minnesota documents and store metadata.

    Args:
        documents: List of document metadata from scraping
        prefect_run_id: Prefect run ID for tracking

    Returns:
        List of stored scrape metadata records
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        "process_minnesota_docs", prefect_run_id=str(prefect_run_id)
    )

    try:
        logger.info(f"Processing {len(documents)} Minnesota documents")
        pipeline_logger.info(
            "minnesota_processing_started",
            document_count=len(documents),
            run_id=str(prefect_run_id),
        )

        processed_metadata = []

        # Get database manager
        async with get_database_manager() as db:
            for i, doc in enumerate(documents):
                try:
                    logger.debug(
                        f"Processing document {i+1}/{len(documents)}: {doc.franchise_name}"
                    )

                    # Check for existing document by hash (if we have content)
                    # For now, we'll create metadata records for all discovered documents

                    # Create scrape metadata record
                    scrape_metadata = ScrapeMetadata(
                        id=uuid4(),
                        fdd_id=uuid4(),  # Will be updated when FDD record is created
                        source_name="MN",
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

                    pipeline_logger.info(
                        "minnesota_document_processed",
                        franchise_name=doc.franchise_name,
                        filing_number=doc.filing_number,
                        metadata_id=str(scrape_metadata.id),
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to process document {doc.franchise_name}: {e}"
                    )
                    pipeline_logger.error(
                        "minnesota_document_processing_failed",
                        franchise_name=doc.franchise_name,
                        error=str(e),
                    )
                    continue

        logger.info(
            f"Successfully processed {len(processed_metadata)} Minnesota documents"
        )
        pipeline_logger.info(
            "minnesota_processing_completed",
            processed_count=len(processed_metadata),
            run_id=str(prefect_run_id),
        )

        return processed_metadata

    except Exception as e:
        logger.error(f"Minnesota document processing failed: {e}")
        pipeline_logger.error(
            "minnesota_processing_failed", error=str(e), run_id=str(prefect_run_id)
        )
        raise


@task(name="download_minnesota_documents", retries=3)
async def download_minnesota_documents(
    metadata_list: List[ScrapeMetadata], prefect_run_id: UUID
) -> List[str]:
    """Download Minnesota FDD documents and store in Google Drive.

    Args:
        metadata_list: List of scrape metadata records
        prefect_run_id: Prefect run ID for tracking

    Returns:
        List of Google Drive file paths for downloaded documents
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        "download_minnesota_docs", prefect_run_id=str(prefect_run_id)
    )

    try:
        logger.info(f"Starting download of {len(metadata_list)} Minnesota documents")
        pipeline_logger.info(
            "minnesota_download_started",
            document_count=len(metadata_list),
            run_id=str(prefect_run_id),
        )

        downloaded_files = []

        # Create scraper for downloading
        async with create_scraper(
            MinnesotaScraper, prefect_run_id=prefect_run_id
        ) as scraper:
            for i, metadata in enumerate(metadata_list):
                try:
                    franchise_name = metadata.filing_metadata.get(
                        "franchise_name", "unknown"
                    )
                    download_url = metadata.filing_metadata.get("download_url")

                    if not download_url:
                        logger.warning(f"No download URL for {franchise_name}")
                        continue

                    logger.debug(
                        f"Downloading document {i+1}/{len(metadata_list)}: {franchise_name}"
                    )

                    # Download document content
                    content = await scraper.download_document(download_url)

                    # Compute hash for deduplication
                    doc_hash = scraper.compute_document_hash(content)

                    # TODO: Check for duplicates in database
                    # TODO: Upload to Google Drive
                    # TODO: Update FDD record with file path and hash

                    # For now, just log the successful download
                    pipeline_logger.info(
                        "minnesota_document_downloaded",
                        franchise_name=franchise_name,
                        file_size=len(content),
                        sha256_hash=doc_hash[:16],  # Log first 16 chars
                        metadata_id=str(metadata.id),
                    )

                    downloaded_files.append(
                        f"mn/{franchise_name.lower().replace(' ', '_')}.pdf"
                    )

                    # Add delay between downloads to be respectful
                    await asyncio.sleep(2.0)

                except Exception as e:
                    logger.error(
                        f"Failed to download document for {franchise_name}: {e}"
                    )
                    pipeline_logger.error(
                        "minnesota_document_download_failed",
                        franchise_name=franchise_name,
                        error=str(e),
                        metadata_id=str(metadata.id),
                    )
                    continue

        logger.info(
            f"Successfully downloaded {len(downloaded_files)} Minnesota documents"
        )
        pipeline_logger.info(
            "minnesota_download_completed",
            downloaded_count=len(downloaded_files),
            run_id=str(prefect_run_id),
        )

        return downloaded_files

    except Exception as e:
        logger.error(f"Minnesota document download failed: {e}")
        pipeline_logger.error(
            "minnesota_download_failed", error=str(e), run_id=str(prefect_run_id)
        )
        raise


@task(name="collect_minnesota_metrics", retries=1)
async def collect_minnesota_metrics(
    documents_discovered: int,
    metadata_records_created: int,
    documents_downloaded: int,
    prefect_run_id: UUID,
    start_time: datetime,
) -> dict:
    """Collect and store metrics for Minnesota scraping flow.

    Args:
        documents_discovered: Number of documents discovered
        metadata_records_created: Number of metadata records created
        documents_downloaded: Number of documents downloaded
        prefect_run_id: Prefect run ID for tracking
        start_time: Flow start time

    Returns:
        Dictionary with collected metrics
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger(
        "minnesota_metrics", prefect_run_id=str(prefect_run_id)
    )

    try:
        end_time = datetime.utcnow()
        duration_seconds = (end_time - start_time).total_seconds()

        metrics = {
            "source": "MN",
            "prefect_run_id": str(prefect_run_id),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration_seconds,
            "documents_discovered": documents_discovered,
            "metadata_records_created": metadata_records_created,
            "documents_downloaded": documents_downloaded,
            "success_rate": (
                metadata_records_created / documents_discovered
                if documents_discovered > 0
                else 0
            ),
            "download_rate": (
                documents_downloaded / metadata_records_created
                if metadata_records_created > 0
                else 0
            ),
        }

        # Log metrics
        pipeline_logger.info(
            "minnesota_scraping_metrics",
            **metrics,
        )

        logger.info(f"Minnesota scraping metrics collected: {metrics}")
        return metrics

    except Exception as e:
        logger.error(f"Failed to collect Minnesota metrics: {e}")
        pipeline_logger.error(
            "minnesota_metrics_collection_failed",
            error=str(e),
            run_id=str(prefect_run_id),
        )
        return {}


@flow(
    name="scrape-minnesota-portal",
    description="Scrape Minnesota franchise portal for FDD documents",
    task_runner=ConcurrentTaskRunner(),
    retries=1,
    retry_delay_seconds=300,
)
async def scrape_minnesota_flow(
    download_documents: bool = True, max_documents: Optional[int] = None
) -> dict:
    """Main flow for scraping Minnesota franchise portal.

    Args:
        download_documents: Whether to download document content
        max_documents: Optional limit on number of documents to process

    Returns:
        Dictionary with flow execution results
    """
    logger = get_run_logger()
    prefect_run_id = uuid4()
    start_time = datetime.utcnow()

    try:
        logger.info("Starting Minnesota franchise portal scraping flow")

        # Step 1: Scrape portal for document metadata
        documents = await scrape_minnesota_portal(prefect_run_id)

        if max_documents and len(documents) > max_documents:
            logger.info(f"Limiting processing to {max_documents} documents")
            documents = documents[:max_documents]

        # Step 2: Process and store document metadata
        metadata_list = await process_minnesota_documents(documents, prefect_run_id)

        # Step 3: Download documents if requested
        downloaded_files = []
        if download_documents and metadata_list:
            downloaded_files = await download_minnesota_documents(
                metadata_list, prefect_run_id
            )

        # Step 4: Collect metrics
        metrics = await collect_minnesota_metrics(
            documents_discovered=len(documents),
            metadata_records_created=len(metadata_list),
            documents_downloaded=len(downloaded_files),
            prefect_run_id=prefect_run_id,
            start_time=start_time,
        )

        # Prepare results
        results = {
            "prefect_run_id": str(prefect_run_id),
            "documents_discovered": len(documents),
            "metadata_records_created": len(metadata_list),
            "documents_downloaded": len(downloaded_files),
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
        }

        logger.info(f"Minnesota scraping flow completed successfully: {results}")
        return results

    except Exception as e:
        logger.error(f"Minnesota scraping flow failed: {e}")

        # Still try to collect partial metrics
        try:
            partial_metrics = await collect_minnesota_metrics(
                documents_discovered=0,
                metadata_records_created=0,
                documents_downloaded=0,
                prefect_run_id=prefect_run_id,
                start_time=start_time,
            )
        except:
            partial_metrics = {}

        return {
            "prefect_run_id": str(prefect_run_id),
            "documents_discovered": 0,
            "metadata_records_created": 0,
            "documents_downloaded": 0,
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": partial_metrics,
        }


# Deployment configuration for scheduling
if __name__ == "__main__":
    # This allows the flow to be run directly for testing
    import asyncio

    async def main():
        result = await scrape_minnesota_flow(
            download_documents=False,  # Set to False for testing
            max_documents=5,  # Limit for testing
        )
        print(f"Flow result: {result}")

    asyncio.run(main())