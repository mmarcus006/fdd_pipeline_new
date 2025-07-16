
import re
import csv
import json

from playwright.sync_api import sync_playwright
import signal
import atexit

# Global Playwright instances
playwright = None
browser = None
page = None

def initialize_browser():
    """Initialize Playwright browser"""
    global playwright, browser, page
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-extensions',
            '--no-first-run',
            '--disable-default-apps'
        ]
    )
    page = browser.new_page()
    
    # Set timeouts
    page.set_default_timeout(30000)  # 30 seconds
    page.set_default_navigation_timeout(30000)  # 30 seconds

def cleanup_browser():
    """Clean up browser resources"""
    global playwright, browser, page
    try:
        if page:
            page.close()
        if browser:
            # Close all pages and contexts
            for context in browser.contexts:
                context.close()
            browser.close()
        if playwright:
            playwright.stop()
    except Exception as e:
        print(f"Error during cleanup: {e}")
    finally:
        page = None
        browser = None
        playwright = None

def cleanup_all_browsers():
    """Force cleanup of any remaining browser processes"""
    import subprocess
    import platform
    
    try:
        system = platform.system().lower()
        if system == "windows":
            # Kill any remaining Chrome/Chromium processes
            subprocess.run(["taskkill", "/f", "/im", "chrome.exe"], 
                         capture_output=True, check=False)
            subprocess.run(["taskkill", "/f", "/im", "chromium.exe"], 
                         capture_output=True, check=False)
            subprocess.run(["taskkill", "/f", "/im", "msedge.exe"], 
                         capture_output=True, check=False)
        elif system == "linux":
            subprocess.run(["pkill", "-f", "chrome"], 
                         capture_output=True, check=False)
            subprocess.run(["pkill", "-f", "chromium"], 
                         capture_output=True, check=False)
        elif system == "darwin":  # macOS
            subprocess.run(["pkill", "-f", "Chrome"], 
                         capture_output=True, check=False)
            subprocess.run(["pkill", "-f", "Chromium"], 
                         capture_output=True, check=False)
    except Exception as e:
        print(f"Error killing browser processes: {e}")

def signal_handler(signum, frame):
    """Handle termination signals"""
    print(f"\nReceived signal {signum}, cleaning up...")
    cleanup_browser()
    cleanup_all_browsers()
    exit(0)

# Register signal handlers and exit handler
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination
atexit.register(cleanup_browser)  # Cleanup on normal exit

# List to store all extracted franchise data
all_franchise_data = []

def get_franchise_names():
    """
    Navigates to the initial page, extracts the HTML table,
    and parses franchise names from the first column.
    """
    print("Navigating to initial page to get franchise names...")
    page.goto("https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx")
    
    # Wait for the table element to be present on the page
    # The table has an ID 'ctl00_cphContent_grdActiveFilings'
    page.wait_for_selector('#ctl00_contentPlaceholder_grdActiveFilings', timeout=30000)

    # Get the outerHTML of the table
    table_html_string = page.evaluate("document.getElementById('ctl00_contentPlaceholder_grdActiveFilings').outerHTML")
    
    if not table_html_string:
        print("Failed to retrieve table HTML. Returning empty list.")
        return []

    franchise_names = []
    # Regex to find rows and extract the content of the first <td> tag within each row
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html_string, re.DOTALL)
    for i, row in enumerate(rows):
        if i == 0: # Skip header row
            continue
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if cells:
            # Clean up HTML entities like &amp;
            name = cells[0].strip().replace('&amp;', '&')
            franchise_names.append(name)
            
    print(f"Found {len(franchise_names)} franchise names.")
    return franchise_names

