"""Database integration for franchise scrapers with deduplication."""

import hashlib
import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from uuid import UUID, uuid4
from datetime import datetime, date
import pandas as pd

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from storage.database.manager import get_database_manager
from models.franchisor import FranchisorCreate, Franchisor
from models.fdd import FDDCreate, FDD, DocumentType, ProcessingStatus
from models.scrape_metadata import ScrapeMetadataCreate, ScrapeStatus
from utils.logging import get_logger

logger = get_logger(__name__)


class ScraperDatabaseIntegration:
    """Handles database operations for scrapers with deduplication."""
    
    def __init__(self):
        self.db = get_database_manager()
        
    def find_or_create_franchisor(self, name: str, **kwargs) -> UUID:
        """Find existing franchisor or create new one.
        
        Args:
            name: Franchisor name
            **kwargs: Additional franchisor data
            
        Returns:
            Franchisor UUID
        """
        try:
            # Clean and normalize the name
            canonical_name = name.strip().title()
            
            # Search for existing franchisor by name
            existing = self.db.get_records_by_filter(
                "franchisors", 
                {"canonical_name": canonical_name},
                limit=1
            )
            
            if existing:
                logger.debug(f"Found existing franchisor: {canonical_name}")
                return UUID(existing[0]["id"])
            
            # Create new franchisor using Pydantic validation
            franchisor_data = FranchisorCreate(
                canonical_name=canonical_name,
                parent_company=kwargs.get("parent_company"),
                website=kwargs.get("website"),
                phone=kwargs.get("phone"),
                email=kwargs.get("email"),
                dba_names=kwargs.get("dba_names", [])
            )
            
            # Convert to dict using model_dump for proper serialization
            record = franchisor_data.model_dump(mode='json')
            record["id"] = str(uuid4())
            record["created_at"] = datetime.utcnow().isoformat()
            record["updated_at"] = datetime.utcnow().isoformat()
            
            self.db.execute_batch_insert("franchisors", [record])
            
            logger.info(f"Created new franchisor: {canonical_name}")
            return UUID(record["id"])
            
        except Exception as e:
            logger.error(f"Error finding/creating franchisor {name}: {e}")
            raise
    
    def check_fdd_duplicate(self, 
                           franchisor_id: UUID, 
                           filing_state: str, 
                           filing_number: Optional[str] = None,
                           issue_date: Optional[date] = None,
                           sha256_hash: Optional[str] = None) -> Optional[UUID]:
        """Check if FDD already exists in database.
        
        Args:
            franchisor_id: Franchisor UUID
            filing_state: State code (e.g., 'MN', 'WI')
            filing_number: Filing number from state portal
            issue_date: Document issue date
            sha256_hash: SHA256 hash of PDF content
            
        Returns:
            Existing FDD UUID if duplicate found, None otherwise
        """
        try:
            filters = {
                "franchise_id": str(franchisor_id),
                "filing_state": filing_state
            }
            
            # Add additional filters if available
            if filing_number:
                filters["filing_number"] = filing_number
            if sha256_hash:
                filters["sha256_hash"] = sha256_hash
                
            existing = self.db.get_records_by_filter("fdds", filters, limit=1)
            
            if existing:
                existing_id = UUID(existing[0]["id"])
                logger.info(f"Found duplicate FDD: {existing_id}")
                return existing_id
                
            # If no exact match but we have a hash, check for hash duplicates
            if sha256_hash:
                hash_duplicates = self.db.get_records_by_filter(
                    "fdds", 
                    {"sha256_hash": sha256_hash}, 
                    limit=1
                )
                if hash_duplicates:
                    duplicate_id = UUID(hash_duplicates[0]["id"])
                    logger.info(f"Found hash duplicate FDD: {duplicate_id}")
                    return duplicate_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking FDD duplicate: {e}")
            return None
    
    def create_fdd_record(self,
                         franchisor_id: UUID,
                         filing_state: str,
                         drive_file_id: str,
                         drive_path: str,
                         filing_number: Optional[str] = None,
                         issue_date: Optional[date] = None,
                         amendment_date: Optional[date] = None,
                         document_type: DocumentType = DocumentType.INITIAL,
                         sha256_hash: Optional[str] = None,
                         total_pages: Optional[int] = None) -> UUID:
        """Create new FDD record in database.
        
        Args:
            franchisor_id: Franchisor UUID
            filing_state: State code
            drive_file_id: Google Drive file ID
            drive_path: Google Drive path
            filing_number: Filing number from state portal
            issue_date: Document issue date
            amendment_date: Amendment date if applicable
            document_type: Document type
            sha256_hash: SHA256 hash of PDF content
            total_pages: Number of pages in PDF
            
        Returns:
            Created FDD UUID
        """
        try:
            # Use Pydantic model for validation
            fdd_data = FDDCreate(
                franchise_id=franchisor_id,
                issue_date=issue_date or date.today(),
                amendment_date=amendment_date,
                document_type=document_type,
                filing_state=filing_state,
                filing_number=filing_number,
                drive_path=drive_path,
                drive_file_id=drive_file_id,
                sha256_hash=sha256_hash,
                total_pages=total_pages,
                language_code="en"
            )
            
            # Convert to dict and add additional fields
            record = fdd_data.model_dump(mode='json')
            fdd_id = uuid4()
            record["id"] = str(fdd_id)
            record["is_amendment"] = document_type == DocumentType.AMENDMENT
            record["processing_status"] = ProcessingStatus.PENDING.value
            record["needs_review"] = False
            record["created_at"] = datetime.utcnow().isoformat()
            
            self.db.execute_batch_insert("fdds", [record])
            
            logger.info(f"Created FDD record: {fdd_id}")
            return fdd_id
            
        except Exception as e:
            logger.error(f"Error creating FDD record: {e}")
            raise
    
    def calculate_pdf_hash(self, pdf_content: bytes) -> str:
        """Calculate SHA256 hash of PDF content."""
        return hashlib.sha256(pdf_content).hexdigest()
    
    def create_scrape_metadata(self,
                             fdd_id: UUID,
                             source_name: str,
                             source_url: str,
                             download_url: Optional[str] = None,
                             portal_id: Optional[str] = None,
                             registration_status: Optional[str] = None,
                             effective_date: Optional[date] = None,
                             scrape_status: ScrapeStatus = ScrapeStatus.DOWNLOADED,
                             failure_reason: Optional[str] = None,
                             filing_metadata: Optional[Dict] = None) -> UUID:
        """Create scrape metadata record for audit trail.
        
        Args:
            fdd_id: Associated FDD UUID
            source_name: State code (MN, WI, etc.)
            source_url: URL where document was found
            download_url: Direct download URL if different from source
            portal_id: State portal's ID for this record
            registration_status: Registration status from portal
            effective_date: Effective date from portal
            scrape_status: Status of the scrape operation
            failure_reason: Reason if scrape failed
            filing_metadata: Additional metadata from portal
            
        Returns:
            Created scrape metadata UUID
        """
        try:
            # Create using Pydantic model for validation
            metadata = ScrapeMetadataCreate(
                fdd_id=fdd_id,
                source_name=source_name.upper(),
                source_url=source_url,
                download_url=download_url,
                portal_id=portal_id,
                registration_status=registration_status,
                effective_date=effective_date,
                scrape_status=scrape_status,
                failure_reason=failure_reason,
                filing_metadata=filing_metadata or {},
                downloaded_at=datetime.utcnow() if scrape_status == ScrapeStatus.DOWNLOADED else None
            )
            
            # Convert to dict and add ID
            record = metadata.model_dump(mode='json')
            metadata_id = uuid4()
            record["id"] = str(metadata_id)
            record["created_at"] = datetime.utcnow().isoformat()
            
            self.db.execute_batch_insert("scrape_metadata", [record])
            
            logger.info(f"Created scrape metadata: {metadata_id}")
            return metadata_id
            
        except Exception as e:
            logger.error(f"Error creating scrape metadata: {e}")
            raise
    
    def process_scraped_data(self, 
                           scraped_df: pd.DataFrame, 
                           state_code: str,
                           pdf_downloads: List[Dict]) -> Dict[str, int]:
        """Process scraped data and save to database with deduplication.
        
        Args:
            scraped_df: DataFrame with scraped registration data
            state_code: State code (MN, WI)
            pdf_downloads: List of downloaded PDF info with file_id, filename, content
            
        Returns:
            Dictionary with processing statistics
        """
        stats = {
            "total_scraped": len(scraped_df),
            "franchisors_created": 0,
            "franchisors_found": 0,
            "fdds_created": 0,
            "fdds_duplicates": 0,
            "errors": 0
        }
        
        try:
            # Create a mapping of PDF downloads by filename or identifier
            pdf_map = {}
            for pdf_info in pdf_downloads:
                # Use filename as key, removing file extension
                key = Path(pdf_info["filename"]).stem
                pdf_map[key] = pdf_info
            
            for index, row in scraped_df.iterrows():
                try:
                    # Extract franchisor name (column names vary by state)
                    if state_code == "MN":
                        franchisor_name = row.get("Franchisor", "")
                        filing_number = row.get("File Number", "")
                        year = row.get("Year", "")
                    elif state_code == "WI":
                        franchisor_name = row.get("Legal Name", "")
                        filing_number = row.get("File Number", "")
                        effective_date_str = row.get("Effective Date", "")
                    else:
                        logger.warning(f"Unknown state code: {state_code}")
                        continue
                    
                    if not franchisor_name:
                        logger.warning(f"No franchisor name in row {index}")
                        continue
                    
                    # Find or create franchisor
                    franchisor_id = self.find_or_create_franchisor(franchisor_name)
                    if franchisor_id:
                        # Check if this was a new creation
                        existing = self.db.get_records_by_filter(
                            "franchisors", 
                            {"id": str(franchisor_id)},
                            limit=1
                        )
                        if existing and existing[0]["created_at"] == existing[0]["updated_at"]:
                            stats["franchisors_created"] += 1
                        else:
                            stats["franchisors_found"] += 1
                    
                    # Look for corresponding PDF download
                    pdf_info = None
                    for key, pdf_data in pdf_map.items():
                        if (franchisor_name.lower() in key.lower() or 
                            filing_number in key):
                            pdf_info = pdf_data
                            break
                    
                    if not pdf_info:
                        logger.warning(f"No PDF found for {franchisor_name}")
                        continue
                    
                    # Calculate PDF hash for deduplication
                    pdf_hash = self.calculate_pdf_hash(pdf_info["content"])
                    
                    # Parse dates
                    issue_date = None
                    if state_code == "MN" and year:
                        try:
                            issue_date = date(int(year), 1, 1)  # Use Jan 1 as default
                        except ValueError:
                            pass
                    elif state_code == "WI" and effective_date_str:
                        try:
                            issue_date = datetime.strptime(effective_date_str, "%Y-%m-%d").date()
                        except ValueError:
                            try:
                                issue_date = datetime.strptime(effective_date_str, "%m/%d/%Y").date()
                            except ValueError:
                                pass
                    
                    # Check for duplicates
                    duplicate_id = self.check_fdd_duplicate(
                        franchisor_id=franchisor_id,
                        filing_state=state_code,
                        filing_number=filing_number,
                        issue_date=issue_date,
                        sha256_hash=pdf_hash
                    )
                    
                    if duplicate_id:
                        stats["fdds_duplicates"] += 1
                        logger.info(f"Skipping duplicate FDD for {franchisor_name}")
                        continue
                    
                    # Create FDD record
                    fdd_id = self.create_fdd_record(
                        franchisor_id=franchisor_id,
                        filing_state=state_code,
                        drive_file_id=pdf_info["file_id"],
                        drive_path=pdf_info.get("drive_path", f"/{state_code.lower()}/{pdf_info['filename']}"),
                        filing_number=filing_number,
                        issue_date=issue_date,
                        sha256_hash=pdf_hash,
                        total_pages=pdf_info.get("total_pages")
                    )
                    
                    if fdd_id:
                        stats["fdds_created"] += 1
                        logger.info(f"Created FDD record for {franchisor_name}: {fdd_id}")
                        
                        # Create scrape metadata record
                        try:
                            # Extract metadata from row
                            source_url = row.get("Document Link", "") or row.get("Details Link", "")
                            download_url = row.get("PDF Link", "") or row.get("Download Link", "")
                            
                            # Parse effective date if available
                            effective_date = None
                            if state_code == "WI" and effective_date_str:
                                try:
                                    effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d").date()
                                except ValueError:
                                    try:
                                        effective_date = datetime.strptime(effective_date_str, "%m/%d/%Y").date()
                                    except ValueError:
                                        pass
                            
                            # Create metadata record
                            self.create_scrape_metadata(
                                fdd_id=fdd_id,
                                source_name=state_code,
                                source_url=source_url,
                                download_url=download_url,
                                portal_id=filing_number,
                                registration_status=row.get("Status", "Registered"),
                                effective_date=effective_date,
                                scrape_status=ScrapeStatus.DOWNLOADED,
                                filing_metadata={
                                    "year": row.get("Year"),
                                    "trade_name": row.get("Trade Name"),
                                    "notes": row.get("Notes"),
                                    "row_index": index
                                }
                            )
                        except Exception as metadata_error:
                            logger.error(f"Error creating scrape metadata: {metadata_error}")
                            # Don't fail the whole process for metadata errors
                    
                except Exception as row_error:
                    stats["errors"] += 1
                    logger.error(f"Error processing row {index}: {row_error}")
                    continue
            
            logger.info(f"Processing complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error processing scraped data: {e}")
            raise
    
    def get_duplicate_fdds(self) -> List[Dict]:
        """Find all duplicate FDDs in the database."""
        try:
            # Find duplicates by SHA256 hash
            query = """
            SELECT sha256_hash, COUNT(*) as count, 
                   array_agg(id) as fdd_ids,
                   array_agg(franchise_id) as franchisor_ids
            FROM fdds 
            WHERE sha256_hash IS NOT NULL
            GROUP BY sha256_hash 
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            """
            
            duplicates = self.db.execute_query(query)
            
            logger.info(f"Found {len(duplicates)} sets of duplicate FDDs")
            return duplicates
            
        except Exception as e:
            logger.error(f"Error finding duplicate FDDs: {e}")
            return []
    
    def cleanup_duplicate_fdds(self, dry_run: bool = True) -> Dict[str, int]:
        """Clean up duplicate FDDs, keeping the oldest one.
        
        Args:
            dry_run: If True, only report what would be deleted
            
        Returns:
            Dictionary with cleanup statistics
        """
        stats = {
            "duplicate_sets": 0,
            "fdds_to_delete": 0,
            "fdds_deleted": 0,
            "errors": 0
        }
        
        try:
            duplicates = self.get_duplicate_fdds()
            stats["duplicate_sets"] = len(duplicates)
            
            for duplicate_set in duplicates:
                try:
                    fdd_ids = duplicate_set["fdd_ids"]
                    
                    # Get full records for these FDDs
                    fdd_records = []
                    for fdd_id in fdd_ids:
                        record = self.db.get_record_by_id("fdds", fdd_id)
                        if record:
                            fdd_records.append(record)
                    
                    if len(fdd_records) <= 1:
                        continue
                    
                    # Sort by created_at to keep the oldest
                    fdd_records.sort(key=lambda x: x["created_at"])
                    keep_record = fdd_records[0]
                    delete_records = fdd_records[1:]
                    
                    logger.info(f"Keeping FDD {keep_record['id']}, deleting {len(delete_records)} duplicates")
                    
                    stats["fdds_to_delete"] += len(delete_records)
                    
                    if not dry_run:
                        # Delete the duplicate records
                        for record in delete_records:
                            success = self.db.delete_record("fdds", record["id"])
                            if success:
                                stats["fdds_deleted"] += 1
                            else:
                                stats["errors"] += 1
                    
                except Exception as set_error:
                    stats["errors"] += 1
                    logger.error(f"Error processing duplicate set: {set_error}")
                    continue
            
            action = "Would delete" if dry_run else "Deleted"
            logger.info(f"{action} {stats['fdds_to_delete']} duplicate FDDs from {stats['duplicate_sets']} sets")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error cleaning up duplicates: {e}")
            raise


# Global instance
_scraper_db = None

def get_scraper_database() -> ScraperDatabaseIntegration:
    """Get global scraper database integration instance."""
    global _scraper_db
    if _scraper_db is None:
        _scraper_db = ScraperDatabaseIntegration()
    return _scraper_db