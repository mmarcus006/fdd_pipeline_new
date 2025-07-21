from pathlib import Path
import re
import time
from playwright.async_api import Playwright, async_playwright, expect
from bs4 import BeautifulSoup
import pandas as pd
from pandas import DataFrame as df
from datetime import datetime

MN_URL = "https://www.cards.commerce.state.mn.us/franchise-registrations?doSearch=true&documentTitle=&franchisor=&franchiseName=&year=&fileNumber=&documentType=Clean+FDD&content="

CSV_FOLDER_ID = "1-maRo3S8fIZQUBsish35rUab1UcCT91R"  # FOR CSV
MN_FOLDER_ID = "19XZAgdCHbliCc3s8A0-MS7EsT6Af-OFa"  # FOR PDFS


async def load_all_results(page):
    """Check for and click 'Load more' button until all results are loaded."""
    
    print("Checking for 'Load more' button...")
    load_more_count = 0
    
    while True:
        # Look for the load more button with different possible selectors
        load_more_selectors = [
            'button:has-text("Load more")',
            'button:has-text("load more")', 
            '[hx-trigger="click"][hx-target="#results"]',
            'button.btn.btn-primary:has-text("Load more")',
            'input[type="submit"][value*="Load more"]'
        ]
        
        load_more_button = None
        for selector in load_more_selectors:
            try:
                button = page.locator(selector)
                if await button.count() > 0 and await button.is_visible():
                    load_more_button = button
                    break
            except:
                continue
        
        if load_more_button:
            print(f"Found 'Load more' button, clicking... (Click #{load_more_count + 1})")
            
            try:
                # Click the load more button
                await load_more_button.click()
                load_more_count += 1
                
                # Wait for the content to load - look for loading indicator
                print("Waiting for new content to load...")
                
                # Wait for loading indicator to appear and disappear
                try:
                    # Wait for loading indicator
                    await page.wait_for_selector('.htmx-indicator', state='visible', timeout=2000)
                    print("Loading indicator appeared...")
                    
                    # Wait for loading to complete
                    await page.wait_for_selector('.htmx-indicator', state='hidden', timeout=10000)
                    print("Loading completed.")
                except:
                    # If no loading indicator, just wait a bit
                    await page.wait_for_timeout(3000)
                
                # Additional wait for content to stabilize
                await page.wait_for_load_state('networkidle')
                
            except Exception as e:
                print(f"Error clicking 'Load more' button: {e}")
                break
        else:
            print("No 'Load more' button found or not visible - all results loaded")
            break
    
    print(f"Finished loading results. Clicked 'Load more' {load_more_count} times.")
    return load_more_count


async def get_mn_registrations():
    """Get Minnesota franchise registrations with load more functionality."""
    
    # Define constants
    current_datetime = datetime.now()
    FORMATTED_DATETIME = current_datetime.strftime('%Y-%m-%d %H.%M')
    FILENAME = f"MN_Active_Registrations_{FORMATTED_DATETIME}.csv"
    
    # Create download directory
    DOWNLOAD_DIR = Path(__file__).parent / "downloads"
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    MN_DOWNLOAD_FOLDER = DOWNLOAD_DIR / "MN"
    MN_DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            print(f"Navigating to Minnesota franchise registrations at: {FORMATTED_DATETIME}")
            
            # Navigate to MN registrations page
            await page.goto(MN_URL, wait_until='networkidle')
            print("Page loaded successfully")
            
            # Load all results by clicking "Load more" if it exists
            await load_all_results(page)
            
            # Extract the final table
            print("Extracting table data...")
            raw_html = await page.content()
            soup = BeautifulSoup(raw_html, 'html.parser')
            table = soup.find('table', id='results')
            
            if table:
                df = pd.read_html(str(table))[0]
                print(f"Found {len(df)} total registrations")
                
                # Save to CSV
                csv_path = MN_DOWNLOAD_FOLDER / FILENAME
                df.to_csv(csv_path, index=False)
                print(f"Saved CSV to: {csv_path}")
                
                # Display sample data
                print("\nFirst 5 rows:")
                print(df.head())
                
                return df
            else:
                print("No results table found")
                return pd.DataFrame()
            
        except Exception as e:
            print(f"Error in MN scraper: {e}")
            return pd.DataFrame()
            
        finally:
            # Close browser
            await context.close()
            await browser.close()


async def main():
    """Main function to run the MN scraper."""
    df = await get_mn_registrations()
    if not df.empty:
        print(f"\n✅ Successfully extracted {len(df)} Minnesota franchise registrations")
    else:
        print("❌ Failed to extract registrations")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())