"""Pytest configuration and fixtures for FDD Pipeline tests."""

import pytest
from pathlib import Path
from unittest.mock import Mock

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def test_data_dir():
    """Provide path to test data directory."""
    return TEST_DATA_DIR


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for testing."""
    mock_client = Mock()
    mock_table = Mock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.execute.return_value = Mock(data=[])
    return mock_client


@pytest.fixture
def sample_settings():
    """Sample settings for testing."""
    from config import Settings

    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_key="test-service-key",
        gdrive_creds_json="/tmp/test-creds.json",
        gdrive_folder_id="test-folder-id",
        mineru_api_key="test-mineru-key",
        gemini_api_key="test-gemini-key",
        debug=True,
        log_level="DEBUG",
    )
