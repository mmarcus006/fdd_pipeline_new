# franchise_scrapers/wi/search.py
"""Wisconsin franchise search module.

Searches for each franchise name and extracts registered filings with details URLs.
"""

import asyncio
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import Page, Browser

from franchise_scrapers.browser import get_browser, get_context, with_retry
from franchise_scrapers.models import WIActiveRow, WIRegisteredRow
from franchise_scrapers.config import settings


class WISearchScraper:
    """Scraper for searching individual franchises."""
    
    SEARCH_URL = "https://apps.dfi.wi.gov/apps/FranchiseSearch/MainSearch.aspx"
    BASE_URL = "https://apps.dfi.wi.gov"
    
    def __init__(self, page: Page):
        self.page = page
        self.registered_rows: List[WIRegisteredRow] = []
    
    async def search_franchise(self, franchise_name: str, filing_number: str) -> Optional[WIRegisteredRow]:
        """Search for a single franchise and extract registered filing.
        
        Args:
            franchise_name: Name to search for
            filing_number: Filing number from active filings
            
        Returns:
            WIRegisteredRow if registered filing found, None otherwise
        """
        print(f"[{datetime.now()}] Searching for: {franchise_name}")
        
        try:
            # Navigate to search page
            await self.page.goto(self.SEARCH_URL, wait_until="networkidle")
            
            # Clear and fill search input
            search_input = await self.page.wait_for_selector("#txtName", timeout=10000)
            await search_input.clear()
            await search_input.fill(franchise_name)
            
            # Click search button
            search_button = await self.page.wait_for_selector("#btnSearch")
            await search_button.click()
            
            # Wait for results
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.5)  # Small delay for complete render
            
            # Look for registered results
            registered_row = await self._find_registered_filing(franchise_name, filing_number)
            
            if registered_row:
                print(f"[{datetime.now()}] Found registered filing for: {franchise_name}")
                return registered_row
            else:
                print(f"[{datetime.now()}] No registered filing found for: {franchise_name}")
                return None
                
        except Exception as e:
            print(f"[{datetime.now()}] Error searching for {franchise_name}: {e}")
            return None
    
    async def _find_registered_filing(self, franchise_name: str, filing_number: str) -> Optional[WIRegisteredRow]:
        """Find registered filing in search results.
        
        Args:
            franchise_name: Franchise name being searched
            filing_number: Filing number to match
            
        Returns:
            WIRegisteredRow if found, None otherwise
        """
        # Look for table rows in search results
        rows = await self.page.query_selector_all("table tr")
        
        for row in rows:
            try:
                # Get row text to check for "Registered" status
                row_text = await row.inner_text()
                
                if "Registered" in row_text:
                    # Look for details link in this row
                    details_link = await row.query_selector('a[href*="details"]')
                    
                    if details_link:
                        href = await details_link.get_attribute("href")
                        if href:
                            # Convert to absolute URL
                            details_url = urljoin(self.BASE_URL, href)
                            
                            # Extract legal name from row (usually first cell)
                            cells = await row.query_selector_all("td")
                            legal_name = franchise_name  # Default
                            
                            if cells and len(cells) > 0:
                                first_cell_text = await cells[0].inner_text()
                                if first_cell_text:
                                    legal_name = first_cell_text.strip()
                            
                            return WIRegisteredRow(
                                filing_number=filing_number,
                                legal_name=legal_name,
                                details_url=details_url
                            )
            except Exception as e:
                print(f"[{datetime.now()}] Error processing row: {e}")
                continue
        
        return None


async def search_single_franchise(browser: Browser, active_row: WIActiveRow) -> Optional[WIRegisteredRow]:
    """Search for a single franchise in a new browser context.
    
    Args:
        browser: Browser instance
        active_row: Active filing row with franchise info
        
    Returns:
        WIRegisteredRow if found, None otherwise
    """
    context = await get_context(browser)
    page = await context.new_page()
    
    try:
        scraper = WISearchScraper(page)
        result = await with_retry(
            scraper.search_franchise,
            active_row.legal_name,
            active_row.filing_number,
            max_attempts=2,
            delays=[1.0, 2.0]
        )
        return result
    finally:
        await context.close()


async def search_wi_franchises(active_rows: List[WIActiveRow], max_workers: int = None) -> List[WIRegisteredRow]:
    """Search for multiple franchises in parallel.
    
    Args:
        active_rows: List of active filing rows to search
        max_workers: Maximum concurrent searches (default from settings)
        
    Returns:
        List of registered franchise rows
    """
    if max_workers is None:
        max_workers = settings.MAX_WORKERS
    
    print(f"[{datetime.now()}] Starting parallel search with {max_workers} workers for {len(active_rows)} franchises")
    
    browser = await get_browser()
    
    try:
        # Process franchises in batches
        registered_rows = []
        
        for i in range(0, len(active_rows), max_workers):
            batch = active_rows[i:i + max_workers]
            print(f"[{datetime.now()}] Processing batch {i//max_workers + 1} ({len(batch)} franchises)")
            
            # Create tasks for parallel processing
            tasks = [
                search_single_franchise(browser, active_row)
                for active_row in batch
            ]
            
            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, WIRegisteredRow):
                    registered_rows.append(result)
                elif isinstance(result, Exception):
                    print(f"[{datetime.now()}] Search error: {result}")
            
            # Throttle between batches
            if i + max_workers < len(active_rows):
                await asyncio.sleep(settings.THROTTLE_SEC)
        
        # Export to CSV
        await export_registered_to_csv(registered_rows)
        
        print(f"[{datetime.now()}] Search complete. Found {len(registered_rows)} registered franchises")
        
        return registered_rows
        
    finally:
        await browser.close()


async def export_registered_to_csv(registered_rows: List[WIRegisteredRow]):
    """Export registered franchise rows to CSV."""
    output_path = settings.DOWNLOAD_DIR / "wi_registered_filings.csv"
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['filing_number', 'legal_name', 'details_url'])
        writer.writeheader()
        
        for row in registered_rows:
            writer.writerow({
                'filing_number': row.filing_number,
                'legal_name': row.legal_name,
                'details_url': str(row.details_url)
            })
    
    print(f"[{datetime.now()}] Exported {len(registered_rows)} rows to wi_registered_filings.csv")


async def search_from_csv(csv_path: Path = None) -> List[WIRegisteredRow]:
    """Load active filings from CSV and search for registered ones.
    
    Args:
        csv_path: Path to active filings CSV (default: wi_active_filings.csv)
        
    Returns:
        List of registered franchise rows
    """
    if csv_path is None:
        csv_path = settings.DOWNLOAD_DIR / "wi_active_filings.csv"
    
    # Load active filings
    active_rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            active_rows.append(WIActiveRow(
                legal_name=row['legal_name'],
                filing_number=row['filing_number']
            ))
    
    print(f"[{datetime.now()}] Loaded {len(active_rows)} active filings from CSV")
    
    # Search for registered filings
    return await search_wi_franchises(active_rows)


if __name__ == "__main__":
    # Test the search module
    async def test():
        print("Starting Wisconsin Search test...")
        
        # Test with a few sample franchises
        test_rows = [
            WIActiveRow(legal_name="SUBWAY", filing_number="12345"),
            WIActiveRow(legal_name="MCDONALD'S", filing_number="67890"),
        ]
        
        registered = await search_wi_franchises(test_rows, max_workers=2)
        
        print(f"\nFound {len(registered)} registered franchises:")
        for row in registered:
            print(f"  - {row.legal_name} ({row.filing_number}): {row.details_url}")
    
    asyncio.run(test())