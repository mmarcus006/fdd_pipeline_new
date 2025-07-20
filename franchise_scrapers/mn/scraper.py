# franchise_scrapers/mn/scraper.py
"""Minnesota CARDS portal scraper for Clean FDD documents."""

import csv
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..browser import get_browser, get_context, with_retry
from ..config import settings
from ..models import CleanFDDRow
from .parsers import (
    parse_row,
    extract_document_id,
    sanitize_filename,
    clean_text,
    is_valid_fdd,
)


# Minnesota CARDS portal URLs
BASE_URL = "https://www.cards.commerce.state.mn.us"
SEARCH_URL = "https://www.cards.commerce.state.mn.us/franchise-registrations?doSearch=true&documentTitle=&franchisor=&franchiseName=&year=&fileNumber=&documentType=Clean+FDD&content="


async def navigate_to_search(page: Page) -> None:
    """Navigate to the Minnesota CARDS search page with Clean FDD filter.
    
    Args:
        page: Playwright page instance
    """
    print("Navigating to Minnesota CARDS portal...")
    await page.goto(SEARCH_URL, wait_until="networkidle")
    
    # Wait for results table to load
    try:
        await page.wait_for_selector("#results", timeout=10000)
        print("✓ Successfully loaded CARDS search page")
    except PlaywrightTimeout:
        print("⚠ Results table did not load immediately")


async def extract_table_data(page: Page) -> List[Dict[str, Any]]:
    """Extract all data from the current results table.
    
    Args:
        page: Playwright page instance
        
    Returns:
        List of parsed row data dictionaries
    """
    rows = await page.query_selector_all("#results tr")
    
    if not rows:
        print("No rows found in results table")
        return []
    
    print(f"Found {len(rows)} rows in table")
    data = []
    
    for i, row in enumerate(rows):
        # Parse each row
        row_data = await parse_row(row)
        
        if row_data:
            # Add row number for debugging
            row_data['row_number'] = i
            data.append(row_data)
    
    print(f"✓ Extracted {len(data)} valid Clean FDD entries")
    return data


async def click_load_more(page: Page) -> bool:
    """Click the 'Load more' button if available and enabled.
    
    Args:
        page: Playwright page instance
        
    Returns:
        True if button was clicked, False if no more pages
    """
    # Try multiple selectors for the load more button
    selectors = [
        "#pagination button.btn.btn-primary",  # From specs
        'button:has-text("Load more")',
        "#main-content > form ul button",
        'button:has-text("Load More")',
        'button:has-text("LOAD MORE")',
        'a:has-text("Load more")',
        'button[aria-label*="load more" i]',
        ".load-more-button",
        "button.load-more",
    ]
    
    for selector in selectors:
        try:
            button = await page.query_selector(selector)
            if button and await button.is_visible():
                # Check if button is disabled
                is_disabled = await button.get_attribute("disabled")
                if is_disabled:
                    print("Load more button is disabled - reached end")
                    return False
                
                # Click the button
                print(f"Clicking load more button (selector: {selector})")
                await button.click()
                
                # Wait for new content to load
                await asyncio.sleep(2)
                return True
                
        except Exception:
            continue
    
    print("No load more button found")
    return False


async def scrape_all_pages(page: Page, max_pages: int = 50) -> List[Dict[str, Any]]:
    """Scrape all pages of results by clicking 'Load more' button.
    
    Args:
        page: Playwright page instance
        max_pages: Maximum number of pages to load
        
    Returns:
        List of all extracted data
    """
    all_data = []
    page_num = 1
    
    print(f"\nStarting pagination (max {max_pages} pages)...")
    
    while page_num <= max_pages:
        print(f"\n--- Page {page_num} ---")
        
        # Get current count before extraction
        current_count = len(all_data)
        
        # Extract all data from current table
        current_data = await extract_table_data(page)
        
        # Only add new entries (avoid duplicates)
        if current_count > 0:
            new_data = current_data[current_count:]
            if new_data:
                all_data.extend(new_data)
                print(f"Added {len(new_data)} new entries")
            else:
                print("No new entries found")
        else:
            all_data = current_data
        
        # Try to load more
        if not await click_load_more(page):
            print("\n✓ Reached end of results")
            break
        
        # Wait for new content
        try:
            # Wait for table to have more rows than before
            await page.wait_for_function(
                f"document.querySelectorAll('#results tr').length > {len(current_data)}",
                timeout=10000
            )
        except PlaywrightTimeout:
            print("⚠ Timeout waiting for new content")
            break
        
        page_num += 1
        
        # Small delay to be respectful
        await asyncio.sleep(settings.THROTTLE_SEC)
    
    print(f"\n✓ Pagination complete: {page_num} pages processed")
    return all_data


def convert_to_clean_fdd_rows(data: List[Dict[str, Any]]) -> List[CleanFDDRow]:
    """Convert raw scraped data to CleanFDDRow models.
    
    Args:
        data: List of raw data dictionaries
        
    Returns:
        List of CleanFDDRow instances
    """
    rows = []
    scraped_at = datetime.utcnow()
    
    for item in data:
        # Extract document ID
        document_id = extract_document_id(item['download_url'])
        if not document_id:
            print(f"⚠ Skipping row - no document ID found in URL: {item['download_url']}")
            continue
        
        # Make URL absolute
        pdf_url = item['download_url']
        if pdf_url.startswith('/'):
            pdf_url = urljoin(BASE_URL, pdf_url)
        elif not pdf_url.startswith('http'):
            pdf_url = urljoin(BASE_URL, pdf_url)
        
        # Create CleanFDDRow
        row = CleanFDDRow(
            document_id=document_id,
            legal_name=clean_text(item['franchisor']),
            pdf_url=pdf_url,
            scraped_at=scraped_at,
        )
        
        rows.append(row)
    
    return rows


