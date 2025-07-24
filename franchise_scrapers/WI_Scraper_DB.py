"""Wisconsin scraper with database integration and deduplication."""

import asyncio
import io
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Add the parent directory to the path so we can import from storage
sys.path.append(str(Path(__file__).parent.parent))
from storage.google_drive import DriveManager
from franchise_scrapers.database_integration import get_scraper_database
from utils.logging import get_logger

logger = get_logger(__name__)

# Set the client_secret.json path before importing config
os.environ["GDRIVE_CREDS_JSON"] = str(Path(__file__).parent.parent / "storage" / "client_secret.json")

# --- Constants ---
CSV_FOLDER_ID = "1BaJLNcxdVni0IztL5yh7wup8DcMMzxB5"  # CSV folder ID for WI
PDF_FOLDER_ID = "1kvDCC7SXJciG1W6hksfAFJmNA0FRqLEB"  # PDF folder ID for WI


class WisconsinScraperDB:
    """Wisconsin scraper with database integration."""
    
    def __init__(self):
        self.drive_manager = DriveManager(use_oauth2=True, token_file="wi_scraper_token.pickle")
        self.db_integration = get_scraper_database()
        self.downloaded_pdfs: List[Dict] = []
        self.active_registrations_df: Optional[pd.DataFrame] = None

    async def get_active_registrations(self):
        """Get active franchise registrations from Wisconsin DFI site."""
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime('%Y-%m-%d %H.%M')
        filename = f"WI_Active_Registrations_{formatted_datetime}.csv"
        
        logger.info(f"Getting Wisconsin active registrations at: {formatted_datetime}")
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                # Get Active Registrations
                await page.goto("https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx", wait_until='networkidle')
                raw_html = await page.content()
                soup = BeautifulSoup(raw_html, 'html.parser')
                table = soup.find('table', id='ctl00_contentPlaceholder_grdActiveFilings')
                
                if not table:
                    logger.error("Could not find active registrations table")
                    return []
                
                df = pd.read_html(io.StringIO(str(table)))[0]
                logger.info(f"Found {len(df)} active registrations")
                
                # Save registrations to CSV in Google Drive
                try:
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    csv_content = csv_buffer.getvalue().encode('utf-8')
                    
                    file_id = self.drive_manager.upload_file(
                        file_content=csv_content,
                        filename=filename,
                        parent_id=CSV_FOLDER_ID,
                        mime_type="text/csv"
                    )
                    logger.info(f"CSV uploaded to Google Drive with ID: {file_id}")
                except Exception as e:
                    logger.error(f"Error uploading CSV to Google Drive: {e}")
                    # Fallback to local save
                    download_dir = Path(__file__).parent / "downloads" / "WI"
                    download_dir.mkdir(parents=True, exist_ok=True)
                    df.to_csv(download_dir / filename, index=False)
                    logger.warning(f"CSV saved locally as fallback: {download_dir / filename}")
                
                self.active_registrations_df = df
                scraping_names_list = df.iloc[:, 0].tolist()
                return scraping_names_list
                
            finally:
                await context.close()
                await browser.close()

    async def download_pdf(self, page, details_url: str, legal_name: str, trade_name: str, 
                          effective_date: str, filing_number: str) -> Optional[Dict]:
        """Download PDF file and return metadata for database integration."""
        try:
            logger.info(f"Attempting to download PDF for {legal_name} (Filing: {filing_number})")
            
            # Check for download button
            download_selectors = [
                "button:has-text('Download')",
                "input[value*='Download']", 
                "a:has-text('Download')",
                "#btnDownload",
                "input[type='submit'][value*='Download']"
            ]
            
            download_button = None
            for selector in download_selectors:
                button = page.locator(selector)
                if await button.count() > 0:
                    download_button = button
                    break
            
            if not download_button:
                logger.warning(f"No download button found for {legal_name}")
                return None
            
            # Start waiting for the download
            async with page.expect_download() as download_info:
                await download_button.first.click()
            download = await download_info.value
            
            # Format the date
            try:
                effective_date_str = str(effective_date)
                try:
                    date_obj = datetime.strptime(effective_date_str, '%Y-%m-%d')
                except ValueError:
                    try:
                        date_obj = datetime.strptime(effective_date_str, '%m/%d/%Y')
                    except ValueError:
                        date_obj = datetime.now()
                formatted_date = date_obj.strftime('%Y-%m-%d')
            except Exception as date_error:
                logger.warning(f"Date parsing error: {date_error}")
                formatted_date = str(effective_date).replace('/', '-')
            
            # Create filename
            try:
                if pd.isna(trade_name) or trade_name is None or str(trade_name).strip() == '' or str(trade_name).lower() == 'nan':
                    trade_name_clean = str(legal_name)
                else:
                    trade_name_clean = str(trade_name)
                safe_trade_name = re.sub(r'[<>:"/\\|?*]', '_', trade_name_clean)
            except Exception:
                safe_trade_name = re.sub(r'[<>:"/\\|?*]', '_', str(legal_name))
            
            try:
                if pd.isna(filing_number) or filing_number is None or str(filing_number).lower() == 'nan':
                    safe_file_number = "UNKNOWN"
                else:
                    safe_file_number = re.sub(r'[<>:"/\\|?*]', '_', str(filing_number))
            except Exception:
                safe_file_number = "UNKNOWN"
            
            filename = f"{safe_trade_name}_{formatted_date}_{safe_file_number}_WI.pdf"
            
            # Download to temporary location
            temp_path = Path(await download.path())
            
            try:
                # Read the downloaded file
                with open(temp_path, 'rb') as f:
                    pdf_content = f.read()
                
                # Upload to Google Drive
                file_id = self.drive_manager.upload_file(
                    file_content=pdf_content,
                    filename=filename,
                    parent_id=PDF_FOLDER_ID,
                    mime_type="application/pdf"
                )
                
                logger.info(f"PDF uploaded to Google Drive: {filename} (ID: {file_id})")
                
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()
                
                # Return metadata for database integration
                pdf_info = {
                    "filename": filename,
                    "file_id": file_id,
                    "content": pdf_content,
                    "drive_path": f"/wi/{filename}",
                    "legal_name": legal_name,
                    "trade_name": trade_name,
                    "effective_date": effective_date,
                    "filing_number": filing_number
                }
                
                self.downloaded_pdfs.append(pdf_info)
                return pdf_info
                    
            except Exception as upload_error:
                logger.error(f"Error uploading PDF to Google Drive: {upload_error}")
                # Fallback: save locally
                download_dir = Path(__file__).parent / "downloads" / "WI"
                download_dir.mkdir(parents=True, exist_ok=True)
                await download.save_as(download_dir / filename)
                logger.warning(f"PDF saved locally as fallback: {download_dir / filename}")
                return None
            
        except Exception as e:
            logger.error(f"Error downloading PDF for {legal_name}: {e}")
            return None

    async def search_franchise_details(self, franchise_names: list, max_franchises: Optional[int] = None):
        """Search for detailed information on individual franchises."""
        if max_franchises:
            franchise_names = franchise_names[:max_franchises]
            logger.info(f"Limited to first {max_franchises} franchises for testing")
        
        logger.info(f"Searching details for {len(franchise_names)} franchises...")
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                for name in franchise_names:
                    try:
                        logger.info(f"Searching for: {name}")
                        await page.goto("https://apps.dfi.wi.gov/apps/FranchiseSearch/MainSearch.aspx", wait_until='networkidle')
                        await page.locator("#txtName").click()
                        await page.locator("#txtName").fill(name)
                        await page.get_by_role("button", name="(S)earch").click()
                        await page.wait_for_load_state('networkidle')

                        # Read the table of results
                        raw_html = await page.content()
                        soup = BeautifulSoup(raw_html, 'html.parser')
                        table = soup.find('table', id='grdSearchResults')
                        
                        if not table:
                            logger.warning(f"No search results table found for {name}")
                            continue
                        
                        # Get the DataFrame with text content
                        try:
                            df = pd.read_html(io.StringIO(str(table)))[0]
                            logger.info(f"Found {len(df)} search results")
                        except Exception as e:
                            logger.error(f"Error parsing table for {name}: {e}")
                            continue
                        
                        # Extract hyperlinks from the Details column
                        details_links = []
                        table_rows = table.find_all('tr')[1:]  # Skip header row
                        
                        for tr in table_rows:
                            cells = tr.find_all('td')
                            if len(cells) >= 7:
                                details_cell = cells[6]
                                link = details_cell.find('a')
                                if link and link.get('href'):
                                    href = link.get('href')
                                    details_url = "https://apps.dfi.wi.gov/apps/FranchiseSearch/" + href
                                    details_links.append(details_url)
                                else:
                                    details_links.append(None)
                            else:
                                details_links.append(None)
                        
                        # Add the extracted links to the DataFrame
                        df['Details_URL'] = details_links[:len(df)]
                        
                        for index, row in df.iterrows():
                            try:
                                logger.info(f"Processing row {index + 1} of {len(df)}")
                                
                                # Check if we have a valid details URL
                                details_url = row.get('Details_URL')
                                if pd.isna(details_url) or details_url is None:
                                    logger.warning(f"No details URL found for {row.get('Legal Name', 'Unknown')}")
                                    continue
                                    
                                # Skip expired registrations
                                if row['Expiration Date'] == "Expired":
                                    logger.info(f"Skipping expired registration for {row.get('Legal Name', 'Unknown')}")
                                    continue
                                    
                                logger.info(f"Processing row for: {row['Legal Name']}")
                                
                                filing_number = row['File Number']
                                legal_name = row['Legal Name'] 
                                trade_name = row['Trade Name']
                                effective_date = row['Effective Date']
                                expiration_date = row['Expiration Date']
                                filing_status = row['Status']
                                
                                # Navigate to the details page
                                await page.goto(details_url)
                                await page.wait_for_load_state('networkidle')
                                
                                # Download PDF
                                pdf_info = await self.download_pdf(
                                    page, details_url, legal_name, trade_name, 
                                    effective_date, filing_number
                                )
                                
                                # Small delay between downloads
                                await asyncio.sleep(2)
                                
                            except Exception as row_error:
                                logger.error(f"Error processing row for {row.get('Legal Name', 'Unknown')}: {row_error}")
                                continue
                                
                    except Exception as name_error:
                        logger.error(f"Error processing franchise {name}: {name_error}")
                        continue
                        
            except KeyboardInterrupt:
                logger.info("Script interrupted by user. Cleaning up...")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in search_franchise_details: {e}")
                raise
            finally:
                try:
                    await context.close()
                    await browser.close()
                except Exception as cleanup_error:
                    logger.error(f"Error during cleanup: {cleanup_error}")

    async def run_full_scrape_with_db(self, max_franchises: Optional[int] = None):
        """Run complete scrape with database integration."""
        try:
            # Step 1: Get active registrations
            logger.info("Step 1: Getting Wisconsin active registrations...")
            franchise_names = await self.get_active_registrations()
            
            if not franchise_names:
                logger.error("No active registrations found, stopping.")
                return
            
            # Step 2: Search for detailed information and download PDFs
            logger.info("Step 2: Searching franchise details and downloading PDFs...")
            await self.search_franchise_details(franchise_names, max_franchises)
            
            # Step 3: Process data and save to database
            if self.active_registrations_df is not None and self.downloaded_pdfs:
                logger.info("Step 3: Processing data and saving to database...")
                
                # Create a mapping of downloaded PDFs to active registrations
                # This is more complex for WI since we search by name
                stats = self.db_integration.process_scraped_data(
                    scraped_df=self.active_registrations_df,
                    state_code="WI",
                    pdf_downloads=self.downloaded_pdfs
                )
                
                logger.info("Scraping and database integration complete!")
                logger.info(f"Statistics: {stats}")
                
                return stats
            else:
                logger.warning("No data to process for database integration")
                return None
            
        except Exception as e:
            logger.error(f"Error in full scrape: {e}")
            raise


async def main():
    """Main function to run the scraper with database integration."""
    scraper = WisconsinScraperDB()
    
    # Run with limited franchises for testing (remove limit for full scrape)
    stats = await scraper.run_full_scrape_with_db(max_franchises=5)
    
    if stats:
        print("\n" + "="*50)
        print("WISCONSIN SCRAPER - FINAL STATISTICS")
        print("="*50)
        print(f"Total scraped registrations: {stats['total_scraped']}")
        print(f"Franchisors created: {stats['franchisors_created']}")
        print(f"Franchisors found existing: {stats['franchisors_found']}")
        print(f"FDDs created: {stats['fdds_created']}")
        print(f"FDDs skipped (duplicates): {stats['fdds_duplicates']}")
        print(f"Errors: {stats['errors']}")
        print("="*50)


if __name__ == "__main__":
    asyncio.run(main())