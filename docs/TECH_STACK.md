# Technology Stack

This document provides a comprehensive overview of all technologies, frameworks, and packages used in the FDD Pipeline project.

## Core Python Version
- **Python 3.11+** - Required for latest type hints and performance improvements

## Package Management
- **[UV](https://github.com/astral-sh/uv)** (latest) - Fast Python package installer and resolver by Astral
  - Replaces pip, pip-tools, pipx, poetry, pyenv, virtualenv
  - 10-100x faster than pip
  - Handles virtual environments natively
  - Built in Rust for performance and reliability
  - Single binary, no Python required for installation
  - Compatible with pip requirements files

## Workflow Orchestration
- **[Prefect](https://www.prefect.io/)** (2.14+) - Modern workflow orchestration
  - Flow and task decorators for pipeline definition
  - Built-in retry logic and error handling
  - Local and cloud deployment options
  - Real-time monitoring dashboard

## Web Scraping & Automation
- **[Playwright](https://playwright.dev/python/)** (1.40+) - Browser automation
  - Handles JavaScript-heavy sites
  - Built-in wait strategies
  - Headless and headed modes
- **[BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)** (4.12+) - HTML parsing
  - Simple API for navigating HTML
  - Works with requests/httpx responses
- **[httpx](https://www.python-httpx.org/)** (0.25+) - Modern HTTP client
  - Async/sync support
  - Connection pooling
  - Better than requests for production use

## Data Processing & Validation
- **[Pydantic](https://docs.pydantic.dev/)** (2.5+) - Data validation using Python type annotations
  - Settings management from environment
  - JSON schema generation
  - Automatic validation
  - Integration with FastAPI
- **[pandas](https://pandas.pydata.org/)** (2.1+) - Data manipulation
  - Table parsing from HTML
  - CSV/Excel operations
  - Data cleaning utilities

## Database & Storage
- **[supabase-py](https://github.com/supabase/supabase-py)** (2.3+) - Supabase client
  - PostgreSQL access
  - Real-time subscriptions
  - Storage bucket operations
  - Edge function invocation
- **[SQLAlchemy](https://www.sqlalchemy.org/)** (2.0+) - SQL toolkit and ORM
  - Complex query building
  - Connection pooling
  - Migration support
- **[google-api-python-client](https://github.com/googleapis/google-api-python-client)** (2.100+) - Google APIs
  - Drive API for file operations
  - Service account authentication
  - Resumable uploads

## AI/ML Stack

### LLM Integration
- **[instructor](https://github.com/jxnl/instructor)** (1.2+) - Structured LLM outputs
  - Pydantic model integration
  - Automatic retries on validation failure
  - Multi-provider support
- **[google-generativeai](https://github.com/google/generative-ai-python)** (0.3+) - Gemini Pro access
  - Primary LLM for complex extractions
  - Native multimodal support
- **[openai](https://github.com/openai/openai-python)** (1.6+) - OpenAI API
  - Fallback LLM provider
  - GPT-4 for high-complexity tasks
- **[ollama](https://github.com/ollama/ollama-python)** (0.1+) - Local LLM integration
  - Privacy-preserving processing
  - Cost-effective for simple tasks

### Document Processing
- **[MinerU/magic-pdf](https://github.com/opendatalab/MinerU)** (1.3.12, local installation) - GPU-accelerated PDF processing
  - **Purpose**: High-quality PDF to Markdown/JSON conversion with structure preservation
  - **Key Features**:
    - Deep learning-based layout analysis using state-of-the-art models
    - Accurate table and figure detection with boundary recognition
    - Mathematical formula preservation and rendering
    - Multi-language OCR support (84 languages)
    - Section identification and hierarchical structure extraction
    - Automatic removal of headers, footers, and page numbers
  - **Performance**:
    - GPU acceleration with CUDA support (10,000+ tokens/s on RTX 4090)
    - 10-50x faster than CPU-based alternatives
    - Batch processing capabilities with configurable batch size
    - Multi-GPU support via tensor parallelism
  - **Requirements**:
    - NVIDIA GPU with Turing architecture or newer (GTX 1060+)
    - 6-8GB VRAM minimum, 16GB+ recommended for optimal performance
    - ~15GB storage for model files (one-time download)
    - CUDA-compatible drivers
  - **Configuration**:
    - `MINERU_DEVICE`: cuda/cpu mode selection
    - `MINERU_BATCH_SIZE`: Memory optimization (default: 2)
    - `MINERU_MODEL_PATH`: Model storage location
  - **Fallback Options**:
    - CPU mode for environments without GPU
    - PyPDF2 for simple text extraction when MinerU fails
- **[PyPDF2](https://pypdf2.readthedocs.io/)** (3.0+) - PDF manipulation
  - Page splitting
  - Metadata extraction
  - Text extraction fallback

### Embeddings & Similarity
- **[sentence-transformers](https://www.sbert.net/)** (2.2+) - Semantic embeddings
  - Franchise name similarity
  - Deduplication
  - MiniLM-L6-v2 model (384 dimensions)

## API Framework
- **[FastAPI](https://fastapi.tiangolo.com/)** (0.104+) - Modern web API framework
  - Automatic OpenAPI documentation
  - Pydantic integration
  - Async support
  - Dependency injection
- **[uvicorn](https://www.uvicorn.org/)** (0.24+) - ASGI server
  - Production-ready performance
  - Auto-reload in development

## Development Tools

### Code Quality
- **[black](https://black.readthedocs.io/)** (23.12+) - Code formatter
  - Zero-config formatting
  - Consistent style across team
- **[flake8](https://flake8.pycqa.org/)** (6.1+) - Linting
  - PEP 8 compliance
  - Complexity checking
  - Plugin ecosystem
- **[mypy](http://mypy-lang.org/)** (1.7+) - Static type checker
  - Catches type errors before runtime
  - Gradual typing support
  - IDE integration

### Testing
- **[pytest](https://docs.pytest.org/)** (7.4+) - Testing framework
  - Fixture system
  - Parametrized tests
  - Plugin architecture
- **[pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)** (0.21+) - Async test support
- **[pytest-cov](https://pytest-cov.readthedocs.io/)** (4.1+) - Coverage reporting

### Git Hooks
- **[pre-commit](https://pre-commit.com/)** (3.5+) - Git hook management
  - Runs formatters/linters before commit
  - Consistent code quality
  - Language-agnostic

## Utilities
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** (1.0+) - Environment management
  - .env file loading
  - Development/production separation
- **[jinja2](https://jinja.palletsprojects.com/)** (3.1+) - Template engine
  - Prompt template rendering
  - Dynamic YAML generation
- **[pyyaml](https://pyyaml.org/)** (6.0+) - YAML parsing
  - Prompt template loading
  - Configuration files

## Monitoring & Logging
- **[structlog](https://www.structlog.org/)** (23.2+) - Structured logging
  - JSON output
  - Context preservation
  - Performance
- **[python-json-logger](https://github.com/madzak/python-json-logger)** (2.0+) - JSON log formatting

## Email & Notifications
- **Built-in `smtplib`** - Email sending
  - SMTP/TLS support
  - HTML emails
  - Attachment support

## Type Definitions
- **[types-requests](https://github.com/python/typeshed)** - Type stubs
- **[types-pyyaml](https://github.com/python/typeshed)** - Type stubs
- **[pandas-stubs](https://github.com/pandas-dev/pandas-stubs)** - Pandas type stubs

## Optional/Future Additions
- **[redis](https://github.com/redis/redis-py)** - Caching layer
- **[celery](https://docs.celeryproject.org/)** - Distributed task queue
- **[sentry-sdk](https://docs.sentry.io/platforms/python/)** - Error tracking
- **[prometheus-client](https://github.com/prometheus/client_python)** - Metrics export

## Development Environment

### Recommended IDE Extensions
- **VS Code**:
  - Python
  - Pylance
  - Black Formatter
  - GitLens
  - Thunder Client (API testing)

### System Requirements
- **Minimum**: 8GB RAM, 4 CPU cores
- **Recommended**: 16GB RAM, 8 CPU cores, NVIDIA GPU (6GB+ VRAM)
- **GPU**: 
  - Required for optimal MinerU performance
  - NVIDIA GPU with CUDA support (GTX 1060 or better)
  - 6GB+ VRAM for document processing
  - 8GB+ VRAM for local LLM inference
- **Storage**: 65GB+ free space (15GB for MinerU models)

## Version Pinning Strategy
- Exact versions in `requirements.txt` for production
- Flexible versions in `pyproject.toml` for development
- Monthly dependency updates with testing
- Security patches applied immediately

## Installation Example

```bash
# Install UV (one-time setup)
# Option 1: Using standalone installer (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Option 2: Using pipx
pipx install uv

# Option 3: Using pip (if other methods unavailable)
pip install --user uv

# Create virtual environment
uv venv

# Activate environment
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Install dependencies with UV
uv pip sync requirements.txt

# Or install from pyproject.toml (recommended)
uv pip install -e ".[dev]"

# UV handles all dependency resolution automatically
```

## Package Organization

```toml
# pyproject.toml structure
[project]
name = "fdd-pipeline"
dependencies = [
    "prefect>=2.14",
    "pydantic>=2.5",
    "fastapi>=0.104",
    # ... core deps
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "black>=23.12",
    "mypy>=1.7",
    # ... dev deps
]
```

## Security Considerations
- All packages verified through PyPI
- Dependency scanning via GitHub Dependabot
- No packages with known CVEs
- Regular security audits with `pip-audit`

---

For specific version constraints and the complete dependency tree, see `requirements.txt` and `requirements.lock`.