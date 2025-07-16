"""Integration tests for database utilities."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4
from datetime import datetime

from utils.database import (
    DatabaseManager, 
    DatabaseHealthCheck,
    CRUDOperations,
    get_database_manager, 
    get_supabase_client, 
    test_database_connection
)
from models.franchisor import Franchisor, FranchisorCreate


class TestDatabaseHealthCheck:
    """Test DatabaseHealthCheck functionality."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager for testing."""
        return Mock(spec=DatabaseManager)
    
    @pytest.fixture
    def health_check(self, mock_db_manager):
        """DatabaseHealthCheck instance with mocked dependencies."""
        return DatabaseHealthCheck(mock_db_manager)
    
    def test_check_connection_success(self, health_check, mock_db_manager):
        """Test successful connection health check."""
        # Setup mocks
        mock_client = Mock()
        mock_client.table().select().limit().execute.return_value = Mock()
        mock_db_manager.get_supabase_client.return_value = mock_client
        
        # Mock the context manager properly
        mock_session = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_session)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_db_manager.get_session.return_value = mock_context_manager
        
        mock_engine = Mock()
        mock_pool = Mock()
        mock_pool.size.return_value = 10
        mock_pool.checkedin.return_value = 8
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 0
        mock_pool.invalid.return_value = 0
        mock_engine.pool = mock_pool
        mock_db_manager.get_sqlalchemy_engine.return_value = mock_engine
        
        # Execute
        result = health_check.check_connection()
        
        # Verify
        assert result['healthy'] is True
        assert result['supabase_connection'] is True
        assert result['sqlalchemy_connection'] is True
        assert 'response_time_ms' in result
        assert result['pool_status']['size'] == 10
    
    def test_check_connection_failure(self, health_check, mock_db_manager):
        """Test connection health check with failure."""
        # Setup mock to raise exception
        mock_db_manager.get_supabase_client.side_effect = Exception("Connection failed")
        
        # Execute
        result = health_check.check_connection()
        
        # Verify
        assert result['healthy'] is False
        assert result['error'] == "Connection failed"
        assert 'response_time_ms' in result
    
    def test_check_table_exists_success(self, health_check, mock_db_manager):
        """Test successful table existence check."""
        # Setup
        mock_engine = Mock()
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = ['franchisors', 'fdds', 'fdd_sections']
        mock_db_manager.get_sqlalchemy_engine.return_value = mock_engine
        
        with patch('utils.database.inspect', return_value=mock_inspector):
            # Execute
            result = health_check.check_table_exists('franchisors')
        
        # Verify
        assert result is True
    
    def test_check_table_exists_not_found(self, health_check, mock_db_manager):
        """Test table existence check when table doesn't exist."""
        # Setup
        mock_engine = Mock()
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = ['other_table']
        mock_db_manager.get_sqlalchemy_engine.return_value = mock_engine
        
        with patch('utils.database.inspect', return_value=mock_inspector):
            # Execute
            result = health_check.check_table_exists('nonexistent_table')
        
        # Verify
        assert result is False


