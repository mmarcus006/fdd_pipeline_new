#!/usr/bin/env python3
"""Debug pagination detection in Minnesota scraper."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set minimal environment variables
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "placeholder-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "placeholder-service-key")
os.environ.setdefault("GDRIVE_CREDS_JSON", "/tmp/placeholder.json")
os.environ.setdefault("GDRIVE_FOLDER_ID", "placeholder-folder-id")
os.environ.setdefault("GEMINI_API_KEY", "placeholder-gemini-key")
os.environ.setdefault("MINERU_DEVICE", "cpu")
os.environ.setdefault("MINERU_BATCH_SIZE", "2")

from tasks.minnesota_scraper import MinnesotaScraper
from tasks.web_scraping import create_scraper


async def debug_pagination():
    """Debug the pagination detection logic."""
    print("🔍 Debugging pagination detection...")

    try:
        async with create_scraper(
            MinnesotaScraper, headless=False, timeout=60000
        ) as scraper:
            print("✅ Scraper initialized")

            # Navigate to the CARDS portal
            await scraper.safe_navigate(scraper.SEARCH_URL)
            print("✅ Navigated to CARDS portal")

            # Wait for page to load
            await asyncio.sleep(3)

            # Check for pagination elements
            print("\n🔍 Looking for pagination elements...")

            # Look for the specific next page link
            next_page_link = await scraper.page.query_selector(
                'a[hx-post="/api/documents/next-page"]'
            )
            if next_page_link:
                print("✅ Found next page link!")

                # Get the hx-vals attribute
                hx_vals = await next_page_link.get_attribute("hx-vals")
                print(f"📄 hx-vals content: {hx_vals}")

                # Get the link text and other attributes
                link_text = await next_page_link.inner_text()
                print(f"🔗 Link text: '{link_text}'")

                # Get all attributes
                all_attrs = await scraper.page.evaluate(
                    """(element) => {
                    const attrs = {};
                    for (let attr of element.attributes) {
                        attrs[attr.name] = attr.value;
                    }
                    return attrs;
                }""",
                    next_page_link,
                )
                print(f"📋 All link attributes: {json.dumps(all_attrs, indent=2)}")

            else:
                print("❌ Next page link not found!")

                # Look for any pagination-related elements
                print("\n🔍 Looking for other pagination elements...")

                # Look for any links with "next" in them
                next_links = await scraper.page.query_selector_all(
                    'a:has-text("Next"), a:has-text("next"), a:has-text(">")'
                )
                print(f"📄 Found {len(next_links)} potential 'next' links")

                for i, link in enumerate(next_links):
                    text = await link.inner_text()
                    href = await link.get_attribute("href")
                    print(f"   Link {i+1}: '{text}' -> {href}")

                # Look for any HTMX elements
                htmx_elements = await scraper.page.query_selector_all(
                    "[hx-post], [hx-get]"
                )
                print(f"📄 Found {len(htmx_elements)} HTMX elements")

                for i, elem in enumerate(htmx_elements):
                    tag = await elem.evaluate("el => el.tagName")
                    text = await elem.inner_text()
                    hx_post = await elem.get_attribute("hx-post")
                    hx_get = await elem.get_attribute("hx-get")
                    print(
                        f"   HTMX {i+1}: <{tag}> '{text[:30]}...' hx-post='{hx_post}' hx-get='{hx_get}'"
                    )

                # Look for pagination container
                pagination_containers = await scraper.page.query_selector_all(
                    '.pagination, .pager, .page-nav, [class*="page"]'
                )
                print(f"📄 Found {len(pagination_containers)} pagination containers")

                for i, container in enumerate(pagination_containers):
                    html = await container.inner_html()
                    print(f"   Container {i+1}: {html[:100]}...")

            # Check the page source for pagination clues
            print("\n🔍 Checking page source for pagination clues...")
            page_content = await scraper.page.content()

            # Look for pagination-related text
            pagination_keywords = [
                "next-page",
                "pagination",
                "hx-post",
                "page-token",
                "pageToken",
            ]
            for keyword in pagination_keywords:
                if keyword in page_content:
                    print(f"✅ Found '{keyword}' in page source")
                    # Find the context around the keyword
                    start = page_content.find(keyword)
                    context = page_content[max(0, start - 100) : start + 200]
                    print(f"   Context: ...{context}...")
                else:
                    print(f"❌ '{keyword}' not found in page source")

            # Check if there are more results available
            print("\n🔍 Checking for result count information...")

            # Look for result count text
            result_count_elements = await scraper.page.query_selector_all(
                'text*="results", text*="showing", text*="of"'
            )
            for elem in result_count_elements:
                text = await elem.inner_text()
                print(f"📊 Result info: '{text}'")

            # Check the page text for result information
            page_text = await scraper.page.inner_text("body")
            lines = page_text.split("\n")
            for line in lines:
                if any(
                    word in line.lower()
                    for word in ["results", "showing", "page", "of"]
                ):
                    print(f"📊 Result line: '{line.strip()}'")

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_pagination())
