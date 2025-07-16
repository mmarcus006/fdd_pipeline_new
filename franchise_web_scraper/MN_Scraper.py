import re
import time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --- Configuration ---
BASE_URL = "https://www.cards.commerce.state.mn.us"
START_URL = f"{BASE_URL}/franchise-registrations?doSearch=true&documentTitle=&franchisor=&franchiseName=&year=&fileNumber=&documentType=Clean+FDD&content="
API_URL = f"{BASE_URL}/api/documents/next-page"
DOCUMENT_CLASS = "FRANCHISE_REGISTRATIONS"

# --- Output Configuration ---
OUTPUT_DIR = (
    Path(
        "/Users/miller/Library/CloudStorage/GoogleDrive-millermarcusthethird@gmail.com/My Drive/FDD_PDF"
    )
    / "MN"
)
PDF_DOWNLOAD_DIR = OUTPUT_DIR / "MN"
CSV_OUTPUT_FILE = OUTPUT_DIR / "MN" / "franchise_data.csv"


def sanitize_filename(name):
    """Removes characters that are invalid in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name)


def parse_html_row(row, base_url):
    """Parses a single <tr> from the initial HTML table."""
    cells = row.find_all(["th", "td"])
    if not cells or len(cells) < 10:
        return []

    # Helper to extract text from multi-value cells
    def get_multi_value(cell):
        items = [item.get_text(strip=True) for item in cell.find_all("span")]
        return " | ".join(items)

    # Extract data from each cell by index
    franchisor = cells[2].get_text(strip=True)
    franchise_names = get_multi_value(cells[3])
    document_types = get_multi_value(cells[4])
    year = cells[5].get_text(strip=True)
    file_number = cells[6].get_text(strip=True)
    notes = cells[7].get_text(strip=True)
    received_date = cells[8].get_text(strip=True)
    added_on = cells[9].get_text(strip=True)

    # A single row can have multiple document links
    links = cells[1].find_all("a", href=True)
    row_data = []
    for link in links:
        doc_title = link.get_text(strip=True)
        download_url = urljoin(base_url, link["href"])
        row_data.append(
            {
                "franchisor": franchisor,
                "franchise_names": franchise_names,
                "document_title": doc_title,
                "year": year,
                "file_number": file_number,
                "document_types": document_types,
                "received_date": received_date,
                "added_on": added_on,
                "notes": notes,
                "download_url": download_url,
            }
        )
    return row_data


def scrape_all_pages_with_playwright(skip_existing=False):
    """
    Uses Playwright to navigate through all pages, scraping data and downloading PDFs
    from each page with the correct cookies.

    Args:
        skip_existing: If True, skips downloading phase for faster scraping when files exist
    """
    print("--- Starting Playwright scraping and downloading ---")
    if skip_existing:
        print("Note: Skipping downloads of existing files for faster pagination")
    all_data = []
    failed_downloads = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Create a requests session for downloads
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": BASE_URL,
            }
        )

        print(f"Navigating to {START_URL}...")
        page.goto(START_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("#results > tbody > tr", timeout=60000)

        page_num = 1
        has_next_page = True

        while has_next_page:
            print(f"\n--- Processing page {page_num} ---")

            # Get current page HTML
            html_content = page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Scrape data from current page
            page_data = []
            results_table = soup.find("table", id="results")
            if results_table:
                tbody = results_table.find("tbody")
                if tbody:
                    for row in tbody.find_all("tr"):
                        page_data.extend(parse_html_row(row, BASE_URL))

            print(f"Found {len(page_data)} records on page {page_num}")
            all_data.extend(page_data)

            # Get current cookies and update session
            cookies = page.context.cookies()
            session.cookies.clear()
            for cookie in cookies:
                session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/"),
                )

            # Download PDFs from current page
            if not skip_existing:
                print(f"Downloading {len(page_data)} PDFs from page {page_num}...")
                for i, record in enumerate(page_data, 1):
                    success = download_single_pdf(record, session, i, len(page_data))
                    if not success:
                        failed_downloads.append(record)
            else:
                # Just check which files don't exist
                for record in page_data:
                    franchisor = sanitize_filename(
                        record.get("franchisor", "UnknownFranchisor")
                    )
                    doc_title = sanitize_filename(
                        record.get("document_title", "UnknownDoc")
                    )
                    year = record.get("year", "NoYear")
                    filename = f"{year}_{franchisor}_{doc_title}.pdf"
                    filepath = PDF_DOWNLOAD_DIR / filename
                    if not filepath.exists():
                        failed_downloads.append(record)

            # Check for "Load more" button
            try:
                # Wait a bit for page to stabilize after downloads
                time.sleep(1)

                # Try to find the load more button with various selectors
                load_more_selectors = [
                    'button:has-text("Load more")',
                    'button:has-text("Load More")',
                    'button:has-text("LOAD MORE")',
                    'a:has-text("Load more")',
                    'button[aria-label*="load more" i]',
                    ".load-more-button",
                    "button.load-more",
                ]

                load_more_button = None
                for selector in load_more_selectors:
                    try:
                        load_more_button = page.locator(selector).first
                        if load_more_button.is_visible(timeout=1000):
                            print(f"Found load more button with selector: {selector}")
                            break
                    except:
                        continue

                if load_more_button and load_more_button.is_visible():
                    # Store current row count before clicking
                    current_row_count = len(page.locator("#results tbody tr").all())

                    # Click load more and wait for new content
                    print(
                        f"Loading more results (currently have {len(all_data)} total records)..."
                    )
                    load_more_button.click()

                    # Wait for new rows to be added
                    page.wait_for_function(
                        f"document.querySelectorAll('#results tbody tr').length > {current_row_count}",
                        timeout=10000,
                    )
                    time.sleep(2)  # Additional wait for content to stabilize
                    page_num += 1
                else:
                    print(
                        "No visible 'Load more' button found. Reached end of results."
                    )
                    has_next_page = False
            except Exception as e:
                print(
                    f"Error during loading more: {str(e)[:200]}... Ending pagination."
                )
                has_next_page = False

        browser.close()

    return all_data, failed_downloads


def download_single_pdf(record, session, current, total):
    """
    Downloads a single PDF using the provided session with cookies.
    Returns True if successful, False otherwise.
    """
    try:
        franchisor = sanitize_filename(record.get("franchisor", "UnknownFranchisor"))
        doc_title = sanitize_filename(record.get("document_title", "UnknownDoc"))
        year = record.get("year", "NoYear")

        # Create a descriptive and unique filename
        filename = f"{year}_{franchisor}_{doc_title}.pdf"
        filepath = PDF_DOWNLOAD_DIR / filename

        print(f"  [{current}/{total}] {filename}...", end="")

        if filepath.exists():
            print(" [EXISTS]")
            return True

        response = session.get(record["download_url"], timeout=60, stream=True)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(" [SUCCESS]")
        return True

    except requests.exceptions.RequestException as e:
        print(
            f" [FAILED: {e.response.status_code if hasattr(e, 'response') else 'Network Error'}]"
        )
        return False
    except Exception as e:
        print(f" [ERROR: {str(e)}]")
        return False


def retry_failed_downloads(failed_downloads):
    """
    Retry downloading failed PDFs with a fresh session.
    """
    if not failed_downloads:
        return

    print(f"\n--- Retrying {len(failed_downloads)} failed downloads ---")

    # Try with fresh browser session for failed downloads
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to a page to establish session
        page.goto(START_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("#results", timeout=60000)

        # Get cookies
        cookies = page.context.cookies()

        # Create new session with cookies
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": BASE_URL,
            }
        )

        for cookie in cookies:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

        # Retry downloads
        still_failed = []
        for i, record in enumerate(failed_downloads, 1):
            success = download_single_pdf(record, session, i, len(failed_downloads))
            if not success:
                still_failed.append(record)

        browser.close()

        if still_failed:
            print(f"\n{len(still_failed)} downloads still failed after retry.")
            # Save failed downloads to CSV for manual review
            failed_df = pd.DataFrame(still_failed)
            failed_csv = OUTPUT_DIR / "failed_downloads.csv"
            failed_df.to_csv(failed_csv, index=False)
            print(f"Failed downloads saved to: {failed_csv}")


if __name__ == "__main__":
    # Create output directories if they don't exist
    OUTPUT_DIR.mkdir(exist_ok=True)
    PDF_DOWNLOAD_DIR.mkdir(exist_ok=True)

    # --- Execute Scraping and Downloading ---
    all_records, failed_downloads = scrape_all_pages_with_playwright()

    if all_records:
        print("\n--- Data Processing ---")
        # Use pandas to easily handle data and save to CSV
        df = pd.DataFrame(all_records)

        # Remove duplicate rows based on the download URL
        df.drop_duplicates(subset=["download_url"], inplace=True)
        df.reset_index(drop=True, inplace=True)

        print(f"Total unique records found: {len(df)}")

        # Save to CSV
        df.to_csv(CSV_OUTPUT_FILE, index=False)
        print(f"All data has been saved to: {CSV_OUTPUT_FILE}")

        # Retry failed downloads if any
        if failed_downloads:
            retry_failed_downloads(failed_downloads)

        print("\n--- All tasks complete! ---")
        print(f"Data is in '{CSV_OUTPUT_FILE}'")
        print(f"PDFs are in '{PDF_DOWNLOAD_DIR}'")
    else:
        print("No records were found. Exiting.")
