# Development Workflow

## Overview

This document outlines the day-to-day development workflow for the FDD Pipeline project, including code standards, conventions, and contribution guidelines.

## Development Environment Setup

### Prerequisites

- Python 3.11 or later
- UV package manager
- Git
- Prefect (for local workflow testing)

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd fdd_pipeline_new
   ```

2. **Install UV package manager**
   ```bash
   # Recommended: Install using pipx
   pipx install uv
   
   # Alternative: Standalone installer
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Create virtual environment and install dependencies**
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e ".[dev]"
   ```

4. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

## Day-to-Day Development Process

### 1. Starting a New Feature

1. **Update your local main branch**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/descriptive-feature-name
   ```
   
   Branch naming conventions:
   - `feature/` - New features
   - `fix/` - Bug fixes
   - `docs/` - Documentation updates
   - `refactor/` - Code refactoring
   - `test/` - Test additions or modifications

### 2. Development Cycle

1. **Write code following our standards** (see Code Standards section below)

2. **Run code quality checks locally**
   ```bash
   # Format code with Black
   black src/ tests/
   
   # Check linting with Flake8
   flake8 src/ tests/
   
   # Type checking with MyPy
   mypy src/
   ```

3. **Run tests**
   ```bash
   # Run all tests
   pytest
   
   # Run specific test file
   pytest tests/test_specific_module.py
   
   # Run with coverage
   pytest --cov=src --cov-report=html
   ```

4. **Test with Prefect locally**
   ```bash
   # Start Prefect server (in separate terminal)
   prefect server start
   
   # Run your flow
   python src/flows/your_flow.py
   ```

### 3. Committing Changes

1. **Stage your changes**
   ```bash
   git add -A
   ```

2. **Commit with descriptive message**
   ```bash
   git commit -m "feat: add data validation for customer records"
   ```
   
   Commit message format:
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `style:` - Code style changes (formatting, etc.)
   - `refactor:` - Code refactoring
   - `test:` - Test additions or changes
   - `chore:` - Maintenance tasks

3. **Pre-commit hooks will automatically run**
   - If any checks fail, fix the issues and re-commit

### 4. Pushing Changes

1. **Push your feature branch**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a Pull Request**
   - Go to GitHub and create a PR from your branch to main
   - Fill out the PR template with:
     - Description of changes
     - Related issue numbers
     - Testing performed
     - Screenshots (if applicable)

### 5. Code Review Process

1. **Request review** from at least one team member
2. **Address feedback** by pushing additional commits
3. **Ensure all checks pass**:
   - All tests passing
   - Code quality checks passing
   - Documentation updated if needed

### 6. Merging

1. **Once approved**, the PR can be merged
2. **Delete the feature branch** after merging
3. **Update your local repository**
   ```bash
   git checkout main
   git pull origin main
   git branch -d feature/your-feature-name
   ```

## Code Standards and Conventions

### Python Style Guide

We follow PEP 8 with the following specifications:

1. **Code Formatting**
   - Use Black with default settings
   - Line length: 88 characters (Black default)
   - Use double quotes for strings

2. **Imports**
   ```python
   # Standard library imports
   import os
   import sys
   from datetime import datetime
   
   # Third-party imports
   import pandas as pd
   import numpy as np
   from prefect import flow, task
   
   # Local imports
   from src.models import DataModel
   from src.utils import logger
   ```

3. **Naming Conventions**
   - **Variables and functions**: `snake_case`
   - **Classes**: `PascalCase`
   - **Constants**: `UPPER_SNAKE_CASE`
   - **Private methods/attributes**: `_leading_underscore`

4. **Type Hints**
   ```python
   def process_data(
       df: pd.DataFrame,
       config: Dict[str, Any],
       validate: bool = True
   ) -> pd.DataFrame:
       """Process the input dataframe according to config."""
       pass
   ```

