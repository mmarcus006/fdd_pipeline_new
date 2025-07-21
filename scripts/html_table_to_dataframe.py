#!/usr/bin/env python3
"""
HTML Table to DataFrame Converter
=================================

Multiple methods to extract HTML tables and convert them to pandas DataFrames.
Includes examples for both static HTML and Selenium-extracted content.
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import io
from typing import List, Optional, Dict, Any


class HTMLTableExtractor:
    """Class to extract tables from HTML and convert to DataFrames."""
    
    def __init__(self):
        """Initialize the extractor."""
        pass
    
    def method1_pandas_read_html(self, html_content: str, **kwargs) -> List[pd.DataFrame]:
        """
        Method 1: Using pandas.read_html() - Simplest approach
        
        Args:
            html_content: HTML string or URL
            **kwargs: Additional arguments for pd.read_html()
            
        Returns:
            List of DataFrames (one for each table found)
        """
        try:
            # pd.read_html automatically finds all <table> elements
            tables = pd.read_html(html_content, **kwargs)
            print(f"Found {len(tables)} tables using pandas.read_html()")
            return tables
        except Exception as e:
            print(f"Error with pandas.read_html(): {e}")
            return []
    
    def method2_beautifulsoup_manual(self, html_content: str, table_selector: str = "table") -> pd.DataFrame:
        """
        Method 2: Using BeautifulSoup for manual table extraction
        
        Args:
            html_content: HTML string
            table_selector: CSS selector for the table
            
        Returns:
            Single DataFrame
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            table = soup.select_one(table_selector)
            
            if not table:
                print(f"No table found with selector: {table_selector}")
                return pd.DataFrame()
            
            # Extract headers
            headers = []
            header_row = table.find('thead')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            else:
                # Try to find headers in first row
                first_row = table.find('tr')
                if first_row:
                    headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])]
            
            # Extract data rows
            rows = []
            tbody = table.find('tbody')
            if tbody:
                data_rows = tbody.find_all('tr')
            else:
                data_rows = table.find_all('tr')[1:]  # Skip header row if no tbody
            
            for row in data_rows:
                cells = row.find_all(['td', 'th'])
                row_data = [cell.get_text(strip=True) for cell in cells]
                if row_data:  # Only add non-empty rows
                    rows.append(row_data)
            
            # Create DataFrame
            if headers and rows:
                df = pd.DataFrame(rows, columns=headers)
            elif rows:
                df = pd.DataFrame(rows)
            else:
                df = pd.DataFrame()
            
            print(f"Extracted table with {len(df)} rows and {len(df.columns)} columns")
            return df
            
        except Exception as e:
            print(f"Error with BeautifulSoup extraction: {e}")
            return pd.DataFrame()
    
    def method3_selenium_table_extraction(self, driver, table_selector: str) -> pd.DataFrame:
        """
        Method 3: Extract table using Selenium WebDriver
        
        Args:
            driver: Selenium WebDriver instance
            table_selector: CSS selector for the table
            
        Returns:
            Single DataFrame
        """
        try:
            # Wait for table to be present
            wait = WebDriverWait(driver, 10)
            table_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, table_selector))
            )
            
            # Get table HTML and use BeautifulSoup
            table_html = table_element.get_attribute('outerHTML')
            return self.method2_beautifulsoup_manual(table_html, "table")
            
        except Exception as e:
            print(f"Error with Selenium table extraction: {e}")
            return pd.DataFrame()
    
    def method4_selenium_cell_by_cell(self, driver, table_selector: str) -> pd.DataFrame:
        """
        Method 4: Extract table cell by cell using Selenium (for dynamic tables)
        
        Args:
            driver: Selenium WebDriver instance
            table_selector: CSS selector for the table
            
        Returns:
            Single DataFrame
        """
        try:
            # Find the table
            table = driver.find_element(By.CSS_SELECTOR, table_selector)
            
            # Get headers
            headers = []
            try:
                header_elements = table.find_elements(By.CSS_SELECTOR, "thead tr th, thead tr td")
                if not header_elements:
                    # Try first row if no thead
                    header_elements = table.find_elements(By.CSS_SELECTOR, "tr:first-child th, tr:first-child td")
                headers = [elem.text.strip() for elem in header_elements]
            except:
                pass
            
            # Get data rows
            rows = []
            try:
                # Try tbody first
                row_elements = table.find_elements(By.CSS_SELECTOR, "tbody tr")
                if not row_elements:
                    # Fall back to all rows except first if we have headers
                    all_rows = table.find_elements(By.CSS_SELECTOR, "tr")
                    row_elements = all_rows[1:] if headers else all_rows
                
                for row in row_elements:
                    cells = row.find_elements(By.CSS_SELECTOR, "td, th")
                    row_data = [cell.text.strip() for cell in cells]
                    if any(row_data):  # Only add rows with actual data
                        rows.append(row_data)
            except Exception as e:
                print(f"Error extracting rows: {e}")
            
            # Create DataFrame
            if headers and rows:
                # Ensure all rows have same number of columns as headers
                max_cols = len(headers)
                normalized_rows = []
                for row in rows:
                    if len(row) < max_cols:
                        row.extend([''] * (max_cols - len(row)))  # Pad with empty strings
                    elif len(row) > max_cols:
                        row = row[:max_cols]  # Truncate
                    normalized_rows.append(row)
                df = pd.DataFrame(normalized_rows, columns=headers)
            elif rows:
                df = pd.DataFrame(rows)
            else:
                df = pd.DataFrame()
            
            print(f"Extracted table with {len(df)} rows and {len(df.columns)} columns")
            return df
            
        except Exception as e:
            print(f"Error with cell-by-cell extraction: {e}")
            return pd.DataFrame()


