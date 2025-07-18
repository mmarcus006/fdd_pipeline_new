# Testing Strategy

## Overview

This document outlines the comprehensive testing strategy for the FDD Pipeline project, including unit tests, integration tests, golden dataset validation, and performance testing approaches.

## Testing Philosophy

Our testing strategy follows these core principles:

1. **Test-Driven Development (TDD)** - Write tests before implementation when possible
2. **Comprehensive Coverage** - Aim for >80% code coverage
3. **Fast Feedback** - Tests should run quickly to encourage frequent execution
4. **Realistic Testing** - Use golden datasets that represent real-world scenarios
5. **Automated Validation** - Catch issues early through automated testing

## Test Categories

### 1. Unit Tests

Unit tests validate individual components in isolation.

**Location**: `tests/unit/`

**Characteristics**:
- Fast execution (< 1 second per test)
- No external dependencies (mock external services)
- Test single functions or methods
- High code coverage

**Example**:
```python
# tests/unit/test_transformations.py
import pytest
import pandas as pd
from src.transformations.customer import standardize_customer_data

class TestCustomerTransformations:
    def test_standardize_customer_data_valid_input(self):
        # Arrange
        input_data = pd.DataFrame({
            'customer_id': ['123', '456'],
            'name': ['John Doe', 'Jane Smith'],
            'email': ['john@example.com', 'jane@example.com']
        })
        
        # Act
        result = standardize_customer_data(input_data)
        
        # Assert
        assert len(result) == 2
        assert result['customer_id'].dtype == 'int64'
        assert result['email'].str.contains('@').all()
    
    def test_standardize_customer_data_missing_columns(self):
        # Arrange
        input_data = pd.DataFrame({'customer_id': ['123']})
        
        # Act & Assert
        with pytest.raises(ValueError, match="Missing required columns"):
            standardize_customer_data(input_data)
```

### 2. Integration Tests

Integration tests validate the interaction between multiple components.

**Location**: `tests/integration/`

**Characteristics**:
- Test component interactions
- May use test databases or services
- Longer execution time acceptable
- Focus on data flow and system behavior

**Example**:
```python
# tests/integration/test_data_pipeline.py
import pytest
from prefect.testing.utilities import prefect_test_harness
from src.flows.daily_processing import daily_processing_flow

class TestDataPipeline:
    @pytest.fixture(autouse=True, scope="session")
    def prefect_test_fixture(self):
        with prefect_test_harness():
            yield
    
    def test_daily_processing_flow_complete(self, golden_dataset):
        # Arrange
        input_data = golden_dataset['daily_transactions']
        
        # Act
        result = daily_processing_flow(
            input_path=input_data,
            output_path='/tmp/test_output'
        )
        
        # Assert
        assert result.is_successful()
        assert len(result.get_tasks()) == 5
        # Validate output files exist and are correct
```

### 3. Golden Dataset Tests

Golden datasets are carefully curated test datasets that represent real-world scenarios.

**Location**: `tests/fixtures/golden_datasets/`

**Structure**:
```
tests/fixtures/golden_datasets/
├── README.md                    # Documentation of datasets
├── small/                       # Small datasets for unit tests
│   ├── valid_customers.csv
│   ├── valid_transactions.csv
│   └── expected_outputs/
├── medium/                      # Medium datasets for integration tests
│   ├── daily_batch_2024_01.csv
│   └── expected_outputs/
└── edge_cases/                  # Edge case scenarios
    ├── missing_data.csv
    ├── duplicate_records.csv
    └── invalid_formats.csv
```

**Golden Dataset Categories**:

1. **Valid Data**
   - Representative samples of clean, valid data
   - Tests happy path scenarios
   - Validates correct processing

2. **Edge Cases**
   - Missing values
   - Duplicate records
   - Maximum/minimum values
   - Empty datasets

3. **Invalid Data**
   - Malformed records
   - Invalid data types
   - Out-of-range values
   - Inconsistent formats

**Example Golden Dataset Test**:
```python
# tests/unit/test_validations.py
import pytest
import pandas as pd
from src.validations.data_quality import validate_transaction_data

class TestDataValidation:
    @pytest.mark.parametrize("dataset_name", [
        "valid_transactions.csv",
        "transactions_with_nulls.csv",
        "transactions_with_duplicates.csv"
    ])
    def test_validate_transactions_golden_datasets(self, golden_dataset, dataset_name):
        # Arrange
        data = golden_dataset[dataset_name]
        expected = golden_dataset.expected_results[dataset_name]
        
        # Act
        validation_result = validate_transaction_data(data)
        
        # Assert
        assert validation_result.is_valid == expected['is_valid']
        assert validation_result.error_count == expected['error_count']
        assert set(validation_result.error_types) == set(expected['error_types'])
```

