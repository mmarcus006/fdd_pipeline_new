# Technology Stack & Build System

## Core Technologies

### Python Environment
- **Python 3.11+** - Required for latest type hints and performance
- **uv** - Fast Python package manager (replaces pip, poetry, virtualenv)
- **Virtual Environment**: Managed automatically by uv

### Key Frameworks
- **Prefect 2.14+** - Workflow orchestration with decorators and monitoring
- **FastAPI 0.104+** - Modern web API framework with auto-documentation
- **Pydantic 2.5+** - Data validation using Python type annotations
- **Playwright 1.40+** - Browser automation for web scraping
- **Instructor 1.2+** - Structured LLM outputs with Pydantic integration

### AI/ML Stack
- **Gemini Pro** - Primary LLM for complex extractions
- **Ollama** - Local LLM for privacy-preserving/cost-effective processing
- **OpenAI GPT-4** - Fallback for highest accuracy requirements
- **MinerU API** - Document layout analysis and segmentation
- **sentence-transformers** - Semantic embeddings for deduplication

### Storage & Database
- **Supabase/PostgreSQL** - Primary database with built-in auth and APIs
- **Google Drive API** - Document storage with unlimited capacity
- **SQLAlchemy 2.0+** - ORM and query building

### Development Tools
- **black** - Code formatting (zero-config)
- **mypy** - Static type checking
- **pytest** - Testing framework with async support
- **pre-commit** - Git hooks for code quality

## Common Commands

### Environment Setup
```bash
# Install uv if not present
pip install uv

# Create virtual environment and install dependencies
uv venv
uv pip sync requirements.txt

# Development dependencies
uv pip install -e ".[dev]"
```

### Development Workflow
```bash
# Format code
black .

# Type checking
mypy .

# Run tests
pytest

# Run tests with coverage
pytest --cov=.

# Install pre-commit hooks
pre-commit install
```

### Pipeline Operations
```bash
# Start Prefect server (local development)
prefect server start

# Deploy flows
prefect deployment build flows/scrape_mn.py:scrape_minnesota -n mn-weekly
prefect deployment apply

# Start agent
prefect agent start -q default

# Trigger manual run
prefect deployment run scrape-minnesota/mn-weekly
```

### Database Operations
```bash
# Run Supabase migrations
supabase db push

# Reset local database
supabase db reset
```

## Architecture Patterns

### LLM Model Selection Strategy
- **Simple structured data** (Items 5,6,7): Use Ollama local models for speed/cost
- **Complex narratives** (Items 19,21): Use Gemini Pro for accuracy
- **Fallback chain**: Primary → Secondary → OpenAI GPT-4

### Error Handling
- **Retry Logic**: 3 attempts with exponential backoff
- **Graceful Degradation**: Fallback models and manual review flags
- **Comprehensive Logging**: Structured logs with context preservation

### Data Validation Tiers
1. **Schema Validation**: Pydantic models with type checking
2. **Business Rules**: Domain-specific validation (totals, date logic)
3. **Quality Checks**: Completeness scoring and OCR quality assessment

## Configuration Management
- **Environment Variables**: Use `.env` files with python-dotenv
- **Pydantic Settings**: Type-safe configuration management
- **Secrets**: Never commit credentials, use environment variables