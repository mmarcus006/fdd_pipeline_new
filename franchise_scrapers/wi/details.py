# franchise_scrapers/wi/details.py
"""Wisconsin franchise details page scraper and PDF downloader.

Navigates to each details URL, extracts comprehensive metadata, and downloads PDFs.
"""

import asyncio
import csv
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, Browser, Download

from franchise_scrapers.browser import get_browser, get_context, with_retry
from franchise_scrapers.models import WIRegisteredRow, WIDetailsRow
from franchise_scrapers.config import settings


class WIDetailsScraper:
    """Scraper for Wisconsin franchise details pages."""
    
    def __init__(self, page: Page):
        self.page = page
        self.details_rows: List[WIDetailsRow] = []
    
    async def scrape_details(self, registered_row: WIRegisteredRow) -> Optional[WIDetailsRow]:
        """Scrape details page and download PDF.
        
        Args:
            registered_row: Registered franchise with details URL
            
        Returns:
            WIDetailsRow with all extracted information
        """
        print(f"[{datetime.now()}] Scraping details for: {registered_row.legal_name}")
        
        try:
            # Navigate to details page
            await self.page.goto(str(registered_row.details_url), wait_until="networkidle")
            await asyncio.sleep(0.5)  # Allow page to fully render
            
            # Extract all metadata
            metadata = await self._extract_metadata()
            
            # Add filing number from registered row
            metadata['filing_number'] = registered_row.filing_number
            
            # Try to download PDF
            pdf_path, pdf_status = await self._download_pdf(metadata)
            
            # Create details row
            details_row = WIDetailsRow(
                filing_number=registered_row.filing_number,
                status=metadata.get('status', 'Registered'),
                legal_name=metadata.get('legal_name', registered_row.legal_name),
                trade_name=metadata.get('trade_name'),
                contact_email=metadata.get('contact_email'),
                pdf_path=pdf_path,
                pdf_status=pdf_status,
                scraped_at=datetime.utcnow()
            )
            
            self.details_rows.append(details_row)
            
            print(f"[{datetime.now()}] Successfully scraped details for: {registered_row.legal_name}")
            return details_row
            
        except Exception as e:
            print(f"[{datetime.now()}] Error scraping details for {registered_row.legal_name}: {e}")
            
            # Create error row
            error_row = WIDetailsRow(
                filing_number=registered_row.filing_number,
                status='Error',
                legal_name=registered_row.legal_name,
                trade_name=None,
                contact_email=None,
                pdf_path=None,
                pdf_status='failed',
                scraped_at=datetime.utcnow()
            )
            
            self.details_rows.append(error_row)
            return error_row
    
    async def _extract_metadata(self) -> Dict[str, Any]:
        """Extract all metadata from details page.
        
        Returns:
            Dictionary with extracted metadata fields
        """
        # Get page content
        content = await self.page.content()
        
        metadata = {}
        
        # Extract using various patterns
        patterns = {
            'filing_number': r'Filing Number.*?(?:generic.*?)?:\s*"?(\d+)"?',
            'status': r'Filing Status.*?(?:generic.*?)?:\s*(\w+)',
            'legal_name': r'Franchise Legal Name.*?(?:generic.*?)?:\s*"?([^"\n]+)"?',
            'trade_name': r'Franchise Trade Name \(DBA\).*?(?:generic.*?)?:\s*"?([^"\n]+)"?',
            'business_address': r'Franchise Business Address.*?(?:generic.*?)?:\s*"?([^"\n]+)"?',
            'contact_email': r'(?:Email|E-mail).*?(?:generic.*?)?:\s*"?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"?',
            'effective_date': r'Effective.*?(?:cell|generic).*?["\s]+(\d{1,2}/\d{1,2}/\d{4})',
            'filing_type': r'Type.*?(?:cell|generic).*?["\s]+([^"\n]+)',
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                if value:
                    metadata[field] = value
        
        # Try alternative selectors for missing fields
        if 'legal_name' not in metadata:
            # Try to get from page title or header
            try:
                title = await self.page.title()
                if title and 'Details' in title:
                    metadata['legal_name'] = title.replace(' Details', '').strip()
            except:
                pass
        
        # Extract states filed
        states_match = re.search(
            r'States Application Filed.*?(?:States Filed.*?)?:(.*?)(?:group|Contact Person)',
            content,
            re.DOTALL | re.IGNORECASE
        )
        
        if states_match:
            states_text = states_match.group(1)
            states = re.findall(r'(?:text|generic):\s*"?([A-Z]{2})"?', states_text)
            metadata['states_filed'] = states
        
        return metadata
    
    async def _download_pdf(self, metadata: Dict[str, Any]) -> tuple[Optional[str], str]:
        """Download PDF from details page.
        
        Args:
            metadata: Extracted metadata for file naming
            
        Returns:
            Tuple of (pdf_path, status)
        """
        try:
            # Look for download button
            download_button = await self.page.query_selector(
                'button:has-text("Download"), input[value*="Download"]'
            )
            
            if not download_button:
                print(f"[{datetime.now()}] No download button found")
                return None, 'skipped'
            
            # Generate filename
            filing_number = metadata.get('filing_number', 'unknown')
            legal_name = metadata.get('legal_name', 'unknown')
            
            # Clean filename
            safe_name = re.sub(r'[^\w\s-]', '', legal_name)
            safe_name = re.sub(r'[-\s]+', '_', safe_name).lower()
            
            filename = f"{filing_number}_{safe_name}.pdf"
            
            # Start download
            async with self.page.expect_download() as download_info:
                await download_button.click()
                download = await download_info.value
            
            # Save to our directory
            save_path = settings.DOWNLOAD_DIR / filename
            await download.save_as(save_path)
            
            print(f"[{datetime.now()}] Downloaded PDF: {filename}")
            
            # Return relative path
            return str(Path(filename)), 'ok'
            
        except Exception as e:
            print(f"[{datetime.now()}] PDF download failed: {e}")
            return None, 'failed'


async def scrape_single_details(browser: Browser, registered_row: WIRegisteredRow) -> Optional[WIDetailsRow]:
    """Scrape details for a single franchise in a new browser context.
    
    Args:
        browser: Browser instance
        registered_row: Registered franchise row
        
    Returns:
        WIDetailsRow with extracted information
    """
    context = await get_context(browser)
    page = await context.new_page()
    
    try:
        scraper = WIDetailsScraper(page)
        result = await with_retry(
            scraper.scrape_details,
            registered_row,
            max_attempts=2,
            delays=[1.0, 2.0]
        )
        return result
    finally:
        await context.close()


async def scrape_wi_details(registered_rows: List[WIRegisteredRow], max_workers: int = None) -> List[WIDetailsRow]:
    """Scrape details for multiple franchises in parallel.
    
    Args:
        registered_rows: List of registered franchise rows
        max_workers: Maximum concurrent scrapers (default from settings)
        
    Returns:
        List of detail rows with all extracted information
    """
    if max_workers is None:
        max_workers = settings.MAX_WORKERS
    
    print(f"[{datetime.now()}] Starting details scraping for {len(registered_rows)} franchises")
    
    browser = await get_browser()
    
    try:
        details_rows = []
        
        # Process in batches
        for i in range(0, len(registered_rows), max_workers):
            batch = registered_rows[i:i + max_workers]
            print(f"[{datetime.now()}] Processing batch {i//max_workers + 1} ({len(batch)} franchises)")
            
            # Create tasks for parallel processing
            tasks = [
                scrape_single_details(browser, registered_row)
                for registered_row in batch
            ]
            
            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, WIDetailsRow):
                    details_rows.append(result)
                elif isinstance(result, Exception):
                    print(f"[{datetime.now()}] Details scraping error: {result}")
            
            # Throttle between batches
            if i + max_workers < len(registered_rows):
                await asyncio.sleep(settings.THROTTLE_SEC)
        
        # Export to CSV
        await export_details_to_csv(details_rows)
        
        print(f"[{datetime.now()}] Details scraping complete. Processed {len(details_rows)} franchises")
        
        return details_rows
        
    finally:
        await browser.close()