5. **Docstrings**
   ```python
   def calculate_metrics(data: pd.DataFrame) -> Dict[str, float]:
       """
       Calculate key metrics from the input data.
       
       Args:
           data: Input dataframe containing transaction data
           
       Returns:
           Dictionary containing calculated metrics
           
       Raises:
           ValueError: If data is empty or missing required columns
       """
       pass
   ```

### Project Structure

```
fdd_pipeline_new/
├── src/
│   ├── __init__.py
│   ├── flows/           # Prefect flows
│   ├── tasks/           # Prefect tasks
│   ├── models/          # Data models and schemas
│   ├── transformations/ # Data transformation logic
│   ├── validations/     # Data validation logic
│   └── utils/          # Utility functions
├── tests/
│   ├── unit/           # Unit tests
│   ├── integration/    # Integration tests
│   └── fixtures/       # Test fixtures and golden datasets
├── docs/               # Documentation
├── scripts/            # Utility scripts
└── config/            # Configuration files
```

### Configuration Management

1. **Environment Variables**
   - Use `.env` files for local development
   - Never commit sensitive information
   - Document all required environment variables

2. **Configuration Files**
   - Use YAML or JSON for configuration
   - Keep development and production configs separate
   - Version control configuration templates

### Error Handling

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)

def risky_operation(data: pd.DataFrame) -> pd.DataFrame:
    """Perform operation with proper error handling."""
    try:
        # Validate input
        if data.empty:
            raise ValueError("Input dataframe is empty")
            
        # Perform operation
        result = data.copy()
        # ... processing logic ...
        
        logger.info(f"Successfully processed {len(result)} records")
        return result
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in risky_operation: {e}")
        raise
```

## Contributing Guidelines

### Before You Start

1. **Check existing issues** to avoid duplicate work
2. **Discuss major changes** by creating an issue first
3. **Keep changes focused** - one feature/fix per PR

### Pull Request Guidelines

1. **PR Title** should clearly describe the change
2. **PR Description** should include:
   - What changes were made and why
   - How to test the changes
   - Any breaking changes or migrations needed

3. **PR Checklist**:
   - [ ] Code follows project style guidelines
   - [ ] Tests added/updated for new functionality
   - [ ] Documentation updated if needed
   - [ ] All tests passing locally
   - [ ] Pre-commit hooks passing

### Testing Requirements

- All new features must include tests
- Maintain or improve code coverage
- Include both positive and negative test cases
- Test edge cases and error conditions

### Documentation Requirements

- Update docstrings for any modified functions
- Update README if adding new features
- Add inline comments for complex logic
- Update configuration documentation if needed

## Debugging and Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure you're in the project root and have installed in editable mode
   uv pip install -e ".[dev]"
   ```

2. **Pre-commit Hook Failures**
   ```bash
   # Run pre-commit manually to see detailed errors
   pre-commit run --all-files
   ```

3. **Type Checking Errors**
   ```bash
   # Run mypy with more verbose output
   mypy src/ --show-error-codes
   ```

### Debugging Prefect Flows

1. **Enable debug logging**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Use Prefect UI** to monitor flow runs
   ```bash
   prefect server start
   # Navigate to http://localhost:4200
   ```

3. **Test tasks individually**
   ```python
   # Run task synchronously for debugging
   result = my_task.fn(param1, param2)
   ```

## Best Practices

1. **Keep commits atomic** - one logical change per commit
2. **Write self-documenting code** - clear variable names and function purposes
3. **Optimize for readability** - code is read more often than written
4. **Test early and often** - don't wait until the end to test
5. **Ask for help** - reach out if you're stuck or unsure

## Resources

- [Python Style Guide (PEP 8)](https://www.python.org/dev/peps/pep-0008/)
- [Black Documentation](https://black.readthedocs.io/)
- [Prefect Documentation](https://docs.prefect.io/)
- [Pytest Documentation](https://docs.pytest.org/)