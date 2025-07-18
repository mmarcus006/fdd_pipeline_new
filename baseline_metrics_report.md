# FDD Pipeline Baseline Metrics Report

## Executive Summary
This report provides a comprehensive baseline analysis of the FDD Pipeline project's current codebase structure, identifying areas for refactoring and consolidation.

## 1. Project Structure Overview

### Directory Structure
```
fdd_pipeline_new/
├── config.py                 # Configuration management
├── examples/                 # Example data and demonstrations
├── flows/                    # Prefect workflow definitions (5 files)
├── franchise_web_scraper/    # Legacy scrapers (2 files)
├── models/                   # Database models (16 files)
├── prompts/                  # LLM prompts (1 file)
├── scripts/                  # Utility scripts (12 files)
├── src/
│   └── api/                  # FastAPI application (3 files)
├── tasks/                    # Prefect tasks (12 files)
├── tests/                    # Test files (22 files)
└── utils/                    # Utility modules (10 files)
```

### File Count by Directory
- **Root**: 2 Python files
- **examples**: 1 file
- **flows**: 5 files
- **franchise_web_scraper**: 2 files (MN_Scraper.py, WI_scraper.py)
- **models**: 16 files
- **prompts**: 1 file
- **scripts**: 12 files
- **src/api**: 3 files
- **tasks**: 12 files
- **tests**: 22 files
- **utils**: 10 files

**Total**: 87 Python files

## 2. Codebase Metrics

### Overall Statistics
- **Total Python Files**: 87
- **Total Lines of Code**: 30,068
- **Average Lines per File**: ~345

### Module Breakdown
1. **Tests** (22 files) - Largest number of files
2. **Models** (16 files) - Database schema definitions
3. **Tasks** (12 files) - Business logic
4. **Scripts** (12 files) - Utility and deployment scripts
5. **Utils** (10 files) - Shared utilities

## 3. Duplicate Code Analysis

### Minnesota vs Wisconsin Scrapers

#### Common Patterns Identified:
1. **Browser Automation Setup**
   - Both use Playwright for web scraping
   - Similar browser initialization patterns
   - Common session management code

2. **File Operations**
   - Similar filename sanitization functions
   - Duplicate PDF download logic
   - Common CSV export patterns

3. **Error Handling**
   - Similar retry mechanisms
   - Duplicate exception handling patterns

#### Key Differences:
- **MN_Scraper.py**: 356 lines, uses requests + Playwright hybrid approach
- **WI_scraper.py**: 420 lines, pure Playwright approach with more complex cleanup

#### Duplication Estimate: ~40% code overlap

## 4. Database Operations Analysis

### Database Usage Patterns
Database operations are spread across multiple modules:

1. **Core Database Module**: `utils/database.py` (1,276 lines)
   - Main database manager implementation
   - Session management
   - CRUD operations

2. **Models using SQLAlchemy**:
   - All 16 model files use SQLAlchemy
   - Common patterns: Base, Column, Integer, String, DateTime, ForeignKey
   - Relationships defined across models

3. **Database Operations by Module**:
   - **models/**: Schema definitions
   - **tasks/**: Business logic with DB operations
   - **utils/database.py**: Core DB utilities
   - **tests/**: Test database operations

### Database Complexity
- Multiple inheritance patterns in models
- Complex relationships between tables
- JSON field handling for flexible data storage

## 5. Package Dependencies Analysis

### Most Used Imports (Top 20)
1. `from datetime import datetime` (33 occurrences)
2. `import asyncio` (31 occurrences)
3. `from uuid import UUID` (27 occurrences)
4. `from pathlib import Path` (26 occurrences)
5. `import pytest` (20 occurrences)
6. `import os` (17 occurrences)
7. `import sys` (16 occurrences)
8. `from utils.logging import get_logger` (16 occurrences)
9. `import json` (14 occurrences)
10. `from config import get_settings` (12 occurrences)

### External Dependencies
Major external packages used:
- **Web Scraping**: playwright, beautifulsoup4, requests
- **Database**: sqlalchemy, asyncpg
- **Workflow**: prefect
- **API**: fastapi, httpx
- **Data Processing**: pandas, pydantic
- **Document Processing**: PyPDF2, mineru
- **Cloud Services**: google-api-python-client, boto3

## 6. Complexity Analysis

### High Complexity Areas
1. **utils/database.py** (1,276 lines) - Needs breaking down
2. **tasks/schema_validation.py** (1,069+ lines) - Complex validation logic
3. **Legacy scrapers** - Monolithic scripts with mixed concerns

### Code Organization Issues
1. **Mixed Responsibilities**: Scrapers contain download, parsing, and storage logic
2. **Duplicate Validation**: Similar validation patterns across multiple files
3. **Scattered Configuration**: Settings spread across files

## 7. Refactoring Opportunities

### Priority 1: Scraper Consolidation
- Extract common web scraping utilities
- Create base scraper class
- Separate concerns (download, parse, store)

### Priority 2: Database Operations
- Consolidate CRUD operations
- Implement repository pattern
- Centralize transaction management

### Priority 3: Configuration Management
- Centralize all configuration
- Environment-specific settings
- Validation of configuration values

### Priority 4: Testing Infrastructure
- Reduce test duplication
- Create test fixtures library
- Improve test organization

## 8. Technical Debt Summary

### Immediate Concerns
1. **Code Duplication**: ~40% overlap in scrapers
2. **Large Files**: Several files over 1,000 lines
3. **Mixed Concerns**: Business logic mixed with infrastructure

### Long-term Improvements
1. Implement proper separation of concerns
2. Create reusable component library
3. Standardize error handling patterns
4. Improve logging consistency

## 9. Recommendations

### Short-term (Sprint 1-2)
1. Create base scraper class to eliminate duplication
2. Extract common utilities from large files
3. Standardize error handling patterns

### Medium-term (Sprint 3-4)
1. Implement repository pattern for database operations
2. Refactor configuration management
3. Create comprehensive testing utilities

### Long-term (Sprint 5+)
1. Modularize the entire codebase
2. Implement proper dependency injection
3. Create plugin architecture for scrapers

## 10. Metrics for Success

### Code Quality Metrics
- Reduce average file size from 345 to <200 lines
- Eliminate 80% of code duplication
- Achieve 90%+ test coverage

### Maintainability Metrics
- Reduce coupling between modules
- Increase cohesion within modules
- Standardize patterns across codebase

---

*Report generated on: December 2024*
*Next review scheduled: After Phase 1 refactoring*
