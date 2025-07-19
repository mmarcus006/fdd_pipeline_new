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
- [x] **FIXED**: Undefined variables in `run_all()` function (added --limit and --skip-download options)
- [x] **FIXED**: Missing imports for parallel execution in main.py
- [x] **COMPLETED**: Reorganized codebase into logical folders
- [x] **COMPLETED**: Updated all imports to reflect new structure
- [x] **COMPLETED**: Updated documentation (README.md, CLAUDE.md)
- [x] **FIXED**: Updated deployment scripts for new Prefect API (removed deprecated Deployment class)
- [x] **ADDED**: Created alternative flow execution scripts (serve_flows.py, run_flow.py)
- [x] **ADDED**: Added flow-help command to explain new execution methods

### ❌ Remaining Issues

1. **Inconsistent Error Handling**:
   - Some async functions use `try/except` while others let exceptions propagate
   - Should standardize error handling approach
   - **Priority: LOW**

2. **Missing Documentation**:
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

### Previous Structure
```
tasks/                      # Mixed responsibilities
flows/                      # Workflow definitions
utils/                      # Mixed utilities
src/processing/             # Processing code
src/MinerU/                 # MinerU integration
```

### New Structure (COMPLETED)
```
scrapers/                   # All web scraping functionality
├── base/                   
│   ├── base_scraper.py    # Base framework (from tasks/web_scraping.py)
│   └── exceptions.py      # Exception hierarchy (from tasks/exceptions.py)
├── states/                
│   ├── minnesota.py       # Minnesota scraper (from tasks/minnesota_scraper.py)
│   └── wisconsin.py       # Wisconsin scraper (from tasks/wisconsin_scraper.py)
└── utils/
    └── scraping_utils.py  # Scraping utilities (from utils/scraping_utils.py)

processing/                 # All document processing
├── extraction/
│   ├── llm_extraction.py  # LLM extraction (from tasks/llm_extraction.py)
│   └── multimodal.py      # Multimodal processing (from utils/multimodal_processor.py)
├── segmentation/
│   ├── document_segmentation.py  # Segmentation (from tasks/document_segmentation.py)
│   └── enhanced_detector.py      # Enhanced detection (from src/processing/enhanced_fdd_section_detector_claude_v2.py)
├── mineru/
│   ├── mineru_processing.py      # MinerU processing (from tasks/mineru_processing.py)
│   └── mineru_web_api.py         # MinerU API (from src/MinerU/mineru_web_api.py)
└── pdf/
    └── pdf_extractor.py           # PDF extraction (from utils/pdf_extractor.py)

workflows/                  # Prefect workflows
├── base_state_flow.py     # Base flow (from flows/base_state_flow.py)
├── state_configs.py       # Configurations (from flows/state_configs.py)
└── complete_pipeline.py   # Pipeline (from flows/complete_pipeline.py)

storage/                    # Storage integrations
├── google_drive.py        # Google Drive (from tasks/drive_operations.py)
└── database/
    └── manager.py         # Database manager (from utils/database.py)

validation/                 # Data validation
├── schema_validation.py   # Schema validation (from tasks/schema_validation.py)
└── business_rules.py      # Business rules (from utils/validation.py)
```

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