def example_wisconsin_franchise_table():
    """
    Example: Extract the Wisconsin franchise registration table
    (Based on your Selenium template modifications)
    """
    from selenium_template_antibot import AntiBotSeleniumTemplate
    
    print("=== Wisconsin Franchise Table Extraction ===")
    
    scraper = AntiBotSeleniumTemplate(browser="chrome", headless=False)
    extractor = HTMLTableExtractor()
    
    try:
        # Navigate to Wisconsin franchise site
        url = "https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx"
        if scraper.navigate_to_url(url):
            print(f"Successfully navigated to: {scraper.get_current_url()}")
            
            # Wait for page to load
            scraper.human_delay(3, 5)
            
            # Method 1: Try to extract with Selenium cell-by-cell
            print("\n--- Method 1: Selenium Cell-by-Cell ---")
            table_selector = "#ctl00_contentPlaceholder_grdActiveFilings"
            df1 = extractor.method4_selenium_cell_by_cell(scraper.driver, table_selector)
            
            if not df1.empty:
                print("DataFrame shape:", df1.shape)
                print("Columns:", list(df1.columns))
                print("\nFirst 5 rows:")
                print(df1.head())
                
                # Save to CSV
                df1.to_csv("wisconsin_franchise_registrations.csv", index=False)
                print("\nSaved to: wisconsin_franchise_registrations.csv")
            
            # Method 2: Try with pandas read_html on page source
            print("\n--- Method 2: Pandas read_html ---")
            page_source = scraper.get_page_source()
            tables = extractor.method1_pandas_read_html(page_source)
            
            if tables:
                df2 = tables[0]  # First table found
                print("DataFrame shape:", df2.shape)
                print("Columns:", list(df2.columns))
                print("\nFirst 5 rows:")
                print(df2.head())
                
                # Save to CSV
                df2.to_csv("wisconsin_franchise_pandas.csv", index=False)
                print("\nSaved to: wisconsin_franchise_pandas.csv")
            
            # Method 3: BeautifulSoup on specific table
            print("\n--- Method 3: BeautifulSoup Manual ---")
            # Get the table element's HTML
            table_element = scraper.find_element_by_css_selector(table_selector)
            if table_element:
                table_html = table_element.get_attribute('outerHTML')
                df3 = extractor.method2_beautifulsoup_manual(table_html, "table")
                
                if not df3.empty:
                    print("DataFrame shape:", df3.shape)
                    print("Columns:", list(df3.columns))
                    print("\nFirst 5 rows:")
                    print(df3.head())
                    
                    # Save to CSV
                    df3.to_csv("wisconsin_franchise_bs4.csv", index=False)
                    print("\nSaved to: wisconsin_franchise_bs4.csv")
    
    except Exception as e:
        print(f"Error in Wisconsin example: {e}")
    
    finally:
        scraper.close_browser()


def example_static_html_table():
    """Example: Extract table from static HTML string."""
    
    print("\n=== Static HTML Table Example ===")
    
    # Sample HTML with a table
    html_content = """
    <html>
    <body>
        <table id="sample-table" class="data-table">
            <thead>
                <tr>
                    <th>Company Name</th>
                    <th>Registration Date</th>
                    <th>Status</th>
                    <th>State</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>ABC Franchise</td>
                    <td>2023-01-15</td>
                    <td>Active</td>
                    <td>WI</td>
                </tr>
                <tr>
                    <td>XYZ Services</td>
                    <td>2023-02-20</td>
                    <td>Active</td>
                    <td>MN</td>
                </tr>
                <tr>
                    <td>123 Corporation</td>
                    <td>2023-03-10</td>
                    <td>Inactive</td>
                    <td>WI</td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """
    
    extractor = HTMLTableExtractor()
    
    # Method 1: pandas.read_html
    print("--- Method 1: pandas.read_html ---")
    tables = extractor.method1_pandas_read_html(html_content)
    if tables:
        df1 = tables[0]
        print(df1)
    
    # Method 2: BeautifulSoup manual
    print("\n--- Method 2: BeautifulSoup Manual ---")
    df2 = extractor.method2_beautifulsoup_manual(html_content, "#sample-table")
    print(df2)