### 4. Performance Tests

Performance tests ensure the pipeline can handle expected data volumes.

**Location**: `tests/performance/`

**Metrics to Track**:
- Processing time per record
- Memory usage
- CPU utilization
- I/O throughput

**Example**:
```python
# tests/performance/test_batch_processing.py
import pytest
import time
import psutil
from src.tasks.batch_processing import process_large_batch

class TestPerformance:
    @pytest.mark.performance
    def test_large_batch_processing_time(self, large_golden_dataset):
        # Arrange
        data = large_golden_dataset['10k_transactions']
        process = psutil.Process()
        
        # Act
        start_time = time.time()
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        result = process_large_batch(data)
        
        end_time = time.time()
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Assert
        processing_time = end_time - start_time
        memory_increase = peak_memory - start_memory
        
        assert processing_time < 60  # Should process in under 1 minute
        assert memory_increase < 500  # Should use less than 500MB additional
        assert len(result) == len(data)  # No data loss
```

## Test Structure and Organization

### Directory Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── unit/                    # Unit tests
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_transformations.py
│   └── test_validations.py
├── integration/             # Integration tests
│   ├── __init__.py
│   ├── test_flows.py
│   └── test_end_to_end.py
├── performance/             # Performance tests
│   ├── __init__.py
│   └── test_batch_processing.py
├── fixtures/                # Test data and fixtures
│   ├── __init__.py
│   ├── golden_datasets/
│   └── mock_data.py
└── utils/                   # Test utilities
    ├── __init__.py
    └── helpers.py
```

### Fixture Management

**conftest.py example**:
```python
# tests/conftest.py
import pytest
import pandas as pd
from pathlib import Path

@pytest.fixture(scope="session")
def test_data_dir():
    """Path to test data directory."""
    return Path(__file__).parent / "fixtures" / "golden_datasets"

@pytest.fixture
def golden_dataset(test_data_dir):
    """Load golden datasets for testing."""
    class GoldenDataset:
        def __getitem__(self, name):
            file_path = test_data_dir / "small" / name
            if file_path.suffix == '.csv':
                return pd.read_csv(file_path)
            elif file_path.suffix == '.json':
                return pd.read_json(file_path)
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
        
        @property
        def expected_results(self):
            # Load expected results for validation
            return {
                "valid_transactions.csv": {
                    "is_valid": True,
                    "error_count": 0,
                    "error_types": []
                },
                "transactions_with_nulls.csv": {
                    "is_valid": False,
                    "error_count": 5,
                    "error_types": ["null_values"]
                }
            }
    
    return GoldenDataset()

@pytest.fixture
def mock_s3_client():
    """Mock S3 client for testing."""
    from unittest.mock import Mock
    client = Mock()
    client.upload_file.return_value = True
    client.download_file.return_value = True
    return client
```

## Testing Patterns and Best Practices

### 1. Arrange-Act-Assert Pattern

All tests should follow the AAA pattern:

```python
def test_example():
    # Arrange - Set up test data and conditions
    input_data = create_test_data()
    expected_result = {"status": "success"}
    
    # Act - Execute the code being tested
    actual_result = function_under_test(input_data)
    
    # Assert - Verify the results
    assert actual_result == expected_result
```

### 2. Parametrized Tests

Use parametrized tests to test multiple scenarios:

```python
@pytest.mark.parametrize("input_value,expected", [
    (None, "default"),
    ("", "default"),
    ("custom", "custom"),
    ("CUSTOM", "custom"),  # Test case insensitivity
])
def test_get_config_value(input_value, expected):
    result = get_config_value(input_value)
    assert result == expected
```

### 3. Testing Data Transformations

```python
class TestDataTransformations:
    def test_transformation_preserves_row_count(self):
        # Ensure no data loss
        input_df = pd.DataFrame({'id': range(100)})
        output_df = transform_data(input_df)
        assert len(output_df) == len(input_df)
    
    def test_transformation_data_types(self):
        # Verify correct data types
        input_df = pd.DataFrame({
            'date_str': ['2024-01-01', '2024-01-02'],
            'amount_str': ['100.50', '200.75']
        })
        output_df = transform_data(input_df)
        
        assert output_df['date'].dtype == 'datetime64[ns]'
        assert output_df['amount'].dtype == 'float64'
    
    def test_transformation_business_logic(self):
        # Test specific business rules
        input_df = pd.DataFrame({
            'amount': [100, 200, 300],
            'tax_rate': [0.1, 0.15, 0.2]
        })
        output_df = calculate_total_with_tax(input_df)
        
        expected_totals = [110, 230, 360]
        assert output_df['total'].tolist() == expected_totals
