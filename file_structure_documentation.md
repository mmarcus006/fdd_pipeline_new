# FDD Pipeline File Structure Documentation

## Project Root Structure

```
fdd_pipeline_new/
├── config.py                    # Central configuration management
├── pyproject.toml              # Project metadata and dependencies
├── requirements.txt            # Pip dependencies
├── uv.lock                     # UV package manager lock file
├── README.md                   # Project documentation
├── REFACTORING_ANALYSIS.md    # Refactoring plans
├── baseline_metrics_report.md  # This analysis
└── scraper_duplication_analysis.md  # Scraper analysis
```

## Core Directories

### `/models/` - Database Models (16 files)
SQLAlchemy ORM models representing the database schema.

```
models/
├── __init__.py              # Model exports and initialization
├── base.py                  # Base model class (SQLAlchemy declarative base)
├── base_items.py            # Base classes for FDD items
├── composite.py             # Composite/aggregate models
├── fdd.py                   # Main FDD document model
├── franchisor.py            # Franchisor information model
├── item_json.py             # JSON storage for items
├── item5_fees.py            # Item 5: Initial Fees
├── item6_other_fees.py      # Item 6: Other Fees and Costs
├── item7_investment.py      # Item 7: Estimated Initial Investment
├── item19_fpr.py            # Item 19: Financial Performance Representations
├── item20_outlets.py        # Item 20: Outlets and Franchise Information
├── item21_financials.py     # Item 21: Financial Statements (577 lines)
├── pipeline_log.py          # Pipeline execution logging
├── scrape_metadata.py       # Web scraping metadata
└── section.py               # Document section model
```

**Key Patterns**:
- Inheritance from `base_items.py` for all FDD items
- JSON fields for flexible data storage
- Relationships between models using SQLAlchemy

### `/tasks/` - Prefect Tasks (12 files)
Business logic implemented as Prefect tasks.

```
tasks/
├── __init__.py
├── data_storage.py              # Database storage operations
├── document_processing.py       # PDF processing logic (1,084 lines)
├── document_processing_integration.py
├── document_segmentation.py     # Split documents into sections (825 lines)
├── drive_operations.py          # Google Drive integration (896 lines)
├── exceptions.py                # Custom exception classes
├── llm_extraction.py            # LLM-based data extraction (644 lines)
├── minnesota_scraper.py         # MN scraper task wrapper (893 lines)
├── schema_validation.py         # Data validation logic (1,127 lines)
├── web_scraping.py              # Generic web scraping utilities (677 lines)
└── wisconsin_scraper.py         # WI scraper task wrapper (596 lines)
```

**Largest Files** (need refactoring):
- `schema_validation.py` - Complex validation rules
- `document_processing.py` - Monolithic processing logic
- `minnesota_scraper.py` & `wisconsin_scraper.py` - Duplicate code

### `/utils/` - Utility Modules (10 files)
Shared utilities and helper functions.

```
utils/
├── __init__.py
├── database.py                  # Database manager (1,281 lines) ⚠️
├── document_lineage.py          # Document tracking
├── entity_operations.py         # Entity-level operations
├── extraction_monitoring.py     # Monitoring extraction progress
├── local_drive.py              # Local file operations
├── logging.py                  # Logging configuration
├── pdf_extractor.py            # PDF extraction utilities
├── prompt_loader.py            # Load prompts for LLM
└── validation.py               # Validation utilities
```

**Critical File**:
- `database.py` - Largest file in project, handles all DB operations

### `/flows/` - Prefect Workflows (5 files)
Orchestration workflows combining tasks.

```
flows/
├── __init__.py
├── complete_pipeline.py         # Full pipeline workflow
├── process_single_pdf.py        # Single PDF processing
├── scrape_minnesota.py          # MN scraping workflow
└── scrape_wisconsin.py          # WI scraping workflow
```

### `/franchise_web_scraper/` - Legacy Scrapers (2 files)
Original scraper implementations (to be refactored).

```
franchise_web_scraper/
├── MN_Scraper.py               # Minnesota scraper (356 lines)
└── WI_scraper.py               # Wisconsin scraper (420 lines)
```

**Issues**:
- 40% code duplication
- Mixed responsibilities
- No shared utilities

### `/tests/` - Test Suite (22 files)
Comprehensive test coverage for all components.

