# franchise_scrapers/wi/scraper.py
"""Main Wisconsin franchise scraper orchestration.

Coordinates the three-step process:
1. Extract active filings
2. Search for registered franchises
3. Scrape details and download PDFs
"""

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from franchise_scrapers.wi import (
    scrape_wi_active_filings,
    search_wi_franchises,
    scrape_wi_details
)
from franchise_scrapers.models import WIActiveRow
from franchise_scrapers.config import settings


async def run_wi_scraper(
    max_workers: Optional[int] = None,
    limit: Optional[int] = None,
    resume_from_step: Optional[int] = 1
) -> dict:
    """Run the complete Wisconsin franchise scraping pipeline.
    
    Args:
        max_workers: Maximum parallel workers (default from settings)
        limit: Limit number of franchises to process (for testing)
        resume_from_step: Resume from step (1=active, 2=search, 3=details)
        
    Returns:
        Dictionary with scraping statistics
    """
    if max_workers is None:
        max_workers = settings.MAX_WORKERS
    
    print(f"\n{'='*60}")
    print(f"Wisconsin Franchise Scraper")
    print(f"{'='*60}")
    print(f"Started at: {datetime.now()}")
    print(f"Max workers: {max_workers}")
    print(f"Download directory: {settings.DOWNLOAD_DIR}")
    
    if limit:
        print(f"Limited to: {limit} franchises")
    
    if resume_from_step > 1:
        print(f"Resuming from step: {resume_from_step}")
    
    print(f"{'='*60}\n")
    
    stats = {
        'start_time': datetime.now(),
        'active_filings': 0,
        'registered_found': 0,
        'details_scraped': 0,
        'pdfs_downloaded': 0,
        'errors': []
    }
    
    try:
        # Step 1: Extract active filings
        if resume_from_step <= 1:
            print(f"\n[Step 1/3] Extracting active filings...")
            print("-" * 40)
            
            franchise_names = await scrape_wi_active_filings()
            stats['active_filings'] = len(franchise_names)
            
            print(f"✓ Extracted {len(franchise_names)} active filings")
            
            # Apply limit if specified
            if limit and len(franchise_names) > limit:
                franchise_names = franchise_names[:limit]
                print(f"  (Limited to {limit} for processing)")
            
            # Convert to WIActiveRow objects for next step
            # Note: In real implementation, we'd load these from the CSV with filing numbers
            csv_path = settings.DOWNLOAD_DIR / "wi_active_filings.csv"
            active_rows = []
            
            # Load from CSV to get filing numbers
            import csv
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if limit and len(active_rows) >= limit:
                        break
                    active_rows.append(WIActiveRow(
                        legal_name=row['legal_name'],
                        filing_number=row['filing_number']
                    ))
        else:
            # Load from existing CSV
            print(f"\n[Step 1/3] Loading active filings from CSV...")
            csv_path = settings.DOWNLOAD_DIR / "wi_active_filings.csv"
            active_rows = []
            
            import csv
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if limit and len(active_rows) >= limit:
                        break
                    active_rows.append(WIActiveRow(
                        legal_name=row['legal_name'],
                        filing_number=row['filing_number']
                    ))
            
            stats['active_filings'] = len(active_rows)
            print(f"✓ Loaded {len(active_rows)} active filings")
        
        # Step 2: Search for registered franchises
        if resume_from_step <= 2:
            print(f"\n[Step 2/3] Searching for registered franchises...")
            print("-" * 40)
            
            registered_rows = await search_wi_franchises(active_rows, max_workers=max_workers)
            stats['registered_found'] = len(registered_rows)
            
            print(f"✓ Found {len(registered_rows)} registered franchises")
            print(f"  ({len(active_rows) - len(registered_rows)} not registered)")
        else:
            # Load from existing CSV
            print(f"\n[Step 2/3] Loading registered franchises from CSV...")
            from franchise_scrapers.models import WIRegisteredRow
            
            csv_path = settings.DOWNLOAD_DIR / "wi_registered_filings.csv"
            registered_rows = []
            
            import csv
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    registered_rows.append(WIRegisteredRow(
                        filing_number=row['filing_number'],
                        legal_name=row['legal_name'],
                        details_url=row['details_url']
                    ))
            
            stats['registered_found'] = len(registered_rows)
            print(f"✓ Loaded {len(registered_rows)} registered franchises")
        
        # Step 3: Scrape details and download PDFs
        print(f"\n[Step 3/3] Scraping details and downloading PDFs...")
        print("-" * 40)
        
        details_rows = await scrape_wi_details(registered_rows, max_workers=max_workers)
        stats['details_scraped'] = len(details_rows)
        
        # Count successful PDF downloads
        pdfs_downloaded = sum(1 for row in details_rows if row.pdf_status == 'ok')
        stats['pdfs_downloaded'] = pdfs_downloaded
        
        print(f"✓ Scraped {len(details_rows)} detail pages")
        print(f"✓ Downloaded {pdfs_downloaded} PDFs")
        
        # Report any failures
        failed_pdfs = [row for row in details_rows if row.pdf_status == 'failed']
        if failed_pdfs:
            print(f"  ({len(failed_pdfs)} PDF downloads failed)")
            for row in failed_pdfs[:5]:  # Show first 5
                stats['errors'].append(f"PDF failed: {row.legal_name}")
        
    except Exception as e:
        print(f"\n✗ Error during scraping: {e}")
        stats['errors'].append(str(e))
    
    # Calculate runtime
    stats['end_time'] = datetime.now()
    stats['runtime'] = stats['end_time'] - stats['start_time']
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Scraping Summary")
    print(f"{'='*60}")
    print(f"Runtime: {stats['runtime']}")
    print(f"Active filings found: {stats['active_filings']}")
    print(f"Registered franchises: {stats['registered_found']}")
    print(f"Details scraped: {stats['details_scraped']}")
    print(f"PDFs downloaded: {stats['pdfs_downloaded']}")
    
    if stats['errors']:
        print(f"\nErrors encountered: {len(stats['errors'])}")
        for error in stats['errors'][:5]:
            print(f"  - {error}")
    
    print(f"\nOutput files in: {settings.DOWNLOAD_DIR}")
    print(f"  - wi_active_filings.csv")
    print(f"  - wi_registered_filings.csv")
    print(f"  - wi_details_filings.csv")
    print(f"  - PDFs: {stats['pdfs_downloaded']} files")
    print(f"{'='*60}\n")
    
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Wisconsin Franchise Scraper")
    parser.add_argument("--workers", type=int, help="Maximum parallel workers")
    parser.add_argument("--limit", type=int, help="Limit number of franchises to process")
    parser.add_argument("--resume", type=int, choices=[1, 2, 3], default=1,
                       help="Resume from step (1=active, 2=search, 3=details)")
    
    args = parser.parse_args()
    
    # Run the scraper
    asyncio.run(run_wi_scraper(
        max_workers=args.workers,
        limit=args.limit,
        resume_from_step=args.resume
    ))