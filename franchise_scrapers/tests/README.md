# Franchise Scrapers Unit Tests

This directory contains comprehensive unit tests for the franchise_scrapers module.

## Test Structure

```
tests/
├── unit/                      # Unit tests
│   ├── test_models.py        # Tests for Pydantic models
│   ├── test_parsers_mn.py    # Tests for Minnesota parsers
│   ├── test_details_parser_wi.py  # Tests for Wisconsin details parser
│   ├── test_config.py        # Tests for configuration management
│   ├── test_browser.py       # Tests for browser utilities
│   └── fixtures.py           # Shared test fixtures
├── conftest.py               # Pytest configuration
└── run_tests.py             # Test runner script
```

## Running Tests

### Run all unit tests:
```bash
# From the franchise_scrapers directory
python -m pytest tests/unit -v

# Or use the test runner
python tests/run_tests.py
```

### Run specific test file:
```bash
# Using pytest directly
python -m pytest tests/unit/test_models.py -v

# Using the test runner
python tests/run_tests.py models
```

### Run with coverage:
```bash
# Install coverage support
pip install pytest-cov

# Run with coverage
python -m pytest tests/unit --cov=franchise_scrapers --cov-report=html
```

### Run specific test class or method:
```bash
# Run specific test class
python -m pytest tests/unit/test_models.py::TestCleanFDDRow -v

# Run specific test method
python -m pytest tests/unit/test_models.py::TestCleanFDDRow::test_valid_clean_fdd_row -v
```

## Test Coverage

The unit tests cover:

1. **Models (test_models.py)**:
   - All Pydantic models validation
   - Required and optional fields
   - Edge cases (empty strings, None values)
   - Datetime handling
   - Serialization/deserialization

2. **Minnesota Parsers (test_parsers_mn.py)**:
   - HTML row parsing
   - Document ID extraction from URLs
   - Filename sanitization
   - Text cleaning utilities
   - Date and year parsing
   - FDD validation logic

3. **Wisconsin Details Parser (test_details_parser_wi.py)**:
   - Details page scraping
   - Metadata extraction with regex patterns
   - PDF download handling
   - Batch processing
   - CSV import/export
   - Error handling

4. **Configuration (test_config.py)**:
   - Environment variable loading
   - Default values
   - Validation rules
   - Type conversions
   - Backoff parsing
   - Directory creation

5. **Browser Utilities (test_browser.py)**:
   - Browser creation
   - Context configuration
   - Retry logic with exponential backoff
   - Error handling
   - Async operation support

## Writing New Tests

When adding new tests:

1. Follow the existing naming convention: `test_<module_name>.py`
2. Group related tests in classes: `class Test<ComponentName>:`
3. Use descriptive test names: `test_<what_is_being_tested>`
4. Use fixtures for common test data (see `fixtures.py`)
5. Mock external dependencies (Playwright, file system, etc.)
6. Test both success and failure cases
7. Include edge cases and boundary conditions

## Fixtures

Common fixtures are defined in `fixtures.py` and `conftest.py`:

- `sample_mn_table_html`: Sample Minnesota CARDS table HTML
- `sample_wi_details_html`: Sample Wisconsin details page HTML
- `mock_playwright_page/browser/context`: Mock Playwright objects
- `temp_download_dir`: Temporary directory for download tests
- `create_mock_element`: Factory for creating mock HTML elements

## Dependencies

Required packages for running tests:
```
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0  # Optional, for coverage reports
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines. They:
- Don't require actual browser instances (all mocked)
- Don't make real network requests
- Create temporary directories for file operations
- Clean up after themselves
- Run quickly (typically < 10 seconds for all tests)