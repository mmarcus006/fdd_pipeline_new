# FDD Pipeline - Current Project Structure

This document describes the actual current structure of the FDD Pipeline project as it exists today.

## Directory Structure

```
fdd_pipeline_new/
├── docs/                       # Documentation
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   ├── CONFIGURATION_REFERENCE.md
│   ├── MINERU_INTEGRATION.md
│   ├── TECH_STACK.md
│   ├── data_flow.md
│   ├── database_schema.md
│   ├── mineru_processing.md
│   ├── pydantic_models.md
│   ├── system_overview.md
│   ├── troubleshooting.md
│   └── validation_rules.md
│
├── franchise_scrapers/         # Current scraper implementation
│   ├── MN_Scraper.py          # Minnesota scraper (standalone)
│   ├── WI_Scraper.py          # Wisconsin scraper (standalone)
│   ├── browser.py             # Playwright browser factory
│   ├── config.py              # Configuration management
│   ├── models.py              # Pydantic models for scraped data
│   ├── mn/                    # Minnesota scraper package (new structure)
│   │   ├── __init__.py
│   │   ├── scraper.py
│   │   └── parsers.py
│   ├── wi/                    # Wisconsin scraper package (new structure)
│   │   ├── __init__.py
│   │   ├── scraper.py
│   │   ├── search.py
│   │   ├── details.py
│   │   └── parsers.py
│   └── downloads/             # Downloaded files directory
│
├── models/                    # Database models
│   ├── base.py               # Base model classes
│   ├── franchisor.py         # Franchisor entity
│   ├── fdd.py                # FDD document model
│   ├── section.py            # FDD section model
│   ├── item5_fees.py         # Item 5 data model
│   ├── item6_other_fees.py   # Item 6 data model
│   ├── item7_investment.py   # Item 7 data model
│   ├── item19_fpr.py         # Item 19 data model
│   ├── item20_outlets.py     # Item 20 data model
│   ├── item21_financials.py  # Item 21 data model
│   └── composite.py          # Composite models
│
├── processing/               # Document processing
│   ├── extraction/          # LLM extraction
│   │   ├── llm_extraction.py
│   │   └── multimodal.py
│   ├── mineru/              # MinerU integration
│   │   ├── mineru_processing.py
│   │   └── mineru_web_api.py
│   └── segmentation/        # Document segmentation
│       ├── document_segmentation.py
│       └── enhanced_detector.py
│
├── scripts/                  # Utility scripts
│   ├── check_config.py
│   ├── deploy_state_flows.py
│   ├── health_check.py
│   ├── monitoring.py
│   ├── run_flow.py
│   ├── setup_gdrive_structure.py
│   └── validate_config.py
│
├── src/                      # Source code
│   ├── api/                 # FastAPI application
│   │   ├── main.py          # API endpoints
│   │   └── run.py           # Server runner
│   └── reporting/           # Reporting module (empty)
│
├── storage/                  # Storage integrations
│   ├── google_drive.py      # Google Drive manager
│   ├── google_drive_oauth.py # OAuth2 implementation
│   ├── authenticate_gdrive.py # Authentication helper
│   └── database/            # Database layer
│       └── manager.py       # Database operations
│
├── tests/                    # Test suite
│   ├── scrapers/            # Scraper tests (expect new structure)
│   │   ├── states/
│   │   │   ├── test_minnesota.py
│   │   │   └── test_wisconsin.py
│   │   └── test_scraper.py
│   └── storage/
│       └── test_google_drive.py
│
├── validation/               # Data validation
│   ├── schema_validation.py
│   └── business_rules.py
│
├── workflows/                # Prefect workflows
│   ├── base_state_flow.py   # Generic state flow (has import issues)
│   ├── state_configs.py     # State configurations (has import issues)
│   ├── process_single_pdf.py # PDF processing flow
│   └── complete_pipeline.py  # End-to-end pipeline
│
├── flows/                    # Empty directory (legacy)
│   └── __init__.py
│
├── main.py                   # Main CLI entry point
├── config.py                 # Main configuration
├── CLAUDE.md                 # Project documentation
├── MIGRATION_STATUS.md       # Migration tracking
└── pyproject.toml            # Project dependencies
```

## Key Components

### 1. Scrapers (franchise_scrapers/)

**Current Implementation:**
- `MN_Scraper.py` and `WI_Scraper.py` are standalone scripts
- New modular structure in `mn/` and `wi/` subdirectories
- Uses Playwright for browser automation
- Includes retry logic and error handling

**Issues:**
- Two different implementations coexist
- Workflows expect a `scrapers/` module that doesn't exist

### 2. Models (models/)

**Well-structured Pydantic models for:**
- Database entities (Franchisor, FDD, Sections)
- Extracted data (Items 5, 6, 7, 19, 20, 21)
- Validation and serialization

### 3. Processing (processing/)

**Handles:**
- PDF text extraction
- Document segmentation
- LLM-based data extraction
- MinerU Web API integration

### 4. Storage (storage/)

**Provides:**
- Google Drive integration (OAuth2 and Service Account)
- Database operations via Supabase
- File management

### 5. API (src/api/)

**Current endpoints:**
- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /prefect/run/{source}` - Trigger scraping
- `POST /file/upload` - Manual upload

### 6. Workflows (workflows/)

**Status: Partially broken due to import issues**
- Expects `scrapers/` module structure
- Contains good architectural patterns
- Needs import fixes to function

## Configuration

### Environment Variables
```bash
# Database
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_KEY

# Google Drive
GDRIVE_CREDS_JSON
GDRIVE_FOLDER_ID

# API
INTERNAL_API_TOKEN

# Scrapers
THROTTLE_SEC=0.5
HEADLESS=true
DOWNLOAD_DIR=./downloads
MAX_WORKERS=4

# MinerU
MINERU_AUTH_FILE=mineru_auth.json

# LLM APIs
GEMINI_API_KEY
OPENAI_API_KEY
```

## Current Issues

1. **Import Mismatches**
   - `workflows/` expects `scrapers/` module
   - Tests expect new structure
   - Some imports use old paths

2. **Duplicate Implementations**
   - Old: `MN_Scraper.py`, `WI_Scraper.py`
   - New: `mn/scraper.py`, `wi/scraper.py`

3. **Incomplete Refactoring**
   - Started migration to new architecture
   - Not fully completed
   - Both structures coexist

## What Works

1. **Direct Scraper Execution**
   ```bash
   python franchise_scrapers/MN_Scraper.py
   python franchise_scrapers/WI_Scraper.py
   ```

2. **API Server**
   ```bash
   python src/api/run.py
   ```

3. **Google Drive Integration**
   - OAuth2 authentication
   - File uploads
   - Folder organization

4. **Database Operations**
   - Connection management
   - Data models
   - Migrations

## What Needs Fixing

1. **Workflow Execution**
   - Fix imports in `workflows/`
   - Either complete refactoring or update imports

2. **Test Suite**
   - Update test imports to match current structure
   - Add tests for existing functionality

3. **Documentation**
   - Update to reflect current state
   - Remove references to non-existent modules

## Recommendations

1. **Short Term**
   - Fix critical imports to make workflows functional
   - Document current APIs and usage
   - Consolidate scraper implementations

2. **Long Term**
   - Complete the architectural refactoring
   - Implement missing API endpoints
   - Add comprehensive testing
   - Set up CI/CD pipeline