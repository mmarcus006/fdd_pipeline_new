"""Unit tests for Google Drive operations."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import io
from uuid import uuid4

from tasks.drive_operations import DriveManager, DriveFileMetadata
from googleapiclient.errors import HttpError


class TestDriveManager:
    """Test cases for DriveManager class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        with patch('tasks.drive_operations.get_settings') as mock:
            mock.return_value.gdrive_creds_json = '/path/to/creds.json'
            mock.return_value.gdrive_folder_id = 'root_folder_id'
            yield mock.return_value
    
    @pytest.fixture
    def mock_service(self):
        """Mock Google Drive service."""
        return Mock()
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager for testing."""
        return Mock()
    
    @pytest.fixture
    def drive_manager(self, mock_settings, mock_db_manager):
        """DriveManager instance with mocked dependencies."""
        with patch('tasks.drive_operations.service_account'), \
             patch('tasks.drive_operations.build') as mock_build, \
             patch('tasks.drive_operations.get_database_manager', return_value=mock_db_manager):
            
            mock_service = Mock()
            mock_build.return_value = mock_service
            
            manager = DriveManager()
            manager._service = mock_service
            manager._db_manager = mock_db_manager
            return manager
    
    def test_create_folder_success(self, drive_manager):
        """Test successful folder creation."""
        # Setup
        drive_manager.service.files().create().execute.return_value = {'id': 'new_folder_id'}
        
        # Execute
        result = drive_manager.create_folder('test_folder', 'parent_id')
        
        # Verify
        assert result == 'new_folder_id'
        # Check that create was called with the right parameters
        drive_manager.service.files().create.assert_any_call(
            body={
                'name': 'test_folder',
                'parents': ['parent_id'],
                'mimeType': 'application/vnd.google-apps.folder'
            },
            fields='id'
        )
    
    def test_create_folder_http_error(self, drive_manager):
        """Test folder creation with HTTP error."""
        # Setup
        error = HttpError(Mock(status=403), b'Forbidden')
        drive_manager.service.files().create().execute.side_effect = error
        
        # Execute & Verify
        with pytest.raises(HttpError):
            drive_manager.create_folder('test_folder', 'parent_id')
    
    def test_folder_exists_found(self, drive_manager):
        """Test folder existence check when folder exists."""
        # Setup
        drive_manager.service.files().list().execute.return_value = {
            'files': [{'id': 'existing_folder_id', 'name': 'test_folder'}]
        }
        
        # Execute
        result = drive_manager.folder_exists('test_folder', 'parent_id')
        
        # Verify
        assert result == 'existing_folder_id'
        # Check that list was called with the right query
        drive_manager.service.files().list.assert_any_call(
            q="name='test_folder' and parents in 'parent_id' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields='files(id, name)'
        )
    
    def test_folder_exists_not_found(self, drive_manager):
        """Test folder existence check when folder doesn't exist."""
        # Setup
        drive_manager.service.files().list().execute.return_value = {'files': []}
        
        # Execute
        result = drive_manager.folder_exists('test_folder', 'parent_id')
        
        # Verify
        assert result is None
    
    def test_get_or_create_folder_existing(self, drive_manager):
        """Test get_or_create_folder when folder exists."""
        # Setup
        drive_manager.service.files().list().execute.return_value = {
            'files': [{'id': 'existing_folder_id', 'name': 'test_folder'}]
        }
        
        # Execute
        result = drive_manager.get_or_create_folder('test_folder', 'parent_id')
        
        # Verify
        assert result == 'existing_folder_id'
        # Should not call create since folder exists
        drive_manager.service.files().create.assert_not_called()
    
    def test_get_or_create_folder_new(self, drive_manager):
        """Test get_or_create_folder when folder needs to be created."""
        # Setup - first call returns empty (doesn't exist), second call creates
        drive_manager.service.files().list().execute.return_value = {'files': []}
        drive_manager.service.files().create().execute.return_value = {'id': 'new_folder_id'}
        
        # Execute
        result = drive_manager.get_or_create_folder('test_folder', 'parent_id')
        
        # Verify
        assert result == 'new_folder_id'
        # Check that create was called with the right parameters
        drive_manager.service.files().create.assert_any_call(
            body={
                'name': 'test_folder',
                'parents': ['parent_id'],
                'mimeType': 'application/vnd.google-apps.folder'
            },
            fields='id'
        )
    
    def test_upload_file_success(self, drive_manager):
        """Test successful file upload."""
        # Setup
        file_content = b'test file content'
        drive_manager.service.files().create().execute.return_value = {'id': 'uploaded_file_id'}
        
        # Execute
        result = drive_manager.upload_file(file_content, 'test.pdf', 'parent_id')
        
        # Verify
        assert result == 'uploaded_file_id'
        # Check that create was called with the right parameters (ignoring media_body for simplicity)
        calls = drive_manager.service.files().create.call_args_list
        # Find the call with body parameter
        body_call = None
        for call in calls:
            if 'body' in call.kwargs:
                body_call = call
                break
        
        assert body_call is not None
        assert body_call.kwargs['body']['name'] == 'test.pdf'
        assert body_call.kwargs['body']['parents'] == ['parent_id']
    
    def test_upload_file_resumable_large(self, drive_manager):
        """Test resumable upload for large files."""
        # Setup - large file (>5MB)
        file_content = b'x' * (6 * 1024 * 1024)  # 6MB
        
        # Mock the resumable upload process
        mock_request = Mock()
        mock_request.next_chunk.side_effect = [
            (Mock(progress=lambda: 0.5), None),  # 50% progress
            (Mock(progress=lambda: 1.0), {'id': 'uploaded_file_id'})  # Complete
        ]
        drive_manager.service.files().create.return_value = mock_request
        
        # Execute
        result = drive_manager.upload_file(file_content, 'large_test.pdf', 'parent_id')
        
        # Verify
        assert result == 'uploaded_file_id'
        assert mock_request.next_chunk.call_count == 2
    
    def test_download_file_success(self, drive_manager):
        """Test successful file download."""
        # Setup
        test_content = b'downloaded file content'
        mock_request = Mock()
        
        # Mock the download process
        mock_downloader = Mock()
        mock_downloader.next_chunk.side_effect = [
            (Mock(progress=lambda: 0.5), False),  # 50% progress
            (Mock(progress=lambda: 1.0), True)    # Complete
        ]
        
        drive_manager.service.files().get_media.return_value = mock_request
        
        with patch('tasks.drive_operations.MediaIoBaseDownload') as mock_media_download:
            mock_media_download.return_value = mock_downloader
            
            # Mock the BytesIO to return our test content
            with patch('tasks.drive_operations.io.BytesIO') as mock_bytesio:
                mock_file_io = Mock()
                mock_file_io.getvalue.return_value = test_content
                mock_bytesio.return_value = mock_file_io
                
                # Execute
                result = drive_manager.download_file('file_id')
        
        # Verify
        assert result == test_content
        drive_manager.service.files().get_media.assert_called_once_with(fileId='file_id')
    
    def test_get_file_metadata_success(self, drive_manager):
        """Test successful file metadata retrieval."""
        # Setup
        mock_file_info = {
            'id': 'file_id',
            'name': 'test.pdf',
            'size': '1024',
            'createdTime': '2024-01-01T12:00:00.000Z',
            'modifiedTime': '2024-01-02T12:00:00.000Z',
            'mimeType': 'application/pdf',
            'parents': ['parent_id']
        }
        
        drive_manager.service.files().get.return_value.execute.return_value = mock_file_info
        
        # Mock the path construction
        with patch.object(drive_manager, '_get_file_path', return_value='/test/path/test.pdf'):
            # Execute
            result = drive_manager.get_file_metadata('file_id')
        
        # Verify
        assert isinstance(result, DriveFileMetadata)
        assert result.id == 'file_id'
        assert result.name == 'test.pdf'
        assert result.size == 1024
        assert result.mime_type == 'application/pdf'
        assert result.drive_path == '/test/path/test.pdf'
    
    def test_create_folder_structure_success(self, drive_manager):
        """Test successful nested folder structure creation."""
        # Setup - mock folder creation calls
        drive_manager.service.files().list().execute.return_value = {'files': []}  # No existing folders
        drive_manager.service.files().create().execute.side_effect = [
            {'id': 'folder1_id'},
            {'id': 'folder2_id'},
            {'id': 'folder3_id'}
        ]
        
        # Execute
        result = drive_manager.create_folder_structure('fdds/raw/mn')
        
        # Verify
        assert result == 'folder3_id'
        # Check that create was called multiple times (at least 3 for the 3 folders)
        assert drive_manager.service.files().create.call_count >= 3
    
    def test_list_files_success(self, drive_manager):
        """Test successful file listing."""
        # Setup
        mock_files = [
            {
                'id': 'file1_id',
                'name': 'file1.pdf',
                'size': '1024',
                'createdTime': '2024-01-01T12:00:00.000Z',
                'modifiedTime': '2024-01-02T12:00:00.000Z',
                'mimeType': 'application/pdf',
                'parents': ['folder_id']
            },
            {
                'id': 'file2_id',
                'name': 'file2.pdf',
                'size': '2048',
                'createdTime': '2024-01-01T13:00:00.000Z',
                'modifiedTime': '2024-01-02T13:00:00.000Z',
                'mimeType': 'application/pdf',
                'parents': ['folder_id']
            }
        ]
        
        drive_manager.service.files().list().execute.return_value = {'files': mock_files}
        
        # Mock path construction for each file
        with patch.object(drive_manager, '_get_file_path', side_effect=['/path/file1.pdf', '/path/file2.pdf']):
            # Execute
            result = drive_manager.list_files('folder_id')
        
        # Verify
        assert len(result) == 2
        assert all(isinstance(f, DriveFileMetadata) for f in result)
        assert result[0].name == 'file1.pdf'
        assert result[1].name == 'file2.pdf'
    
    def test_delete_file_success(self, drive_manager):
        """Test successful file deletion."""
        # Setup
        drive_manager.service.files().delete().execute.return_value = None
        
        # Execute
        result = drive_manager.delete_file('file_id')
        
        # Verify
        assert result is True
        # Check that delete was called with the right parameters
        drive_manager.service.files().delete.assert_any_call(fileId='file_id')
    
    def test_delete_file_error(self, drive_manager):
        """Test file deletion with error."""
        # Setup
        error = HttpError(Mock(status=404), b'Not Found')
        drive_manager.service.files().delete().execute.side_effect = error
        
        # Execute
        result = drive_manager.delete_file('file_id')
        
        # Verify
        assert result is False
    
    def test_verify_permissions_success(self, drive_manager):
        """Test successful permission verification."""
        # Setup
        drive_manager.service.files().list().execute.return_value = {'files': []}
        drive_manager.service.files().create().execute.return_value = {'id': 'test_file_id'}
        drive_manager.service.files().delete().execute.return_value = None
        
        # Execute
        result = drive_manager.verify_permissions()
        
        # Verify
        assert result is True
        # Check that the methods were called with the right parameters
        drive_manager.service.files().list.assert_any_call(
            q="parents in 'root_folder_id'",
            fields='files(id, name)',
            pageSize=1
        )
        # Check that create and delete were called
        assert drive_manager.service.files().create.call_count >= 1
        assert drive_manager.service.files().delete.call_count >= 1
    
    def test_verify_permissions_failure(self, drive_manager):
        """Test permission verification failure."""
        # Setup
        error = HttpError(Mock(status=403), b'Forbidden')
        drive_manager.service.files().list().execute.side_effect = error
        
        # Execute
        result = drive_manager.verify_permissions()
        
        # Verify
        assert result is False
    
    def test_get_storage_quota_success(self, drive_manager):
        """Test successful storage quota retrieval."""
        # Setup
        mock_quota = {
            'storageQuota': {
                'limit': '15000000000',  # 15GB
                'usage': '5000000000',   # 5GB
                'usageInDrive': '3000000000'  # 3GB
            }
        }
        drive_manager.service.about().get().execute.return_value = mock_quota
        
        # Execute
        result = drive_manager.get_storage_quota()
        
        # Verify
        assert result['limit'] == 15000000000
        assert result['usage'] == 5000000000
        assert result['usage_in_drive'] == 3000000000
    
    def test_folder_cache(self, drive_manager):
        """Test that folder cache works correctly."""
        # Setup
        drive_manager.service.files().list().execute.return_value = {
            'files': [{'id': 'existing_folder_id', 'name': 'test_folder'}]
        }
        
        # Execute - call twice
        result1 = drive_manager.get_or_create_folder('test_folder', 'parent_id')
        result2 = drive_manager.get_or_create_folder('test_folder', 'parent_id')
        
        # Verify
        assert result1 == result2 == 'existing_folder_id'
        # The second call should use cache, so we should see the folder in cache
        cache_key = "parent_id/test_folder"
        assert cache_key in drive_manager._folder_cache
        assert drive_manager._folder_cache[cache_key] == 'existing_folder_id'
    
    def test_handle_rate_limit_with_retry_after(self, drive_manager):
        """Test rate limit handling with retry-after header."""
        # Setup
        mock_response = Mock()
        mock_response.status = 429
        mock_response.get.return_value = '5'  # 5 second retry-after
        error = HttpError(mock_response, b'Rate limit exceeded')
        
        with patch('tasks.drive_operations.time.sleep') as mock_sleep:
            # Execute
            result = drive_manager._handle_rate_limit(error)
        
        # Verify
        assert result is True
        mock_sleep.assert_called_once_with(5)
    
    def test_handle_rate_limit_without_retry_after(self, drive_manager):
        """Test rate limit handling without retry-after header."""
        # Setup
        mock_response = Mock()
        mock_response.status = 429
        mock_response.get.return_value = None  # No retry-after header
        error = HttpError(mock_response, b'Rate limit exceeded')
        
        with patch('tasks.drive_operations.time.sleep') as mock_sleep:
            # Execute
            result = drive_manager._handle_rate_limit(error)
        
        # Verify
        assert result is True
        # Should use exponential backoff calculation
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] > 0  # Some positive delay
    
    def test_handle_non_rate_limit_error(self, drive_manager):
        """Test handling of non-rate-limit errors."""
        # Setup
        mock_response = Mock()
        mock_response.status = 403  # Not a rate limit error
        error = HttpError(mock_response, b'Forbidden')
        
        # Execute
        result = drive_manager._handle_rate_limit(error)
        
        # Verify
        assert result is False
    
    def test_execute_with_retry_success_first_attempt(self, drive_manager):
        """Test successful operation on first attempt."""
        # Setup
        mock_operation = Mock(return_value='success')
        
        # Execute
        result = drive_manager._execute_with_retry(mock_operation, 'arg1', kwarg1='value1')
        
        # Verify
        assert result == 'success'
        mock_operation.assert_called_once_with('arg1', kwarg1='value1')
    
    def test_execute_with_retry_rate_limit_then_success(self, drive_manager):
        """Test retry after rate limit error."""
        # Setup
        mock_response = Mock()
        mock_response.status = 429
        mock_response.get.return_value = '1'
        rate_limit_error = HttpError(mock_response, b'Rate limit exceeded')
        
        mock_operation = Mock(side_effect=[rate_limit_error, 'success'])
        
        with patch('tasks.drive_operations.time.sleep'):
            # Execute
            result = drive_manager._execute_with_retry(mock_operation)
        
        # Verify
        assert result == 'success'
        assert mock_operation.call_count == 2
    
    def test_execute_with_retry_server_error_then_success(self, drive_manager):
        """Test retry after server error."""
        # Setup
        mock_response = Mock()
        mock_response.status = 500
        server_error = HttpError(mock_response, b'Internal Server Error')
        
        mock_operation = Mock(side_effect=[server_error, 'success'])
        
        with patch('tasks.drive_operations.time.sleep'):
            # Execute
            result = drive_manager._execute_with_retry(mock_operation)
        
        # Verify
        assert result == 'success'
        assert mock_operation.call_count == 2
    
    def test_execute_with_retry_exhausted(self, drive_manager):
        """Test retry exhaustion."""
        # Setup
        mock_response = Mock()
        mock_response.status = 500
        server_error = HttpError(mock_response, b'Internal Server Error')
        
        mock_operation = Mock(side_effect=server_error)
        
        with patch('tasks.drive_operations.time.sleep'):
            # Execute & Verify
            with pytest.raises(HttpError):
                drive_manager._execute_with_retry(mock_operation)
        
        # Should have tried max_retries + 1 times
        assert mock_operation.call_count == drive_manager._max_retries + 1
    
    def test_upload_file_with_metadata_sync_new_file(self, drive_manager):
        """Test uploading new file with metadata synchronization."""
        # Setup
        file_content = b'test file content'
        fdd_id = uuid4()
        
        # Mock file metadata
        mock_metadata = DriveFileMetadata(
            id='uploaded_file_id',
            name='test.pdf',
            size=len(file_content),
            created_time=datetime.now(),
            modified_time=datetime.now(),
            mime_type='application/pdf',
            parents=['folder_id'],
            drive_path='/fdds/raw/test.pdf'
        )
        
        # Mock database operations
        drive_manager._db_manager.get_records_by_filter.return_value = []  # No existing files
        drive_manager._db_manager.execute_batch_insert.return_value = 1
        
        with patch.object(drive_manager, 'create_folder_structure', return_value='folder_id'), \
             patch.object(drive_manager, 'upload_file', return_value='uploaded_file_id'), \
             patch.object(drive_manager, 'get_file_metadata', return_value=mock_metadata), \
             patch('tasks.drive_operations.hashlib.sha256') as mock_hash:
            
            mock_hash.return_value.hexdigest.return_value = 'test_hash'
            
            # Execute
            file_id, metadata = drive_manager.upload_file_with_metadata_sync(
                file_content, 'test.pdf', 'fdds/raw', fdd_id
            )
        
        # Verify
        assert file_id == 'uploaded_file_id'
        assert metadata == mock_metadata
        
        # Check database operations
        drive_manager._db_manager.get_records_by_filter.assert_called_once_with(
            'drive_files', {'sha256_hash': 'test_hash'}
        )
        drive_manager._db_manager.execute_batch_insert.assert_called_once()
        
        # Check the record that was inserted
        insert_call = drive_manager._db_manager.execute_batch_insert.call_args
        assert insert_call[0][0] == 'drive_files'  # Table name
        record = insert_call[0][1][0]  # First record in batch
        assert record['drive_file_id'] == 'uploaded_file_id'
        assert record['filename'] == 'test.pdf'
        assert record['sha256_hash'] == 'test_hash'
        assert record['fdd_id'] == str(fdd_id)
    
    def test_upload_file_with_metadata_sync_duplicate_file(self, drive_manager):
        """Test uploading duplicate file (already exists)."""
        # Setup
        file_content = b'test file content'
        existing_file_record = {
            'drive_file_id': 'existing_file_id',
            'filename': 'existing.pdf'
        }
        
        # Mock existing file in database
        drive_manager._db_manager.get_records_by_filter.return_value = [existing_file_record]
        
        # Mock file metadata
        mock_metadata = DriveFileMetadata(
            id='existing_file_id',
            name='existing.pdf',
            size=len(file_content),
            created_time=datetime.now(),
            modified_time=datetime.now(),
            mime_type='application/pdf',
            parents=['folder_id'],
            drive_path='/fdds/raw/existing.pdf'
        )
        
        with patch.object(drive_manager, 'create_folder_structure', return_value='folder_id'), \
             patch.object(drive_manager, 'get_file_metadata', return_value=mock_metadata), \
             patch('tasks.drive_operations.hashlib.sha256') as mock_hash:
            
            mock_hash.return_value.hexdigest.return_value = 'existing_hash'
            
            # Execute
            file_id, metadata = drive_manager.upload_file_with_metadata_sync(
                file_content, 'test.pdf', 'fdds/raw'
            )
        
        # Verify
        assert file_id == 'existing_file_id'
        assert metadata == mock_metadata
        
        # Should not have called upload or insert
        drive_manager.service.files().create.assert_not_called()
        drive_manager._db_manager.execute_batch_insert.assert_not_called()
    
    def test_sync_file_metadata_to_db_new_record(self, drive_manager):
        """Test syncing file metadata to database for new record."""
        # Setup
        fdd_id = uuid4()
        mock_metadata = DriveFileMetadata(
            id='file_id',
            name='test.pdf',
            size=1024,
            created_time=datetime.now(),
            modified_time=datetime.now(),
            mime_type='application/pdf',
            parents=['folder_id'],
            drive_path='/test/path/test.pdf'
        )
        
        # Mock no existing record
        drive_manager._db_manager.get_records_by_filter.return_value = []
        drive_manager._db_manager.execute_batch_insert.return_value = 1
        
        with patch.object(drive_manager, 'get_file_metadata', return_value=mock_metadata):
            # Execute
            result = drive_manager.sync_file_metadata_to_db('file_id', fdd_id)
        
        # Verify
        assert result is True
        drive_manager._db_manager.execute_batch_insert.assert_called_once()
        
        # Check the record that was inserted
        insert_call = drive_manager._db_manager.execute_batch_insert.call_args
        record = insert_call[0][1][0]  # First record in batch
        assert record['drive_file_id'] == 'file_id'
        assert record['fdd_id'] == str(fdd_id)
    
    def test_sync_file_metadata_to_db_existing_record(self, drive_manager):
        """Test syncing file metadata to database for existing record."""
        # Setup
        existing_record = {'id': 'db_record_id', 'drive_file_id': 'file_id'}
        mock_metadata = DriveFileMetadata(
            id='file_id',
            name='test.pdf',
            size=1024,
            created_time=datetime.now(),
            modified_time=datetime.now(),
            mime_type='application/pdf',
            parents=['folder_id'],
            drive_path='/test/path/test.pdf'
        )
        
        # Mock existing record
        drive_manager._db_manager.get_records_by_filter.return_value = [existing_record]
        drive_manager._db_manager.update_record.return_value = existing_record
        
        with patch.object(drive_manager, 'get_file_metadata', return_value=mock_metadata):
            # Execute
            result = drive_manager.sync_file_metadata_to_db('file_id')
        
        # Verify
        assert result is True
        drive_manager._db_manager.update_record.assert_called_once()
        # Check that the call was made with the right table and record ID
        call_args = drive_manager._db_manager.update_record.call_args
        assert call_args[0][0] == 'drive_files'
        assert call_args[0][1] == 'db_record_id'
        assert isinstance(call_args[0][2], dict)  # Third argument should be a dict
    
    def test_get_files_by_fdd_id(self, drive_manager):
        """Test getting files by FDD ID."""
        # Setup
        fdd_id = uuid4()
        file_records = [
            {'drive_file_id': 'file1_id', 'filename': 'file1.pdf'},
            {'drive_file_id': 'file2_id', 'filename': 'file2.pdf'}
        ]
        
        mock_metadata_1 = DriveFileMetadata(
            id='file1_id', name='file1.pdf', size=1024,
            created_time=datetime.now(), modified_time=datetime.now(),
            mime_type='application/pdf', parents=['folder_id'],
            drive_path='/path/file1.pdf'
        )
        mock_metadata_2 = DriveFileMetadata(
            id='file2_id', name='file2.pdf', size=2048,
            created_time=datetime.now(), modified_time=datetime.now(),
            mime_type='application/pdf', parents=['folder_id'],
            drive_path='/path/file2.pdf'
        )
        
        drive_manager._db_manager.get_records_by_filter.return_value = file_records
        
        with patch.object(drive_manager, 'get_file_metadata', side_effect=[mock_metadata_1, mock_metadata_2]):
            # Execute
            result = drive_manager.get_files_by_fdd_id(fdd_id)
        
        # Verify
        assert len(result) == 2
        assert result[0] == mock_metadata_1
        assert result[1] == mock_metadata_2
        
        drive_manager._db_manager.get_records_by_filter.assert_called_once_with(
            'drive_files', {'fdd_id': str(fdd_id)}
        )
    
    def test_get_files_by_fdd_id_with_missing_file(self, drive_manager):
        """Test getting files by FDD ID when some files are missing from Drive."""
        # Setup
        fdd_id = uuid4()
        file_records = [
            {'drive_file_id': 'file1_id', 'filename': 'file1.pdf'},
            {'drive_file_id': 'missing_file_id', 'filename': 'missing.pdf'}
        ]
        
        mock_metadata_1 = DriveFileMetadata(
            id='file1_id', name='file1.pdf', size=1024,
            created_time=datetime.now(), modified_time=datetime.now(),
            mime_type='application/pdf', parents=['folder_id'],
            drive_path='/path/file1.pdf'
        )
        
        # Mock 404 error for missing file
        mock_response = Mock()
        mock_response.status = 404
        not_found_error = HttpError(mock_response, b'Not Found')
        
        drive_manager._db_manager.get_records_by_filter.return_value = file_records
        
        with patch.object(drive_manager, 'get_file_metadata', side_effect=[mock_metadata_1, not_found_error]):
            # Execute
            result = drive_manager.get_files_by_fdd_id(fdd_id)
        
        # Verify - should only return the found file
        assert len(result) == 1
        assert result[0] == mock_metadata_1
    
    def test_cleanup_orphaned_files(self, drive_manager):
        """Test cleanup of orphaned files."""
        # Setup
        file_records = [
            {'id': 'record1_id', 'drive_file_id': 'existing_file_id', 'filename': 'existing.pdf'},
            {'id': 'record2_id', 'drive_file_id': 'orphaned_file_id', 'filename': 'orphaned.pdf'}
        ]
        
        drive_manager._db_manager.get_records_by_filter.return_value = file_records
        
        # Mock Drive API responses
        mock_response_404 = Mock()
        mock_response_404.status = 404
        not_found_error = HttpError(mock_response_404, b'Not Found')
        
        drive_manager.service.files().get.return_value.execute.side_effect = [
            {'id': 'existing_file_id'},  # First file exists
            not_found_error  # Second file is orphaned
        ]
        
        drive_manager._db_manager.delete_record.return_value = True
        
        # Execute
        result = drive_manager.cleanup_orphaned_files()
        
        # Verify
        assert result['total_checked'] == 2
        assert result['orphaned_found'] == 1
        assert result['orphaned_cleaned'] == 1
        assert result['errors'] == 0
        
        # Check that orphaned record was deleted
        drive_manager._db_manager.delete_record.assert_called_once_with('drive_files', 'record2_id')


class TestDriveFileMetadata:
    """Test cases for DriveFileMetadata dataclass."""
    
    def test_drive_file_metadata_creation(self):
        """Test DriveFileMetadata creation and attributes."""
        created_time = datetime.now()
        modified_time = datetime.now()
        
        metadata = DriveFileMetadata(
            id='file_id',
            name='test.pdf',
            size=1024,
            created_time=created_time,
            modified_time=modified_time,
            mime_type='application/pdf',
            parents=['parent_id'],
            drive_path='/test/path/test.pdf'
        )
        
        assert metadata.id == 'file_id'
        assert metadata.name == 'test.pdf'
        assert metadata.size == 1024
        assert metadata.created_time == created_time
        assert metadata.modified_time == modified_time
        assert metadata.mime_type == 'application/pdf'
        assert metadata.parents == ['parent_id']
        assert metadata.drive_path == '/test/path/test.pdf'


def test_get_drive_manager():
    """Test the global drive manager getter."""
    from tasks.drive_operations import get_drive_manager
    
    manager = get_drive_manager()
    assert isinstance(manager, DriveManager)
    
    # Should return the same instance
    manager2 = get_drive_manager()
    assert manager is manager2