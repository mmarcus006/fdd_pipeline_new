#!/usr/bin/env python3
"""Test script for Minnesota CARDS scraper."""

import asyncio
import json
from tasks.minnesota_scraper import MinnesotaScraper
from tasks.web_scraping import create_scraper


async def test_minnesota_scraper():
    """Test the Minnesota CARDS scraper."""
    print("🚀 Testing Minnesota CARDS scraper...")

    try:
        # Create and test the scraper
        async with create_scraper(
            MinnesotaScraper, headless=False, timeout=60000
        ) as scraper:
            print("✅ Scraper initialized successfully")

            # Discover documents
            print("🔍 Discovering documents from CARDS portal...")
            documents = await scraper.discover_documents()

            print(f"📄 Found {len(documents)} documents")

            # Display first few documents
            for i, doc in enumerate(documents[:5]):
                print(f"\n📋 Document {i+1}:")
                print(f"   Franchise: {doc.franchise_name}")
                print(
                    f"   Franchisor: {doc.additional_metadata.get('franchisor', 'N/A')}"
                )
                print(f"   Year: {doc.additional_metadata.get('year', 'N/A')}")
                print(f"   File Number: {doc.filing_number or 'N/A'}")
                print(f"   Document Type: {doc.document_type}")
                print(f"   Download URL: {doc.download_url}")
                print(
                    f"   Document ID: {doc.additional_metadata.get('document_id', 'N/A')}"
                )

            # Save results to file
            results = []
            for doc in documents:
                results.append(
                    {
                        "franchise_name": doc.franchise_name,
                        "franchisor": doc.additional_metadata.get("franchisor"),
                        "year": doc.additional_metadata.get("year"),
                        "filing_number": doc.filing_number,
                        "document_type": doc.document_type,
                        "download_url": doc.download_url,
                        "document_id": doc.additional_metadata.get("document_id"),
                        "source_url": doc.source_url,
                    }
                )

            with open("minnesota_scraper_results.json", "w") as f:
                json.dump(results, f, indent=2)

            print(f"\n💾 Results saved to minnesota_scraper_results.json")
            print(
                f"✅ Test completed successfully! Found {len(documents)} total documents"
            )

            return documents

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


async def test_document_download():
    """Test downloading a single document."""
    print("\n🔽 Testing document download...")

    try:
        async with create_scraper(
            MinnesotaScraper, headless=True, timeout=60000
        ) as scraper:
            # Load results from previous test
            try:
                with open("minnesota_scraper_results.json", "r") as f:
                    results = json.load(f)

                if not results:
                    print("❌ No documents found to test download")
                    return

                # Test downloading the first document
                test_doc = results[0]
                print(f"📥 Testing download of: {test_doc['franchise_name']}")
                print(f"🔗 URL: {test_doc['download_url']}")

                # Download the document
                content = await scraper.download_document(test_doc["download_url"])

                # Compute hash
                doc_hash = scraper.compute_document_hash(content)

                print(f"✅ Download successful!")
                print(f"📊 File size: {len(content):,} bytes")
                print(f"🔐 SHA256: {doc_hash[:16]}...")

                # Save a sample document
                filename = f"sample_{test_doc['franchise_name'].replace(' ', '_')}.pdf"
                with open(filename, "wb") as f:
                    f.write(content)

                print(f"💾 Sample document saved as: {filename}")

            except FileNotFoundError:
                print("❌ Please run the discovery test first")

    except Exception as e:
        print(f"❌ Download test failed: {e}")
        raise


if __name__ == "__main__":
    print("🧪 Minnesota CARDS Scraper Test Suite")
    print("=" * 50)

    # Run discovery test
    asyncio.run(test_minnesota_scraper())

    # Run download test
    asyncio.run(test_document_download())

    print("\n🎉 All tests completed!")
