#!/usr/bin/env python3
"""Test version of MN scraper that processes only 3 franchises to verify Google Drive uploads."""

import asyncio
import csv
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Add the parent directory to the path so we can import from storage
sys.path.append(str(Path(__file__).parent.parent))
from storage.google_drive import DriveManager

# Set the client_secret.json path before importing config
os.environ["GDRIVE_CREDS_JSON"] = str(Path(__file__).parent.parent / "storage" / "client_secret.json")

# --- Constants from your script ---
MN_URL = "https://www.cards.commerce.state.mn.us/franchise-registrations?doSearch=true&documentTitle=&franchisor=&franchiseName=&year=&fileNumber=&documentType=Clean+FDD&content="
BASE_URL = "https://www.cards.commerce.state.mn.us"

async def load_all_results(page):
    """
    Check for and click the 'Load more' button until it is no longer visible, 
    ensuring all dynamic content is loaded on the page.
    """
    print("Checking for 'Load more' button...")
    load_more_count = 0
    
    # For testing, limit to 1 click to get fewer results
    max_clicks = 1
    
    while load_more_count < max_clicks:
        load_more_button = page.locator('button:has-text("Load more")')
        
        try:
            # Wait for a short period to see if the button is present and visible
            await load_more_button.wait_for(state='visible', timeout=10000)
            print(f"Found 'Load more' button, clicking... (Click #{load_more_count + 1})")
            
            await load_more_button.click()
            load_more_count += 1
            
            # Wait for the network to be idle after the click, indicating new content has loaded
            await page.wait_for_load_state('networkidle', timeout=15000)
            print("New content loaded.")
            
        except Exception:
            # This will happen when the button is no longer found or visible after the timeout
            print("No more 'Load more' buttons found. All results are loaded.")
            break
            
    print(f"Finished loading results. Clicked 'Load more' {load_more_count} times.")
    return load_more_count

def parse_table_with_links(soup, base_url):
    """
    Parses the HTML table using BeautifulSoup to extract row data and hyperlinks.
    
    Returns:
        list: A list of lists containing the scraped data, with headers as the first item.
    """
    table = soup.find('table', id='results')
    if not table:
        return []

    all_data = []

    # Extract headers
    headers = [th.text.strip() for th in table.select('thead th')]
    headers[1] = "Document Link"  # Rename for clarity
    all_data.append(headers)

    # Extract rows - limit to first 3 for testing
    rows = table.select('tbody tr')[:3]
    print(f"TEST MODE: Processing only first {len(rows)} rows")
    
    for row in rows:
        cells = row.find_all(['th', 'td'])
        row_data = [cell.text.strip().replace('\n', ' | ') for cell in cells]
        
        # Extract the hyperlink from the second cell (Document column)
        link_tag = cells[1].find('a')
        if link_tag and link_tag.has_attr('href'):
            relative_url = link_tag['href']
            full_url = urljoin(base_url, relative_url)
            row_data[1] = full_url
        else:
            row_data[1] = cells[1].text.strip()
            
        all_data.append(row_data)
        
    return all_data

