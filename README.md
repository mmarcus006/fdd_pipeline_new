# FDD Pipeline

Automated FDD (Franchise Disclosure Document) processing pipeline for extracting and analyzing franchise data from state regulatory portals.

## Features

- **Web Scraping**: Automated scraping of FDD documents from state regulatory websites (Minnesota CARDS, Wisconsin DFI)
- **Document Processing**: MinerU Web API integration for PDF layout analysis and section detection
- **AI Data Extraction**: Multi-model LLM framework for extracting structured data from FDD items (5, 6, 7, 19, 20, 21)
- **Data Validation**: Comprehensive schema and business rule validation
- **Database Integration**: Supabase PostgreSQL with full data lineage tracking
- **Workflow Orchestration**: Prefect-based pipeline with retry logic and monitoring
- **API Server**: FastAPI endpoints for programmatic access
- **Google Drive Storage**: Automatic document organization and storage

## Technology Stack

- **Python 3.11+**: Core language
- **Prefect 2.14+**: Workflow orchestration and monitoring
- **Instructor**: Structured LLM outputs with Pydantic integration
- **Playwright**: Browser automation for web scraping and MinerU authentication
- **MinerU Web API**: Advanced PDF processing and layout analysis
- **Supabase**: PostgreSQL database with built-in auth and storage
- **Pydantic 2.5+**: Data validation and modeling
- **FastAPI**: REST API framework
- **Google Gemini/OpenAI**: Primary LLM providers
- **Ollama**: Local LLM support for cost optimization

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd fdd_pipeline_new
```

2. Install dependencies:
```bash
uv sync
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys and settings
```

See [Configuration Reference](docs/CONFIGURATION_REFERENCE.md) for detailed setup.

## Quick Start

### Command Line Interface

```bash
# Run complete pipeline for all states
python main.py run-all

# Scrape specific state
python main.py scrape --state minnesota
python main.py scrape --state wisconsin

# Process a single PDF
python main.py process-pdf --path /path/to/fdd.pdf

# Health check
python main.py health-check

# Deploy to Prefect
python main.py orchestrate --deploy --schedule
```

### API Server

```bash
# Start the API server
python -m src.api.run

# API will be available at http://localhost:8000
# Documentation at http://localhost:8000/docs
```

## Project Structure

```
fdd_pipeline_new/
├── scrapers/           # Web scraping functionality
│   ├── base/          # Base scraper framework
│   ├── states/        # State-specific scrapers
│   └── utils/         # Scraping utilities
├── processing/         # Document processing
│   ├── extraction/    # LLM data extraction
│   ├── segmentation/  # Document segmentation
│   ├── mineru/        # MinerU integration
│   └── pdf/           # PDF utilities
├── workflows/          # Prefect workflow definitions
├── storage/            # Storage integrations
│   ├── database/      # Database management
│   └── google_drive.py
├── validation/         # Data validation
├── models/             # Pydantic data models
├── utils/              # General utilities
├── src/                # Additional source code
│   └── api/           # FastAPI endpoints
├── docs/              # Documentation
└── main.py            # CLI entry point
```

## Documentation

- [Project Overview (CLAUDE.md)](CLAUDE.md) - Comprehensive project documentation
- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [Database Schema](docs/database_schema.md) - PostgreSQL schema reference
- [Technology Stack](docs/TECH_STACK.md) - Detailed dependency list
- [MinerU Integration](docs/MINERU_INTEGRATION.md) - PDF processing setup
- [API Reference](docs/API_REFERENCE.md) - REST API documentation

## Development

This project uses:
- **UV** for dependency management
- **Black** for code formatting
- **Flake8** for linting
- **Pytest** for testing

Run tests:
```bash
pytest
```

Format code:
```bash
black .
```

## License

MIT License 