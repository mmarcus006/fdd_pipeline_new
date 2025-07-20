# ABOUTME: Test suite for Google Drive integration
# ABOUTME: Tests real Google Drive operations without mocking - requires actual credentials

import pytest
import tempfile
import os
import time
import hashlib
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from typing import List

from storage.google_drive import (
    DriveManager,
    DriveFileMetadata,
    get_drive_manager,
    create_folder_structure_markdown
)
from config import get_settings
from storage.database import get_database_manager
from googleapiclient.errors import HttpError


class TestDriveManager:
    """Test suite for Google Drive operations using real API calls."""

    @pytest.fixture
    def drive_manager(self):
        """Get a real DriveManager instance."""
        # Use OAuth2 for tests
        return get_drive_manager(use_oauth2=True)

    @pytest.fixture
    def test_folder_name(self):
        """Generate unique test folder name."""
        return f"test_folder_{uuid4().hex[:8]}_{int(time.time())}"

    @pytest.fixture
    def test_file_content(self):
        """Generate test file content."""
        return b"Test PDF content for FDD Pipeline integration tests\n" * 100

    @pytest.fixture
    def cleanup_folders(self, drive_manager):
        """Cleanup test folders after tests."""
        created_folders = []
        
        yield created_folders
        
        # Cleanup after test
        for folder_id in created_folders:
            try:
                drive_manager.delete_file(folder_id)
            except Exception:
                pass  # Ignore cleanup errors

    def test_initialization(self, drive_manager):
        """Test DriveManager initialization."""
        assert drive_manager is not None
        assert drive_manager.settings is not None
        assert drive_manager._service is None  # Lazy initialization
        assert drive_manager._folder_cache == {}
        assert drive_manager._db_manager is not None
        assert drive_manager._rate_limit_delay == 0.1
        assert drive_manager._max_retries == 3

    def test_service_lazy_initialization(self, drive_manager):
        """Test that Drive service is initialized lazily."""
        assert drive_manager._service is None
        
        # Access service property
        service = drive_manager.service
        
        assert service is not None
        assert drive_manager._service is not None
        assert hasattr(service, 'files')
        assert hasattr(service, 'about')

    def test_verify_permissions(self, drive_manager):
        """Test permission verification with real API."""
        result = drive_manager.verify_permissions()
        assert result is True

    def test_create_folder(self, drive_manager, test_folder_name, cleanup_folders):
        """Test folder creation in Google Drive."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        assert folder_id is not None
        assert len(folder_id) > 0
        
        # Verify folder exists
        folder_info = drive_manager.service.files().get(
            fileId=folder_id,
            fields="id,name,mimeType"
        ).execute()
        
        assert folder_info['id'] == folder_id
        assert folder_info['name'] == test_folder_name
        assert folder_info['mimeType'] == 'application/vnd.google-apps.folder'

    def test_folder_exists(self, drive_manager, test_folder_name, cleanup_folders):
        """Test checking if folder exists."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Check non-existent folder
        result = drive_manager.folder_exists(test_folder_name, parent_id)
        assert result is None
        
        # Create folder
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        # Check existing folder
        result = drive_manager.folder_exists(test_folder_name, parent_id)
        assert result == folder_id

    def test_get_or_create_folder(self, drive_manager, test_folder_name, cleanup_folders):
        """Test get or create folder functionality."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # First call should create
        folder_id1 = drive_manager.get_or_create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id1)
        assert folder_id1 is not None
        
        # Second call should return existing
        folder_id2 = drive_manager.get_or_create_folder(test_folder_name, parent_id)
        assert folder_id2 == folder_id1
        
        # Check cache
        cache_key = f"{parent_id}/{test_folder_name}"
        assert drive_manager._folder_cache[cache_key] == folder_id1

    def test_upload_file(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test file upload to Google Drive."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create test folder
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        # Upload file
        filename = f"test_document_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            test_file_content,
            filename,
            folder_id,
            mime_type="application/pdf"
        )
        
        assert file_id is not None
        
        # Verify file exists
        file_info = drive_manager.service.files().get(
            fileId=file_id,
            fields="id,name,size,mimeType"
        ).execute()
        
        assert file_info['id'] == file_id
        assert file_info['name'] == filename
        assert int(file_info['size']) == len(test_file_content)
        assert file_info['mimeType'] == 'application/pdf'
        
        # Cleanup file
        drive_manager.delete_file(file_id)

    def test_resumable_upload_large_file(self, drive_manager, test_folder_name, cleanup_folders):
        """Test resumable upload for large files."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create large test content (>5MB)
        large_content = b"X" * (6 * 1024 * 1024)  # 6MB
        
        # Create test folder
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        # Upload large file with resumable=True
        filename = f"large_test_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            large_content,
            filename,
            folder_id,
            mime_type="application/pdf",
            resumable=True
        )
        
        assert file_id is not None
        
        # Verify file
        file_info = drive_manager.service.files().get(
            fileId=file_id,
            fields="id,size"
        ).execute()
        
        assert int(file_info['size']) == len(large_content)
        
        # Cleanup
        drive_manager.delete_file(file_id)

    def test_download_file(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test file download from Google Drive."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder and upload file
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        filename = f"download_test_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            test_file_content,
            filename,
            folder_id
        )
        
        # Download file
        downloaded_content = drive_manager.download_file(file_id)
        
        assert downloaded_content == test_file_content
        assert len(downloaded_content) == len(test_file_content)
        
        # Cleanup
        drive_manager.delete_file(file_id)

    def test_get_file_metadata(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test getting file metadata."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder and upload file
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        filename = f"metadata_test_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            test_file_content,
            filename,
            folder_id
        )
        
        # Get metadata
        metadata = drive_manager.get_file_metadata(file_id)
        
        assert isinstance(metadata, DriveFileMetadata)
        assert metadata.id == file_id
        assert metadata.name == filename
        assert metadata.size == len(test_file_content)
        assert metadata.mime_type == "application/pdf"
        assert folder_id in metadata.parents
        assert isinstance(metadata.created_time, datetime)
        assert isinstance(metadata.modified_time, datetime)
        assert test_folder_name in metadata.drive_path
        
        # Cleanup
        drive_manager.delete_file(file_id)

    def test_create_folder_structure(self, drive_manager, cleanup_folders):
        """Test creating nested folder structure."""
        base_folder_id = drive_manager.settings.gdrive_folder_id
        
        # Create nested structure
        test_path = f"test_{uuid4().hex[:8]}/level1/level2/level3"
        final_folder_id = drive_manager.create_folder_structure(test_path, base_folder_id)
        
        assert final_folder_id is not None
        
        # Verify the deepest folder exists
        folder_info = drive_manager.service.files().get(
            fileId=final_folder_id,
            fields="name"
        ).execute()
        
        assert folder_info['name'] == 'level3'
        
        # Get root test folder for cleanup
        root_parts = test_path.split('/')[0]
        root_folder_id = drive_manager.folder_exists(root_parts, base_folder_id)
        if root_folder_id:
            cleanup_folders.append(root_folder_id)

    def test_list_files(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test listing files in a folder."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        # Upload multiple files
        file_ids = []
        for i in range(3):
            filename = f"list_test_{i}_{uuid4().hex[:8]}.pdf"
            file_id = drive_manager.upload_file(
                test_file_content,
                filename,
                folder_id
            )
            file_ids.append(file_id)
        
        # List files
        files = drive_manager.list_files(folder_id)
        
        assert len(files) == 3
        assert all(isinstance(f, DriveFileMetadata) for f in files)
        assert all(f.mime_type == "application/pdf" for f in files)
        
        # List with mime type filter
        pdf_files = drive_manager.list_files(folder_id, mime_type="application/pdf")
        assert len(pdf_files) == 3
        
        # Cleanup
        for file_id in file_ids:
            drive_manager.delete_file(file_id)

    def test_delete_file(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test file deletion."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder and upload file
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        filename = f"delete_test_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            test_file_content,
            filename,
            folder_id
        )
        
        # Delete file
        result = drive_manager.delete_file(file_id)
        assert result is True
        
        # Verify file is deleted
        with pytest.raises(HttpError) as exc_info:
            drive_manager.service.files().get(fileId=file_id).execute()
        assert exc_info.value.resp.status == 404

    def test_get_storage_quota(self, drive_manager):
        """Test getting storage quota information."""
        quota = drive_manager.get_storage_quota()
        
        assert isinstance(quota, dict)
        assert 'limit' in quota
        assert 'usage' in quota
        assert 'usage_in_drive' in quota
        assert all(isinstance(v, int) for v in quota.values())

    def test_rate_limit_handling(self, drive_manager):
        """Test rate limit handling with rapid API calls."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Make multiple rapid folder checks (shouldn't trigger rate limit but tests the mechanism)
        results = []
        for i in range(5):
            result = drive_manager.folder_exists(f"nonexistent_{i}", parent_id)
            results.append(result)
        
        assert all(r is None for r in results)

    def test_upload_file_with_metadata_sync(self, drive_manager, test_file_content, cleanup_folders):
        """Test file upload with database metadata synchronization."""
        # Create unique folder path
        folder_path = f"test_sync_{uuid4().hex[:8]}/fdds/processed"
        filename = f"sync_test_{uuid4().hex[:8]}.pdf"
        
        # Upload file with metadata sync
        file_id, metadata = drive_manager.upload_file_with_metadata_sync(
            test_file_content,
            filename,
            folder_path,
            document_type="test_document"
        )
        
        assert file_id is not None
        assert isinstance(metadata, DriveFileMetadata)
        assert metadata.name == filename
        
        # Verify database record
        db_manager = drive_manager._db_manager
        records = db_manager.get_records_by_filter(
            "drive_files",
            {"drive_file_id": file_id}
        )
        
        assert len(records) == 1
        record = records[0]
        assert record['filename'] == filename
        assert record['folder_path'] == folder_path
        assert record['file_size'] == len(test_file_content)
        assert record['mime_type'] == "application/pdf"
        assert record['document_type'] == "test_document"
        
        # Test deduplication - upload same content again
        file_id2, metadata2 = drive_manager.upload_file_with_metadata_sync(
            test_file_content,
            f"duplicate_{filename}",
            folder_path,
            document_type="test_document"
        )
        
        # Should return the same file ID due to hash matching
        assert file_id2 == file_id
        
        # Cleanup
        drive_manager.delete_file(file_id)
        db_manager.delete_record("drive_files", record['id'])
        
        # Cleanup folder
        root_folder = folder_path.split('/')[0]
        root_id = drive_manager.folder_exists(root_folder, drive_manager.settings.gdrive_folder_id)
        if root_id:
            cleanup_folders.append(root_id)

    def test_sync_file_metadata_to_db(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test synchronizing file metadata to database."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder and upload file
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        filename = f"db_sync_test_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            test_file_content,
            filename,
            folder_id
        )
        
        # Sync metadata to database
        fdd_id = uuid4()
        result = drive_manager.sync_file_metadata_to_db(file_id, fdd_id)
        assert result is True
        
        # Verify database record
        db_manager = drive_manager._db_manager
        records = db_manager.get_records_by_filter(
            "drive_files",
            {"drive_file_id": file_id}
        )
        
        assert len(records) == 1
        record = records[0]
        assert record['filename'] == filename
        assert record['fdd_id'] == str(fdd_id)
        
        # Update sync (should update existing record)
        result2 = drive_manager.sync_file_metadata_to_db(file_id, fdd_id)
        assert result2 is True
        
        # Should still be only one record
        records2 = db_manager.get_records_by_filter(
            "drive_files",
            {"drive_file_id": file_id}
        )
        assert len(records2) == 1
        
        # Cleanup
        drive_manager.delete_file(file_id)
        db_manager.delete_record("drive_files", record['id'])

    def test_get_files_by_fdd_id(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test getting files by FDD ID."""
        parent_id = drive_manager.settings.gdrive_folder_id
        fdd_id = uuid4()
        
        # Create folder
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        # Upload multiple files for same FDD
        file_ids = []
        db_records = []
        
        for i in range(2):
            filename = f"fdd_test_{i}_{uuid4().hex[:8]}.pdf"
            file_id = drive_manager.upload_file(
                test_file_content,
                filename,
                folder_id
            )
            file_ids.append(file_id)
            
            # Add database record
            drive_manager.sync_file_metadata_to_db(file_id, fdd_id)
            records = drive_manager._db_manager.get_records_by_filter(
                "drive_files",
                {"drive_file_id": file_id}
            )
            db_records.extend(records)
        
        # Get files by FDD ID
        files = drive_manager.get_files_by_fdd_id(fdd_id)
        
        assert len(files) == 2
        assert all(isinstance(f, DriveFileMetadata) for f in files)
        assert all(f.id in file_ids for f in files)
        
        # Cleanup
        for file_id in file_ids:
            drive_manager.delete_file(file_id)
        for record in db_records:
            drive_manager._db_manager.delete_record("drive_files", record['id'])

    def test_cleanup_orphaned_files(self, drive_manager):
        """Test cleanup of orphaned file records."""
        # Create a fake orphaned record in database
        db_manager = drive_manager._db_manager
        
        orphaned_record = {
            "drive_file_id": f"fake_orphaned_{uuid4().hex}",
            "filename": "orphaned_test.pdf",
            "folder_path": "/test/orphaned",
            "file_size": 1000,
            "mime_type": "application/pdf",
            "sha256_hash": hashlib.sha256(b"fake").hexdigest(),
            "document_type": "test",
            "created_at": datetime.now().isoformat(),
            "modified_at": datetime.now().isoformat()
        }
        
        db_manager.execute_batch_insert("drive_files", [orphaned_record])
        
        # Get the inserted record ID
        records = db_manager.get_records_by_filter(
            "drive_files",
            {"drive_file_id": orphaned_record["drive_file_id"]}
        )
        assert len(records) == 1
        record_id = records[0]['id']
        
        # Run cleanup
        stats = drive_manager.cleanup_orphaned_files()
        
        assert stats['orphaned_found'] >= 1
        assert stats['orphaned_cleaned'] >= 1
        
        # Verify record was removed
        records_after = db_manager.get_records_by_filter(
            "drive_files",
            {"drive_file_id": orphaned_record["drive_file_id"]}
        )
        assert len(records_after) == 0

    def test_file_path_construction(self, drive_manager, test_file_content, cleanup_folders):
        """Test file path construction in Drive."""
        # Create nested folder structure
        base_id = drive_manager.settings.gdrive_folder_id
        test_path = f"test_path_{uuid4().hex[:8]}/sublevel1/sublevel2"
        
        final_folder_id = drive_manager.create_folder_structure(test_path, base_id)
        
        # Upload a file to the deepest folder
        filename = f"path_test_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            test_file_content,
            filename,
            final_folder_id
        )
        
        # Get file metadata to check path
        metadata = drive_manager.get_file_metadata(file_id)
        
        # Path should contain all folder levels
        assert "sublevel2" in metadata.drive_path
        assert filename in metadata.drive_path
        
        # Cleanup
        drive_manager.delete_file(file_id)
        root_folder = test_path.split('/')[0]
        root_id = drive_manager.folder_exists(root_folder, base_id)
        if root_id:
            cleanup_folders.append(root_id)

    def test_download_file_streaming(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test streaming download functionality."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder and upload file
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        filename = f"stream_test_{uuid4().hex[:8]}.pdf"
        file_id = drive_manager.upload_file(
            test_file_content,
            filename,
            folder_id
        )
        
        # Test download with progress tracking
        content = drive_manager.download_file(file_id)
        assert content == test_file_content
        
        # Cleanup
        drive_manager.delete_file(file_id)

    def test_concurrent_operations(self, drive_manager, test_file_content, test_folder_name, cleanup_folders):
        """Test concurrent file operations."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Create folder
        folder_id = drive_manager.create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        # Upload multiple files concurrently
        file_ids = []
        for i in range(3):
            filename = f"concurrent_{i}_{uuid4().hex[:8]}.pdf"
            file_id = drive_manager.upload_file(
                test_file_content + f" File {i}".encode(),
                filename,
                folder_id
            )
            file_ids.append(file_id)
            time.sleep(0.1)  # Small delay to respect rate limits
        
        # Verify all files exist
        files = drive_manager.list_files(folder_id)
        assert len(files) == 3
        
        # Cleanup
        for file_id in file_ids:
            drive_manager.delete_file(file_id)

    def test_batch_upload_files(self, drive_manager, test_file_content, cleanup_folders):
        """Test batch file upload functionality."""
        folder_path = f"test_batch_{uuid4().hex[:8]}/documents"
        
        # Prepare batch of files
        files = [
            {
                'content': test_file_content + f" File 1".encode(),
                'filename': f"batch_1_{uuid4().hex[:8]}.pdf",
                'mime_type': 'application/pdf'
            },
            {
                'content': test_file_content + f" File 2".encode(),
                'filename': f"batch_2_{uuid4().hex[:8]}.pdf",
                'mime_type': 'application/pdf'
            },
            {
                'content': b"Test text file content",
                'filename': f"batch_3_{uuid4().hex[:8]}.txt",
                'mime_type': 'text/plain'
            }
        ]
        
        # Upload batch
        results = drive_manager.batch_upload_files(
            files=files,
            folder_path=folder_path,
            document_type="batch_test"
        )
        
        assert len(results) == 3
        
        # Verify each file
        for i, (file_id, metadata) in enumerate(results):
            assert file_id is not None
            assert isinstance(metadata, DriveFileMetadata)
            assert metadata.name == files[i]['filename']
            assert metadata.mime_type == files[i]['mime_type']
            
            # Cleanup
            drive_manager.delete_file(file_id)
        
        # Cleanup folder
        root_folder = folder_path.split('/')[0]
        root_id = drive_manager.folder_exists(root_folder, drive_manager.settings.gdrive_folder_id)
        if root_id:
            cleanup_folders.append(root_id)

    def test_folder_cache_operations(self, drive_manager, test_folder_name, cleanup_folders):
        """Test folder cache functionality."""
        parent_id = drive_manager.settings.gdrive_folder_id
        
        # Clear cache first
        drive_manager.clear_folder_cache()
        assert len(drive_manager._folder_cache) == 0
        
        # Create folder (should cache it)
        folder_id = drive_manager.get_or_create_folder(test_folder_name, parent_id)
        cleanup_folders.append(folder_id)
        
        # Check cache
        cache_key = f"{parent_id}/{test_folder_name}"
        assert cache_key in drive_manager._folder_cache
        assert drive_manager._folder_cache[cache_key] == folder_id
        
        # Clear cache
        drive_manager.clear_folder_cache()
        assert len(drive_manager._folder_cache) == 0

    def test_error_handling(self, drive_manager):
        """Test error handling for various scenarios."""
        # Test invalid file ID
        with pytest.raises(HttpError) as exc_info:
            drive_manager.get_file_metadata("invalid_file_id_12345")
        assert exc_info.value.resp.status == 404
        
        # Test invalid folder ID for upload
        with pytest.raises(HttpError):
            drive_manager.upload_file(
                b"test content",
                "test.pdf",
                "invalid_folder_id_12345"
            )
        
        # Test download non-existent file
        with pytest.raises(HttpError):
            drive_manager.download_file("non_existent_file_id")


class TestDriveManagerUtilities:
    """Test utility functions and edge cases."""
    
    def test_create_folder_structure_markdown(self, tmp_path):
        """Test markdown folder structure generation."""
        output_file = tmp_path / "test_structure.md"
        
        # This will use the default folder ID from settings
        result_path = create_folder_structure_markdown(
            output_file=str(output_file),
            max_depth=2  # Limit depth for testing
        )
        
        assert Path(result_path).exists()
        content = Path(result_path).read_text()
        
        assert "# Google Drive Folder Structure" in content
        assert "Folder ID:" in content
        assert "Generated:" in content
        assert "## Structure" in content

    def test_singleton_behavior(self):
        """Test that get_drive_manager returns the same instance."""
        manager1 = get_drive_manager()
        manager2 = get_drive_manager()
        
        assert manager1 is manager2

    def test_hash_computation(self):
        """Test SHA256 hash computation for deduplication."""
        manager = get_drive_manager()
        
        content1 = b"Test content 1"
        content2 = b"Test content 2"
        content1_copy = b"Test content 1"
        
        # Compute hashes
        hash1 = hashlib.sha256(content1).hexdigest()
        hash2 = hashlib.sha256(content2).hexdigest()
        hash1_copy = hashlib.sha256(content1_copy).hexdigest()
        
        # Same content should have same hash
        assert hash1 == hash1_copy
        
        # Different content should have different hash
        assert hash1 != hash2
        
        # Hashes should be 64 characters (SHA256)
        assert len(hash1) == 64
        assert len(hash2) == 64