```

### 4. Testing Error Conditions

```python
def test_invalid_input_raises_exception():
    with pytest.raises(ValueError, match="Invalid customer ID format"):
        validate_customer_id("ABC123!")  # Invalid format

def test_empty_dataframe_handling():
    empty_df = pd.DataFrame()
    result = process_transactions(empty_df)
    assert result.empty
    assert list(result.columns) == ['transaction_id', 'status']  # Schema preserved
```

### 5. Mock External Dependencies

```python
from unittest.mock import patch, Mock

@patch('src.connectors.s3.boto3.client')
def test_s3_upload(mock_boto_client):
    # Arrange
    mock_s3 = Mock()
    mock_boto_client.return_value = mock_s3
    mock_s3.upload_file.return_value = None
    
    # Act
    result = upload_to_s3('test.csv', 'bucket', 'key')
    
    # Assert
    assert result is True
    mock_s3.upload_file.assert_called_once_with('test.csv', 'bucket', 'key')
```

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_transformations.py

# Run specific test
pytest tests/unit/test_transformations.py::test_standardize_customer_data

# Run tests matching pattern
pytest -k "customer"

# Run tests with specific marker
pytest -m "unit"

# Run tests in parallel
pytest -n auto

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Markers

Define custom markers in `pytest.ini`:

```ini
[tool:pytest]
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (slower, multiple components)
    performance: Performance tests (measure speed/resources)
    golden: Tests using golden datasets
    slow: Tests that take > 5 seconds
    requires_db: Tests that need database connection
```

Use markers in tests:

```python
@pytest.mark.unit
def test_fast_unit():
    pass

@pytest.mark.integration
@pytest.mark.requires_db
def test_database_integration():
    pass

@pytest.mark.slow
@pytest.mark.performance
def test_large_batch_performance():
    pass
```

### Coverage Configuration

Create `.coveragerc`:

```ini
[run]
source = src
omit = 
    */tests/*
    */venv/*
    */__pycache__/*

[report]
precision = 2
show_missing = True
skip_covered = False

[html]
directory = htmlcov
```

## Continuous Testing

### Pre-commit Hooks

Configure `.pre-commit-config.yaml` to run tests:

```yaml
- repo: local
  hooks:
    - id: pytest-check
      name: pytest-check
      entry: pytest tests/unit -x
      language: system
      pass_filenames: false
      always_run: true
```

### Test Automation Guidelines

1. **Run unit tests on every commit** (via pre-commit)
2. **Run full test suite before pushing**
3. **Monitor test execution time** - investigate slow tests
4. **Maintain test coverage** above 80%
5. **Regular test maintenance** - update golden datasets quarterly

## Testing Checklist

Before submitting a PR, ensure:

- [ ] All new code has corresponding tests
- [ ] All tests pass locally
- [ ] Code coverage meets or exceeds 80%
- [ ] Golden dataset tests cover main scenarios
- [ ] Performance tests pass for large datasets
- [ ] No skipped or disabled tests without justification
- [ ] Test documentation is updated if needed

## Troubleshooting

### Common Issues

1. **Import Errors in Tests**
   ```bash
   # Ensure project is installed in editable mode with UV
   uv pip install -e ".[dev]"
   
   # Alternative: Set Python path manually
   export PYTHONPATH="${PYTHONPATH}:${PWD}/src"
   ```

2. **Fixture Not Found**
   ```python
   # Check fixture is in conftest.py or properly imported
   # Use pytest --fixtures to list available fixtures
   ```

3. **Flaky Tests**
   - Add retry logic for network-dependent tests
   - Use fixed random seeds for reproducibility
   - Mock time-dependent functions

4. **Slow Tests**
   ```python
   # Use pytest-timeout to identify slow tests
   @pytest.mark.timeout(10)  # Fail if test takes > 10 seconds
   def test_should_be_fast():
       pass
   ```

## Best Practices Summary

1. **Write tests first** when implementing new features
2. **Keep tests simple** and focused on one thing
3. **Use descriptive test names** that explain what is being tested
4. **Maintain test independence** - tests shouldn't depend on each other
5. **Clean up after tests** - don't leave test artifacts
6. **Update golden datasets** when business logic changes
7. **Review test code** as carefully as production code
8. **Monitor test metrics** - execution time, coverage, flakiness