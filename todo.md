# FDD Pipeline Todo List

## Webscraping Process Documentation

### Complete Webscraping Flow (Start to Finish)

1. **Entry Point**: `main.py`
   - Command: `python main.py scrape --state [minnesota|wisconsin|all]`
   - Routes to `scrape()` function which calls `scrape_state_flow()`

2. **Flow Orchestration**: `flows/base_state_flow.py`
   - Main flow: `scrape_state_flow()`
   - Steps:
     a. `scrape_state_portal()` - Discovers documents
     b. `process_state_documents()` - Stores metadata
     c. `download_state_documents()` - Downloads PDFs
     d. `collect_state_metrics()` - Gathers statistics

3. **Scraper Implementation**: `tasks/web_scraping.py` + state-specific scrapers
   - Base class: `BaseScraper` (abstract)
   - State implementations: `MinnesotaScraper`, `WisconsinScraper`
   - Core methods: `discover_documents()`, `extract_document_metadata()`

4. **Data Storage**:
   - Database: Supabase PostgreSQL
   - Files: Google Drive
   - Models: `models/scrape_metadata.py`, `models/fdd.py`

5. **Supporting Components**:
   - Utilities: `utils/scraping_utils.py`
   - Exceptions: `tasks/exceptions.py`
   - Config: `flows/state_configs.py`

## Identified Issues

### ✅ Completed Tasks
- [x] Base scraping framework is well-structured
- [x] State-specific scrapers follow consistent patterns
- [x] Error handling is comprehensive
- [x] Retry logic is implemented properly
- [x] Database integration is clean
- [x] Google Drive integration works correctly

### ❌ Issues Found

1. **Line 293-295 in main.py**: Undefined variables in `run_all()` function
   - `download` and `max_documents` are used but not defined
   - Location: `main.py:293-295, 305-306`
   - **Priority: HIGH**

2. **Missing Import in main.py**: 
   - The `run_all()` function references state configs but doesn't import them properly for parallel execution
   - Location: `main.py:286-310`
   - **Priority: MEDIUM**

3. **Inconsistent Error Handling**:
   - Some async functions use `try/except` while others let exceptions propagate
   - Should standardize error handling approach
   - **Priority: LOW**

4. **Missing Documentation**:
   - No API documentation for the scraper classes
   - Missing docstrings for some key methods
   - **Priority: LOW**

## Enhancement Opportunities

### 🔄 In Progress
- [ ] Fix undefined variables in `run_all()` function
- [ ] Add proper imports for parallel execution
- [ ] Standardize error handling across all async functions

### 📋 Planned Enhancements
- [ ] Add California state scraper
- [ ] Implement incremental scraping (only new documents)
- [ ] Add webhook notifications for scraping events
- [ ] Create admin dashboard for monitoring scraping status
- [ ] Add automated tests for scrapers
- [ ] Implement document change detection and diff tracking
- [ ] Add more comprehensive logging for debugging
- [ ] Create scraper health monitoring endpoint

## Code Organization

### Current Structure
```
tasks/
├── web_scraping.py         # Base scraper framework
├── minnesota_scraper.py    # Minnesota implementation
├── wisconsin_scraper.py    # Wisconsin implementation
└── exceptions.py           # Scraping exceptions

flows/
├── base_state_flow.py      # Generic state flow
├── state_configs.py        # State configurations
└── complete_pipeline.py    # End-to-end flow

utils/
└── scraping_utils.py       # Helper functions

models/
├── scrape_metadata.py      # Scraping audit model
└── fdd.py                  # FDD document model
```

### Recommended Improvements
1. Create a `scrapers/` directory to consolidate all scraper-related code
2. Move state-specific scrapers to `scrapers/states/`
3. Create a `scrapers/base/` for framework code
4. Add comprehensive unit tests in `tests/scrapers/`

## Next Steps

1. **Immediate** (Today):
   - Fix the undefined variables bug in `main.py`
   - Test the `run_all()` command thoroughly

2. **Short Term** (This Week):
   - Add missing documentation
   - Standardize error handling
   - Create unit tests for scrapers

3. **Long Term** (This Month):
   - Implement California scraper
   - Add incremental scraping capability
   - Create monitoring dashboard

## Notes

- The webscraping architecture is well-designed and extensible
- The use of Playwright over Selenium was a good choice for reliability
- The state configuration pattern makes adding new states straightforward
- The retry logic and error handling are robust
- The integration with Prefect for orchestration is clean

## Testing Checklist

- [ ] Test Minnesota scraper with limit parameter
- [ ] Test Wisconsin scraper with limit parameter
- [ ] Test parallel execution with `run_all`
- [ ] Test error handling with invalid state
- [ ] Test retry logic with network failures
- [ ] Test deduplication with existing documents
- [ ] Test Google Drive upload failures
- [ ] Test database connection failures

---
Last Updated: 2025-07-19