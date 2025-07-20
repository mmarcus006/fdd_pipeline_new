"""Pytest configuration and shared fixtures for franchise_scrapers tests."""

import pytest
import asyncio
from pathlib import Path
import sys

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import all fixtures from the fixtures module
from franchise_scrapers.tests.unit.fixtures import *


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_environment(monkeypatch):
    """Reset environment variables before each test."""
    # Clear any franchise_scrapers related environment variables
    env_vars_to_clear = [
        'HEADLESS',
        'DOWNLOAD_DIR',
        'THROTTLE_SEC',
        'PDF_RETRY_MAX',
        'PDF_RETRY_BACKOFF',
        'MAX_WORKERS'
    ]
    
    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings for testing."""
    from unittest.mock import MagicMock
    from pathlib import Path
    
    mock = MagicMock()
    mock.HEADLESS = True
    mock.DOWNLOAD_DIR = Path("./test_downloads")
    mock.THROTTLE_SEC = 0.1
    mock.PDF_RETRY_MAX = 3
    mock.PDF_RETRY_BACKOFF = [0.1, 0.2, 0.4]
    mock.MAX_WORKERS = 2
    
    monkeypatch.setattr('franchise_scrapers.config.settings', mock)
    return mock


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)