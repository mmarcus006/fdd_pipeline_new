from pathlib import Path
import re
import os
import sys
from datetime import datetime
import io
from playwright.async_api import Playwright, async_playwright, expect
from bs4 import BeautifulSoup
import pandas as pd
from pandas import DataFrame as df

# Add the parent directory to the path so we can import from storage
sys.path.append(str(Path(__file__).parent.parent))
from storage.google_drive import DriveManager

# Set the client_secret.json path before importing config
os.environ["GDRIVE_CREDS_JSON"] = str(Path(__file__).parent.parent / "storage" / "client_secret.json")

async def get_active_registrations(playwright: Playwright) -> list:
    """Get active franchise registrations from Wisconsin DFI site."""
    
    #DEFINE CONSTANTS
    current_datetime = datetime.now()
    FORMATTED_DATETIME = current_datetime.strftime('%Y-%m-%d %H.%M')
    print(f"Getting active registrations at: {current_datetime.strftime('%Y-%m-%d %H.%M')}")
    FILENAME = f"WI_Active_Registrations_{FORMATTED_DATETIME}.csv"
    CSV_FOLDER_ID = "1BaJLNcxdVni0IztL5yh7wup8DcMMzxB5"  # CSV folder ID
    
    # Initialize Google Drive Manager with OAuth2
    print("Initializing Google Drive connection...")
    drive_manager = DriveManager(use_oauth2=True, token_file="wi_scraper_token.pickle")
    
    #LAUNCH BROWSER    
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        #Get Active Registrations
        await page.goto("https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx", wait_until='networkidle')
        raw_html = await page.content()
        soup = BeautifulSoup(raw_html, 'html.parser')
        table = soup.find('table', id='ctl00_contentPlaceholder_grdActiveFilings')
        df = pd.read_html(str(table))[0]
        print(f"Found {len(df)} active registrations")
        
        #SAVE REGISTRATIONS TO CSV in Google Drive
        try:
            # Convert DataFrame to CSV in memory
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
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
            # Fallback to local save if Drive upload fails
            DOWNLOAD_DIR = Path(__file__).parent / "downloads"
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(DOWNLOAD_DIR / FILENAME, index=False)
            print(f"[WARNING] CSV saved locally as fallback: {DOWNLOAD_DIR / FILENAME}")
        
        scraping_names_list = df.iloc[:, 0].tolist()
        
        return scraping_names_list
        
    finally:
        await context.close()
        await browser.close()


async def search_franchise_details(playwright: Playwright, franchise_names: list) -> None:
    """Search for detailed information on individual franchises."""
    
    print(f"Searching details for {len(franchise_names)} franchises...")
    
    #LAUNCH BROWSER    
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        #GO TO MAIN SEARCH PAGE    
        for name in franchise_names:
            print(f"Searching for: {name}")
            await page.goto("https://apps.dfi.wi.gov/apps/FranchiseSearch/MainSearch.aspx", wait_until='networkidle')
            await page.locator("#txtName").click()
            await page.locator("#txtName").fill(name)
            await page.get_by_role("button", name="(S)earch").click()
            await page.wait_for_load_state('networkidle')

            #Read the table of results into dataframe and extract hyperlinks
            raw_html = await page.content()
            soup = BeautifulSoup(raw_html, 'html.parser')
            table = soup.find('table', id='grdSearchResults')
            
            # Get the DataFrame with text content
            df = pd.read_html(str(table))[0]
            print(f"Found {len(df)} search results")
            
            # Extract hyperlinks from the Details column using BeautifulSoup
            details_links = []
            table_rows = table.find_all('tr')[1:]  # Skip header row
            
            for tr in table_rows:
                cells = tr.find_all('td')
                if len(cells) >= 7:  # Make sure we have enough columns
                    # The Details link is typically in the last column (index 6)
                    details_cell = cells[6]
                    link = details_cell.find('a')
                    if link and link.get('href'):
                        # Convert relative URL to absolute URL
                        href = link.get('href')
                        details_url = "https://apps.dfi.wi.gov/apps/FranchiseSearch/" + href
                        details_links.append(details_url)
                    else:
                        details_links.append(None)  # No link found in this row
                else:
                    details_links.append(None)  # Row doesn't have enough columns
            
            # Add the extracted links to the DataFrame (one URL per row)
            df['Details_URL'] = details_links[:len(df)]
            
            for index, row in df.iterrows():
                print(f"Processing row {index + 1} of {len(df)}")
                
                # Check if we have a valid details URL
                details_url = row.get('Details_URL')
                if pd.isna(details_url) or details_url is None:
                    print(f"No details URL found for {row.get('Legal Name', 'Unknown')}")
                    continue
                    
                # Skip expired registrations if desired
                if row['Expiration Date'] == "Expired":
                    print(f"Skipping expired registration for {row.get('Legal Name', 'Unknown')}")
                    continue
                    
                print("Processing row for: ", row['Legal Name'])
                print(f"Details URL: {details_url}")
                
                filing_number = row['File Number']
                legal_name = row['Legal Name'] 
                trade_name = row['Trade Name']
                effective_date = row['Effective Date']
                expiration_date = row['Expiration Date']
                filing_status = row['Status']
                
                # Navigate to the details page
                await page.goto(details_url)
                await page.wait_for_load_state('networkidle')
                await download_pdf(page, details_url, legal_name, trade_name, effective_date, filing_number)
    finally:
                await context.close()
                await browser.close()


