#!/usr/bin/env python3
"""
Wisconsin Franchise Table Extractor
===================================

Specific implementation for extracting the Wisconsin franchise registration table
and converting it to a pandas DataFrame with proper cleaning.
"""

import pandas as pd
from selenium_template_antibot import AntiBotSeleniumTemplate
from html_table_to_dataframe import HTMLTableExtractor, advanced_table_cleaning
import time


def extract_wisconsin_franchise_table(save_csv: bool = True, clean_data: bool = True) -> pd.DataFrame:
    """
    Extract the Wisconsin franchise registration table and return as DataFrame.
    
    Args:
        save_csv: Whether to save the result to CSV
        clean_data: Whether to apply data cleaning
        
    Returns:
        DataFrame containing the franchise registration data
    """
    
    print("🏢 Starting Wisconsin Franchise Table Extraction...")
    
    # Initialize scraper and extractor
    scraper = AntiBotSeleniumTemplate(browser="chrome", headless=False)
    extractor = HTMLTableExtractor()
    
    try:
        # Navigate to Wisconsin franchise registration site
        url = "https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx"
        print(f"📍 Navigating to: {url}")
        
        if not scraper.navigate_to_url(url):
            print("❌ Failed to navigate to Wisconsin franchise site")
            return pd.DataFrame()
        
        print(f"✅ Successfully navigated to: {scraper.get_current_url()}")
        print(f"📄 Page title: {scraper.get_page_title()}")
        
        # Wait for page to fully load
        print("⏳ Waiting for page to load...")
        scraper.human_delay(3, 5)
        
        # The Wisconsin table ID
        table_selector = "#ctl00_contentPlaceholder_grdActiveFilings"
        
        # Method 1: Try Selenium cell-by-cell extraction (most reliable for dynamic tables)
        print("\n🔍 Method 1: Selenium Cell-by-Cell Extraction")
        df = extractor.method4_selenium_cell_by_cell(scraper.driver, table_selector)
        
        if df.empty:
            print("⚠️  Cell-by-cell extraction failed, trying alternative methods...")
            
            # Method 2: Try BeautifulSoup with table HTML
            print("\n🔍 Method 2: BeautifulSoup on Table HTML")
            table_element = scraper.find_element_by_css_selector(table_selector)
            if table_element:
                table_html = table_element.get_attribute('outerHTML')
                df = extractor.method2_beautifulsoup_manual(table_html, "table")
            
            if df.empty:
                print("⚠️  BeautifulSoup extraction failed, trying pandas...")
                
                # Method 3: Try pandas read_html on full page
                print("\n🔍 Method 3: Pandas read_html")
                page_source = scraper.get_page_source()
                tables = extractor.method1_pandas_read_html(page_source)
                
                if tables:
                    # Find the largest table (likely the main data table)
                    df = max(tables, key=len)
                    print(f"📊 Selected largest table with {len(df)} rows")
        
        # Check if we got data
        if df.empty:
            print("❌ Failed to extract table data with all methods")
            return pd.DataFrame()
        
        print(f"✅ Successfully extracted table!")
        print(f"📊 Raw data shape: {df.shape}")
        print(f"📝 Columns: {list(df.columns)}")
        
        # Clean the data if requested
        if clean_data:
            print("\n🧹 Cleaning data...")
            df = advanced_table_cleaning(df)
            
            # Wisconsin-specific cleaning
            df = clean_wisconsin_franchise_data(df)
        
        print(f"📊 Final data shape: {df.shape}")
        
        # Display sample of data
        if not df.empty:
            print("\n📋 Sample data (first 5 rows):")
            print(df.head().to_string())
        
        # Save to CSV if requested
        if save_csv and not df.empty:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"wisconsin_franchise_registrations_{timestamp}.csv"
            df.to_csv(filename, index=False)
            print(f"💾 Saved to: {filename}")
        
        return df
        
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        return pd.DataFrame()
        
    finally:
        scraper.close_browser()
        print("🔒 Browser closed")


