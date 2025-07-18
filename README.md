# FDD Pipeline

Automated FDD (Franchise Disclosure Document) processing pipeline for extracting and analyzing franchise data.

## Features

- **Web Scraping**: Automated scraping of FDD documents from state regulatory websites
- **Document Processing**: AI-powered extraction of structured data from FDD documents
- **Data Validation**: Comprehensive validation of extracted franchise information
- **Database Integration**: Supabase integration for data storage and management
- **Workflow Orchestration**: Prefect-based pipeline orchestration

## Technology Stack

- **Python 3.11+**: Core language
- **Prefect**: Workflow orchestration
- **Instructor**: LLM-powered data extraction
- **Playwright**: Web automation
- **Supabase**: Database and storage
- **Pydantic**: Data validation and modeling

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

3. Configure environment variables (see configuration documentation)

## Usage

The pipeline consists of several main components:

- **Web Scraping**: Extract FDD documents from regulatory websites
- **Document Processing**: Parse and extract structured data from PDFs
- **Data Storage**: Store processed data in Supabase database

For detailed usage instructions, see the documentation in the `docs/` directory.

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