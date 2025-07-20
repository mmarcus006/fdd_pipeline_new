# franchise_scrapers/wi/__init__.py
"""Wisconsin franchise scrapers package.

Provides scrapers for:
1. Active filings table extraction
2. Franchise search for registered status
3. Details page scraping and PDF download
"""

from .active import scrape_wi_active_filings, WIActiveScraper
from .search import search_wi_franchises, search_from_csv as search_from_active_csv, WISearchScraper
from .details import scrape_wi_details, scrape_from_csv as scrape_details_from_csv, WIDetailsScraper

__all__ = [
    # Main functions
    'scrape_wi_active_filings',
    'search_wi_franchises', 
    'scrape_wi_details',
    
    # CSV-based functions
    'search_from_active_csv',
    'scrape_details_from_csv',
    
    # Scraper classes
    'WIActiveScraper',
    'WISearchScraper', 
    'WIDetailsScraper',
]