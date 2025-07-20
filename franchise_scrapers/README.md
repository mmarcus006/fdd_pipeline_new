# Franchise FDD Scrapers

A Python package for scraping Franchise Disclosure Documents (FDDs) from state regulatory portals.

## Features

- **Minnesota Scraper**: Extracts Clean FDD documents from the Minnesota Department of Commerce CARDS portal
- **Wisconsin Scraper**: Multi-step extraction from the Wisconsin Department of Financial Institutions portal
- **Parallel Processing**: Configurable concurrent workers for Wisconsin search operations
- **Retry Logic**: Exponential backoff for network failures and PDF downloads
- **Progress Reporting**: Clear status updates during scraping operations
- **CSV Exports**: Structured data output at each stage
- **PDF Downloads**: Optional document downloading with proper file naming

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd fdd_pipeline_new
```

2. Install dependencies:
```bash
pip install -r franchise_scrapers/requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

## Usage

### Command Line Interface

The package provides a `franchise-scrapers` command with subcommands for each state:

#### Minnesota Scraper

```bash
# Basic scraping (table data only)
python -m franchise_scrapers mn

# With PDF downloads
python -m franchise_scrapers mn --download

# Limit pages scraped
python -m franchise_scrapers mn --max-pages 5
```

Output: `mn_clean_fdd.csv`

#### Wisconsin Scraper

```bash
# Basic active filings extraction
python -m franchise_scrapers wi

# Full pipeline with details and PDFs
python -m franchise_scrapers wi --details --download

# Parallel search with 8 workers
python -m franchise_scrapers wi --details --download --max-workers 8

# Resume from a specific step
python -m franchise_scrapers wi --details --download --resume-from search
```

Outputs:
- `wi_active_filings.csv` - Initial franchise list
- `wi_registered_filings.csv` - Filtered registered franchises
- `wi_details_filings.csv` - Complete filing details

### Python API

```python
import asyncio
from franchise_scrapers.mn import scrape_minnesota
from franchise_scrapers.wi import run_wisconsin_pipeline

# Minnesota
async def mn_example():
    rows = await scrape_minnesota(download_pdfs_flag=True, max_pages=10)
    print(f"Found {len(rows)} documents")

# Wisconsin
async def wi_example():
    await run_wisconsin_pipeline(
        details_flag=True,
        download_flag=True,
        max_workers=4
    )

# Run examples
asyncio.run(mn_example())
asyncio.run(wi_example())
```

## Configuration

Environment variables (in `.env`):

```env
# Browser Configuration
HEADLESS=true                    # Run browser in headless mode

# Download Configuration
DOWNLOAD_DIR=./downloads         # Directory for PDF downloads

# Rate Limiting
THROTTLE_SEC=0.5                # Delay between page actions

# Retry Configuration
PDF_RETRY_MAX=3                 # Maximum retry attempts
PDF_RETRY_BACKOFF=1,2,4         # Retry delays in seconds

# Parallelization
MAX_WORKERS=4                   # Concurrent workers for Wisconsin
```

## Testing

### Unit Tests

```bash
# Run all unit tests
pytest franchise_scrapers/tests/unit/

# Run specific test file
pytest franchise_scrapers/tests/unit/test_models.py -v
```

### Integration Tests

```bash
# Run mock integration tests (no internet required)
pytest franchise_scrapers/tests/integration/ -m mock

# Run live tests against actual portals
pytest franchise_scrapers/tests/integration/ --live -m live

# Run all tests
pytest franchise_scrapers/tests/
```

## Project Structure

```
franchise_scrapers/
├── __init__.py
├── __main__.py           # Package entry point
├── config.py             # Environment configuration
├── browser.py            # Browser factory and retry logic
├── models.py             # Pydantic data models
├── cli.py                # Typer CLI interface
├── mn/                   # Minnesota scraper
│   ├── __init__.py
│   ├── scraper.py        # Main scraping logic
│   └── parsers.py        # HTML parsing utilities
├── wi/                   # Wisconsin scraper
│   ├── __init__.py
│   ├── active.py         # Active filings extraction
│   ├── search.py         # Franchise search
│   ├── details.py        # Details extraction
│   └── scraper.py        # Main orchestration
└── tests/                # Test suite
    ├── unit/             # Unit tests
    └── integration/      # Integration tests
```

## Data Models

### Minnesota (CleanFDDRow)
- `document_id`: Unique filing identifier
- `legal_name`: Legal franchisor name
- `pdf_url`: Absolute URL to PDF
- `scraped_at`: UTC timestamp
- `pdf_status`: Download status (optional)
- `pdf_path`: Local file path (optional)

### Wisconsin
- **WIActiveRow**: Basic franchise info from active filings
- **WIRegisteredRow**: Registered franchises with details URL
- **WIDetailsRow**: Complete filing information with metadata

## Error Handling

The scrapers implement robust error handling:
- Network timeouts trigger automatic retries
- Failed PDF downloads are marked but don't stop execution
- Invalid data is logged and skipped
- Progress is saved for resume capability (Wisconsin)

## Contributing

1. Follow existing code patterns
2. Add tests for new functionality
3. Use conventional commits
4. Update documentation as needed

## License

See LICENSE file in the parent repository.