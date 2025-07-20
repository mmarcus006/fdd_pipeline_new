# franchise_scrapers/wi/active.py
"""Wisconsin Active Filings scraper module.

Extracts franchise names from the active filings table at:
https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx
"""

import asyncio
import csv
from pathlib import Path
from datetime import datetime
from typing import List
from playwright.async_api import Page

from franchise_scrapers.browser import get_browser, get_context
from franchise_scrapers.models import WIActiveRow
from franchise_scrapers.config import settings


class WIActiveScraper:
    """Scraper for Wisconsin active filings table."""
    
    BASE_URL = "https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx"
    TABLE_SELECTOR = "#ctl00_contentPlaceholder_grdActiveFilings"
    
    def __init__(self, page: Page):
        self.page = page
        self.rows: List[WIActiveRow] = []
    
    async def scrape(self) -> List[str]:
        """Scrape active filings and return list of franchise names.
        
        Returns:
            List of franchise names for next processing step
        """
        print(f"[{datetime.now()}] Navigating to active filings page...")
        await self.page.goto(self.BASE_URL, wait_until="networkidle")
        
        # Wait for table to load
        print(f"[{datetime.now()}] Waiting for active filings table...")
        await self.page.wait_for_selector(self.TABLE_SELECTOR, timeout=30000)
        
        # Extract table rows
        print(f"[{datetime.now()}] Extracting table data...")
        table_rows = await self._extract_table_rows()
        
        print(f"[{datetime.now()}] Found {len(table_rows)} active filings")
        
        # Convert to WIActiveRow models
        franchise_names = []
        for row_data in table_rows:
            if len(row_data) >= 2:  # Need at least 2 columns
                active_row = WIActiveRow(
                    legal_name=row_data[0].strip(),
                    filing_number=row_data[1].strip()
                )
                self.rows.append(active_row)
                franchise_names.append(active_row.legal_name)
        
        # Export to CSV
        await self._export_to_csv()
        
        print(f"[{datetime.now()}] Exported {len(self.rows)} rows to wi_active_filings.csv")
        
        return franchise_names
    
    async def _extract_table_rows(self) -> List[List[str]]:
        """Extract rows from the active filings table.
        
        Returns:
            List of row data (each row is a list of cell values)
        """
        # Get all table rows except header
        rows = await self.page.query_selector_all(f"{self.TABLE_SELECTOR} tr")
        
        table_data = []
        for i, row in enumerate(rows):
            if i == 0:  # Skip header row
                continue
            
            # Get all cells in this row
            cells = await row.query_selector_all("td")
            row_data = []
            
            for cell in cells:
                text = await cell.inner_text()
                row_data.append(text.strip())
            
            if row_data:  # Only add non-empty rows
                table_data.append(row_data)
        
        return table_data
    
    async def _export_to_csv(self):
        """Export scraped rows to CSV file."""
        output_path = settings.DOWNLOAD_DIR / "wi_active_filings.csv"
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['legal_name', 'filing_number'])
            writer.writeheader()
            
            for row in self.rows:
                writer.writerow({
                    'legal_name': row.legal_name,
                    'filing_number': row.filing_number
                })


async def scrape_wi_active_filings() -> List[str]:
    """Main entry point for scraping Wisconsin active filings.
    
    Returns:
        List of franchise names for further processing
    """
    browser = await get_browser()
    context = await get_context(browser)
    page = await context.new_page()
    
    try:
        scraper = WIActiveScraper(page)
        franchise_names = await scraper.scrape()
        return franchise_names
    finally:
        await context.close()
        await browser.close()


if __name__ == "__main__":
    # Test the scraper
    async def test():
        print("Starting Wisconsin Active Filings scraper test...")
        franchise_names = await scrape_wi_active_filings()
        print(f"\nExtracted {len(franchise_names)} franchise names:")
        for i, name in enumerate(franchise_names[:5]):  # Show first 5
            print(f"  {i+1}. {name}")
        if len(franchise_names) > 5:
            print(f"  ... and {len(franchise_names) - 5} more")
    
    asyncio.run(test())