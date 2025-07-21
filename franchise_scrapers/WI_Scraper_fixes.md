# WI_Scraper.py Fixes Applied

## Issues Fixed:

### 1. Type Error in Date Parsing (Line 186-193)
**Problem**: `effective_date` was an integer but code expected string
**Fix**: Added `str()` conversion before parsing dates
```python
effective_date_str = str(effective_date)
formatted_date = str(effective_date).replace('/', '-')
```

### 2. Wrong Table Selector (Line 102)
**Problem**: Used `'grdSearchResults'` instead of full ID
**Fix**: Updated to `'ctl00_contentPlaceholder_grdSearchResults'`

### 3. Pandas FutureWarning (Lines 44, 105)
**Problem**: Passing HTML string directly to pd.read_html is deprecated
**Fix**: Wrapped HTML in `io.StringIO()`:
```python
df = pd.read_html(io.StringIO(str(table)))[0]
```

### 4. Wrong Search Button Selector (Line 96)
**Problem**: Used `get_by_role("button", name="(S)earch")`
**Fix**: Changed to `page.locator("#btnSearch").click()`

### 5. File Naming with None/NaN Values (Lines 197-198)
**Problem**: Code didn't handle None/NaN values in trade_name or filing_number
**Fix**: Added proper None/NaN checks and fallback values:
```python
safe_trade_name = re.sub(r'[<>:"/\\|?*]', '_', str(trade_name) if trade_name and not pd.isna(trade_name) else legal_name)
safe_file_number = re.sub(r'[<>:"/\\|?*]', '_', str(filing_number) if filing_number and not pd.isna(filing_number) else "UNKNOWN")
```

### 6. Missing Dependencies
**Problem**: `html5lib` was not installed
**Fix**: Installed via `pip install html5lib lxml`

## Recommendation:
Consider using the new `franchise_scrapers` package implementation instead, which:
- Already has these fixes implemented
- Uses the correct selectors from specs
- Has proper error handling and retry logic
- Follows modular architecture
- Includes comprehensive tests

To use the new implementation:
```python
from franchise_scrapers.wi.scraper import scrape_wisconsin
import asyncio

# Run the scraper
asyncio.run(scrape_wisconsin(download_pdfs=True))
```