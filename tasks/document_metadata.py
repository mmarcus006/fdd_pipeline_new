"""Shared document metadata operations for all scrapers."""

import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from tasks.web_scraping import DocumentMetadata, BaseScraper
from utils.logging import get_logger

logger = get_logger(__name__)


async def process_all_documents_with_downloads(
    scraper: BaseScraper,
    output_dir: Optional[Path] = None,
    limit: Optional[int] = None,
    skip_existing: bool = True
) -> Dict[str, Any]:
    """Discover all documents and download them using any scraper.
    
    Args:
        scraper: Scraper instance to use
        output_dir: Directory to save downloads
        limit: Maximum number of documents to process
        skip_existing: Skip downloading existing files
        
    Returns:
        Dictionary with processing results
    """
    results = {
        "discovered": 0,
        "downloaded": 0,
        "failed": 0,
        "skipped": 0,
        "documents": []
    }
    
    try:
        # Discover documents
        documents = await scraper.discover_documents()
        results["discovered"] = len(documents)
        
        # Apply limit if specified
        if limit:
            documents = documents[:limit]
        
        # Process each document
        for i, doc in enumerate(documents):
            try:
                logger.info(
                    "processing_document",
                    index=i + 1,
                    total=len(documents),
                    franchise=doc.franchise_name
                )
                
                # Download document
                filepath = await download_and_save_document(
                    scraper=scraper,
                    doc=doc,
                    output_dir=output_dir,
                    skip_existing=skip_existing
                )
                
                if filepath:
                    if filepath.exists() and skip_existing:
                        results["skipped"] += 1
                    else:
                        results["downloaded"] += 1
                    
                    # Add to results with filepath
                    doc_result = doc.model_dump()
                    doc_result["local_filepath"] = str(filepath)
                    results["documents"].append(doc_result)
                else:
                    results["failed"] += 1
                
                # Be respectful between downloads
                await scraper.page.wait_for_timeout(1000)
                
            except Exception as e:
                logger.error(
                    "document_processing_failed",
                    franchise=doc.franchise_name,
                    error=str(e)
                )
                results["failed"] += 1
        
        return results
        
    except Exception as e:
        logger.error(
            "batch_processing_failed",
            error=str(e)
        )
        results["error"] = str(e)
        return results


async def download_and_save_document(
    scraper: BaseScraper,
    doc: DocumentMetadata,
    output_dir: Optional[Path] = None,
    skip_existing: bool = True
) -> Optional[Path]:
    """Download document and save to local filesystem.
    
    Args:
        scraper: Scraper instance to use
        doc: Document metadata
        output_dir: Optional output directory
        skip_existing: Skip if file already exists
        
    Returns:
        Path to saved file or None if download failed
    """
    try:
        # Extract metadata
        franchise_name = doc.franchise_name
        download_url = doc.download_url
        
        # Extract year from metadata if available
        year = None
        if doc.additional_metadata:
            year = doc.additional_metadata.get("year")
        if not year and doc.filing_date:
            try:
                year = datetime.strptime(doc.filing_date, "%Y-%m-%d").year
            except:
                year = datetime.now().year
        
        # Create filename
        from utils.scraping_utils import create_document_filename
        filename = create_document_filename(
            franchise_name=franchise_name,
            year=str(year) if year else datetime.now().strftime("%Y"),
            filing_number=doc.filing_number,
            document_type=doc.document_type or "FDD"
        )
        
        # Determine output path
        if not output_dir:
            output_dir = Path("downloads") / scraper.source_name
        
        filepath = output_dir / filename
        
        # Check if file exists
        if skip_existing and filepath.exists():
            logger.info(
                "file_already_exists",
                franchise=franchise_name,
                filepath=str(filepath)
            )
            return filepath
        
        # Sync cookies between browser and HTTP client
        await scraper.manage_cookies()
        
        # Download using streaming method
        success = await scraper.download_file_streaming(
            download_url,
            filepath,
            progress_callback=lambda curr, total: logger.debug(
                "download_progress",
                franchise=franchise_name,
                progress=f"{curr}/{total}" if total else f"{curr} bytes"
            )
        )
        
        if success:
            logger.info(
                "document_saved",
                franchise=franchise_name,
                filepath=str(filepath)
            )
            return filepath
        
        return None
        
    except Exception as e:
        logger.error(
            "document_save_failed",
            franchise=doc.franchise_name,
            url=doc.download_url,
            error=str(e)
        )
        return None


def export_documents_to_csv(
    documents: List[DocumentMetadata], 
    filepath: Path,
    state_code: str
) -> bool:
    """Export document metadata to CSV file.
    
    Args:
        documents: List of document metadata to export
        filepath: Path to save CSV file
        state_code: State code for formatting
        
    Returns:
        True if export successful
    """
    try:
        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare data for CSV based on state
        rows = []
        
        if state_code == "MN":
            # Minnesota format
            for doc in documents:
                metadata = doc.additional_metadata or {}
                row = {
                    "Franchisor": metadata.get("franchisor", ""),
                    "Franchise Names": doc.franchise_name,
                    "Document Title": metadata.get("title", ""),
                    "Year": metadata.get("year", ""),
                    "File Number": doc.filing_number or "",
                    "Document Types": doc.document_type,
                    "Received Date": metadata.get("received_date", ""),
                    "Added On": metadata.get("added_on", ""),
                    "Notes": metadata.get("notes", ""),
                    "Download URL": doc.download_url,
                    "Document ID": metadata.get("document_id", ""),
                }
                rows.append(row)
                
        elif state_code == "WI":
            # Wisconsin format
            for doc in documents:
                metadata = doc.additional_metadata or {}
                row = {
                    "Franchise Name": doc.franchise_name,
                    "Filing Number": doc.filing_number or "",
                    "Filing Date": doc.filing_date or "",
                    "Document Type": doc.document_type,
                    "Source URL": doc.source_url,
                    "Download URL": doc.download_url,
                }
                
                # Add additional metadata fields
                if "franchisor_info" in metadata:
                    info = metadata["franchisor_info"]
                    row.update({
                        "Legal Name": info.get("legal_name", ""),
                        "Trade Name": info.get("trade_name", ""),
                        "Business Address": info.get("business_address", ""),
                        "Filing Status": info.get("filing_status", ""),
                    })
                
                if "filing_info" in metadata:
                    info = metadata["filing_info"]
                    row.update({
                        "Filing Type": info.get("type", ""),
                        "Effective Date": info.get("effective", ""),
                    })
                
                if "states_filed" in metadata:
                    states = metadata["states_filed"]
                    row["States Filed"] = ", ".join(states) if states else ""
                
                rows.append(row)
        
        else:
            # Generic format
            for doc in documents:
                row = {
                    "Franchise Name": doc.franchise_name,
                    "Filing Date": doc.filing_date or "",
                    "Document Type": doc.document_type,
                    "Filing Number": doc.filing_number or "",
                    "Source URL": doc.source_url,
                    "Download URL": doc.download_url,
                    "File Size": doc.file_size or "",
                }
                rows.append(row)
        
        # Write to CSV
        if rows:
            fieldnames = list(rows[0].keys())
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            logger.info(
                "csv_export_completed",
                filepath=str(filepath),
                row_count=len(rows)
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(
            "csv_export_failed",
            filepath=str(filepath),
            error=str(e)
        )
        return False