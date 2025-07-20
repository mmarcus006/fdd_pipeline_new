# franchise_scrapers/wi/test_scraper.py
"""Test script for Wisconsin franchise scrapers.

Provides various test scenarios for the WI scraping modules.
"""

import asyncio
from pathlib import Path
from datetime import datetime

from franchise_scrapers.wi import (
    scrape_wi_active_filings,
    search_wi_franchises,
    scrape_wi_details,
    WIActiveScraper,
    WISearchScraper,
    WIDetailsScraper
)
from franchise_scrapers.models import WIActiveRow, WIRegisteredRow
from franchise_scrapers.browser import get_browser, get_context
from franchise_scrapers.config import settings


async def test_active_filings():
    """Test active filings extraction."""
    print("\n" + "="*60)
    print("Test 1: Active Filings Extraction")
    print("="*60)
    
    try:
        # Test basic extraction
        franchise_names = await scrape_wi_active_filings()
        
        print(f"✓ Successfully extracted {len(franchise_names)} active filings")
        print(f"\nFirst 5 franchises:")
        for i, name in enumerate(franchise_names[:5]):
            print(f"  {i+1}. {name}")
        
        # Check CSV output
        csv_path = settings.DOWNLOAD_DIR / "wi_active_filings.csv"
        if csv_path.exists():
            print(f"\n✓ CSV file created: {csv_path}")
            
            # Load and verify CSV
            import csv
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                print(f"  - Rows in CSV: {len(rows)}")
                print(f"  - Columns: {reader.fieldnames}")
        else:
            print(f"\n✗ CSV file not found: {csv_path}")
            
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def test_single_search():
    """Test searching for a single franchise."""
    print("\n" + "="*60)
    print("Test 2: Single Franchise Search")
    print("="*60)
    
    browser = await get_browser()
    context = await get_context(browser)
    page = await context.new_page()
    
    try:
        # Create test franchise
        test_franchise = WIActiveRow(
            legal_name="SUBWAY",
            filing_number="12345"
        )
        
        print(f"Testing search for: {test_franchise.legal_name}")
        
        scraper = WISearchScraper(page)
        result = await scraper.search_franchise(
            test_franchise.legal_name,
            test_franchise.filing_number
        )
        
        if result:
            print(f"\n✓ Found registered franchise:")
            print(f"  - Legal Name: {result.legal_name}")
            print(f"  - Filing Number: {result.filing_number}")
            print(f"  - Details URL: {result.details_url}")
        else:
            print(f"\n✗ No registered franchise found")
            
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await context.close()
        await browser.close()


async def test_batch_search():
    """Test searching for multiple franchises."""
    print("\n" + "="*60)
    print("Test 3: Batch Franchise Search")
    print("="*60)
    
    try:
        # Create test franchises
        test_franchises = [
            WIActiveRow(legal_name="SUBWAY", filing_number="10001"),
            WIActiveRow(legal_name="MCDONALD'S", filing_number="10002"),
            WIActiveRow(legal_name="BURGER KING", filing_number="10003"),
        ]
        
        print(f"Testing batch search for {len(test_franchises)} franchises")
        
        # Run search with limited workers
        registered = await search_wi_franchises(test_franchises, max_workers=2)
        
        print(f"\n✓ Search completed:")
        print(f"  - Total searched: {len(test_franchises)}")
        print(f"  - Registered found: {len(registered)}")
        
        if registered:
            print(f"\nRegistered franchises:")
            for row in registered:
                print(f"  - {row.legal_name}: {row.details_url}")
        
        # Check CSV output
        csv_path = settings.DOWNLOAD_DIR / "wi_registered_filings.csv"
        if csv_path.exists():
            print(f"\n✓ CSV file created: {csv_path}")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def test_details_scraping():
    """Test details page scraping."""
    print("\n" + "="*60)
    print("Test 4: Details Page Scraping")
    print("="*60)
    
    browser = await get_browser()
    context = await get_context(browser)
    page = await context.new_page()
    
    try:
        # Create test registered franchise
        test_franchise = WIRegisteredRow(
            filing_number="12345",
            legal_name="Test Franchise",
            details_url="https://apps.dfi.wi.gov/apps/FranchiseSearch/Details.aspx?id=12345"
        )
        
        print(f"Testing details scraping for: {test_franchise.legal_name}")
        print(f"URL: {test_franchise.details_url}")
        
        scraper = WIDetailsScraper(page)
        result = await scraper.scrape_details(test_franchise)
        
        if result:
            print(f"\n✓ Details extracted:")
            print(f"  - Filing Number: {result.filing_number}")
            print(f"  - Status: {result.status}")
            print(f"  - Legal Name: {result.legal_name}")
            print(f"  - Trade Name: {result.trade_name or 'N/A'}")
            print(f"  - Contact Email: {result.contact_email or 'N/A'}")
            print(f"  - PDF Status: {result.pdf_status}")
            print(f"  - PDF Path: {result.pdf_path or 'N/A'}")
        else:
            print(f"\n✗ No details extracted")
            
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await context.close()
        await browser.close()


