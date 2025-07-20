# franchise_scrapers/mn/test_scraper.py
"""Test script for Minnesota CARDS scraper."""

import asyncio
from datetime import datetime

from .scraper import scrape_minnesota


async def test_minnesota_scraper():
    """Run a quick test of the Minnesota scraper."""
    print("\n" + "="*60)
    print("MINNESOTA SCRAPER TEST")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")
    
    try:
        # Test scraping first page only (no downloads)
        print("Test 1: Scrape first page only (no PDF downloads)")
        print("-" * 40)
        
        rows = await scrape_minnesota(
            download_pdfs_flag=False,
            max_pages=1  # Only first page for testing
        )
        
        print(f"\n✓ Test completed successfully!")
        print(f"  - Found {len(rows)} Clean FDD documents")
        
        if rows:
            print(f"\nFirst 5 entries:")
            for i, row in enumerate(rows[:5], 1):
                print(f"\n  {i}. {row.legal_name}")
                print(f"     Document ID: {row.document_id}")
                print(f"     PDF URL: {row.pdf_url}")
                print(f"     Scraped at: {row.scraped_at}")
        
        # Check CSV export
        import os
        if os.path.exists("mn_clean_fdd.csv"):
            print(f"\n✓ CSV file created: mn_clean_fdd.csv")
            
            # Show first few lines
            with open("mn_clean_fdd.csv", 'r', encoding='utf-8') as f:
                lines = f.readlines()[:6]  # Header + 5 rows
                print("\nCSV Preview:")
                print("-" * 40)
                for line in lines:
                    print(line.rstrip())
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_minnesota_scraper())