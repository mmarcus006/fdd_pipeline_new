# Wisconsin Franchise Scraper

This module implements a three-step scraper for Wisconsin franchise filings from the DFI (Department of Financial Institutions) portal.

## Overview

The Wisconsin scraper follows a three-step process:

1. **Active Filings Extraction** (`active.py`)
   - Navigates to: https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx
   - Extracts franchise names from the active filings table
   - Exports to: `wi_active_filings.csv`

2. **Franchise Search** (`search.py`)
   - Searches for each franchise name individually
   - Filters for "Registered" status only
   - Extracts details page URLs
   - Supports parallel searching with configurable workers
   - Exports to: `wi_registered_filings.csv`

3. **Details Extraction & PDF Download** (`details.py`)
   - Navigates to each details page URL
   - Extracts comprehensive metadata (filing number, legal name, trade name, email, etc.)
   - Downloads FDD PDFs with retry logic
   - File naming: `<filing_number>_<legal_name_snake>.pdf`
   - Exports to: `wi_details_filings.csv`

## Usage

### Running the Complete Pipeline

```python
from franchise_scrapers.wi.scraper import run_wi_scraper

# Run with default settings
stats = await run_wi_scraper()

# Run with custom settings
stats = await run_wi_scraper(
    max_workers=4,      # Parallel workers
    limit=10,           # Limit to 10 franchises (for testing)
    resume_from_step=1  # Start from beginning
)
```

### Command Line Usage

```bash
# Run the complete pipeline
python -m franchise_scrapers.wi.scraper

# Run with options
python -m franchise_scrapers.wi.scraper --workers 4 --limit 10

# Resume from a specific step
python -m franchise_scrapers.wi.scraper --resume 2  # Resume from search step
```

### Running Individual Steps

```python
# Step 1: Extract active filings
from franchise_scrapers.wi import scrape_wi_active_filings
franchise_names = await scrape_wi_active_filings()

# Step 2: Search for registered franchises
from franchise_scrapers.wi import search_from_active_csv
registered_rows = await search_from_active_csv()

# Step 3: Scrape details and download PDFs
from franchise_scrapers.wi import scrape_details_from_csv
details_rows = await scrape_details_from_csv()
```

## Testing

Run the test suite:

```bash
# Run all tests
python -m franchise_scrapers.wi.test_scraper

# Run specific test
python -m franchise_scrapers.wi.test_scraper --test active
python -m franchise_scrapers.wi.test_scraper --test search
python -m franchise_scrapers.wi.test_scraper --test details
python -m franchise_scrapers.wi.test_scraper --test full
```

## Configuration

The scrapers use settings from `franchise_scrapers/config.py`:

- `HEADLESS`: Run browser in headless mode (default: true)
- `DOWNLOAD_DIR`: Directory for PDFs and CSVs (default: ./downloads)
- `THROTTLE_SEC`: Delay between requests (default: 0.5 seconds)
- `PDF_RETRY_MAX`: Maximum PDF download retries (default: 3)
- `PDF_RETRY_BACKOFF`: Retry delays (default: 1,2,4 seconds)
- `MAX_WORKERS`: Maximum parallel workers (default: 4)

## Output Files

All output files are saved to the configured `DOWNLOAD_DIR`:

1. **wi_active_filings.csv**
   - Columns: `legal_name`, `filing_number`
   - All active franchise filings

2. **wi_registered_filings.csv**
   - Columns: `filing_number`, `legal_name`, `details_url`
   - Only franchises with "Registered" status

3. **wi_details_filings.csv**
   - Columns: `filing_number`, `status`, `legal_name`, `trade_name`, `contact_email`, `pdf_path`, `pdf_status`, `scraped_at`
   - Comprehensive details for each franchise

4. **PDF Files**
   - Named: `<filing_number>_<legal_name_snake>.pdf`
   - Downloaded FDD documents

## Error Handling

The scrapers include robust error handling:

- Retry logic for network failures
- Graceful handling of missing elements
- PDF download retries with exponential backoff
- Detailed error reporting in output CSVs
- Progress tracking and logging

## Performance

- Parallel processing with configurable workers
- Rate limiting to respect server resources
- Browser context isolation for stability
- Efficient memory usage with streaming downloads

## Dependencies

- playwright: Browser automation
- pydantic: Data validation
- asyncio: Asynchronous execution
- csv: Data export

## Notes

- The Wisconsin portal may change its structure; the scrapers are designed to be resilient but may need updates
- PDF downloads require adequate disk space
- Network connectivity affects performance
- Consider running in batches for large datasets