async def test_full_pipeline():
    """Test the full pipeline with a small sample."""
    print("\n" + "="*60)
    print("Test 5: Full Pipeline (Limited Sample)")
    print("="*60)
    
    try:
        from franchise_scrapers.wi.scraper import run_wi_scraper
        
        print("Running full pipeline with limit=3...")
        
        stats = await run_wi_scraper(
            max_workers=2,
            limit=3,
            resume_from_step=1
        )
        
        print(f"\n✓ Pipeline completed successfully")
        print(f"  - Runtime: {stats['runtime']}")
        print(f"  - Errors: {len(stats['errors'])}")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def test_resume_capability():
    """Test resuming from different steps."""
    print("\n" + "="*60)
    print("Test 6: Resume Capability")
    print("="*60)
    
    try:
        # Check if we have existing CSV files
        active_csv = settings.DOWNLOAD_DIR / "wi_active_filings.csv"
        registered_csv = settings.DOWNLOAD_DIR / "wi_registered_filings.csv"
        
        if active_csv.exists():
            print(f"✓ Active filings CSV exists")
            
            # Test resuming from step 2
            from franchise_scrapers.wi.scraper import run_wi_scraper
            
            print("\nTesting resume from step 2 (search)...")
            stats = await run_wi_scraper(
                max_workers=2,
                limit=2,
                resume_from_step=2
            )
            
            print(f"✓ Successfully resumed from step 2")
            
        else:
            print(f"✗ No existing CSV files to test resume functionality")
            print(f"  Run test_full_pipeline() first to generate CSV files")
            
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all tests."""
    print(f"\nWisconsin Scraper Test Suite")
    print(f"Started at: {datetime.now()}")
    print(f"Download directory: {settings.DOWNLOAD_DIR}")
    
    # Create download directory if it doesn't exist
    settings.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Run tests
    tests = [
        ("Active Filings", test_active_filings),
        ("Single Search", test_single_search),
        ("Batch Search", test_batch_search),
        ("Details Scraping", test_details_scraping),
        ("Full Pipeline", test_full_pipeline),
        ("Resume Capability", test_resume_capability),
    ]
    
    print(f"\nRunning {len(tests)} tests...\n")
    
    for i, (name, test_func) in enumerate(tests):
        print(f"\n[Test {i+1}/{len(tests)}] {name}")
        
        try:
            await test_func()
        except Exception as e:
            print(f"\n✗ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
        
        # Small delay between tests
        await asyncio.sleep(1)
    
    print(f"\n\nTest suite completed at: {datetime.now()}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Wisconsin Scrapers")
    parser.add_argument("--test", choices=[
        "active", "search", "batch", "details", "full", "resume", "all"
    ], default="all", help="Which test to run")
    
    args = parser.parse_args()
    
    if args.test == "all":
        asyncio.run(main())
    elif args.test == "active":
        asyncio.run(test_active_filings())
    elif args.test == "search":
        asyncio.run(test_single_search())
    elif args.test == "batch":
        asyncio.run(test_batch_search())
    elif args.test == "details":
        asyncio.run(test_details_scraping())
    elif args.test == "full":
        asyncio.run(test_full_pipeline())
    elif args.test == "resume":
        asyncio.run(test_resume_capability())