# Integration Tests for Franchise Scrapers

This directory contains integration tests for the franchise scraping workflows.

## Test Structure

- **`conftest.py`**: Shared fixtures and test configuration
- **`test_mn_flow.py`**: Minnesota CARDS portal integration tests
- **`test_active_wi.py`**: Wisconsin active filings extraction tests
- **`test_details_wi.py`**: Full Wisconsin workflow tests (active -> search -> details)

## Running Tests

### Mock Tests (Default - CI Friendly)
These tests use mocked responses and don't require internet access:

```bash
# Run all mock integration tests
pytest franchise_scrapers/tests/integration/ -m mock

# Run specific test file
pytest franchise_scrapers/tests/integration/test_mn_flow.py -m mock

# Run with verbose output
pytest franchise_scrapers/tests/integration/ -m mock -v
```

### Live Tests (Requires Internet)
These tests interact with actual state portals:

```bash
# Run live integration tests
pytest franchise_scrapers/tests/integration/ --live -m live

# Run specific live test
pytest franchise_scrapers/tests/integration/test_mn_flow.py::TestMinnesotaFlow::test_live_minnesota_scraping --live

# Run with timeout (recommended for live tests)
pytest franchise_scrapers/tests/integration/ --live -m live --timeout=300
```

### All Tests
```bash
# Run both mock and live tests
pytest franchise_scrapers/tests/integration/

# Run with coverage
pytest franchise_scrapers/tests/integration/ --cov=franchise_scrapers --cov-report=html
```

## Test Markers

- `@pytest.mark.mock`: Tests that use mocked data (default)
- `@pytest.mark.live`: Tests that connect to real portals (requires `--live` flag)
- `@pytest.mark.asyncio`: Async test functions
- `@pytest.mark.timeout(seconds)`: Set timeout for long-running tests

## Test Categories

### Minnesota Tests (`test_mn_flow.py`)
- Navigation and page loading
- Table data extraction
- Pagination handling
- CSV output generation
- PDF download flow (mocked and live)
- Error recovery mechanisms
- Full workflow integration

### Wisconsin Active Tests (`test_active_wi.py`)
- Active filings page navigation
- HTML table parsing
- CSV format validation
- Error handling (network, missing data)
- Empty/malformed data handling

### Wisconsin Full Workflow Tests (`test_details_wi.py`)
- Search functionality
- Parallel search operations
- Details page extraction
- PDF download process
- Resume capability from existing CSVs
- Data consistency validation
- End-to-end workflow

## Fixtures

### Mock Fixtures
- `mock_browser`: Async mock of Playwright browser/page
- `sample_mn_table_data`: Sample Minnesota franchise data
- `sample_wi_active_data`: Sample Wisconsin active filings
- `sample_wi_registered_data`: Sample registered franchises
- `sample_wi_details_data`: Sample details page data
- `mock_html_responses`: HTML page mocks for different portals
- `mock_download`: Mock file download object

### Utility Fixtures
- `temp_dir`: Temporary directory for test outputs
- `mock_csv_writer`: CSV writer that creates real files
- `assert_csv_contents`: Helper for CSV validation
- `cleanup_downloads`: Cleanup downloaded files after tests

## Environment Variables

Tests respect these environment variables:
- `HEADLESS`: Run browser in headless mode (default: true for tests)
- `DOWNLOAD_DIR`: Directory for downloaded files (uses temp dir in tests)
- `THROTTLE_SEC`: Delay between requests (reduced for tests)

## Writing New Tests

1. **Mock Tests**: Use the `mock_browser` fixture and mock all external calls
2. **Live Tests**: Mark with `@pytest.mark.live` and handle timeouts
3. **Async Tests**: Use `@pytest.mark.asyncio` decorator
4. **Data Validation**: Use `assert_csv_contents` for CSV validation
5. **Error Cases**: Test both success and failure scenarios

## CI/CD Integration

For CI pipelines, run only mock tests:
```yaml
pytest franchise_scrapers/tests/integration/ -m mock --tb=short
```

For nightly/scheduled runs, include live tests:
```yaml
pytest franchise_scrapers/tests/integration/ --live --timeout=600
```

## Debugging

Enable debug output:
```bash
# Set logging level
pytest franchise_scrapers/tests/integration/ -s -v --log-cli-level=DEBUG

# Run single test with print statements
pytest -s franchise_scrapers/tests/integration/test_mn_flow.py::TestMinnesotaFlow::test_extract_table_data
```

## Known Issues

1. **Live tests may fail due to portal changes**: State portals occasionally update their HTML structure
2. **Rate limiting**: Live tests may trigger rate limits if run too frequently
3. **Download timeouts**: PDF downloads can be slow on state portals

## Contributing

When adding new integration tests:
1. Create both mock and live versions when possible
2. Use appropriate markers (`@pytest.mark.mock`, `@pytest.mark.live`)
3. Handle timeouts and network errors gracefully
4. Document any specific portal quirks in test docstrings
5. Keep test data minimal but representative