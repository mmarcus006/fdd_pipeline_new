"""Wisconsin franchise portal scraping flow."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID, uuid4

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from tasks.wisconsin_scraper import WisconsinScraper
from tasks.web_scraping import DocumentMetadata, ScrapingError, create_scraper
from models.scrape_metadata import ScrapeMetadata
from utils.database import get_database_manager
from utils.logging import PipelineLogger


@task(name="scrape_wisconsin_portal", retries=3, retry_delay_seconds=60)
async def scrape_wisconsin_portal(prefect_run_id: UUID) -> List[DocumentMetadata]:
    """Scrape the Wisconsin franchise portal for FDD documents.
    
    Args:
        prefect_run_id: Prefect run ID for tracking
        
    Returns:
        List of discovered document metadata
        
    Raises:
        ScrapingError: If scraping fails after all retries
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger("scrape_wisconsin", prefect_run_id=str(prefect_run_id))
    
    try:
        logger.info("Starting Wisconsin portal scraping")
        pipeline_logger.info("wisconsin_scraping_started", run_id=str(prefect_run_id))
        
        # Create and run scraper
        async with create_scraper(WisconsinScraper, prefect_run_id=prefect_run_id) as scraper:
            documents = await scraper.scrape_portal()
        
        logger.info(f"Wisconsin scraping completed successfully. Found {len(documents)} documents")
        pipeline_logger.info(
            "wisconsin_scraping_completed",
            documents_found=len(documents),
            run_id=str(prefect_run_id)
        )
        
        return documents
        
    except Exception as e:
        logger.error(f"Wisconsin scraping failed: {e}")
        pipeline_logger.error(
            "wisconsin_scraping_failed",
            error=str(e),
            run_id=str(prefect_run_id)
        )
        raise ScrapingError(f"Wisconsin portal scraping failed: {e}")


