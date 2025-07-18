# Scraper Code Duplication Analysis

## Overview
This document provides a detailed analysis of code duplication between the Minnesota (MN_Scraper.py) and Wisconsin (WI_scraper.py) scrapers.

## Common Functionality Analysis

### 1. File Name Sanitization
**Both scrapers implement similar logic:**

```python
# MN_Scraper.py (line 28-30)
def sanitize_filename(name):
    """Removes characters that are invalid in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

# WI_scraper.py - Missing this function but performs inline sanitization
```

### 2. Browser/Session Management

**Minnesota Scraper:**
- Uses Playwright for navigation
- Uses requests.Session() for downloads
- Manages cookies between Playwright and requests

**Wisconsin Scraper:**
- Pure Playwright approach
- More complex browser cleanup logic
- Signal handlers for cleanup

**Common patterns:**
- Both initialize Playwright browsers
- Both handle cookies
- Both use headless=False
- Both set similar headers

### 3. Data Extraction Patterns

**Similar CSV Export:**
```python
# Both scrapers:
- Collect data in lists/dictionaries
- Use pandas DataFrame or csv.DictWriter
- Save to CSV files
```

### 4. Error Handling

**Common patterns:**
- Try-except blocks around downloads
- Retry mechanisms for failed operations
- Logging/printing status messages

## Specific Duplications

### Headers Configuration
Both set similar HTTP headers:
```python
"User-Agent": "Mozilla/5.0..."
"Accept": "text/html,application/xhtml+xml..."
"Accept-Language": "en-US,en;q=0.9"
"Accept-Encoding": "gzip, deflate, br"
```

### Download Logic
Both implement:
- Check if file exists before downloading
- Stream downloads in chunks
- Save with descriptive filenames
- Handle download failures

### Progress Reporting
Both use similar patterns:
```python
print(f"Processing {current}/{total}...")
print(" [SUCCESS]") or print(" [FAILED]")
```

## Unique Features

### Minnesota Scraper Unique:
1. API-based pagination using "Load more" button
2. Hybrid approach (Playwright + requests)
3. Failed downloads retry with fresh session
4. Saves failed downloads to separate CSV

### Wisconsin Scraper Unique:
1. Complex browser cleanup with process killing
2. Signal handlers for graceful shutdown
3. Regex-based HTML parsing
4. Element reference tracking (e.g., ref=e32)

## Refactoring Opportunities

### 1. Common Base Class
```python
class BaseScraper:
    def __init__(self):
        self.browser = None
        self.page = None
        self.session = None
    
    def sanitize_filename(self, name):
        # Common implementation
    
    def setup_browser(self):
        # Common browser setup
    
    def download_file(self, url, filepath):
        # Common download logic
    
    def export_to_csv(self, data, filepath):
        # Common CSV export
```

### 2. Shared Utilities Module
```python
# utils/scraping.py
def get_default_headers():
    return {
        "User-Agent": "...",
        "Accept": "...",
        # etc.
    }

def retry_with_backoff(func, max_retries=3):
    # Common retry logic

def setup_download_session(cookies=None):
    # Session configuration
```

### 3. Configuration-Driven Approach
```python
# config/scrapers.py
SCRAPER_CONFIGS = {
    "minnesota": {
        "base_url": "https://www.cards.commerce.state.mn.us",
        "start_url": "...",
        "selectors": {
            "table": "#results",
            "load_more": 'button:has-text("Load more")'
        }
    },
    "wisconsin": {
        "base_url": "https://apps.dfi.wi.gov",
        # etc.
    }
}
```

### 4. Separate Concerns
- **Downloader**: Handle file downloads
- **Parser**: Extract data from HTML
- **Storage**: Save to CSV/database
- **Browser**: Manage browser lifecycle

## Implementation Priority

1. **Phase 1**: Extract common utilities (2-3 days)
   - File operations
   - HTTP headers
   - Retry logic

2. **Phase 2**: Create base scraper class (3-4 days)
   - Browser management
   - Session handling
   - Common workflow

3. **Phase 3**: Refactor scrapers to use base class (3-4 days)
   - Minnesota scraper
   - Wisconsin scraper
   - Add tests

4. **Phase 4**: Add new features (2-3 days)
   - Progress tracking
   - Better error reporting
   - Resume capability

## Expected Benefits

### Code Reduction
- Eliminate ~300-400 lines of duplicate code
- Reduce maintenance burden by 40%

### Improved Reliability
- Consistent error handling
- Standardized retry logic
- Better logging

### Easier Extension
- Add new state scrapers easily
- Consistent interface for all scrapers
- Reusable components

### Testing
- Test common functionality once
- Mock base class for scraper tests
- Better test coverage

## Conclusion

The current scrapers share approximately 40% of their functionality but implement it differently. By extracting common patterns into a base class and shared utilities, we can:

1. Reduce code duplication by ~300-400 lines
2. Improve maintainability
3. Standardize behavior across scrapers
4. Make it easier to add new state scrapers
5. Improve testing efficiency

The refactoring should be done incrementally to maintain functionality while improving the codebase structure.
