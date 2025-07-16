# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in 
this repository.

**MILLERS CUSTOM RULES**


## Project Overview

This is the FDD (Franchise Disclosure Document) Pipeline - a Python-based document processing system for acquiring, processing, validating, and storing franchise disclosure documents from state registries. The system uses Prefect for orchestration, multiple LLMs for extraction, and hybrid cloud storage.

## Key Responsibilities When Working on This Code

1. **Maintain idempotency** - All operations should be safely retryable
2. **Preserve observability** - Use structured logging and Prefect task decorators
3. **Handle failures gracefully** - Implement exponential backoff and circuit breakers
4. **Validate all data** - Use Pydantic models for type safety
5. **Test thoroughly** - Unit tests for logic, integration tests for external services

## Technology Stack

- **Python 3.11+** with UV package manager
- **Prefect** - Workflow orchestration
- **Playwright** - Web scraping automation
- **MinerU** - Local PDF parsing and extraction (GPU-accelerated)
- **Instructor** - Structured LLM outputs
- **LLMs**: Gemini Pro (primary), Ollama (local), OpenAI (fallback)
- **Supabase** - PostgreSQL database
- **Google Drive API** - Document storage
- **Pydantic** - Data validation
- **Loguru** - Structured logging

## High-Level Architecture

The pipeline follows a distributed, event-driven architecture:

```
State Portals → Scrapers → Queue → Processing → Validation → Storage
                   ↓                    ↓            ↓           ↓
              [Playwright]    [MinerU(local)+LLMs] [Validators] [Supabase/GDrive]
```

### Core Components

1. **Acquisition Layer** (`scrapers/`)
   - State-specific web scrapers using Playwright
   - Handles authentication, navigation, and download
   - Implements retry logic and rate limiting

2. **Processing Layer** (`processors/`)
   - PDF parsing with MinerU (local GPU-accelerated installation)
   - LLM extraction using Instructor
   - Multi-model fallback strategy

3. **Validation Layer** (`validators/`)
   - Schema validation with Pydantic
   - Business rule validation
   - Cross-reference checks

4. **Storage Layer** (`storage/`)
   - Metadata in Supabase (PostgreSQL)
   - Documents in Google Drive
   - Hybrid indexing for fast retrieval

## Development Commands

```bash
# Setup environment
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Install MinerU locally
pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com
# Download models (run once, ~15GB)
magic-pdf model-download

# Run tests
pytest tests/ -v
pytest tests/unit/ -v --cov=src
pytest tests/integration/ -v -m "not slow"

# Linting and formatting
ruff check .
ruff format .
mypy src/

# Run specific scraper
python -m src.scrapers.wisconsin_scraper

# Run Prefect flow
prefect server start  # In one terminal
python -m src.flows.fdd_pipeline  # In another

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "Description"
```

## Common Development Tasks

### Adding a New State Scraper

1. Create new file in `src/scrapers/{state}_scraper.py`
2. Inherit from `BaseScraper` class
3. Implement required methods: `authenticate()`, `navigate_to_search()`, `extract_results()`, `download_document()`
4. Add state configuration to `config/states.yaml`
5. Register in `src/scrapers/__init__.py`

### Adding a New LLM Model

1. Create adapter in `src/llm/adapters/{model}_adapter.py`
2. Implement `LLMAdapter` interface
3. Add to model registry in `src/llm/registry.py`
4. Update fallback chain in `config/llm_config.yaml`

### Modifying Extraction Schema

1. Update Pydantic models in `src/models/fdd_schema.py`
2. Generate new migration: `alembic revision --autogenerate`
3. Update validation rules in `src/validators/schema_validator.py`
4. Add tests for new fields

## Environment Configuration

Required environment variables (create `.env` file):

```bash
# LLM APIs
GEMINI_API_KEY=
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

# Storage
SUPABASE_URL=
SUPABASE_KEY=
GOOGLE_DRIVE_CREDENTIALS_PATH=

# Prefect
PREFECT_API_URL=
PREFECT_API_KEY=

# Scraping
PROXY_URL=  # Optional
USER_AGENT=  # Optional

# MinerU Local
MINERU_MODEL_PATH=~/.mineru/models  # Path to downloaded models
MINERU_DEVICE=cuda  # cuda or cpu
```

## Code Standards

- Use type hints for all function signatures
- Implement proper error handling with custom exceptions
- Log at appropriate levels (DEBUG for details, INFO for flow, ERROR for failures)
- Use async/await for I/O operations
- Follow PEP 8 with 88-character line limit (Black formatting)
- Document complex logic with inline comments
- Create Pydantic models for all data structures

## Testing Guidelines

- Unit tests for all business logic
- Integration tests for external services (marked with `@pytest.mark.integration`)
- Use `pytest-mock` for mocking external dependencies
- Maintain >80% code coverage
- Test both success and failure paths

## Monitoring and Debugging

- Check Prefect UI for flow runs: http://localhost:4200
- Logs are structured JSON, searchable by correlation ID
- Use `LOGURU_LEVEL=DEBUG` for verbose logging
- Monitor retry attempts in `logs/retries.log`
- Database queries logged with execution time

## Common Issues and Solutions

1. **Playwright timeout**: Increase `timeout` in scraper config or check proxy
2. **LLM extraction fails**: Check model availability, API limits, or schema complexity
3. **Storage upload fails**: Verify credentials and quota limits
4. **Memory issues with large PDFs**: Reduce batch size or use CPU mode for MinerU
5. **Duplicate documents**: Check idempotency keys in database
6. **MinerU GPU errors**: Ensure CUDA is properly installed, fallback to CPU mode
7. **MinerU model download fails**: Check disk space (~15GB required) and network connection