@task(name="process_wisconsin_documents", retries=2)
async def process_wisconsin_documents(
    documents: List[DocumentMetadata],
    prefect_run_id: UUID
) -> List[ScrapeMetadata]:
    """Process discovered Wisconsin documents and store metadata.
    
    Args:
        documents: List of document metadata from scraping
        prefect_run_id: Prefect run ID for tracking
        
    Returns:
        List of stored scrape metadata records
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger("process_wisconsin_docs", prefect_run_id=str(prefect_run_id))
    
    try:
        logger.info(f"Processing {len(documents)} Wisconsin documents")
        pipeline_logger.info(
            "wisconsin_processing_started",
            document_count=len(documents),
            run_id=str(prefect_run_id)
        )
        
        processed_metadata = []
        
        # Get database manager
        async with get_database_manager() as db:
            for i, doc in enumerate(documents):
                try:
                    logger.debug(f"Processing document {i+1}/{len(documents)}: {doc.franchise_name}")
                    
                    # Check for existing document by hash (if we have content)
                    # For now, we'll create metadata records for all discovered documents
                    
                    # Create scrape metadata record
                    scrape_metadata = ScrapeMetadata(
                        id=uuid4(),
                        fdd_id=uuid4(),  # Will be updated when FDD record is created
                        source_name="WI",
                        source_url=doc.source_url,
                        filing_metadata={
                            'franchise_name': doc.franchise_name,
                            'filing_date': doc.filing_date,
                            'document_type': doc.document_type,
                            'filing_number': doc.filing_number,
                            'download_url': doc.download_url,
                            'file_size': doc.file_size,
                            'additional_metadata': doc.additional_metadata
                        },
                        prefect_run_id=prefect_run_id,
                        scraped_at=datetime.utcnow()
                    )
                    
                    # Store in database
                    await db.create_scrape_metadata(scrape_metadata)
                    processed_metadata.append(scrape_metadata)
                    
                    pipeline_logger.info(
                        "wisconsin_document_processed",
                        franchise_name=doc.franchise_name,
                        filing_number=doc.filing_number,
                        metadata_id=str(scrape_metadata.id)
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to process document {doc.franchise_name}: {e}")
                    pipeline_logger.error(
                        "wisconsin_document_processing_failed",
                        franchise_name=doc.franchise_name,
                        error=str(e)
                    )
                    continue
        
        logger.info(f"Successfully processed {len(processed_metadata)} Wisconsin documents")
        pipeline_logger.info(
            "wisconsin_processing_completed",
            processed_count=len(processed_metadata),
            run_id=str(prefect_run_id)
        )
        
        return processed_metadata
        
    except Exception as e:
        logger.error(f"Wisconsin document processing failed: {e}")
        pipeline_logger.error(
            "wisconsin_processing_failed",
            error=str(e),
            run_id=str(prefect_run_id)
        )
        raise


@task(name="download_wisconsin_documents", retries=3)
async def download_wisconsin_documents(
    metadata_list: List[ScrapeMetadata],
    prefect_run_id: UUID
) -> List[str]:
    """Download Wisconsin FDD documents and store in Google Drive.
    
    Args:
        metadata_list: List of scrape metadata records
        prefect_run_id: Prefect run ID for tracking
        
    Returns:
        List of Google Drive file paths for downloaded documents
    """
    logger = get_run_logger()
    pipeline_logger = PipelineLogger("download_wisconsin_docs", prefect_run_id=str(prefect_run_id))
    
    try:
        logger.info(f"Starting download of {len(metadata_list)} Wisconsin documents")
        pipeline_logger.info(
            "wisconsin_download_started",
            document_count=len(metadata_list),
            run_id=str(prefect_run_id)
        )
        
        downloaded_files = []
        
        # Create scraper for downloading
        async with create_scraper(WisconsinScraper, prefect_run_id=prefect_run_id) as scraper:
            for i, metadata in enumerate(metadata_list):
                try:
                    franchise_name = metadata.filing_metadata.get('franchise_name', 'unknown')
                    download_url = metadata.filing_metadata.get('download_url')
                    
                    if not download_url:
                        logger.warning(f"No download URL for {franchise_name}")
                        continue
                    
                    logger.debug(f"Downloading document {i+1}/{len(metadata_list)}: {franchise_name}")
                    
                    # Download document content
                    content = await scraper.download_document(download_url)
                    
                    # Compute hash for deduplication
                    doc_hash = scraper.compute_document_hash(content)
                    
                    # TODO: Check for duplicates in database
                    # TODO: Upload to Google Drive
                    # TODO: Update FDD record with file path and hash
                    
                    # For now, just log the successful download
                    pipeline_logger.info(
                        "wisconsin_document_downloaded",
                        franchise_name=franchise_name,
                        file_size=len(content),
                        sha256_hash=doc_hash[:16],  # Log first 16 chars
                        metadata_id=str(metadata.id)
                    )
                    
                    downloaded_files.append(f"wi/{franchise_name.lower().replace(' ', '_')}.pdf")
                    
                    # Add delay between downloads to be respectful
                    await asyncio.sleep(2.0)
                    
                except Exception as e:
                    logger.error(f"Failed to download document for {franchise_name}: {e}")
                    pipeline_logger.error(
                        "wisconsin_document_download_failed",
                        franchise_name=franchise_name,
                        error=str(e),
                        metadata_id=str(metadata.id)
                    )
                    continue
        
        logger.info(f"Successfully downloaded {len(downloaded_files)} Wisconsin documents")
        pipeline_logger.info(
            "wisconsin_download_completed",
            downloaded_count=len(downloaded_files),
            run_id=str(prefect_run_id)
        )
        
        return downloaded_files
        
    except Exception as e:
        logger.error(f"Wisconsin document download failed: {e}")
        pipeline_logger.error(
            "wisconsin_download_failed",
            error=str(e),
            run_id=str(prefect_run_id)
        )
        raise


@flow(
    name="scrape-wisconsin-portal",
    description="Scrape Wisconsin franchise portal for FDD documents",
    task_runner=ConcurrentTaskRunner(),
    retries=1,
    retry_delay_seconds=300
)
async def scrape_wisconsin_flow(
    download_documents: bool = True,
    max_documents: Optional[int] = None
) -> dict:
    """Main flow for scraping Wisconsin franchise portal.
    
    Args:
        download_documents: Whether to download document content
        max_documents: Optional limit on number of documents to process
        
    Returns:
        Dictionary with flow execution results
    """
    logger = get_run_logger()
    prefect_run_id = uuid4()
    
    try:
        logger.info("Starting Wisconsin franchise portal scraping flow")
        
        # Step 1: Scrape portal for document metadata
        documents = await scrape_wisconsin_portal(prefect_run_id)
        
        if max_documents and len(documents) > max_documents:
            logger.info(f"Limiting processing to {max_documents} documents")
            documents = documents[:max_documents]
        
        # Step 2: Process and store document metadata
        metadata_list = await process_wisconsin_documents(documents, prefect_run_id)
        
        # Step 3: Download documents if requested
        downloaded_files = []
        if download_documents and metadata_list:
            downloaded_files = await download_wisconsin_documents(metadata_list, prefect_run_id)
        
        # Prepare results
        results = {
            'prefect_run_id': str(prefect_run_id),
            'documents_discovered': len(documents),
            'metadata_records_created': len(metadata_list),
            'documents_downloaded': len(downloaded_files),
            'success': True,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Wisconsin scraping flow completed successfully: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Wisconsin scraping flow failed: {e}")
        return {
            'prefect_run_id': str(prefect_run_id),
            'documents_discovered': 0,
            'metadata_records_created': 0,
            'documents_downloaded': 0,
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


# Deployment configuration for scheduling
if __name__ == "__main__":
    # This allows the flow to be run directly for testing
    import asyncio
    
    async def main():
        result = await scrape_wisconsin_flow(
            download_documents=False,  # Set to False for testing
            max_documents=5  # Limit for testing
        )
        print(f"Flow result: {result}")
    
    asyncio.run(main())