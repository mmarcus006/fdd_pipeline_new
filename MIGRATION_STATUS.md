# FDD Pipeline Migration Status

## Overview

This document tracks the incomplete refactoring from the old scraper architecture to the new modular architecture. The project is currently in a transitional state with two different implementations coexisting.

## Architecture Transition

### Current State (What Exists)

1. **franchise_scrapers/** - Original implementation
   ```
   franchise_scrapers/
   ├── MN_Scraper.py          # Standalone Minnesota scraper
   ├── WI_Scraper.py          # Standalone Wisconsin scraper
   ├── browser.py             # Browser factory with Playwright
   ├── config.py              # Configuration with environment variables
   └── models.py              # Pydantic models for scraped data
   ```

2. **workflows/** - New flow architecture (partially implemented)
   ```
   workflows/
   ├── base_state_flow.py     # Generic state flow (expects scrapers/ module)
   ├── state_configs.py       # State configurations (expects scrapers/ module)
   ├── process_single_pdf.py  # PDF processing flow
   └── complete_pipeline.py   # End-to-end pipeline
   ```

### Target State (What's Planned)

1. **scrapers/** - New modular architecture (NOT YET IMPLEMENTED)
   ```
   scrapers/
   ├── base/
   │   ├── base_scraper.py    # Abstract base class
   │   └── exceptions.py      # Custom exceptions
   ├── states/
   │   ├── __init__.py
   │   ├── minnesota.py       # MinnesotaScraper(BaseScraper)
   │   └── wisconsin.py       # WisconsinScraper(BaseScraper)
   └── utils/
       └── scraping_utils.py  # Common utilities
   ```

## Import Mismatches

The following files have imports that expect the new structure:

1. **workflows/state_configs.py**
   ```python
   from scrapers.states.minnesota import MinnesotaScraper  # Doesn't exist
   from scrapers.states.wisconsin import WisconsinScraper  # Doesn't exist
   ```

2. **workflows/base_state_flow.py**
   ```python
   from scrapers.base.base_scraper import BaseScraper     # Doesn't exist
   from scrapers.base.exceptions import WebScrapingException  # Doesn't exist
   ```

3. **tests/scrapers/*** - Test files expect new structure
   ```python
   from scrapers.states.minnesota import MinnesotaScraper  # Doesn't exist
   from scrapers.states.wisconsin import WisconsinScraper  # Doesn't exist
   ```

## Migration Tasks

### High Priority
1. **Option A: Complete the Refactoring**
   - [ ] Create `scrapers/base/base_scraper.py` with abstract base class
   - [ ] Create `scrapers/base/exceptions.py` with exception hierarchy
   - [ ] Refactor `MN_Scraper.py` → `scrapers/states/minnesota.py`
   - [ ] Refactor `WI_Scraper.py` → `scrapers/states/wisconsin.py`
   - [ ] Create `scrapers/utils/scraping_utils.py`
   - [ ] Update all imports
   - [ ] Test the new structure

2. **Option B: Revert to Current Implementation**
   - [ ] Update `workflows/state_configs.py` to import from `franchise_scrapers`
   - [ ] Update `workflows/base_state_flow.py` to work with current scrapers
   - [ ] Update test files to match current structure
   - [ ] Document the current architecture as permanent

### Medium Priority
- [ ] Update documentation to reflect chosen approach
- [ ] Clean up duplicate/obsolete files
- [ ] Ensure consistent naming conventions
- [ ] Add proper type hints throughout

### Low Priority
- [ ] Add more comprehensive tests
- [ ] Optimize scraper performance
- [ ] Add scraper monitoring/metrics

## Current Workarounds

To run the scrapers in their current state:

1. **Minnesota Scraper**
   ```bash
   python franchise_scrapers/MN_Scraper.py
   # or
   python -m franchise_scrapers.mn.scraper
   ```

2. **Wisconsin Scraper**
   ```bash
   python franchise_scrapers/WI_Scraper.py
   # or
   python -m franchise_scrapers.wi.scraper
   ```

3. **Workflows won't run** due to import errors unless:
   - The `scrapers/` module is created, or
   - The imports are updated to use `franchise_scrapers`

## Recommendations

### Short Term (Immediate)
1. **Document the current state** - Update all documentation to reflect what actually exists
2. **Fix critical imports** - Either create the missing modules or update imports
3. **Choose a direction** - Decide whether to complete the refactoring or stick with current implementation

### Long Term
1. **If completing refactoring:**
   - Follow the planned architecture strictly
   - Ensure backward compatibility during transition
   - Update all dependent code simultaneously

2. **If keeping current implementation:**
   - Remove references to planned architecture
   - Optimize the current implementation
   - Document it as the permanent solution

## Impact Analysis

### What Works Now
- Individual scrapers can be run directly
- Basic functionality is intact
- Google Drive integration works
- PDF downloads work (with fixes applied)

### What's Broken
- Workflow orchestration (import errors)
- Unified state flow execution
- Test suite (expects new structure)
- CLI commands that depend on workflows

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| TBD | Choose migration path | Pending team discussion |

## Notes

- The refactoring appears to have been started but not completed
- Both architectures have merit - the new one is cleaner but requires more work
- Current implementation is functional but less maintainable
- Tests were written for the new architecture before it was implemented