async def get_mn_registrations():
    """
    Launches a browser, navigates to the MN franchise registrations page, loads all results,
    scrapes the complete table including document links, and saves it to a CSV.
    """
    # --- File and folder setup ---
    current_datetime = datetime.now()
    FORMATTED_DATETIME = current_datetime.strftime('%Y-%m-%d %H.%M')
    FILENAME = f"MN_Active_Registrations_TEST_{FORMATTED_DATETIME}.csv"
    CSV_FOLDER_ID = "1-maRo3S8fIZQUBsish35rUab1UcCT91R"  # CSV folder ID for MN
    
    # Initialize Google Drive Manager with OAuth2
    print("Initializing Google Drive connection...")
    drive_manager = DriveManager(use_oauth2=True, token_file="mn_scraper_token.pickle")
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            print(f"Navigating to Minnesota franchise registrations at: {FORMATTED_DATETIME}")
            await page.goto(MN_URL, wait_until='networkidle', timeout=60000)
            print("Page loaded successfully.")
            
            # Use the load_all_results function to handle dynamic content
            await load_all_results(page)
            
            print("Extracting final table data with BeautifulSoup for link extraction...")
            raw_html = await page.content()
            soup = BeautifulSoup(raw_html, 'html.parser')
            
            # Use the custom parser to get data and hyperlinks
            scraped_data = parse_table_with_links(soup, BASE_URL)
            
            if len(scraped_data) > 1:
                # Convert to pandas DataFrame for easy CSV saving
                headers = scraped_data[0]
                rows = scraped_data[1:]
                df = pd.DataFrame(rows, columns=headers)
                
                print(f"Found {len(df)} total registrations.")
                
                # Save to CSV in Google Drive
                try:
                    # Convert DataFrame to CSV in memory
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False, quoting=csv.QUOTE_ALL)
                    csv_content = csv_buffer.getvalue().encode('utf-8')
                    
                    # Upload to Google Drive
                    file_id = drive_manager.upload_file(
                        file_content=csv_content,
                        filename=FILENAME,
                        parent_id=CSV_FOLDER_ID,
                        mime_type="text/csv"
                    )
                    print(f"[SUCCESS] CSV uploaded to Google Drive with ID: {file_id}")
                except Exception as e:
                    print(f"[ERROR] Error uploading CSV to Google Drive: {e}")
                
                print("\nFirst 3 rows of extracted data:")
                print(df.head(3))
                
                return df
            else:
                print("No results table found on the page.")
                return pd.DataFrame()
            
        except Exception as e:
            print(f"An error occurred in the MN scraper: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
            
        finally:
            print("Closing browser.")
            await context.close()
            await browser.close()


async def download_pdf(page, document_url: str, franchisor: str, year: str, file_number: str) -> None:
    """Download PDF file from the document link and upload to Google Drive."""
    
    PDF_FOLDER_ID = "16DZN-GCRq1ejSrjaVPCU0vjB_jgHptN7"  # PDF folder ID for MN
    
    # Initialize Google Drive Manager with OAuth2
    drive_manager = DriveManager(use_oauth2=True, token_file="mn_scraper_token.pickle")
    
    try:
        print(f"Attempting to download PDF for {franchisor} (File Number: {file_number})")
        print(f"Document URL: {document_url}")
        
        # Navigate to the document URL
        await page.goto(document_url, wait_until='networkidle', timeout=60000)
        
        # Wait for the PDF to load - MN site typically loads PDF directly
        await page.wait_for_load_state('networkidle')
        
        # Start waiting for the download
        async with page.expect_download(timeout=30000) as download_info:
            # The PDF should auto-download or we might need to trigger it
            # Some PDFs load in viewer, others download directly
            pass
        
        try:
            download = await download_info.value
            
            # Format the year for filename
            year_clean = str(year).replace('/', '-')
            
            # Create filename with convention: {Franchisor}_{Year}_{File Number}_MN.pdf
            safe_franchisor = re.sub(r'[<>:"/\\|?*]', '_', str(franchisor))
            safe_file_number = re.sub(r'[<>:"/\\|?*]', '_', str(file_number))
            filename = f"{safe_franchisor}_{year_clean}_{safe_file_number}_MN.pdf"
            
            # Download to temporary location first
            temp_path = Path(await download.path())
            
            try:
                # Read the downloaded file
                with open(temp_path, 'rb') as f:
                    pdf_content = f.read()
                
                print(f"PDF downloaded, size: {len(pdf_content)} bytes")
                
                # Upload to Google Drive
                file_id = drive_manager.upload_file(
                    file_content=pdf_content,
                    filename=filename,
                    parent_id=PDF_FOLDER_ID,
                    mime_type="application/pdf"
                )
                print(f"[SUCCESS] PDF uploaded to Google Drive: {filename} (ID: {file_id})")
                
                # Clean up the temporary download
                if temp_path.exists():
                    temp_path.unlink()
                    
            except Exception as upload_error:
                print(f"[ERROR] Error uploading PDF to Google Drive: {upload_error}")
                
        except Exception as download_error:
            # PDF might be displayed inline, not downloadable
            print(f"[WARNING] Could not download PDF directly: {download_error}")
            print("PDF might be displayed inline on the page")
            
    except Exception as e:
        print(f"[ERROR] Error accessing document for {franchisor}: {e}")
        import traceback
        traceback.print_exc()


async def download_all_pdfs(df):
    """Download all PDFs from the registration DataFrame."""
    
    print(f"\nStarting PDF downloads for {len(df)} registrations...")
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        
        # Configure downloads
        context = await browser.new_context(
            accept_downloads=True
        )
        page = await context.new_page()
        
        try:
            success_count = 0
            
            for index, row in df.iterrows():
                try:
                    print(f"\nProcessing {index + 1} of {len(df)}")
                    
                    # Extract data from row
                    document_url = row.get('Document Link', '')
                    franchisor = row.get('Franchisor', 'Unknown')
                    year = row.get('Year', 'Unknown')
                    file_number = row.get('File Number', 'Unknown')
                    
                    if not document_url or not document_url.startswith('http'):
                        print(f"[WARNING] No valid document URL for {franchisor}")
                        continue
                    
                    await download_pdf(page, document_url, franchisor, year, file_number)
                    success_count += 1
                    
                    # Small delay between downloads to be respectful
                    await asyncio.sleep(2)
                    
                except Exception as row_error:
                    print(f"[ERROR] Error processing row {index + 1}: {row_error}")
                    continue
            
            print(f"\n[SUMMARY] Successfully processed {success_count} out of {len(df)} documents")
            
        finally:
            await context.close()
            await browser.close()


async def main():
    """Main function to run the scraper."""
    print("\n========== TEST MN SCRAPER WITH GOOGLE DRIVE ==========")
    print("This test will process only 3 franchises to verify Google Drive uploads\n")
    
    df = await get_mn_registrations()
    if not df.empty:
        print(f"\n[SUCCESS] Successfully extracted {len(df)} Minnesota franchise registrations.")
        
        # Download all PDFs
        await download_all_pdfs(df)
    else:
        print("\n[ERROR] Failed to extract registrations.")
    
    print("\n========== TEST COMPLETE ==========")

if __name__ == "__main__":
    asyncio.run(main())