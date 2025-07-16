# Project Structure & Organization

## Directory Layout

```
fdd-pipeline/
├── .kiro/                     # Kiro IDE configuration
│   └── steering/              # AI assistant guidance rules
├── docs/                      # Comprehensive documentation
│   ├── 01_architecture/       # System design documents
│   ├── 02_data_model/         # Database schema and Pydantic models
│   ├── 03_implementation/     # Setup guides and workflows
│   ├── 04_operations/         # Deployment and monitoring
│   └── 05_api_reference/      # API documentation
├── flows/                     # Prefect workflow definitions
├── models/                    # Pydantic models for each FDD section
├── prompts/                   # YAML prompt templates for LLM extraction
├── tasks/                     # Reusable Prefect tasks
├── utils/                     # Helper functions and utilities
├── migrations/                # Supabase schema migrations
├── tests/                     # Test suite
├── franchise_web_scraper/     # Legacy scraper (reference implementation)
└── config.py                  # Centralized configuration
```

## Code Organization Patterns

### Prefect Workflows (`flows/`)
- **State-specific scrapers**: `scrape_mn.py`, `scrape_wi.py`
- **Processing pipelines**: `process_documents.py`, `extract_sections.py`
- **Validation workflows**: `validate_data.py`, `quality_checks.py`
- **Maintenance tasks**: `cleanup_old_files.py`, `update_embeddings.py`

### Pydantic Models (`models/`)
- **Core entities**: `franchisor.py`, `fdd.py`, `section.py`
- **Structured data**: `item5_fees.py`, `item6_other_fees.py`, `item7_investment.py`
- **Financial data**: `item19_fpr.py`, `item20_outlets.py`, `item21_financials.py`
- **Operational**: `scrape_metadata.py`, `pipeline_logs.py`

### LLM Prompts (`prompts/`)
- **Section-specific**: `item_01.yaml`, `item_02.yaml`, etc.
- **Generic templates**: `base_extraction.yaml`, `validation_prompt.yaml`
- **Fallback prompts**: `simple_extraction.yaml`, `error_recovery.yaml`

### Reusable Tasks (`tasks/`)
- **Scraping**: `web_scraping.py`, `document_download.py`
- **Processing**: `document_segmentation.py`, `llm_extraction.py`
- **Storage**: `drive_operations.py`, `database_operations.py`
- **Validation**: `schema_validation.py`, `business_rules.py`

## File Naming Conventions

### Python Files
- **Snake_case** for all Python files and modules
- **Descriptive names**: `franchise_scraper.py`, `document_processor.py`
- **Prefect flows**: `{action}_{target}.py` (e.g., `scrape_minnesota.py`)
- **Models**: `{entity}.py` or `item{number}_{description}.py`

### Documentation
- **UPPERCASE** for main docs: `README.md`, `ARCHITECTURE.md`
- **Numbered sections**: `01_architecture/`, `02_data_model/`
- **Descriptive filenames**: `system_overview.md`, `database_schema.md`

### Configuration Files
- **Environment**: `.env`, `.env.template`, `.env.example`
- **Dependencies**: `requirements.txt`, `requirements-dev.txt`
- **Config**: `config.py`, `settings.py`

## Import Organization

### Standard Import Order
```python
# Standard library imports
import os
import json
from datetime import datetime
from typing import Optional, List, Dict

# Third-party imports
from pydantic import BaseModel, Field
from prefect import flow, task
import httpx

# Local imports
from models.franchisor import Franchisor
from tasks.web_scraping import scrape_portal
from utils.validation import validate_fdd_data
```

### Relative Imports
- Use absolute imports from project root
- Avoid deep relative imports (`../../`)
- Group related imports together

## Data Storage Patterns

### Google Drive Structure
```
/fdds/
├── /raw/                      # Original PDFs by source
│   ├── /mn/{franchise_slug}/
│   └── /wi/{franchise_slug}/
├── /processed/                # Segmented documents
│   └── /{franchise_id}/{year}/
└── /archive/                  # Superseded documents
```

### Database Schema Organization
- **Core tables**: `franchisors`, `fdds`, `fdd_sections`
- **Structured data**: `item5_initial_fees`, `item6_other_fees`, etc.
- **Operational**: `scrape_metadata`, `pipeline_logs`, `extraction_attempts`
- **Views**: Aggregated data for common queries

## Testing Structure

### Test Organization
```
tests/
├── unit/                      # Unit tests for individual functions
├── integration/               # Integration tests for workflows
├── fixtures/                  # Test data and mock objects
└── conftest.py               # Pytest configuration and fixtures
```

### Test Naming
- **Test files**: `test_{module_name}.py`
- **Test functions**: `test_{function_name}_{scenario}`
- **Test classes**: `Test{ClassName}`

## Configuration Management

### Environment Variables
- **Database**: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- **Storage**: `GDRIVE_FOLDER_ID`, `GDRIVE_CREDS_JSON`
- **AI Services**: `GEMINI_API_KEY`, `OPENAI_API_KEY`
- **Workflow**: `PREFECT_API_URL`, `PREFECT_API_KEY`

### Settings Hierarchy
1. Environment variables (highest priority)
2. `.env` file
3. Default values in `config.py`
4. Runtime configuration

## Documentation Standards

### Code Documentation
- **Docstrings**: Use Google-style docstrings for all functions/classes
- **Type hints**: Required for all function parameters and returns
- **Comments**: Explain business logic, not obvious code

### API Documentation
- **FastAPI**: Automatic OpenAPI generation
- **Pydantic models**: Include field descriptions and examples
- **Edge functions**: Document in `docs/05_api_reference/`

## Development Workflow

### Branch Strategy
- **main**: Production-ready code
- **develop**: Integration branch for features
- **feature/***: Individual feature development
- **hotfix/***: Critical production fixes

### Code Quality Gates
1. **Pre-commit hooks**: Format, lint, type check
2. **Tests**: Unit and integration test coverage
3. **Documentation**: Update relevant docs
4. **Review**: Peer code review required