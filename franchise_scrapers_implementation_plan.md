# Franchise FDD Scrapers Implementation Plan

## Project Overview

This document outlines the implementation plan for the Franchise FDD Scrapers project, a standalone web scraping system for extracting Franchise Disclosure Documents (FDDs) from state regulatory portals.

## Architecture

### Package Structure

```
franchise_scrapers/
├── __init__.py                 # Package initialization
├── config.py                   # Environment-based configuration
├── browser.py                  # Reusable browser factory
├── models.py                   # Pydantic data models
├── cli.py                      # Typer CLI interface
├── mn/                         # Minnesota scraper modules
│   ├── __init__.py
│   ├── scraper.py             # Main scraping logic
│   └── parsers.py             # Row parsing helpers
├── wi/                         # Wisconsin scraper modules
│   ├── __init__.py
│   ├── active.py              # Active filings extraction
│   ├── search.py              # Franchise search functionality
│   └── details.py             # Details page extraction
└── tests/                      # Test suite
    ├── unit/
    │   ├── test_parsers_mn.py
    │   ├── test_models.py
    │   └── test_details_parser_wi.py
    └── integration/
        ├── test_mn_flow.py
        ├── test_active_wi.py
        └── test_details_wi.py
```

## Core Components

### 1. Configuration Module (`config.py`)

**Purpose**: Centralized configuration management using environment variables.

**Key Features**:
- Load settings from `.env` file using `python-dotenv`
- Provide defaults for all configuration values
- Single `settings` object accessible throughout the package

**Environment Variables**:
```
HEADLESS=true                    # Browser headless mode
DOWNLOAD_DIR=./downloads         # PDF download directory
THROTTLE_SEC=0.5                # Base delay between actions
PDF_RETRY_MAX=3                 # Max PDF download attempts
PDF_RETRY_BACKOFF=1,2,4         # Retry delays in seconds
MAX_WORKERS=4                   # Concurrent workers
```

### 2. Browser Factory (`browser.py`)

**Purpose**: Centralized browser management for Playwright.

**Key Features**:
- Async browser creation with configurable headless mode
- Context creation with download directory setup
- Proper resource cleanup

**API**:
```python
async def get_browser() -> Browser:
    """Create and return a configured browser instance."""
```

### 3. Data Models (`models.py`)

**Purpose**: Type-safe data structures with validation.

**Models**:

#### Minnesota Models
- `CleanFDDRow`: Represents a row from the Minnesota Clean FDD table
  - `document_id`: Unique filing identifier
  - `legal_name`: Legal franchisor name
  - `pdf_url`: Absolute URL to the FDD PDF
  - `scraped_at`: UTC timestamp

#### Wisconsin Models
- `WIActiveRow`: Row from Wisconsin Active Filings list
  - `legal_name`: Legal franchisor name
  - `filing_number`: Numeric filing number

- `WIRegisteredRow`: Filtered registered franchises
  - `filing_number`: Filing number (primary key)
  - `legal_name`: Name from search results
  - `details_url`: Absolute details page URL

- `WIDetailsRow`: Complete filing details
  - `filing_number`: Primary key
  - `status`: Filing status
  - `legal_name`: Legal name
  - `trade_name`: DBA/trade name (optional)
  - `contact_email`: Contact email (optional)
  - `pdf_path`: Downloaded PDF path
  - `pdf_status`: Download status (ok/failed/skipped)
  - `scraped_at`: UTC timestamp

### 4. Retry Logic

**Purpose**: Robust error handling for network operations.

**Implementation**:
```python
async def with_retry(coro):
    """Execute coroutine with exponential backoff retry."""
```

**Features**:
- Configurable retry attempts via `PDF_RETRY_MAX`
- Exponential backoff delays from `PDF_RETRY_BACKOFF`
- Applies to all network operations and downloads

## Minnesota Scraper Implementation

### Workflow

1. **Navigation**: Navigate to Minnesota CARDS portal with Clean FDD filter
2. **Table Extraction**: Wait for results table to load
3. **Pagination**: Handle "Load More" button clicks
   - Click button while present
   - Wait for new rows or timeout after 2 polls with no growth
4. **Data Extraction**: Parse each table row into `CleanFDDRow`
5. **CSV Export**: Write results to `mn_clean_fdd.csv`
6. **PDF Downloads** (optional): Download each PDF with retry logic

### Key Components

#### `mn/scraper.py`
- Main scraping flow orchestration
- Pagination handling
- CSV export functionality
- PDF download coordination

#### `mn/parsers.py`
- Row parsing logic
- Data cleaning utilities
- URL construction helpers

