# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**MILLERS CUSTOM RULES**

## Project Overview

This is the FDD (Franchise Disclosure Document) Pipeline - a Python-based document processing system for acquiring, processing, validating, and storing franchise disclosure documents from state registries. The system uses Prefect for orchestration, multiple LLMs for extraction, and hybrid cloud storage.

## Key Commands

```bash
# Environment setup (UV package manager - NOT pip)
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Install MinerU locally (GPU-accelerated PDF processing)
pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com
magic-pdf model-download  # One-time setup, ~15GB

# Testing
pytest                          # Run all tests
pytest tests/unit/ -v --cov=src # Unit tests with coverage
pytest -m "not slow"            # Skip slow tests
make test                       # Via Makefile

# Code quality
black .                         # Format code
flake8                         # Lint
mypy .                         # Type checking
make check                     # All quality checks

# Prefect workflow
prefect server start           # Start server (terminal 1)
make prefect-deploy           # Deploy flows
prefect agent start -q default # Start agent (terminal 2)

# Database
make db-migrate               # Run migrations
make db-reset                # Reset database
```

## Architecture

The pipeline follows a distributed, event-driven architecture:

```
State Portals → Scrapers → Queue → Processing → Validation → Storage
                   ↓                    ↓            ↓           ↓
              [Playwright]    [MinerU(local)+LLMs] [Validators] [Supabase/GDrive]
```

### Core Components

1. **Scrapers** (`franchise_web_scraper/`, `tasks/*_scraper.py`)
   - State-specific implementations (WI_scraper.py, minnesota_scraper.py)
   - Use Playwright for browser automation
   - Implement retry logic and rate limiting

2. **Processing** (`tasks/`, `models/`)
   - PDF parsing with MinerU (local GPU installation)
   - LLM extraction using Instructor library
   - Multi-model fallback: Gemini Pro → Ollama → OpenAI

3. **Storage** (`utils/database.py`, `tasks/drive_operations.py`)
   - Metadata in Supabase (PostgreSQL)
   - Documents in Google Drive
   - Entity operations for deduplication

4. **Orchestration** (`flows/`)
   - Prefect flows for state-specific pipelines
   - Task decorators for retries and monitoring

## Development Patterns

### Adding a New State Scraper

1. Create `franchise_web_scraper/{STATE}_scraper.py`
2. Follow pattern from `WI_scraper.py` or `minnesota_scraper.py`
3. Implement methods: `login()`, `search_franchises()`, `get_document_details()`, `download_document()`
4. Create corresponding flow in `flows/scrape_{state}.py`
5. Add tests in `tests/test_{state}_scraper.py`

### Working with LLMs

```python
# Always use Instructor for structured outputs
from models.fdd_models import FDDSection
import instructor

# Pattern for LLM extraction with fallback
async def extract_section(text: str, model: str = "gemini-pro"):
    client = instructor.from_gemini(...)  # or from_openai, from_ollama
    return await client.create(
        model=model,
        response_model=FDDSection,
        messages=[...]
    )
```

### Database Operations

```python
# Always use utils.database functions
from utils.database import get_supabase_client, store_franchise_data

# Pattern for idempotent operations
client = get_supabase_client()
existing = client.table("franchises").select("*").eq("portal_id", id).execute()
if not existing.data:
    # Insert new record
```

## Environment Configuration

Create `.env` from `.env.template`:

```bash
# LLM APIs
GEMINI_API_KEY=
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

# Storage
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=
GDRIVE_CREDS_JSON=  # Path to service account JSON
GDRIVE_FOLDER_ID=

# MinerU Local
MINERU_MODEL_PATH=~/.mineru/models
MINERU_DEVICE=cuda  # or cpu
MINERU_BATCH_SIZE=2
```

## Code Standards

- **Type hints required** for all functions
- **Async/await** for I/O operations
- **Pydantic models** for all data structures (see `models/`)
- **Black formatting** with 88-char line limit
- **Structured logging** with correlation IDs
- **Test coverage target**: 80%+

## Common Issues

1. **Playwright timeout**: Check `--headed` mode, increase timeout, verify selectors
2. **MinerU GPU errors**: Fallback to `MINERU_DEVICE=cpu`, check CUDA installation
3. **LLM rate limits**: Implement exponential backoff, use fallback models
4. **Duplicate documents**: Check `entity_operations.py` fuzzy matching logic
5. **Large PDF memory issues**: Reduce `MINERU_BATCH_SIZE`, use CPU mode

## Testing Strategy

```bash
# Golden datasets for consistent testing
tests/fixtures/golden_datasets/

# Test markers
pytest -m unit        # Fast unit tests
pytest -m integration # External service tests
pytest -m performance # Performance benchmarks
```

## Project Structure

```
franchise_web_scraper/  # State-specific scrapers
flows/                  # Prefect workflow definitions  
models/                 # Pydantic models for FDD sections
prompts/               # LLM prompt templates (YAML)
tasks/                 # Reusable scraping/processing tasks
utils/                 # Database, logging, entity operations
migrations/            # Supabase schema (SQL)
tests/                 # Comprehensive test suite
config.py              # Pydantic Settings configuration
```

## Important Notes

- **UV is the package manager** - not pip or poetry
- **MinerU requires ~15GB** disk space for models
- **Always check existing patterns** before implementing new features
- **Prefect decorators** required on all tasks/flows
- **Idempotency is critical** - all operations must be retryable