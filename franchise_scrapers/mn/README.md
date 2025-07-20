# Minnesota CARDS Portal Scraper

This module scrapes Clean FDD documents from the Minnesota Department of Commerce CARDS portal.

## Features

- Automated scraping of the Minnesota CARDS portal
- Handles pagination with "Load More" button
- Extracts document metadata from table rows
- Optional PDF download with retry logic
- CSV export of results
- Progress reporting throughout the process

## Usage

### As a Module

```python
from franchise_scrapers.mn import scrape_minnesota

# Scrape without downloading PDFs
rows = await scrape_minnesota(download_pdfs_flag=False, max_pages=10)

# Scrape and download PDFs
rows = await scrape_minnesota(download_pdfs_flag=True, max_pages=5)
```

### Command Line

```bash
# Scrape all pages (no PDF downloads)
python -m franchise_scrapers.mn.scraper

# Scrape and download PDFs (limited to 5 pages)
python -m franchise_scrapers.mn.scraper --download-pdfs --max-pages 5

# Run test
python -m franchise_scrapers.mn.test_scraper
```

## Output

The scraper produces:

1. **CSV File**: `mn_clean_fdd.csv` containing:
   - `document_id`: Unique filing identifier from URL
   - `legal_name`: Legal franchisor name
   - `pdf_url`: Direct download URL
   - `scraped_at`: UTC timestamp
   - `pdf_status`: Download status (ok/failed/skipped)
   - `pdf_path`: Local path if downloaded

2. **Downloaded PDFs** (optional): Saved to `downloads/mn/` directory with format:
   - `{sanitized_franchisor_name}_{document_id}.pdf`

## Data Model

Uses the `CleanFDDRow` model from `franchise_scrapers.models`:
- `document_id`: Extracted from documentId parameter in URL
- `legal_name`: Franchisor name from table
- `pdf_url`: Absolute URL for PDF download
- `scraped_at`: UTC timestamp of scraping

## Parser Utilities

The `parsers.py` module provides:
- `parse_row()`: Extract data from table rows
- `extract_document_id()`: Parse document ID from URLs
- `sanitize_filename()`: Create safe filenames
- `clean_text()`: Normalize text data
- `is_valid_fdd()`: Filter valid FDD documents

## Configuration

Controlled via environment variables (see `franchise_scrapers/config.py`):
- `HEADLESS`: Run browser in headless mode (default: true)
- `DOWNLOAD_DIR`: Directory for PDFs (default: ./downloads)
- `THROTTLE_SEC`: Delay between requests (default: 0.5)
- `PDF_RETRY_MAX`: Max download retries (default: 3)
- `PDF_RETRY_BACKOFF`: Retry delays (default: 1,2,4)

## Minnesota CARDS Portal Details

- **URL**: https://www.cards.commerce.state.mn.us
- **Search URL**: Pre-filtered for "Clean FDD" documents
- **Table Structure**: 9 columns including Document, Franchisor, Year, etc.
- **Pagination**: "Load more" button loads additional results
- **Document IDs**: UUID format in documentId URL parameter