### Output Format

CSV columns:
- `document_id`: Unique identifier from URL
- `legal_name`: Franchisor legal name
- `pdf_url`: Full download URL
- `scraped_at`: ISO timestamp
- `pdf_status`: Download status (if --download used)

## Wisconsin Scraper Implementation

### Multi-Step Workflow

1. **Active Filings Extraction**
   - Navigate to active filings page
   - Extract franchise names from table
   - Export to `wi_active_filings.csv`

2. **Search and Filter** (optionally parallel)
   - For each active franchise:
     - Search by name
     - Keep only "Registered" status
   - Export to `wi_registered_filings.csv`

3. **Details Extraction** (if --details flag)
   - Visit each details URL
   - Extract comprehensive metadata
   - Export to `wi_details_filings.csv`

4. **PDF Downloads** (if --download flag)
   - Download PDFs with retry logic
   - Name files: `<filing#>_<legal-snake>.pdf`

### Key Components

#### `wi/active.py`
- Active filings table extraction
- Franchise name parsing

#### `wi/search.py`
- Search form interaction
- Result filtering for "Registered" status
- Details URL extraction

#### `wi/details.py`
- Details page parsing
- Metadata extraction
- PDF download handling

### Output Formats

**wi_active_filings.csv**:
- `legal_name`: Franchise legal name
- `filing_number`: Numeric filing ID

**wi_registered_filings.csv**:
- `filing_number`: Filing ID (joins with active)
- `legal_name`: Name from search
- `details_url`: Full details page URL

**wi_details_filings.csv**:
- All fields from `WIDetailsRow` model
- Enhanced metadata from details page
- PDF download status

## CLI Implementation

### Structure

```
franchise-scrapers
├── mn                          # Minnesota scraper
│   └── --download             # Include PDF downloads
└── wi                          # Wisconsin scraper
    ├── --details              # Extract details pages
    ├── --download             # Download PDFs
    └── --max-workers N        # Parallel search workers
```

### Command Examples

```bash
# Minnesota - table only
python -m franchise_scrapers mn

# Minnesota - with PDFs
python -m franchise_scrapers mn --download

# Wisconsin - active list only
python -m franchise_scrapers wi

# Wisconsin - full pipeline with parallel search
python -m franchise_scrapers wi --details --download --max-workers 8
```

### Progress Reporting

- Show current operation status
- Display retry attempts
- Report download progress
- Clear error messages

## Testing Strategy

### Unit Tests

**Focus**: Individual component functionality

- Model validation with edge cases
- Parser functions with HTML fixtures
- Retry logic with mocked failures
- URL construction and sanitization

### Integration Tests

**Focus**: End-to-end workflows

- Live scraping with `pytest -m live`
- Mock mode for CI/CD pipelines
- Error scenario handling
- Rate limit compliance

### Test Fixtures

- Sample HTML responses
- Edge case data
- Error response mocks

## Error Handling

### Scraping Errors
- Network timeouts → Retry with backoff
- Element not found → Log and continue
- Rate limits → Respect delays

### Download Errors
- Connection failures → Retry
- File system errors → Mark as failed
- Timeout → Mark as failed after retries

### Data Errors
- Invalid data → Skip row with warning
- Parsing failures → Log details
- Validation errors → Report specifics

## Security Considerations

1. **URL Validation**: Verify all URLs start with expected domains
2. **Filename Sanitization**: ASCII, lowercase, replace spaces
3. **No Credentials**: Never store authentication in code
4. **Rate Limiting**: Respect server resources

## Performance Optimization

1. **Async Operations**: Maximize concurrent operations
2. **Connection Pooling**: Reuse browser contexts
3. **Selective Downloads**: Only download when requested
4. **Progress Tracking**: Avoid re-processing

## Deployment

### Requirements

```
playwright>=1.40.0
pydantic>=2.0.0
typer>=0.9.0
python-dotenv>=1.0.0
pandas>=2.0.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
```

### Installation

```bash
# Clone repository
git clone <repo-url>
cd franchise_scrapers

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run scrapers
python -m franchise_scrapers mn --download
```

## Maintenance

### Regular Tasks
- Monitor state portal changes
- Update selectors as needed
- Review error logs
- Update dependencies

### Adding New States
1. Create new module in package
2. Implement state-specific logic
3. Add CLI command
4. Create tests
5. Update documentation

## Conclusion

This implementation provides a robust, maintainable solution for scraping FDD documents from state portals. The modular architecture allows for easy extension to additional states while maintaining consistent patterns and error handling throughout the system.