def process_franchise(franchise_name):
    """
    Processes a single franchise: searches for it, extracts details, and downloads the document.
    """
    print(f"\nProcessing franchise: {franchise_name}")
    
    # Navigate to the search page
    page.goto("https://apps.dfi.wi.gov/apps/FranchiseSearch/MainSearch.aspx")
    
    # Type the franchise name into the search box
    # Using the original ref 'e32' - need to find element by ID
    search_input = page.query_selector('#ctl00_contentPlaceholder_txtSearch') or page.query_selector('input[type="text"]')
    if search_input:
        search_input.fill(franchise_name)
    
    # Click the search button
    # Using the original ref 'e42' - need to find element by ID
    search_button = page.query_selector('#ctl00_contentPlaceholder_btnSearch') or page.query_selector('input[type="submit"], button[type="submit"]')
    if search_button:
        search_button.click()

    # Wait for results to load
    page.wait_for_load_state('networkidle')
    
    # Look for Details link with "Registered" status in the same row
    # Try to find the details link directly
    details_links = page.query_selector_all('a[href*="details"]')
    details_link = None
    
    for link in details_links:
        # Check if this Details link is in a row with "Registered" status
        # Use evaluate to get the parent row's text content
        row_text = page.evaluate('(element) => element.closest("tr").textContent', link)
        if row_text and "Registered" in row_text:
            details_link = link
            break
    
    if details_link:
        print("Found details link for registered franchise. Clicking it.")
        details_link.click()
        
        # Wait for details page to load
        page.wait_for_load_state('networkidle')

        # Get the snapshot of the details page
        details_snapshot_output = page.content()

        # Initialize data dictionaries
        franchisor_info = {}
        filings_info = {}
        states_info = []

        # Extract Franchisor Name and Address
        franchisor_name_address_match = re.search(r'group "Franchisor Name and Address" \[ref=e\d+\]:\n(.*?)(?=group "Filings for this Registration")', details_snapshot_output, re.DOTALL)
        if franchisor_name_address_match:
            section_content = franchisor_name_address_match.group(1)
            
            # Safe regex extraction with proper None checking
            filing_number_match = re.search(r'Filing Number.*?generic \[ref=e\d+\]: "(\d+)"', section_content)
            franchisor_info['Filing Number'] = filing_number_match.group(1) if filing_number_match else ''
            
            filing_status_match = re.search(r'Filing Status.*?generic \[ref=e\d+\]: (\w+)', section_content)
            franchisor_info['Filing Status'] = filing_status_match.group(1) if filing_status_match else ''
            
            legal_name_match = re.search(r'Franchise Legal Name.*?generic \[ref=e\d+\]: (.*?)\n', section_content)
            franchisor_info['Franchise Legal Name'] = legal_name_match.group(1).strip() if legal_name_match else ''
            
            trade_name_match = re.search(r'Franchise Trade Name \(DBA\).*?generic \[ref=e\d+\]: (.*?)\n', section_content)
            franchisor_info['Franchise Trade Name (DBA)'] = trade_name_match.group(1).strip() if trade_name_match else ''
            
            # Extracting multi-line address
            address_lines = re.findall(r'Franchise Business Address.*?generic \[ref=e\d+\]: (.*?)\n|^\s+- cell \[ref=e\d+\]:\n\s+- cell \[ref=e\d+\]:\n\s+- generic \[ref=e\d+\]: (.*?)\n|^\s+- cell \[ref=e\d+\]:\n\s+- cell \[ref=e\d+\]:\n\s+- generic \[ref=e\d+\]: (.*?)\n', section_content, re.MULTILINE)
            
            full_address = []
            for match_tuple in address_lines:
                for item in match_tuple:
                    if item:
                        full_address.append(item.strip())
            franchisor_info['Franchise Business Address'] = ", ".join(full_address)

        # Extract Filings for this Registration
        filings_section_match = re.search(r'group "Filings for this Registration" \[ref=e\d+\]:\n(.*?)(?=group "States Application Filed")', details_snapshot_output, re.DOTALL)
        if filings_section_match:
            section_content = filings_section_match.group(1)
            
            # Safe regex extraction with proper None checking
            legal_name_match = re.search(r'Legal Name.*?cell "(.*?)"', section_content)
            filings_info['Legal Name'] = legal_name_match.group(1).strip() if legal_name_match else ''
            
            trade_name_match = re.search(r'Trade Name.*?cell "(.*?)"', section_content)
            filings_info['Trade Name'] = trade_name_match.group(1).strip() if trade_name_match else ''
            
            type_match = re.search(r'Type.*?cell "(.*?)"', section_content)
            filings_info['Type'] = type_match.group(1).strip() if type_match else ''
            
            status_match = re.search(r'Status.*?cell "(.*?)"', section_content)
            filings_info['Status'] = status_match.group(1).strip() if status_match else ''
            
            effective_match = re.search(r'Effective.*?cell "(.*?)"', section_content)
            filings_info['Effective'] = effective_match.group(1).strip() if effective_match else ''

        # Extract States Application Filed
        states_section_match = re.search(r'group "States Application Filed" \[ref=e\d+\]:\n(.*?)(?=group "Contact Person")', details_snapshot_output, re.DOTALL)
        if states_section_match:
            section_content = states_section_match.group(1)
            states_list_match = re.search(r'States Filed.*?generic \[ref=e\d+\]:\n(.*)', section_content, re.DOTALL)
            if states_list_match:
                states_text = states_list_match.group(1)
                states_info = [s.strip() for s in re.findall(r'text: (.*?)\n', states_text)]

        # Combine all extracted data for this franchise
        combined_data = {
            'Franchise Name': franchise_name,
            'Filing Number': franchisor_info.get('Filing Number', ''),
            'Filing Status': franchisor_info.get('Filing Status', ''),
            'Franchise Legal Name': franchisor_info.get('Franchise Legal Name', ''),
            'Franchise Trade Name (DBA)': franchisor_info.get('Franchise Trade Name (DBA)', ''),
            'Franchise Business Address': franchisor_info.get('Franchise Business Address', ''),
            'Filings Legal Name': filings_info.get('Legal Name', ''),
            'Filings Trade Name': filings_info.get('Trade Name', ''),
            'Filings Type': filings_info.get('Type', ''),
            'Filings Status': filings_info.get('Status', ''),
            'Filings Effective': filings_info.get('Effective', ''),
            'States Filed': ", ".join(states_info)
        }
        all_franchise_data.append(combined_data)

        # Click download button if available
        # Using the original ref 'e199' or look for download button
        download_button = page.query_selector('#e199') or page.query_selector('button:has-text("Download"), input[value*="Download"]')
        if download_button:
            print("Found download button. Clicking it.")
            download_button.click()
        else:
            print("Download button not found on details page.")

        # Go back to search results page
        page.go_back()
        page.wait_for_load_state('networkidle')
        
        # Clear the search box for the next iteration
        # Using the original ref 'e43' or look for clear button
        clear_button = page.query_selector('#e43') or page.query_selector('input[type="reset"], button:has-text("Clear")')
        if clear_button:
            clear_button.click()
    else:
        print(f"No 'Registered' details link found for {franchise_name}. Skipping to next franchise.")
        # Clear the search box even if no details found
        # Using the original ref 'e43' or look for clear button
        clear_button = page.query_selector('#e43') or page.query_selector('input[type="reset"], button:has-text("Clear")')
        if clear_button:
            clear_button.click()