async def download_pdf(page, details_url: str, legal_name: str, trade_name: str, effective_date: str, filing_number: str) -> None:
    """Download PDF file from the franchise details page and upload to Google Drive."""
    
    PDF_FOLDER_ID = "1kvDCC7SXJciG1W6hksfAFJmNA0FRqLEB"  # PDF folder ID
    
    # Initialize Google Drive Manager with OAuth2
    drive_manager = DriveManager(use_oauth2=True, token_file="wi_scraper_token.pickle")
    
    try:
        print(f"Attempting to download PDF for {legal_name} (Filing: {filing_number})")
        
        # Check if download button exists
        download_button = page.locator("button:has-text('Download'), input[value*='Download'], a:has-text('Download')")
        
        if await download_button.count() > 0:
            # Start waiting for the download
            async with page.expect_download() as download_info:
                # Perform the action that initiates download
                await download_button.first.click()
            download = await download_info.value
            
            # Format the date from effective_date (assuming format like "2024-12-01")
            try:
                date_obj = datetime.strptime(effective_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%Y-%d-%m')  # YYYY-DD-mm format as requested
            except:
                # If date parsing fails, use the original effective_date
                formatted_date = effective_date.replace('/', '-')
            
            # Create filename with new convention: "Trade Name"_"effective date"_"File Number"_State.pdf
            safe_trade_name = re.sub(r'[<>:"/\\|?*]', '_', trade_name)
            safe_file_number = re.sub(r'[<>:"/\\|?*]', '_', filing_number)
            filename = f"{safe_trade_name}_{formatted_date}_{safe_file_number}_WI.pdf"
            
            # Download to temporary location first
            temp_path = Path(download.path())
            
            try:
                # Read the downloaded file
                with open(temp_path, 'rb') as f:
                    pdf_content = f.read()
                
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
                # Fallback: save locally if upload fails
                DOWNLOAD_DIR = Path(__file__).parent / "downloads" / "WI"
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                await download.save_as(DOWNLOAD_DIR / filename)
                print(f"[WARNING] PDF saved locally as fallback: {DOWNLOAD_DIR / filename}")
            
        else:
            print(f"[WARNING] No download button found for {legal_name}")
            
    except Exception as e:
        print(f"[ERROR] Error downloading PDF for {legal_name}: {e}")


async def run(playwright: Playwright) -> None:
    """Main function that orchestrates both scraping operations."""
    
    # First, get the list of active registrations
    franchise_names = await get_active_registrations(playwright)
    
    # Then search for detailed information on each franchise
    await search_franchise_details(playwright, franchise_names)


if __name__ == "__main__":
    import asyncio
    
    async def main():
        async with async_playwright() as playwright:
            await run(playwright)
    
    asyncio.run(main())