async def export_details_to_csv(details_rows: List[WIDetailsRow]):
    """Export detailed franchise information to CSV."""
    output_path = settings.DOWNLOAD_DIR / "wi_details_filings.csv"
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'filing_number', 'status', 'legal_name', 'trade_name', 
            'contact_email', 'pdf_path', 'pdf_status', 'scraped_at'
        ])
        writer.writeheader()
        
        for row in details_rows:
            writer.writerow({
                'filing_number': row.filing_number,
                'status': row.status,
                'legal_name': row.legal_name,
                'trade_name': row.trade_name or '',
                'contact_email': row.contact_email or '',
                'pdf_path': row.pdf_path or '',
                'pdf_status': row.pdf_status,
                'scraped_at': row.scraped_at.isoformat()
            })
    
    print(f"[{datetime.now()}] Exported {len(details_rows)} rows to wi_details_filings.csv")


async def scrape_from_csv(csv_path: Path = None) -> List[WIDetailsRow]:
    """Load registered filings from CSV and scrape details.
    
    Args:
        csv_path: Path to registered filings CSV (default: wi_registered_filings.csv)
        
    Returns:
        List of detail rows with all information
    """
    if csv_path is None:
        csv_path = settings.DOWNLOAD_DIR / "wi_registered_filings.csv"
    
    # Load registered filings
    registered_rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            registered_rows.append(WIRegisteredRow(
                filing_number=row['filing_number'],
                legal_name=row['legal_name'],
                details_url=row['details_url']
            ))
    
    print(f"[{datetime.now()}] Loaded {len(registered_rows)} registered filings from CSV")
    
    # Scrape details
    return await scrape_wi_details(registered_rows)


if __name__ == "__main__":
    # Test the details scraper
    async def test():
        print("Starting Wisconsin Details scraper test...")
        
        # Test with a sample registered row
        test_row = WIRegisteredRow(
            filing_number="12345",
            legal_name="Test Franchise",
            details_url="https://apps.dfi.wi.gov/apps/FranchiseSearch/Details.aspx?id=12345"
        )
        
        details = await scrape_wi_details([test_row], max_workers=1)
        
        if details:
            row = details[0]
            print(f"\nExtracted details:")
            print(f"  Filing Number: {row.filing_number}")
            print(f"  Status: {row.status}")
            print(f"  Legal Name: {row.legal_name}")
            print(f"  Trade Name: {row.trade_name}")
            print(f"  Contact Email: {row.contact_email}")
            print(f"  PDF Path: {row.pdf_path}")
            print(f"  PDF Status: {row.pdf_status}")
    
    asyncio.run(test())