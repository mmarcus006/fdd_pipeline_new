"""Minnesota scraper with database integration and deduplication."""

import asyncio
import csv
import io
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin
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
MN_URL = "https://www.cards.commerce.state.mn.us/franchise-registrations?doSearch=true&documentTitle=&franchisor=&franchiseName=&year=&fileNumber=&documentType=Clean+FDD&content="
BASE_URL = "https://www.cards.commerce.state.mn.us"
CSV_FOLDER_ID = "1-maRo3S8fIZQUBsish35rUab1UcCT91R"  # CSV folder ID for MN
PDF_FOLDER_ID = "16DZN-GCRq1ejSrjaVPCU0vjB_jgHptN7"  # PDF folder ID for MN


class MinnesotaScraperDB:
    """Minnesota scraper with database integration."""
    
    def __init__(self):
        self.drive_manager = DriveManager(use_oauth2=True, token_file="mn_scraper_token.pickle")
        self.db_integration = get_scraper_database()
        self.downloaded_pdfs: List[Dict] = []
        
    async def load_all_results(self, page):
        """Load all results by clicking 'Load more' button until no more results."""
        logger.info("Checking for 'Load more' button...")
        load_more_count = 0
        
        while True:
            load_more_button = page.locator('button:has-text("Load more")')
            
            try:
                await load_more_button.wait_for(state='visible', timeout=10000)
                logger.info(f"Found 'Load more' button, clicking... (Click #{load_more_count + 1})")
                
                await load_more_button.click()
                load_more_count += 1
                
                await page.wait_for_load_state('networkidle', timeout=15000)
                logger.info("New content loaded.")
                
            except Exception:
                logger.info("No more 'Load more' buttons found. All results are loaded.")
                break
                
        logger.info(f"Finished loading results. Clicked 'Load more' {load_more_count} times.")
        return load_more_count

    def parse_table_with_links(self, soup, base_url):
        """Parse the HTML table using BeautifulSoup to extract row data and hyperlinks."""
        table = soup.find('table', id='results')
        if not table:
            return []

        all_data = []

        # Extract headers
        headers = [th.text.strip() for th in table.select('thead th')]
        headers[1] = "Document Link"  # Rename for clarity
        all_data.append(headers)

        # Extract rows
        rows = table.select('tbody tr')
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

    async def get_mn_registrations(self):
        """Scrape Minnesota franchise registrations and save to CSV."""
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime('%Y-%m-%d %H.%M')
        filename = f"MN_Active_Registrations_{formatted_datetime}.csv"
        
        logger.info(f"Starting Minnesota scraper at: {formatted_datetime}")
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                logger.info(f"Navigating to Minnesota franchise registrations")
                await page.goto(MN_URL, wait_until='networkidle', timeout=60000)
                logger.info("Page loaded successfully.")
                
                # Load all results
                await self.load_all_results(page)
                
                logger.info("Extracting final table data with BeautifulSoup...")
                raw_html = await page.content()
                soup = BeautifulSoup(raw_html, 'html.parser')
                
                # Parse table data
                scraped_data = self.parse_table_with_links(soup, BASE_URL)
                
                if len(scraped_data) > 1:
                    # Convert to pandas DataFrame
                    headers = scraped_data[0]
                    rows = scraped_data[1:]
                    df = pd.DataFrame(rows, columns=headers)
                    
                    logger.info(f"Found {len(df)} total registrations.")
                    
                    # Save CSV to Google Drive
                    try:
                        csv_buffer = io.StringIO()
                        df.to_csv(csv_buffer, index=False, quoting=csv.QUOTE_ALL)
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
                        download_dir = Path(__file__).parent / "downloads" / "MN"
                        download_dir.mkdir(parents=True, exist_ok=True)
                        csv_path = download_dir / filename
                        df.to_csv(csv_path, index=False, quoting=csv.QUOTE_ALL)
                        logger.warning(f"CSV saved locally as fallback: {csv_path}")
                    
                    logger.info("First 5 rows of extracted data:")
                    logger.info(df.head().to_string())
                    
                    return df
                else:
                    logger.warning("No results table found on the page.")
                    return pd.DataFrame()
                
            except Exception as e:
                logger.error(f"Error in MN scraper: {e}")
                return pd.DataFrame()
                
            finally:
                logger.info("Closing browser.")
                await context.close()
                await browser.close()

    async def download_pdf(self, page, document_url: str, franchisor: str, year: str, file_number: str) -> Optional[Dict]:
        """Download PDF file and return metadata for database integration."""
        try:
            logger.info(f"Attempting to download PDF for {franchisor} (File Number: {file_number})")
            
            # Navigate to the document URL
            await page.goto(document_url, wait_until='networkidle', timeout=60000)
            await page.wait_for_load_state('networkidle')
            
            # Start waiting for the download
            async with page.expect_download(timeout=30000) as download_info:
                pass
            
            try:
                download = await download_info.value
                
                # Format filename
                year_clean = str(year).replace('/', '-')
                safe_franchisor = re.sub(r'[<>:"/\\|?*]', '_', str(franchisor))
                safe_file_number = re.sub(r'[<>:"/\\|?*]', '_', str(file_number))
                filename = f"{safe_franchisor}_{year_clean}_{safe_file_number}_MN.pdf"
                
                # Download to temporary location
                temp_path = Path(await download.path())
                
                try:
                    # Read the downloaded file
                    with open(temp_path, 'rb') as f:
                        pdf_content = f.read()
                    
                    logger.info(f"PDF downloaded, size: {len(pdf_content)} bytes")
                    
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
                        "drive_path": f"/mn/{filename}",
                        "franchisor": franchisor,
                        "year": year,
                        "file_number": file_number
                    }
                    
                    self.downloaded_pdfs.append(pdf_info)
                    return pdf_info
                        
                except Exception as upload_error:
                    logger.error(f"Error uploading PDF to Google Drive: {upload_error}")
                    # Fallback: save locally
                    download_dir = Path(__file__).parent / "downloads" / "MN"
                    download_dir.mkdir(parents=True, exist_ok=True)
                    fallback_path = download_dir / filename
                    temp_path.rename(fallback_path)
                    logger.warning(f"PDF saved locally as fallback: {fallback_path}")
                    return None
                    
            except Exception as download_error:
                logger.warning(f"Could not download PDF directly: {download_error}")
                return None
                
        except Exception as e:
            logger.error(f"Error accessing document for {franchisor}: {e}")
            return None

    async def download_all_pdfs(self, df):
        """Download all PDFs from the registration DataFrame."""
        logger.info(f"Starting PDF downloads for {len(df)} registrations...")
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            
            try:
                success_count = 0
                
                for index, row in df.iterrows():
                    try:
                        logger.info(f"Processing {index + 1} of {len(df)}")
                        
                        # Extract data from row
                        document_url = row.get('Document Link', '')
                        franchisor = row.get('Franchisor', 'Unknown')
                        year = row.get('Year', 'Unknown')
                        file_number = row.get('File Number', 'Unknown')
                        
                        if not document_url or not document_url.startswith('http'):
                            logger.warning(f"No valid document URL for {franchisor}")
                            continue
                        
                        pdf_info = await self.download_pdf(page, document_url, franchisor, year, file_number)
                        if pdf_info:
                            success_count += 1
                        
                        # Small delay between downloads
                        await asyncio.sleep(2)
                        
                    except Exception as row_error:
                        logger.error(f"Error processing row {index + 1}: {row_error}")
                        continue
                
                logger.info(f"Successfully processed {success_count} out of {len(df)} documents")
                
            finally:
                await context.close()
                await browser.close()

    async def run_full_scrape_with_db(self, max_pdfs: Optional[int] = None):
        """Run complete scrape with database integration."""
        try:
            # Step 1: Scrape registrations
            logger.info("Step 1: Scraping Minnesota registrations...")
            df = await self.get_mn_registrations()
            
            if df.empty:
                logger.error("No registrations found, stopping.")
                return
            
            # Step 2: Download PDFs (limit for testing)
            if max_pdfs:
                df = df.head(max_pdfs)
                logger.info(f"Limited to first {max_pdfs} registrations for testing")
            
            logger.info("Step 2: Downloading PDFs...")
            await self.download_all_pdfs(df)
            
            # Step 3: Process data and save to database
            logger.info("Step 3: Processing data and saving to database...")
            stats = self.db_integration.process_scraped_data(
                scraped_df=df,
                state_code="MN",
                pdf_downloads=self.downloaded_pdfs
            )
            
            logger.info("Scraping and database integration complete!")
            logger.info(f"Statistics: {stats}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error in full scrape: {e}")
            raise


async def main():
    """Main function to run the scraper with database integration."""
    scraper = MinnesotaScraperDB()
    
    # Run with limited PDFs for testing (remove limit for full scrape)
    stats = await scraper.run_full_scrape_with_db(max_pdfs=5)
    
    if stats:
        print("\n" + "="*50)
        print("MINNESOTA SCRAPER - FINAL STATISTICS")
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