class TestDatabaseManager:
    """Test DatabaseManager functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        with patch('utils.database.get_settings') as mock:
            mock.return_value.supabase_url = 'https://test.supabase.co'
            mock.return_value.supabase_service_key = 'test-service-key'
            mock.return_value.debug = False
            yield mock.return_value
    
    @pytest.fixture
    def db_manager(self, mock_settings):
        """DatabaseManager instance with mocked dependencies."""
        return DatabaseManager()
    
    def test_singleton_behavior(self):
        """Test that database manager behaves as singleton."""
        manager1 = get_database_manager()
        manager2 = get_database_manager()
        
        assert manager1 is manager2
    
    @patch('utils.database.create_client')
    def test_supabase_client_initialization(self, mock_create_client, db_manager):
        """Test Supabase client initialization."""
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        
        client = db_manager.get_supabase_client()
        
        assert client is mock_client
        mock_create_client.assert_called_once_with(
            'https://test.supabase.co',
            'test-service-key'
        )
    
    @patch('utils.database.create_engine')
    def test_sqlalchemy_engine_initialization(self, mock_create_engine, db_manager):
        """Test SQLAlchemy engine initialization."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        engine = db_manager.get_sqlalchemy_engine()
        
        assert engine is mock_engine
        mock_create_engine.assert_called_once()
        
        # Check connection string format
        call_args = mock_create_engine.call_args[0]
        assert call_args[0].startswith('postgresql://postgres:test-service-key@')
    
    def test_execute_query_success(self, db_manager):
        """Test successful query execution."""
        # Setup
        mock_session = Mock()
        mock_result = Mock()
        mock_result.returns_rows = True
        mock_result.keys.return_value = ['id', 'name']
        mock_result.fetchall.return_value = [('1', 'Test'), ('2', 'Test2')]
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Execute
            result = db_manager.execute_query("SELECT * FROM test")
        
        # Verify
        assert len(result) == 2
        assert result[0] == {'id': '1', 'name': 'Test'}
        assert result[1] == {'id': '2', 'name': 'Test2'}
    
    def test_execute_batch_insert_success(self, db_manager):
        """Test successful batch insert."""
        # Setup
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': '1'}, {'id': '2'}]
        mock_client.table().insert().execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            records = [{'name': 'Test1'}, {'name': 'Test2'}]
            result = db_manager.execute_batch_insert('test_table', records)
        
        # Verify
        assert result == 2
        mock_client.table.assert_called_with('test_table')
    
    def test_upsert_record_success(self, db_manager):
        """Test successful record upsert."""
        # Setup
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': '1', 'name': 'Test'}]
        mock_client.table().upsert().execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            record = {'name': 'Test'}
            result = db_manager.upsert_record('test_table', record, ['name'])
        
        # Verify
        assert result == {'id': '1', 'name': 'Test'}
        mock_client.table().upsert.assert_called_with(record, on_conflict='name')
    
    def test_get_record_by_id_found(self, db_manager):
        """Test getting record by ID when found."""
        # Setup
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': '1', 'name': 'Test'}]
        mock_client.table().select().eq().execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            result = db_manager.get_record_by_id('test_table', '1')
        
        # Verify
        assert result == {'id': '1', 'name': 'Test'}
    
    def test_get_record_by_id_not_found(self, db_manager):
        """Test getting record by ID when not found."""
        # Setup
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = []
        mock_client.table().select().eq().execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            result = db_manager.get_record_by_id('test_table', '1')
        
        # Verify
        assert result is None
    
    def test_get_records_by_filter_success(self, db_manager):
        """Test getting records with filters."""
        # Setup
        mock_client = Mock()
        mock_query = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': '1', 'status': 'active'}]
        
        # Chain the query methods
        mock_client.table.return_value.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            result = db_manager.get_records_by_filter(
                'test_table', 
                {'status': 'active'}, 
                limit=10, 
                order_by='created_at'
            )
        
        # Verify
        assert result == [{'id': '1', 'status': 'active'}]
        mock_query.eq.assert_called_with('status', 'active')
        mock_query.order.assert_called_with('created_at')
        mock_query.limit.assert_called_with(10)
    
    def test_update_record_success(self, db_manager):
        """Test successful record update."""
        # Setup
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': '1', 'name': 'Updated'}]
        mock_client.table().update().eq().execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            result = db_manager.update_record('test_table', '1', {'name': 'Updated'})
        
        # Verify
        assert result == {'id': '1', 'name': 'Updated'}
    
    def test_delete_record_success(self, db_manager):
        """Test successful record deletion."""
        # Setup
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': '1'}]
        mock_client.table().delete().eq().execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            result = db_manager.delete_record('test_table', '1')
        
        # Verify
        assert result is True
    
    def test_count_records_success(self, db_manager):
        """Test successful record counting."""
        # Setup
        mock_client = Mock()
        mock_query = Mock()
        mock_response = Mock()
        mock_response.count = 42
        
        mock_client.table.return_value.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.execute.return_value = mock_response
        
        with patch.object(db_manager, 'get_supabase_client', return_value=mock_client):
            # Execute
            result = db_manager.count_records('test_table', {'status': 'active'})
        
        # Verify
        assert result == 42
    
    def test_transaction_success(self, db_manager):
        """Test successful transaction."""
        # Setup
        mock_session = Mock()
        
        with patch.object(db_manager, 'get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Execute
            with db_manager.transaction() as session:
                session.execute("INSERT INTO test VALUES (1)")
        
        # Verify
        mock_session.commit.assert_called_once()
    
    def test_transaction_rollback_on_error(self, db_manager):
        """Test transaction rollback on error."""
        # Setup
        mock_session = Mock()
        
        with patch.object(db_manager, 'get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Execute & Verify
            with pytest.raises(ValueError):
                with db_manager.transaction() as session:
                    raise ValueError("Test error")
        
        mock_session.rollback.assert_called_once()


class TestCRUDOperations:
    """Test CRUDOperations functionality."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager for testing."""
        return Mock(spec=DatabaseManager)
    
    @pytest.fixture
    def crud_ops(self, mock_db_manager):
        """CRUDOperations instance for testing."""
        return CRUDOperations(mock_db_manager, 'franchisors', Franchisor)
    
    def test_create_success(self, crud_ops, mock_db_manager):
        """Test successful record creation."""
        # Setup
        mock_client = Mock()
        mock_response = Mock()
        test_data = {
            'id': str(uuid4()),
            'canonical_name': 'Test Franchise',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        mock_response.data = [test_data]
        mock_client.table().insert().execute.return_value = mock_response
        mock_db_manager.get_supabase_client.return_value = mock_client
        
        # Execute
        franchisor_create = FranchisorCreate(canonical_name='Test Franchise')
        result = crud_ops.create(franchisor_create)
        
        # Verify
        assert isinstance(result, Franchisor)
        assert result.canonical_name == 'Test Franchise'
    
    def test_get_by_id_found(self, crud_ops, mock_db_manager):
        """Test getting record by ID when found."""
        # Setup
        test_data = {
            'id': str(uuid4()),
            'canonical_name': 'Test Franchise',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        mock_db_manager.get_record_by_id.return_value = test_data
        
        # Execute
        result = crud_ops.get_by_id(test_data['id'])
        
        # Verify
        assert isinstance(result, Franchisor)
        assert result.canonical_name == 'Test Franchise'
    
    def test_get_by_id_not_found(self, crud_ops, mock_db_manager):
        """Test getting record by ID when not found."""
        # Setup
        mock_db_manager.get_record_by_id.return_value = None
        
        # Execute
        result = crud_ops.get_by_id('nonexistent-id')
        
        # Verify
        assert result is None
    
    def test_get_many_success(self, crud_ops, mock_db_manager):
        """Test getting multiple records."""
        # Setup
        test_data = [
            {
                'id': str(uuid4()),
                'canonical_name': 'Test Franchise 1',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            },
            {
                'id': str(uuid4()),
                'canonical_name': 'Test Franchise 2',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
        ]
        mock_db_manager.get_records_by_filter.return_value = test_data
        
        # Execute
        result = crud_ops.get_many({'status': 'active'}, limit=10)
        
        # Verify
        assert len(result) == 2
        assert all(isinstance(item, Franchisor) for item in result)
        assert result[0].canonical_name == 'Test Franchise 1'
        assert result[1].canonical_name == 'Test Franchise 2'
    
    def test_update_success(self, crud_ops, mock_db_manager):
        """Test successful record update."""
        # Setup
        test_data = {
            'id': str(uuid4()),
            'canonical_name': 'Updated Franchise',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        mock_db_manager.update_record.return_value = test_data
        
        # Execute
        result = crud_ops.update(test_data['id'], {'canonical_name': 'Updated Franchise'})
        
        # Verify
        assert isinstance(result, Franchisor)
        assert result.canonical_name == 'Updated Franchise'
    
    def test_delete_success(self, crud_ops, mock_db_manager):
        """Test successful record deletion."""
        # Setup
        mock_db_manager.delete_record.return_value = True
        
        # Execute
        result = crud_ops.delete('test-id')
        
        # Verify
        assert result is True
        mock_db_manager.delete_record.assert_called_once_with('franchisors', 'test-id')
    
    def test_count_success(self, crud_ops, mock_db_manager):
        """Test successful record counting."""
        # Setup
        mock_db_manager.count_records.return_value = 42
        
        # Execute
        result = crud_ops.count({'status': 'active'})
        
        # Verify
        assert result == 42
        mock_db_manager.count_records.assert_called_once_with('franchisors', {'status': 'active'})


def test_global_functions():
    """Test global utility functions."""
    # Test get_database_manager
    manager1 = get_database_manager()
    manager2 = get_database_manager()
    assert manager1 is manager2
    
    # Test get_supabase_client
    with patch.object(manager1, 'get_supabase_client') as mock_method:
        mock_client = Mock()
        mock_method.return_value = mock_client
        
        client = get_supabase_client()
        assert client is mock_client
    
    # Test test_database_connection
    with patch.object(manager1, 'test_connection') as mock_method:
        mock_method.return_value = True
        
        result = test_database_connection()
        assert result is True