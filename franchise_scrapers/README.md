# Franchise Scrapers

This directory contains web scrapers for state franchise disclosure portals. The scrapers automatically download FDD (Franchise Disclosure Document) files from state websites.

## Current Implementation

### Available Scrapers

1. **Minnesota (MN)**
   - Portal: Minnesota CARDS
   - URL: https://www.cards.commerce.state.mn.us
   - Files: `MN_Scraper.py` or `mn/scraper.py`

2. **Wisconsin (WI)**
   - Portal: Wisconsin DFI
   - URL: https://apps.dfi.wi.gov
   - Files: `WI_Scraper.py` or `wi/scraper.py`

## Usage

### Running Individual Scrapers

#### Minnesota Scraper
```bash
# Using standalone script
python franchise_scrapers/MN_Scraper.py

# Using module
python -m franchise_scrapers.mn.scraper

# With options
python -m franchise_scrapers.mn.scraper --download-pdfs --max-pages 5
```

#### Wisconsin Scraper
```bash
# Using standalone script
python franchise_scrapers/WI_Scraper.py

# Using module (after fixing imports)
python -m franchise_scrapers.wi.scraper

# Note: WI_Scraper.py has been fixed for type errors and selector issues
```

### Configuration

Create a `.env` file in the project root:

```bash
# Scraper settings
HEADLESS=true              # Run browser in headless mode
DOWNLOAD_DIR=./downloads   # Where to save PDFs
THROTTLE_SEC=0.5          # Delay between requests
PDF_RETRY_MAX=3           # Max download retries
PDF_RETRY_BACKOFF=1,2,4   # Retry delays in seconds
MAX_WORKERS=4             # Parallel workers for WI search

# Google Drive (for WI_Scraper.py)
GDRIVE_CREDS_JSON=storage/client_secret.json
```

## Architecture

### Current Structure (Mixed)

```
franchise_scrapers/
├── MN_Scraper.py          # Standalone Minnesota scraper
├── WI_Scraper.py          # Standalone Wisconsin scraper (with fixes)
├── WI_Scraper_fixes.md    # Documentation of fixes applied
├── browser.py             # Shared browser factory
├── config.py              # Configuration management
├── models.py              # Pydantic data models
│
├── mn/                    # New modular structure
│   ├── __init__.py
│   ├── scraper.py        # Main scraper logic
│   └── parsers.py        # HTML parsing utilities
│
├── wi/                    # New modular structure
│   ├── __init__.py
│   ├── scraper.py        # Main scraper logic
│   ├── search.py         # Search functionality
│   ├── details.py        # Detail page scraping
│   └── parsers.py        # HTML parsing utilities
│
└── downloads/             # Downloaded PDFs
    ├── mn/               # Minnesota PDFs
    └── wi/               # Wisconsin PDFs
```

## Known Issues

### Wisconsin Scraper (WI_Scraper.py)
Fixed issues:
- ✅ Type error with effective_date parsing
- ✅ Wrong table selector (now uses `ctl00_contentPlaceholder_grdSearchResults`)
- ✅ Pandas FutureWarning (now uses StringIO)
- ✅ Search button selector (now uses `#btnSearch`)
- ✅ File naming with None/NaN values

Remaining issues:
- Google Drive OAuth2 authentication may need refresh
- Some PDFs may fail to download due to portal issues

### Minnesota Scraper
- Pagination button selector may need updates if portal changes
- Large PDFs (>50MB) may timeout during download

### Import Issues
The new modular structure (`mn/` and `wi/` directories) has import paths that don't match the workflow expectations. See `MIGRATION_STATUS.md` for details.

## Features

### Common Features
- Playwright-based browser automation
- Retry logic with exponential backoff
- Progress tracking and logging
- CSV export of scraped data
- Configurable delays to avoid rate limiting

### Minnesota-Specific
- Handles "Load more" pagination
- Filters for "Clean FDD" documents only
- Extracts document IDs from URLs
- Saves to `downloads/mn/` directory

### Wisconsin-Specific
- Two-phase scraping (active list → search → details)
- Parallel search processing
- Google Drive integration for uploads
- Handles expired registrations
- Saves to `downloads/wi/` directory

## Output

### CSV Files
- Minnesota: `mn_clean_fdd.csv`
- Wisconsin: 
  - `WI_Active_Registrations_YYYY-MM-DD HH.MM.csv`
  - `wi_registered_filings.csv`
  - `wi_details_filings.csv`

### PDF Naming Convention
- Minnesota: `{franchisor_name}_{document_id}.pdf`
- Wisconsin: `{trade_name}_{effective_date}_{file_number}_WI.pdf`

## Dependencies

Required packages:
```bash
playwright
pandas
beautifulsoup4
pydantic
python-dotenv
html5lib  # For pandas read_html
lxml      # For pandas read_html
```

Install Playwright browsers:
```bash
playwright install chromium
```

## Troubleshooting

### "Element not found" errors
- Check if selectors have changed on the portal
- Increase timeouts in browser configuration
- Run with `HEADLESS=false` to see what's happening

### Download failures
- Check `DOWNLOAD_DIR` permissions
- Verify PDF URLs are accessible
- Increase `PDF_RETRY_MAX` for flaky connections

### Import errors
- Use the standalone scripts (`MN_Scraper.py`, `WI_Scraper.py`)
- Or fix imports in workflows to use `franchise_scrapers` module

### Rate limiting
- Increase `THROTTLE_SEC` delay
- Reduce `MAX_WORKERS` for Wisconsin
- Add random delays between requests

## Future Improvements

1. **Complete refactoring** to new architecture
2. **Add more states** (California, New York, Illinois)
3. **Implement incremental scraping** (only new documents)
4. **Add database integration** for scraped metadata
5. **Improve error handling** and recovery
6. **Add automated testing** for selectors
7. **Implement proxy support** for rate limiting issues