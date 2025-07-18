# FDD Pipeline Dependencies Inventory

## Overview
This document provides a comprehensive inventory of all Python packages and their usage across the FDD Pipeline project.

## Standard Library Dependencies

### Most Used Standard Library Modules
1. **datetime** (33 files) - Date/time handling
2. **asyncio** (31 files) - Asynchronous programming
3. **uuid** (27 files) - Unique identifier generation
4. **pathlib** (26 files) - File system paths
5. **os** (17 files) - Operating system interface
6. **sys** (16 files) - System-specific parameters
7. **json** (14 files) - JSON data handling
8. **time** (10 files) - Time-related functions
9. **re** (7 files) - Regular expressions
10. **logging** (8 files) - Logging facility

## External Dependencies

### Web Scraping & Automation
- **playwright** - Web browser automation
  - Used in: franchise_web_scraper/, tasks/web_scraping.py
  - Purpose: Automated web scraping
  
- **beautifulsoup4** - HTML/XML parsing
  - Used in: franchise_web_scraper/MN_Scraper.py
  - Purpose: Parse HTML content
  
- **requests** - HTTP library
  - Used in: franchise_web_scraper/, various tasks
  - Purpose: HTTP requests for downloads

### Database & ORM
- **sqlalchemy** - SQL toolkit and ORM
  - Used in: All model files, utils/database.py
  - Purpose: Database abstraction and ORM
  
- **asyncpg** - Async PostgreSQL driver
  - Used in: utils/database.py
  - Purpose: Async database operations

### Workflow Orchestration
- **prefect** - Workflow orchestration
  - Used in: flows/, tasks/
  - Purpose: Pipeline orchestration and task management

### Web Framework & API
- **fastapi** - Modern web framework
  - Used in: src/api/
  - Purpose: REST API endpoints
  
- **httpx** - Async HTTP client
  - Used in: Various async operations
  - Purpose: Async HTTP requests

### Data Processing & Validation
- **pydantic** - Data validation
  - Used in: models/, tasks/
  - Purpose: Data validation and settings management
  
- **pandas** - Data manipulation
  - Used in: franchise_web_scraper/, data processing
  - Purpose: Data analysis and CSV handling

### Document Processing
- **PyPDF2** - PDF processing
  - Used in: Document processing tasks
  - Purpose: Extract text from PDFs
  
- **mineru** - Document extraction
  - Used in: Document processing pipeline
  - Purpose: Advanced document parsing

### Cloud Services
- **google-api-python-client** - Google APIs
  - Used in: Drive operations
  - Purpose: Google Drive integration
  
- **boto3** - AWS SDK
  - Used in: S3 operations
  - Purpose: AWS service integration

### Testing
- **pytest** - Testing framework
  - Used in: All test files
  - Purpose: Unit and integration testing
  
- **unittest.mock** - Mocking library
  - Used in: Test files
  - Purpose: Mock objects for testing

## Usage Matrix by Module

### Core Modules Dependencies

| Module | Key Dependencies |
|--------|------------------|
| **models/** | sqlalchemy, pydantic, datetime, uuid |
| **tasks/** | prefect, pydantic, asyncio, httpx |
| **utils/** | sqlalchemy, logging, pathlib |
| **flows/** | prefect, datetime, logging |
| **tests/** | pytest, unittest.mock, asyncio |

### Scraper-Specific Dependencies

| Scraper | Dependencies |
|---------|--------------|
| **MN_Scraper.py** | playwright, beautifulsoup4, requests, pandas |
| **WI_scraper.py** | playwright, csv, json, signal |

## Dependency Patterns

### Async vs Sync
- **Async-heavy modules**: utils/database.py, API endpoints
- **Sync modules**: Legacy scrapers, some utility scripts

### Data Flow Dependencies
```
Input (Web/Files) → Processing (pydantic/pandas) → Storage (sqlalchemy) → Output (API/Files)
```

### Testing Dependencies
- Heavy use of mocking for external services
- Async test patterns with pytest-asyncio
- Fixtures for database and file operations

## Version Requirements

From pyproject.toml and requirements.txt:
- Python 3.11+
- Major versions:
  - sqlalchemy ~2.0
  - prefect ~2.0
  - fastapi ~0.100+
  - pydantic ~2.0

## Redundant or Overlapping Dependencies

### Potential Consolidation
1. **HTTP Libraries**: Both requests and httpx are used
   - Recommendation: Standardize on httpx for async support

2. **PDF Processing**: Multiple PDF libraries
   - Current: PyPDF2, pypdf, mineru
   - Recommendation: Evaluate and choose one primary library

3. **Date/Time Handling**: datetime, time, pendulum
   - Recommendation: Standardize date handling approach

## Security Considerations

### External Service Dependencies
- Google API credentials
- AWS credentials
- Database connection strings

### Network Dependencies
- All scrapers require internet access
- API endpoints expose data externally
- Cloud storage integrations

## Recommendations

### 1. Dependency Standardization
- Choose one HTTP client library
- Standardize PDF processing approach
- Consolidate date/time handling

### 2. Version Pinning
- Create comprehensive requirements.txt
- Use poetry or pip-tools for dependency management
- Regular security updates

### 3. Modular Dependencies
- Core dependencies vs optional features
- Separate production and development dependencies
- Create dependency groups for different components

### 4. Documentation
- Document why each dependency is needed
- Create migration guides for dependency updates
- Maintain compatibility matrix

## Dependency Health Metrics

### Update Status
- Check for outdated packages
- Security vulnerability scanning
- License compatibility

### Usage Efficiency
- Identify barely-used dependencies
- Find duplicate functionality
- Measure import time impact

## Next Steps

1. **Audit**: Full dependency audit with versions
2. **Consolidate**: Remove redundant packages
3. **Document**: Create dependency decision records
4. **Automate**: Set up dependency update automation
5. **Monitor**: Track dependency health metrics
