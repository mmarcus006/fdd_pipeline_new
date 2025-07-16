#!/usr/bin/env python3
"""Simple test for Minnesota scraper without full config system."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set minimal environment variables to avoid config issues
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "placeholder-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "placeholder-service-key")
os.environ.setdefault("GDRIVE_CREDS_JSON", "/tmp/placeholder.json")
os.environ.setdefault("GDRIVE_FOLDER_ID", "placeholder-folder-id")
os.environ.setdefault("GEMINI_API_KEY", "placeholder-gemini-key")
os.environ.setdefault("MINERU_DEVICE", "cpu")
os.environ.setdefault("MINERU_BATCH_SIZE", "2")

# Now import the scraper
from tasks.minnesota_scraper import MinnesotaScraper
from tasks.web_scraping import create_scraper


async def simple_test():
    """Simple test of Minnesota scraper."""
    print("🚀 Testing Minnesota CARDS scraper (simple version)...")

    try:
        # Create scraper with visible browser for debugging
        async with create_scraper(
            MinnesotaScraper, headless=False, timeout=60000
        ) as scraper:
            print("✅ Scraper initialized successfully")

            # Test just the first page discovery
            print("🔍 Discovering documents from first page...")

            # Navigate to the CARDS portal
            await scraper.safe_navigate(scraper.SEARCH_URL)
            print("✅ Successfully navigated to CARDS portal")

            # Wait a bit for the page to fully load
            await asyncio.sleep(3)

            # Check if results table exists
            results_table = await scraper.page.query_selector("#results")
            if results_table:
                print("✅ Found results table")

                # Count rows
                rows = await scraper.page.query_selector_all("#results tr")
                print(f"📊 Found {len(rows)} rows in results table")

                # Check if there's a "no results" message
                page_text = await scraper.page.inner_text("body")
                if (
                    "no results" in page_text.lower()
                    or "0 results" in page_text.lower()
                ):
                    print("ℹ️ Page indicates no results found")

                # Extract documents from current page
                documents = await scraper._extract_cards_results()
                print(f"📄 Found {len(documents)} documents on first page")

                # If no documents found, let's debug the table structure
                if len(documents) == 0 and len(rows) > 1:
                    print("🔍 Debugging table structure...")

                    # Check header row
                    header_row = rows[0]
                    header_cells = await header_row.query_selector_all("th, td")
                    print(f"   Header row: {len(header_cells)} cells")
                    for j, cell in enumerate(header_cells):
                        text = await cell.inner_text()
                        print(f"     Header {j}: '{text.strip()}'")

                    # Check first few data rows
                    for i, row in enumerate(rows[1:4]):  # Check first 3 data rows
                        cells = await row.query_selector_all("td")
                        print(f"   Row {i+1}: {len(cells)} cells")
                        if cells:
                            for j, cell in enumerate(cells):  # All cells
                                text = await cell.inner_text()
                                print(f"     Cell {j}: '{text.strip()[:30]}...'")

                                # Check for download links
                                link = await cell.query_selector("a")
                                if link:
                                    href = await link.get_attribute("href")
                                    print(f"       -> Link: {href}")
            else:
                print("❌ Results table not found")
                # Let's see what's on the page
                page_title = await scraper.page.title()
                print(f"📄 Page title: {page_title}")

                # Check for any tables
                all_tables = await scraper.page.query_selector_all("table")
                print(f"📊 Found {len(all_tables)} tables on page")

                # Check page content
                page_text = await scraper.page.inner_text("body")
                print(f"📝 Page content preview: {page_text[:200]}...")

            # Display first few documents
            for i, doc in enumerate(documents[:3]):
                print(f"\n📋 Document {i+1}:")
                print(f"   Franchise: {doc.franchise_name}")
                print(
                    f"   Franchisor: {doc.additional_metadata.get('franchisor', 'N/A')}"
                )
                print(f"   Year: {doc.additional_metadata.get('year', 'N/A')}")
                print(f"   Document Type: {doc.document_type}")
                print(f"   Download URL: {doc.download_url}")

            # Save results
            results = []
            for doc in documents:
                results.append(
                    {
                        "franchise_name": doc.franchise_name,
                        "franchisor": doc.additional_metadata.get("franchisor"),
                        "year": doc.additional_metadata.get("year"),
                        "document_type": doc.document_type,
                        "download_url": doc.download_url,
                        "document_id": doc.additional_metadata.get("document_id"),
                    }
                )

            with open("simple_mn_results.json", "w") as f:
                json.dump(results, f, indent=2)

            print(f"\n💾 Results saved to simple_mn_results.json")
            print(f"✅ Simple test completed! Found {len(documents)} documents")

            return documents

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(simple_test())
