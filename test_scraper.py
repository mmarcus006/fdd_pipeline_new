#!/usr/bin/env python
"""Test scraper without Prefect dependencies."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.states.minnesota import MinnesotaScraper
from utils.logging import get_logger

logger = get_logger(__name__)


async def test_minnesota_scraper():
    """Test the Minnesota scraper directly."""

    logger.info("Starting Minnesota scraper test...")

    # Create scraper instance
    scraper = MinnesotaScraper(
        headless=True,  # Run in headless mode
        timeout=30000,  # 30 second timeout
    )

    try:
        # Initialize the scraper
        await scraper.initialize()
        logger.info("Scraper initialized successfully")

        # Discover documents
        logger.info("Discovering documents...")
        documents = await scraper.discover_documents()

        logger.info(f"Found {len(documents)} documents")

        # Print document information (limit to first 3 for display)
        for i, doc in enumerate(documents[:3], 1):
            logger.info(f"\nDocument {i}:")
            logger.info(f"  Franchise: {doc.franchise_name}")
            logger.info(f"  Document Type: {doc.document_type}")
            logger.info(f"  Filing Date: {doc.filing_date}")
            logger.info(f"  Filing Number: {doc.filing_number}")
            logger.info(f"  Source URL: {doc.source_url}")
            logger.info(f"  Download URL: {doc.download_url}")

        # Test metadata extraction for the first document
        if documents:
            logger.info("\nExtracting metadata for first document...")
            metadata = await scraper.extract_document_metadata(documents[0])
            logger.info(f"Enhanced metadata: {metadata}")

    except Exception as e:
        logger.error(f"Scraper test failed: {e}", exc_info=True)

    finally:
        # Clean up
        await scraper.cleanup()
        logger.info("Scraper cleanup completed")


if __name__ == "__main__":
    asyncio.run(test_minnesota_scraper())
