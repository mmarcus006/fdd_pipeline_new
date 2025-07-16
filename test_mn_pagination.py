#!/usr/bin/env python3
"""Test Minnesota scraper pagination functionality."""

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


async def test_pagination():
    """Test the full pagination functionality of Minnesota scraper."""
    print("🚀 Testing Minnesota CARDS scraper with FULL PAGINATION...")

    try:
        # Create scraper with visible browser for debugging
        async with create_scraper(
            MinnesotaScraper, headless=False, timeout=60000
        ) as scraper:
            print("✅ Scraper initialized successfully")

            # Test the full discovery process (including pagination)
            print("🔄 Starting full document discovery with pagination...")
            print("⚠️  This will take several minutes as it processes multiple pages...")

            # Use the full discover_documents method which includes pagination
            documents = await scraper.discover_documents()

            print(f"\n🎉 PAGINATION TEST COMPLETE!")
            print(f"📄 Total documents found: {len(documents)}")

            # Analyze the results
            years = {}
            franchisors = set()

            for doc in documents:
                year = doc.additional_metadata.get("year", "Unknown")
                years[year] = years.get(year, 0) + 1
                franchisors.add(doc.additional_metadata.get("franchisor", "Unknown"))

            print(f"\n📊 RESULTS ANALYSIS:")
            print(f"   📅 Documents by year:")
            for year, count in sorted(years.items()):
                print(f"      {year}: {count} documents")
            print(f"   🏢 Unique franchisors: {len(franchisors)}")

            # Show sample documents from different pages
            print(f"\n📋 SAMPLE DOCUMENTS:")
            sample_indices = (
                [0, 499, 999, len(documents) - 1]
                if len(documents) > 1000
                else [0, len(documents) // 2, len(documents) - 1]
            )

            for i, idx in enumerate(sample_indices):
                if idx < len(documents):
                    doc = documents[idx]
                    print(f"   Document {idx+1} (approx page {idx//500 + 1}):")
                    print(f"      Franchise: {doc.franchise_name}")
                    print(
                        f"      Franchisor: {doc.additional_metadata.get('franchisor', 'N/A')}"
                    )
                    print(f"      Year: {doc.additional_metadata.get('year', 'N/A')}")
                    print(
                        f"      Discovery method: {doc.additional_metadata.get('discovery_method', 'N/A')}"
                    )

            # Save results
            results = []
            for doc in documents:
                results.append(
                    {
                        "franchise_name": doc.franchise_name,
                        "franchisor": doc.additional_metadata.get("franchisor"),
                        "year": doc.additional_metadata.get("year"),
                        "document_type": doc.document_type,
                        "filing_number": doc.filing_number,
                        "download_url": doc.download_url,
                        "document_id": doc.additional_metadata.get("document_id"),
                        "discovery_method": doc.additional_metadata.get(
                            "discovery_method"
                        ),
                    }
                )

            with open("mn_pagination_results.json", "w") as f:
                json.dump(results, f, indent=2)

            print(f"\n💾 Full results saved to mn_pagination_results.json")
            print(f"✅ Pagination test completed successfully!")

            # Verify we got more than just the first page
            if len(documents) > 500:
                print(
                    f"🎯 SUCCESS: Pagination worked! Got {len(documents)} documents (more than 500)"
                )

                # Check if we have documents from different discovery methods
                methods = set(
                    doc.additional_metadata.get("discovery_method") for doc in documents
                )
                print(f"📊 Discovery methods used: {methods}")

                if "cards_api" in methods:
                    print("✅ API pagination method was used successfully")
                else:
                    print(
                        "⚠️  Only table method was used - API pagination may not have worked"
                    )
            else:
                print(
                    f"⚠️  Only got {len(documents)} documents - pagination may not be working"
                )

            return documents

    except Exception as e:
        print(f"❌ Pagination test failed: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(test_pagination())