def clean_wisconsin_franchise_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Wisconsin-specific data cleaning to the franchise DataFrame.
    
    Args:
        df: Raw DataFrame from table extraction
        
    Returns:
        Cleaned DataFrame with Wisconsin-specific formatting
    """
    if df.empty:
        return df
    
    cleaned_df = df.copy()
    
    # Common Wisconsin franchise table column mappings
    column_mappings = {
        'Franchise Name': ['franchise_name', 'company_name', 'name'],
        'Registration Date': ['registration_date', 'date_registered', 'reg_date'],
        'Status': ['status', 'registration_status'],
        'Effective Date': ['effective_date', 'date_effective'],
        'Expiration Date': ['expiration_date', 'date_expiration', 'exp_date'],
        'Business Address': ['business_address', 'address'],
        'State': ['state', 'registration_state']
    }
    
    # Normalize column names
    for standard_name, variations in column_mappings.items():
        for col in cleaned_df.columns:
            if any(var in col.lower() for var in variations):
                cleaned_df = cleaned_df.rename(columns={col: standard_name})
                break
    
    # Clean date columns
    date_columns = [col for col in cleaned_df.columns if 'date' in col.lower()]
    for col in date_columns:
        try:
            cleaned_df[col] = pd.to_datetime(cleaned_df[col], errors='coerce')
        except:
            pass
    
    # Clean status column
    if 'Status' in cleaned_df.columns:
        status_mapping = {
            'active': 'Active',
            'inactive': 'Inactive',
            'pending': 'Pending',
            'expired': 'Expired',
            'suspended': 'Suspended'
        }
        cleaned_df['Status'] = cleaned_df['Status'].str.lower().map(status_mapping).fillna(cleaned_df['Status'])
    
    # Remove completely empty rows
    cleaned_df = cleaned_df.dropna(how='all')
    
    print(f"🧹 Wisconsin-specific cleaning complete")
    return cleaned_df


def quick_extract() -> pd.DataFrame:
    """Quick extraction without extra options - for immediate use."""
    return extract_wisconsin_franchise_table(save_csv=True, clean_data=True)


def analyze_wisconsin_data(df: pd.DataFrame) -> None:
    """
    Perform basic analysis on the Wisconsin franchise data.
    
    Args:
        df: DataFrame containing Wisconsin franchise data
    """
    if df.empty:
        print("❌ No data to analyze")
        return
    
    print("\n📊 WISCONSIN FRANCHISE DATA ANALYSIS")
    print("=" * 50)
    
    print(f"📋 Total Records: {len(df)}")
    print(f"📝 Columns: {len(df.columns)}")
    
    # Status distribution
    if 'Status' in df.columns:
        print("\n📈 Status Distribution:")
        status_counts = df['Status'].value_counts()
        for status, count in status_counts.items():
            percentage = (count / len(df)) * 100
            print(f"   {status}: {count} ({percentage:.1f}%)")
    
    # Date analysis
    date_columns = [col for col in df.columns if 'date' in col.lower()]
    if date_columns:
        print(f"\n📅 Date Range Analysis:")
        for col in date_columns:
            try:
                min_date = df[col].min()
                max_date = df[col].max()
                print(f"   {col}: {min_date} to {max_date}")
            except:
                pass
    
    # Missing data
    print(f"\n❓ Missing Data:")
    missing_data = df.isnull().sum()
    for col, missing_count in missing_data.items():
        if missing_count > 0:
            percentage = (missing_count / len(df)) * 100
            print(f"   {col}: {missing_count} ({percentage:.1f}%)")
    
    # Sample records
    print(f"\n📋 Sample Records:")
    print(df.head(3).to_string())


if __name__ == "__main__":
    """Run the Wisconsin franchise table extraction when script is executed directly."""
    
    print("🏢 Wisconsin Franchise Registration Table Extractor")
    print("=" * 60)
    
    # Extract the data
    franchise_df = extract_wisconsin_franchise_table(save_csv=True, clean_data=True)
    
    if not franchise_df.empty:
        # Perform analysis
        analyze_wisconsin_data(franchise_df)
        
        print("\n✅ Extraction completed successfully!")
        print("\n💡 Usage tips:")
        print("   - Use extract_wisconsin_franchise_table() for custom options")
        print("   - Use quick_extract() for immediate results")
        print("   - Check the CSV file for the complete dataset")
        
    else:
        print("❌ Extraction failed. Please check your internet connection and try again.")
    
    print("\n" + "=" * 60) 