```
tests/
├── __init__.py
├── conftest.py                 # Pytest fixtures
├── test_config.py
├── test_database.py
├── test_database_integration.py (698 lines)
├── test_document_processing.py  (610 lines)
├── test_document_processing_integration.py
├── test_document_segmentation.py (610 lines)
├── test_document_segmentation_integration.py
├── test_drive_operations.py     (889 lines)
├── test_llm_extraction.py
├── test_minnesota_flow.py
├── test_minnesota_flow_integration.py
├── test_minnesota_flow_simple.py
├── test_models.py              (964 lines)
├── test_prompt_loader.py
├── test_schema_validation.py
├── test_schema_validation_enhanced.py
├── test_validation_utils.py
├── test_web_scraping.py
├── test_wisconsin_flow.py
└── test_wisconsin_scraper.py
```

**Test Categories**:
- Unit tests (isolated component testing)
- Integration tests (*_integration.py files)
- Flow tests (end-to-end workflow testing)

### `/src/api/` - FastAPI Application (3 files)
REST API for external access.

```
src/api/
├── __init__.py
├── main.py                     # FastAPI app definition
└── run.py                      # API runner script
```

### `/scripts/` - Utility Scripts (12 files)
Administrative and deployment scripts.

```
scripts/
├── backup_database.py          # Database backup utility
├── check_config.py             # Configuration validation
├── deploy_minnesota_flow.py    # Deploy MN workflow
├── genson_schema_extractor.py  # Extract JSON schemas
├── health_check.py             # System health checks
├── monitoring.py               # Runtime monitoring
├── optimize_mineru.py          # Optimize document processor
├── orchestrate_workflow.py     # Workflow orchestration
├── run_deduplication.py        # Remove duplicate data
├── setup_gdrive_structure.py   # Initialize Google Drive
├── validate_config.py          # Config validation
└── verify_minnesota_implementation.py  # Verify MN setup
```

## Supporting Directories

### `/docs/` - Documentation
Comprehensive project documentation.

### `/migrations/` - Database Migrations
SQL migration scripts for database schema changes.

### `/examples/` - Example Data
Sample FDDs and extracted data for testing.

### `/prompts/` - LLM Prompts
Prompt templates for GPT extraction.

### `/config/` - Configuration Files
Environment-specific configuration.

## File Size Distribution

### Large Files (>800 lines) - Priority for Refactoring
1. `utils/database.py` - 1,281 lines
2. `tasks/schema_validation.py` - 1,127 lines
3. `tasks/document_processing.py` - 1,084 lines
4. `tests/test_models.py` - 964 lines
5. `tasks/drive_operations.py` - 896 lines
6. `tasks/minnesota_scraper.py` - 893 lines
7. `tests/test_drive_operations.py` - 889 lines
8. `tasks/document_segmentation.py` - 825 lines

### Medium Files (400-800 lines)
- Most model files
- Integration test files
- Scraper implementations

### Small Files (<400 lines)
- Utility scripts
- Configuration files
- Simple models

## Dependency Relationships

### Core Dependencies
```
models/ ← tasks/ ← flows/ ← src/api/
   ↑        ↑        ↑
   └────────┴────────┴──── utils/
```

### Test Dependencies
```
tests/ → all modules (for testing)
```

## Refactoring Priorities

### High Priority
1. **Split `utils/database.py`** into:
   - Connection management
   - CRUD operations
   - Transaction handling
   - Query builders

2. **Consolidate scrapers** into:
   - Base scraper class
   - State-specific implementations
   - Shared utilities

3. **Simplify `tasks/schema_validation.py`**:
   - Extract validation rules
   - Create validation registry
   - Separate concerns

### Medium Priority
1. Standardize error handling
2. Consolidate logging patterns
3. Extract common test utilities

### Low Priority
1. Documentation updates
2. Code style consistency
3. Performance optimizations

## Metrics Summary

- **Total Files**: 87 Python files
- **Total Lines**: 30,068
- **Average File Size**: 345 lines
- **Files Over 1000 Lines**: 4
- **Files Over 500 Lines**: 15
- **Test Coverage**: 22 test files (~25% of codebase)

This structure reveals a mature but complex codebase that would benefit from:
1. Breaking down large files
2. Extracting common patterns
3. Reducing coupling between modules
4. Standardizing patterns across similar components
