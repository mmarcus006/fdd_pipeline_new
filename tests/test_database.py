"""Tests for database utilities."""

import pytest
from unittest.mock import Mock, patch

from utils.database import DatabaseManager, get_supabase_client


def test_database_manager_initialization():
    """Test DatabaseManager initialization."""
    db_manager = DatabaseManager()
    assert db_manager.settings is not None
    assert db_manager._supabase_client is None


@patch("utils.database.create_client")
def test_get_supabase_client(mock_create_client, sample_settings):
    """Test Supabase client creation."""
    mock_client = Mock()
    mock_create_client.return_value = mock_client

    with patch("utils.database.get_settings", return_value=sample_settings):
        db_manager = DatabaseManager()
        client = db_manager.get_supabase_client()

        assert client == mock_client
        mock_create_client.assert_called_once_with(
            sample_settings.supabase_url, sample_settings.supabase_service_key
        )


@patch("utils.database.db_manager")
def test_get_supabase_client_function(mock_db_manager):
    """Test get_supabase_client convenience function."""
    mock_client = Mock()
    mock_db_manager.get_supabase_client.return_value = mock_client

    client = get_supabase_client()

    assert client == mock_client
    mock_db_manager.get_supabase_client.assert_called_once()