def example_web_table_extraction():
    """Example: Extract table from a website URL."""
    
    print("\n=== Web Table Extraction Example ===")
    
    extractor = HTMLTableExtractor()
    
    # Example with a website that has tables (Wikipedia)
    url = "https://en.wikipedia.org/wiki/List_of_countries_by_population"
    
    try:
        print(f"Extracting tables from: {url}")
        
        # Method 1: Direct pandas read_html from URL
        tables = extractor.method1_pandas_read_html(url)
        
        if tables:
            # Usually the first large table is the main data table
            main_table = tables[0]
            print(f"Main table shape: {main_table.shape}")
            print("Columns:", list(main_table.columns))
            print("\nFirst 5 rows:")
            print(main_table.head())
            
            # Clean and save
            main_table.to_csv("country_population_table.csv", index=False)
            print("\nSaved to: country_population_table.csv")
        
    except Exception as e:
        print(f"Error extracting from web: {e}")


def advanced_table_cleaning(df: pd.DataFrame) -> pd.DataFrame:
    """
    Advanced DataFrame cleaning for scraped tables.
    
    Args:
        df: Raw DataFrame from table extraction
        
    Returns:
        Cleaned DataFrame
    """
    if df.empty:
        return df
    
    # Make a copy
    cleaned_df = df.copy()
    
    # Remove empty rows
    cleaned_df = cleaned_df.dropna(how='all')
    
    # Remove empty columns
    cleaned_df = cleaned_df.dropna(axis=1, how='all')
    
    # Strip whitespace from string columns
    string_columns = cleaned_df.select_dtypes(include=['object']).columns
    for col in string_columns:
        cleaned_df[col] = cleaned_df[col].astype(str).str.strip()
    
    # Replace common problematic values
    cleaned_df = cleaned_df.replace(['', 'nan', 'None', 'N/A', '--'], pd.NA)
    
    # Try to convert numeric columns
    for col in cleaned_df.columns:
        # Try to convert to numeric if it looks like numbers
        if cleaned_df[col].dtype == 'object':
            # Remove common non-numeric characters
            temp_series = cleaned_df[col].astype(str).str.replace(r'[,$%]', '', regex=True)
            try:
                numeric_series = pd.to_numeric(temp_series, errors='coerce')
                # If more than 50% converted successfully, use numeric version
                if numeric_series.notna().sum() / len(numeric_series) > 0.5:
                    cleaned_df[col] = numeric_series
            except:
                pass
    
    # Try to convert date columns
    for col in cleaned_df.columns:
        if any(keyword in col.lower() for keyword in ['date', 'time', 'created', 'updated']):
            try:
                cleaned_df[col] = pd.to_datetime(cleaned_df[col], errors='coerce')
            except:
                pass
    
    print(f"Cleaned DataFrame: {len(cleaned_df)} rows, {len(cleaned_df.columns)} columns")
    return cleaned_df


if __name__ == "__main__":
    """Run examples when script is executed directly."""
    
    print("HTML Table to DataFrame Converter Examples\n")
    
    # Run examples
    try:
        # Static HTML example
        example_static_html_table()
        
        # Web extraction example
        example_web_table_extraction()
        
        # Wisconsin franchise example (if Selenium template is available)
        try:
            example_wisconsin_franchise_table()
        except ImportError:
            print("\nSkipping Wisconsin example - selenium_template_antibot not found")
        except Exception as e:
            print(f"\nError in Wisconsin example: {e}")
    
    except Exception as e:
        print(f"Error in examples: {e}")
    
    print("\n=== Summary ===")
    print("Methods for HTML table to DataFrame conversion:")
    print("1. pandas.read_html() - Simplest, works with URLs and HTML strings")
    print("2. BeautifulSoup manual - More control, works with complex tables")
    print("3. Selenium extraction - For dynamic/JavaScript tables")
    print("4. Cell-by-cell Selenium - For problematic dynamic tables")
    print("\nChoose based on your specific use case and table complexity.") 