# Main script execution
if __name__ == "__main__":
    try:
        # Clean up any existing browser processes first
        cleanup_all_browsers()
        
        # Initialize browser
        initialize_browser()
        
        franchise_names_to_process = get_franchise_names()

        # Process a limited number of franchises for demonstration
        # For full execution, remove the slicing [0:5]
        for i, name in enumerate(franchise_names_to_process):
            if i >= 5: # Limit to first 5 for demonstration purposes
                break
            try:
                process_franchise(name)
            except Exception as e:
                print(f"Error processing franchise {name}: {e}")
                continue

        # Convert collected data to CSV
        if all_franchise_data:
            csv_file = "franchise_data.csv"
            # Ensure all dictionaries have the same keys for CSV header
            all_keys = set()
            for data_row in all_franchise_data:
                all_keys.update(data_row.keys())
            
            fieldnames = sorted(list(all_keys)) # Sort keys for consistent CSV column order

            with open(csv_file, 'w', newline='', encoding='utf-8') as output_file:
                dict_writer = csv.DictWriter(output_file, fieldnames=fieldnames)
                dict_writer.writeheader()
                dict_writer.writerows(all_franchise_data)
            print(f"Data successfully saved to {csv_file}")
        else:
            print("No franchise data collected.")
    
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Clean up browser resources
        print("Cleaning up browser resources...")
        cleanup_browser()
        # Force cleanup any remaining browser processes
        cleanup_all_browsers()
        print("Cleanup completed.")
