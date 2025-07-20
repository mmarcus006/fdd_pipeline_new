# Franchise Scrapers Implementation TODO List

## Project Setup
- [x] Create implementation plan documentation
- [x] Create this TODO list
- [x] Create .env.example file with all required variables
- [x] Update .gitignore to exclude:
  - [x] `*.csv` output files
  - [x] `downloads/` directory
  - [x] `.env` file
  - [x] `__pycache__/`
  - [x] `.pytest_cache/`

## Package Structure
- [x] Create `franchise_scrapers/` directory
- [x] Create `franchise_scrapers/__init__.py`
- [x] Create `franchise_scrapers/mn/` directory
- [x] Create `franchise_scrapers/mn/__init__.py`
- [x] Create `franchise_scrapers/wi/` directory
- [x] Create `franchise_scrapers/wi/__init__.py`
- [x] Create `franchise_scrapers/tests/` directory structure
- [x] Create `franchise_scrapers/tests/unit/` directory
- [x] Create `franchise_scrapers/tests/integration/` directory

## Core Components

### Configuration Module
- [x] Create `franchise_scrapers/config.py`
- [x] Implement dotenv loading
- [x] Define Settings class with:
  - [x] HEADLESS (bool)
  - [x] DOWNLOAD_DIR (str)
  - [x] THROTTLE_SEC (float)
  - [x] PDF_RETRY_MAX (int)
  - [x] PDF_RETRY_BACKOFF (str)
  - [x] MAX_WORKERS (int)
- [x] Create singleton settings instance
- [x] Add validation for settings

### Browser Factory
- [x] Create `franchise_scrapers/browser.py`
- [x] Implement `get_browser()` async function
- [x] Add browser configuration options
- [x] Implement context creation helper
- [x] Add proper cleanup handling

### Data Models
- [x] Create `franchise_scrapers/models.py`
- [x] Implement Minnesota models:
  - [x] CleanFDDRow with all fields
  - [x] Add field descriptions
  - [x] Add validation
- [x] Implement Wisconsin models:
  - [x] WIActiveRow
  - [x] WIRegisteredRow
  - [x] WIDetailsRow
  - [x] Add field descriptions
  - [x] Add validation

### Retry Logic
- [x] Add retry utility to `franchise_scrapers/browser.py`
- [x] Implement exponential backoff
- [x] Parse retry delays from config
- [x] Add proper exception handling

## Minnesota Scraper

### Main Scraper Module
- [x] Create `franchise_scrapers/mn/scraper.py`
- [x] Implement main scraping flow:
  - [x] Browser initialization
  - [x] Navigation to CARDS portal
  - [x] Table detection and waiting
  - [x] Pagination handling
  - [x] Data extraction
  - [x] CSV export
- [x] Implement PDF download functionality:
  - [x] Download with retry
  - [x] Status tracking
  - [x] File naming

### Parser Module
- [x] Create `franchise_scrapers/mn/parsers.py`
- [x] Implement `parse_row()` function
- [x] Add data cleaning utilities
- [x] Add URL construction helpers
- [x] Implement document ID extraction

## Wisconsin Scraper

### Active Filings Module
- [x] Create `franchise_scrapers/wi/active.py`
- [x] Implement active filings extraction:
  - [x] Navigation to active filings page
  - [x] Table extraction
  - [x] Data parsing
  - [x] CSV export

### Search Module
- [x] Create `franchise_scrapers/wi/search.py`
- [x] Implement franchise search:
  - [x] Search form interaction
  - [x] Result filtering
  - [x] Details URL extraction
  - [x] CSV export
- [x] Add parallel search support:
  - [x] Worker pool management
  - [x] Concurrent search execution

### Details Module
- [x] Create `franchise_scrapers/wi/details.py`
- [x] Implement details extraction:
  - [x] Navigation to details page
  - [x] Metadata parsing
  - [x] PDF download functionality
  - [x] Enhanced CSV export

## CLI Implementation

### Main CLI Module
- [x] Create `franchise_scrapers/cli.py`
- [x] Set up Typer application
- [x] Implement root command group
- [x] Add Minnesota command:
  - [x] Basic execution
  - [x] --download flag
  - [x] Progress reporting
- [x] Add Wisconsin command:
  - [x] Basic execution
  - [x] --details flag
  - [x] --download flag
  - [x] --max-workers option
  - [x] Progress reporting
- [x] Add proper help text
- [x] Implement error handling

## Testing

### Unit Tests
- [x] Create `franchise_scrapers/tests/unit/test_models.py`
  - [x] Test model validation
  - [x] Test field constraints
  - [x] Test edge cases
- [x] Create `franchise_scrapers/tests/unit/test_parsers_mn.py`
  - [x] Test row parsing
  - [x] Test with HTML fixtures
  - [x] Test error cases
- [x] Create `franchise_scrapers/tests/unit/test_details_parser_wi.py`
  - [x] Test details parsing
  - [x] Test data extraction
  - [x] Test error handling

### Integration Tests
- [x] Create `franchise_scrapers/tests/integration/test_mn_flow.py`
  - [x] Test full MN workflow
  - [x] Test with live flag
  - [x] Mock mode for CI
- [x] Create `franchise_scrapers/tests/integration/test_active_wi.py`
  - [x] Test active filings extraction
  - [x] Test table parsing
- [x] Create `franchise_scrapers/tests/integration/test_details_wi.py`
  - [x] Test details workflow
  - [x] Test PDF downloads

### Test Fixtures
- [x] Create HTML fixtures for MN
- [x] Create HTML fixtures for WI
- [x] Create mock response data
- [x] Create test configuration

## Documentation

### Package Documentation
- [x] Add docstrings to all modules
- [x] Add type hints throughout
- [x] Create README.md for package
- [x] Add usage examples

### Development Documentation
- [x] Document setup process
- [x] Add contributing guidelines
- [x] Document testing approach
- [x] Add troubleshooting guide

## Final Steps

### Package Setup
- [x] Create requirements.txt
- [x] Create setup.py (optional)
- [x] Add __main__.py for package execution

### Quality Assurance
- [x] Run full test suite
- [x] Test with real portals
- [x] Verify CSV outputs
- [x] Test PDF downloads
- [x] Check error handling

### Deployment Preparation
- [x] Clean up debug code
- [x] Optimize performance
- [x] Add logging configuration
- [x] Create deployment instructions

## Progress Tracking

**Total Tasks**: 120  
**Completed**: 120  
**In Progress**: 0  
**Remaining**: 0

**Completion**: 100%

---

*Last Updated*: Implementation completed