async def download_pdf(page: Page, row: CleanFDDRow, download_dir: Path) -> CleanFDDRow:
    """Download a PDF file with retry logic.
    
    Args:
        page: Playwright page instance
        row: CleanFDDRow with download URL
        download_dir: Directory to save PDFs
        
    Returns:
        Updated CleanFDDRow with download status
    """
    # Create filename
    filename = f"{sanitize_filename(row.legal_name)}_{row.document_id}.pdf"
    filepath = download_dir / filename
    
    try:
        print(f"  Downloading: {row.legal_name}...")
        
        # Start download
        async with page.expect_download() as download_info:
            await page.goto(row.pdf_url)
            download = await download_info.value
        
        # Save to our location
        await download.save_as(filepath)
        
        # Verify file exists and has content
        if filepath.exists() and filepath.stat().st_size > 0:
            row.pdf_status = "ok"
            row.pdf_path = str(filepath.relative_to(settings.DOWNLOAD_DIR))
            print(f"  ✓ Downloaded: {filename}")
        else:
            row.pdf_status = "failed"
            print(f"  ✗ Download failed: empty file")
            
    except Exception as e:
        row.pdf_status = "failed"
        print(f"  ✗ Download failed: {e}")
    
    return row


async def download_pdfs(rows: List[CleanFDDRow], page: Page) -> List[CleanFDDRow]:
    """Download PDFs for all rows with retry logic.
    
    Args:
        rows: List of CleanFDDRow instances
        page: Playwright page instance
        
    Returns:
        Updated list with download status
    """
    print(f"\nStarting PDF downloads for {len(rows)} documents...")
    
    # Create download directory
    mn_downloads = settings.DOWNLOAD_DIR / "mn"
    mn_downloads.mkdir(exist_ok=True)
    
    for i, row in enumerate(rows, 1):
        print(f"\n[{i}/{len(rows)}] {row.legal_name}")
        
        # Download with retry
        updated_row = await with_retry(
            download_pdf,
            page,
            row,
            mn_downloads,
            max_attempts=settings.PDF_RETRY_MAX,
            delays=settings.PDF_RETRY_BACKOFF
        )
        
        # Update the row in place
        rows[i-1] = updated_row
        
        # Throttle between downloads
        if i < len(rows):
            await asyncio.sleep(settings.THROTTLE_SEC)
    
    # Summary
    success_count = sum(1 for r in rows if r.pdf_status == "ok")
    print(f"\n✓ Download complete: {success_count}/{len(rows)} successful")
    
    return rows


def export_to_csv(rows: List[CleanFDDRow], output_file: str = "mn_clean_fdd.csv") -> None:
    """Export CleanFDDRow data to CSV file.
    
    Args:
        rows: List of CleanFDDRow instances
        output_file: Output CSV filename
    """
    output_path = Path(output_file)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow([
            'document_id',
            'legal_name',
            'pdf_url',
            'scraped_at',
            'pdf_status',
            'pdf_path'
        ])
        
        # Write data
        for row in rows:
            writer.writerow([
                row.document_id,
                row.legal_name,
                row.pdf_url,
                row.scraped_at.isoformat(),
                row.pdf_status or '',
                row.pdf_path or ''
            ])
    
    print(f"\n✓ Exported {len(rows)} rows to {output_path}")


async def scrape_minnesota(download_pdfs_flag: bool = False, max_pages: int = 50) -> List[CleanFDDRow]:
    """Main scraping function for Minnesota CARDS portal.
    
    Args:
        download_pdfs_flag: Whether to download PDFs
        max_pages: Maximum pages to scrape
        
    Returns:
        List of CleanFDDRow instances
    """
    print("\n" + "="*60)
    print("MINNESOTA CARDS SCRAPER")
    print("="*60 + "\n")
    
    browser = await get_browser()
    context = await get_context(browser)
    page = await context.new_page()
    
    try:
        # Navigate to search page
        await navigate_to_search(page)
        
        # Scrape all pages
        raw_data = await scrape_all_pages(page, max_pages)
        
        print(f"\nTotal documents found: {len(raw_data)}")
        
        # Convert to CleanFDDRow models
        rows = convert_to_clean_fdd_rows(raw_data)
        print(f"Valid Clean FDD rows: {len(rows)}")
        
        # Optionally download PDFs
        if download_pdfs_flag and rows:
            rows = await download_pdfs(rows, page)
        
        # Export to CSV
        export_to_csv(rows)
        
        return rows
        
    finally:
        await page.close()
        await context.close()
        await browser.close()


# CLI entry point
async def main():
    """CLI entry point for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Minnesota CARDS portal")
    parser.add_argument(
        "--download-pdfs",
        action="store_true",
        help="Download PDF files"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum pages to scrape (default: 50)"
    )
    
    args = parser.parse_args()
    
    # Run scraper
    rows = await scrape_minnesota(
        download_pdfs_flag=args.download_pdfs,
        max_pages=args.max_pages
    )
    
    print(f"\n✓ Scraping complete! Found {len(rows)} Clean FDD documents")


if __name__ == "__main__":
    asyncio.run(main())