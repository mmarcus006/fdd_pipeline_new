"""Google Drive operations for FDD Pipeline document storage."""

import os
import io
import time
import hashlib
import pickle
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from dataclasses import dataclass
from uuid import UUID
import threading

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from config import get_settings
from utils.logging import get_logger
from storage.database.manager import get_database_manager

logger = get_logger(__name__)

# OAuth2 scopes required for Google Drive operations
SCOPES = ['https://www.googleapis.com/auth/drive']


@dataclass
class DriveFileMetadata:
    """Metadata for a Google Drive file."""

    id: str
    name: str
    size: int
    created_time: datetime
    modified_time: datetime
    mime_type: str
    parents: List[str]
    drive_path: str


class DriveManager:
    """Manages Google Drive operations for FDD document storage."""

    def __init__(self, use_oauth2: bool = False, token_file: Optional[str] = None):
        """Initialize DriveManager with authentication.
        
        Args:
            use_oauth2: If True, use OAuth2 authentication instead of service account
            token_file: Path to OAuth2 token file (only used if use_oauth2=True)
        """
        self.settings = get_settings()
        self.use_oauth2 = use_oauth2
        self.token_file = token_file or "google_drive_token.pickle"
        self._service = None
        self._service_lock = threading.Lock()
        self._folder_cache: Dict[str, str] = {}
        self._cache_lock = threading.Lock()
        self._db_manager = get_database_manager()
        self._rate_limit_delay = 0.1  # Base delay between API calls
        self._max_retries = 3

    @property
    def service(self):
        """Get authenticated Google Drive service (lazy initialization with thread safety)."""
        if self._service is None:
            with self._service_lock:
                # Double-check locking pattern
                if self._service is None:
                    self._service = self._get_drive_service()
        return self._service

    def _get_drive_service(self):
        """Get authenticated Google Drive service."""
        try:
            if self.use_oauth2:
                # OAuth2 authentication
                creds = self._get_oauth2_credentials()
            else:
                # Service account authentication
                creds = service_account.Credentials.from_service_account_file(
                    self.settings.gdrive_creds_json,
                    scopes=SCOPES,
                )
            
            service = build("drive", "v3", credentials=creds)
            logger.info(f"Google Drive service initialized successfully using {'OAuth2' if self.use_oauth2 else 'service account'}")
            return service
        except Exception as e:
            logger.error("Failed to initialize Google Drive service", error=str(e))
            raise

    def _get_oauth2_credentials(self):
        """Get OAuth2 credentials, refreshing or prompting for auth as needed."""
        
        creds = None
        token_path = Path(self.token_file)
        
        # Load existing token if available
        if token_path.exists():
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
                logger.debug("Loaded existing OAuth2 token")
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired OAuth2 token")
                creds.refresh(Request())
            else:
                logger.info("Initiating OAuth2 authentication flow")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.settings.gdrive_creds_json, SCOPES
                )
                # Try console-based auth for headless environments
                try:
                    creds = flow.run_console()
                except Exception:
                    # Fallback to local server
                    creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
                logger.info("Saved OAuth2 token for future use")
        
        return creds

    def create_folder(self, name: str, parent_id: str) -> str:
        """Create a folder in Google Drive.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Created folder ID

        Raises:
            HttpError: If folder creation fails
        """
        try:
            folder_metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }

            folder = (
                self.service.files().create(body=folder_metadata, fields="id").execute()
            )

            folder_id = folder.get("id")
            logger.info(
                "Created Google Drive folder",
                folder_name=name,
                folder_id=folder_id,
                parent_id=parent_id,
            )
            return folder_id

        except HttpError as e:
            logger.error(
                "Failed to create Google Drive folder",
                folder_name=name,
                parent_id=parent_id,
                error=str(e),
            )
            raise

    def folder_exists(self, name: str, parent_id: str) -> Optional[str]:
        """Check if folder exists and return its ID.

        Args:
            name: Folder name to check
            parent_id: Parent folder ID

        Returns:
            Folder ID if exists, None otherwise
        """
        try:
            # Escape single quotes in folder name to prevent query injection
            escaped_name = name.replace("'", "\\'")
            query = f"name='{escaped_name}' and parents in '{parent_id}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            results = self._execute_with_retry(
                lambda: self.service.files().list(
                    q=query, 
                    fields="files(id, name)",
                    pageSize=1
                ).execute()
            )
            
            files = results.get("files", [])

            if files:
                folder_id = files[0]["id"]
                logger.debug(
                    "Found existing folder", folder_name=name, folder_id=folder_id
                )
                return folder_id
            return None

        except HttpError as e:
            logger.error(
                "Failed to check folder existence",
                folder_name=name,
                parent_id=parent_id,
                error=str(e),
            )
            return None

    def get_or_create_folder(self, name: str, parent_id: str) -> str:
        """Get existing folder ID or create new folder.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Folder ID (existing or newly created)
        """
        # Check cache first with thread safety
        cache_key = f"{parent_id}/{name}"
        with self._cache_lock:
            if cache_key in self._folder_cache:
                return self._folder_cache[cache_key]

        folder_id = self.folder_exists(name, parent_id)
        if folder_id:
            logger.debug("Using existing folder", folder_name=name, folder_id=folder_id)
        else:
            folder_id = self.create_folder(name, parent_id)
            logger.info("Created new folder", folder_name=name, folder_id=folder_id)

        # Cache the result with thread safety
        with self._cache_lock:
            self._folder_cache[cache_key] = folder_id
        return folder_id

    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        parent_id: str,
        mime_type: str = "application/pdf",
        resumable: bool = True,
    ) -> str:
        """Upload a file to Google Drive with resumable upload support.

        Args:
            file_content: File content as bytes
            filename: Name for the uploaded file
            parent_id: Parent folder ID
            mime_type: MIME type of the file
            resumable: Whether to use resumable upload for large files

        Returns:
            Uploaded file ID

        Raises:
            HttpError: If upload fails
        """
        try:
            file_metadata = {"name": filename, "parents": [parent_id]}

            # Create media upload object
            media = MediaIoBaseUpload(
                io.BytesIO(file_content), mimetype=mime_type, resumable=resumable
            )

            # Upload the file
            request = self.service.files().create(
                body=file_metadata, media_body=media, fields="id"
            )

            file_id = None
            response = None

            if resumable and len(file_content) > 5 * 1024 * 1024:  # 5MB threshold
                # Resumable upload for large files
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        logger.debug(
                            "Upload progress",
                            filename=filename,
                            progress=f"{int(status.progress() * 100)}%",
                        )
            else:
                # Simple upload for small files
                response = request.execute()

            file_id = response.get("id")
            logger.info(
                "Successfully uploaded file to Google Drive",
                filename=filename,
                file_id=file_id,
                parent_id=parent_id,
                file_size=len(file_content),
            )
            return file_id

        except HttpError as e:
            logger.error(
                "Failed to upload file to Google Drive",
                filename=filename,
                parent_id=parent_id,
                file_size=len(file_content),
                error=str(e),
            )
            raise

    def download_file(self, file_id: str) -> bytes:
        """Download a file from Google Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            File content as bytes

        Raises:
            HttpError: If download fails
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(
                        "Download progress",
                        file_id=file_id,
                        progress=f"{int(status.progress() * 100)}%",
                    )

            file_content = file_io.getvalue()
            logger.info(
                "Successfully downloaded file from Google Drive",
                file_id=file_id,
                file_size=len(file_content),
            )
            return file_content

        except HttpError as e:
            logger.error(
                "Failed to download file from Google Drive",
                file_id=file_id,
                error=str(e),
            )
            raise

    def get_file_metadata(self, file_id: str) -> DriveFileMetadata:
        """Get metadata for a Google Drive file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata

        Raises:
            HttpError: If metadata retrieval fails
        """
        try:
            file_info = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,size,createdTime,modifiedTime,mimeType,parents",
                )
                .execute()
            )

            # Get the drive path by traversing parents
            drive_path = self._get_file_path(file_id)

            metadata = DriveFileMetadata(
                id=file_info["id"],
                name=file_info["name"],
                size=int(file_info.get("size", 0)),
                created_time=datetime.fromisoformat(
                    file_info["createdTime"].replace("Z", "+00:00")
                ),
                modified_time=datetime.fromisoformat(
                    file_info["modifiedTime"].replace("Z", "+00:00")
                ),
                mime_type=file_info["mimeType"],
                parents=file_info.get("parents", []),
                drive_path=drive_path,
            )

            logger.debug(
                "Retrieved file metadata",
                file_id=file_id,
                filename=metadata.name,
                drive_path=drive_path,
            )
            return metadata

        except HttpError as e:
            logger.error("Failed to get file metadata", file_id=file_id, error=str(e))
            raise

    def _get_file_path(self, file_id: str) -> str:
        """Get the full path of a file in Google Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            Full path string (e.g., "/fdds/raw/mn/franchise_name.pdf")
        """
        try:
            path_parts = []
            current_id = file_id

            while current_id and current_id != self.settings.gdrive_folder_id:
                file_info = (
                    self.service.files()
                    .get(fileId=current_id, fields="name,parents")
                    .execute()
                )

                path_parts.append(file_info["name"])
                parents = file_info.get("parents", [])
                current_id = parents[0] if parents else None

            # Reverse to get correct order and join with "/"
            path_parts.reverse()
            return "/" + "/".join(path_parts)

        except Exception as e:
            logger.warning(
                "Failed to construct file path", file_id=file_id, error=str(e)
            )
            return f"/unknown/{file_id}"

    def create_folder_structure(
        self, path: str, base_folder_id: Optional[str] = None
    ) -> str:
        """Create a nested folder structure in Google Drive.

        Args:
            path: Folder path (e.g., "fdds/raw/mn/franchise_name")
            base_folder_id: Base folder ID (defaults to configured root folder)

        Returns:
            Final folder ID
        """
        if base_folder_id is None:
            base_folder_id = self.settings.gdrive_folder_id

        # Split path and create folders recursively
        path_parts = [part for part in path.split("/") if part]
        current_folder_id = base_folder_id

        for folder_name in path_parts:
            current_folder_id = self.get_or_create_folder(
                folder_name, current_folder_id
            )

        logger.info(
            "Created folder structure", path=path, final_folder_id=current_folder_id
        )
        return current_folder_id

    def list_files(
        self, folder_id: str, mime_type: Optional[str] = None
    ) -> List[DriveFileMetadata]:
        """List files in a Google Drive folder.

        Args:
            folder_id: Folder ID to list files from
            mime_type: Optional MIME type filter

        Returns:
            List of file metadata
        """
        try:
            query = f"parents in '{folder_id}' and trashed=false"
            if mime_type:
                query += f" and mimeType='{mime_type}'"

            results = (
                self.service.files()
                .list(
                    q=query,
                    fields="files(id,name,size,createdTime,modifiedTime,mimeType,parents)",
                )
                .execute()
            )

            files = results.get("files", [])
            file_list = []

            for file_info in files:
                drive_path = self._get_file_path(file_info["id"])
                metadata = DriveFileMetadata(
                    id=file_info["id"],
                    name=file_info["name"],
                    size=int(file_info.get("size", 0)),
                    created_time=datetime.fromisoformat(
                        file_info["createdTime"].replace("Z", "+00:00")
                    ),
                    modified_time=datetime.fromisoformat(
                        file_info["modifiedTime"].replace("Z", "+00:00")
                    ),
                    mime_type=file_info["mimeType"],
                    parents=file_info.get("parents", []),
                    drive_path=drive_path,
                )
                file_list.append(metadata)

            logger.info(
                "Listed files in folder", folder_id=folder_id, file_count=len(file_list)
            )
            return file_list

        except HttpError as e:
            logger.error(
                "Failed to list files in folder", folder_id=folder_id, error=str(e)
            )
            raise

    def delete_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive.

        Args:
            file_id: File ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info("Successfully deleted file", file_id=file_id)
            return True

        except HttpError as e:
            logger.error("Failed to delete file", file_id=file_id, error=str(e))
            return False

    def verify_permissions(self) -> bool:
        """Verify that the service account has proper permissions.

        Returns:
            True if permissions are valid, False otherwise
        """
        try:
            # Try to list files in the root folder
            results = (
                self.service.files()
                .list(
                    q=f"parents in '{self.settings.gdrive_folder_id}'",
                    fields="files(id, name)",
                    pageSize=1,
                )
                .execute()
            )

            logger.debug("Verified read permissions")

            # Try to create and delete a test file
            test_file = {
                "name": f"test_permissions_{int(time.time())}.txt",
                "parents": [self.settings.gdrive_folder_id],
            }

            created_file = self.service.files().create(body=test_file).execute()
            file_id = created_file.get("id")

            # Delete the test file
            self.service.files().delete(fileId=file_id).execute()

            logger.info("Verified Google Drive permissions successfully")
            return True

        except HttpError as e:
            logger.error("Google Drive permission verification failed", error=str(e))
            return False

    def get_storage_quota(self) -> Dict[str, int]:
        """Get Google Drive storage quota information.

        Returns:
            Dictionary with quota information
        """
        try:
            about = self.service.about().get(fields="storageQuota").execute()
            quota = about.get("storageQuota", {})

            return {
                "limit": int(quota.get("limit", 0)),
                "usage": int(quota.get("usage", 0)),
                "usage_in_drive": int(quota.get("usageInDrive", 0)),
            }

        except HttpError as e:
            logger.error("Failed to get storage quota", error=str(e))
            return {}

    def _handle_rate_limit(self, error: HttpError) -> bool:
        """Handle rate limiting errors with exponential backoff.

        Args:
            error: HttpError from Google API

        Returns:
            True if should retry, False otherwise
        """
        if error.resp.status == 429:  # Rate limit exceeded
            # Extract retry-after header if available
            retry_after = error.resp.get("retry-after")
            if retry_after:
                delay = int(retry_after)
            else:
                # Use exponential backoff
                delay = min(self._rate_limit_delay * (2**self._max_retries), 60)

            logger.warning(
                "Rate limit exceeded, waiting before retry", delay_seconds=delay
            )
            time.sleep(delay)
            self._rate_limit_delay *= 2  # Increase delay for next time
            return True

        return False

    def _execute_with_retry(self, operation_func, *args, **kwargs):
        """Execute an operation with retry logic for rate limits and transient errors.

        Args:
            operation_func: Function to execute
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the operation

        Raises:
            HttpError: If all retries are exhausted
        """
        last_error = None

        for attempt in range(self._max_retries + 1):
            try:
                # Add small delay between API calls to be respectful
                if attempt > 0:
                    time.sleep(self._rate_limit_delay)

                return operation_func(*args, **kwargs)

            except HttpError as e:
                last_error = e

                # Handle rate limiting
                if self._handle_rate_limit(e):
                    logger.info(
                        "Retrying after rate limit",
                        attempt=attempt + 1,
                        max_attempts=self._max_retries + 1,
                    )
                    continue

                # Handle other retryable errors (5xx server errors)
                if 500 <= e.resp.status < 600:
                    delay = (2**attempt) * self._rate_limit_delay
                    logger.warning(
                        "Server error, retrying",
                        status_code=e.resp.status,
                        attempt=attempt + 1,
                        delay_seconds=delay,
                    )
                    time.sleep(delay)
                    continue

                # Non-retryable error, raise immediately
                raise

            except Exception as e:
                # For non-HTTP errors, only retry a few times
                if attempt < 2:
                    delay = (2**attempt) * self._rate_limit_delay
                    logger.warning(
                        "Unexpected error, retrying",
                        error=str(e),
                        attempt=attempt + 1,
                        delay_seconds=delay,
                    )
                    time.sleep(delay)
                    continue
                raise

        # All retries exhausted
        if last_error:
            raise last_error
        else:
            raise Exception("All retries exhausted")

    def batch_upload_files(
        self,
        files: List[Dict[str, any]],
        folder_path: str,
        fdd_id: Optional[UUID] = None,
        document_type: str = "original",
    ) -> List[Tuple[str, DriveFileMetadata]]:
        """Upload multiple files in batch with metadata sync.

        Args:
            files: List of dicts with 'content', 'filename', and optional 'mime_type'
            folder_path: Folder path for all files
            fdd_id: Optional FDD ID for database linking
            document_type: Type of document

        Returns:
            List of tuples of (file_id, metadata)
        """
        results = []
        folder_id = self.create_folder_structure(folder_path)
        
        for file_info in files:
            try:
                file_id, metadata = self.upload_file_with_metadata_sync(
                    file_content=file_info['content'],
                    filename=file_info['filename'],
                    folder_path=folder_path,
                    fdd_id=fdd_id,
                    document_type=document_type,
                    mime_type=file_info.get('mime_type', 'application/pdf')
                )
                results.append((file_id, metadata))
                
                # Small delay between uploads to respect rate limits
                time.sleep(self._rate_limit_delay)
                
            except Exception as e:
                logger.error(
                    "Failed to upload file in batch",
                    filename=file_info['filename'],
                    error=str(e)
                )
                continue
        
        return results

    def upload_file_with_metadata_sync(
        self,
        file_content: bytes,
        filename: str,
        folder_path: str,
        fdd_id: Optional[UUID] = None,
        document_type: str = "original",
        mime_type: str = "application/pdf",
    ) -> Tuple[str, DriveFileMetadata]:
        """Upload file and synchronize metadata with database.

        Args:
            file_content: File content as bytes
            filename: Name for the uploaded file
            folder_path: Folder path (e.g., "fdds/raw/mn/franchise_name")
            fdd_id: Optional FDD ID for database linking
            document_type: Type of document (original, processed, section)
            mime_type: MIME type of the file

        Returns:
            Tuple of (file_id, metadata)
        """
        try:
            # Create folder structure
            folder_id = self.create_folder_structure(folder_path)

            # Calculate file hash for deduplication
            file_hash = hashlib.sha256(file_content).hexdigest()

            # Check if file already exists in database
            existing_files = self._db_manager.get_records_by_filter(
                "drive_files", {"sha256_hash": file_hash}
            )

            if existing_files:
                logger.info(
                    "File already exists, skipping upload",
                    filename=filename,
                    existing_file_id=existing_files[0]["drive_file_id"],
                )
                # Return existing file metadata
                existing_metadata = self.get_file_metadata(
                    existing_files[0]["drive_file_id"]
                )
                return existing_files[0]["drive_file_id"], existing_metadata

            # Upload file with retry logic
            def upload_operation():
                return self.upload_file(file_content, filename, folder_id, mime_type)

            file_id = self._execute_with_retry(upload_operation)

            # Get file metadata
            metadata = self.get_file_metadata(file_id)

            # Store metadata in database
            drive_file_record = {
                "drive_file_id": file_id,
                "filename": filename,
                "folder_path": folder_path,
                "file_size": len(file_content),
                "mime_type": mime_type,
                "sha256_hash": file_hash,
                "document_type": document_type,
                "fdd_id": str(fdd_id) if fdd_id else None,
                "created_at": metadata.created_time.isoformat(),
                "modified_at": metadata.modified_time.isoformat(),
                "drive_path": metadata.drive_path,
            }

            self._db_manager.execute_batch_insert("drive_files", [drive_file_record])

            logger.info(
                "File uploaded and metadata synchronized",
                filename=filename,
                file_id=file_id,
                folder_path=folder_path,
                file_size=len(file_content),
            )

            return file_id, metadata

        except Exception as e:
            logger.error(
                "Failed to upload file with metadata sync",
                filename=filename,
                folder_path=folder_path,
                error=str(e),
            )
            raise

    def sync_file_metadata_to_db(
        self, file_id: str, fdd_id: Optional[UUID] = None
    ) -> bool:
        """Synchronize Google Drive file metadata to database.

        Args:
            file_id: Google Drive file ID
            fdd_id: Optional FDD ID for linking

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get file metadata from Drive
            metadata = self.get_file_metadata(file_id)

            # Check if record already exists
            existing_record = self._db_manager.get_records_by_filter(
                "drive_files", {"drive_file_id": file_id}
            )

            drive_file_record = {
                "drive_file_id": file_id,
                "filename": metadata.name,
                "file_size": metadata.size,
                "mime_type": metadata.mime_type,
                "fdd_id": str(fdd_id) if fdd_id else None,
                "created_at": metadata.created_time.isoformat(),
                "modified_at": metadata.modified_time.isoformat(),
                "drive_path": metadata.drive_path,
            }

            if existing_record:
                # Update existing record
                self._db_manager.update_record(
                    "drive_files", existing_record[0]["id"], drive_file_record
                )
                logger.debug("Updated existing file metadata", file_id=file_id)
            else:
                # Insert new record
                self._db_manager.execute_batch_insert(
                    "drive_files", [drive_file_record]
                )
                logger.debug("Inserted new file metadata", file_id=file_id)

            return True

        except Exception as e:
            logger.error(
                "Failed to sync file metadata to database",
                file_id=file_id,
                error=str(e),
            )
            return False

    def get_files_by_fdd_id(self, fdd_id: UUID) -> List[DriveFileMetadata]:
        """Get all Google Drive files associated with an FDD.

        Args:
            fdd_id: FDD UUID

        Returns:
            List of file metadata
        """
        try:
            # Get file records from database
            file_records = self._db_manager.get_records_by_filter(
                "drive_files", {"fdd_id": str(fdd_id)}
            )

            metadata_list = []
            for record in file_records:
                try:
                    # Get fresh metadata from Drive
                    metadata = self.get_file_metadata(record["drive_file_id"])
                    metadata_list.append(metadata)
                except HttpError as e:
                    if e.resp.status == 404:
                        logger.warning(
                            "File not found in Drive, may have been deleted",
                            file_id=record["drive_file_id"],
                        )
                        continue
                    raise

            return metadata_list

        except Exception as e:
            logger.error(
                "Failed to get files by FDD ID", fdd_id=str(fdd_id), error=str(e)
            )
            raise

    def clear_folder_cache(self) -> None:
        """Clear the folder cache (useful after bulk operations)."""
        with self._cache_lock:
            self._folder_cache.clear()
        logger.debug("Cleared folder cache")

    def cleanup_orphaned_files(self) -> Dict[str, int]:
        """Clean up files that exist in database but not in Google Drive.

        Returns:
            Dictionary with cleanup statistics
        """
        try:
            # Get all file records from database
            all_file_records = self._db_manager.get_records_by_filter("drive_files", {})

            stats = {
                "total_checked": len(all_file_records),
                "orphaned_found": 0,
                "orphaned_cleaned": 0,
                "errors": 0,
            }

            for record in all_file_records:
                try:
                    # Check if file exists in Drive
                    self.service.files().get(
                        fileId=record["drive_file_id"], fields="id"
                    ).execute()

                except HttpError as e:
                    if e.resp.status == 404:
                        # File doesn't exist in Drive, remove from database
                        stats["orphaned_found"] += 1
                        try:
                            self._db_manager.delete_record("drive_files", record["id"])
                            stats["orphaned_cleaned"] += 1
                            logger.info(
                                "Cleaned up orphaned file record",
                                file_id=record["drive_file_id"],
                                filename=record.get("filename"),
                            )
                        except Exception as cleanup_error:
                            stats["errors"] += 1
                            logger.error(
                                "Failed to clean up orphaned record",
                                record_id=record["id"],
                                error=str(cleanup_error),
                            )
                    else:
                        stats["errors"] += 1
                        logger.error(
                            "Error checking file existence",
                            file_id=record["drive_file_id"],
                            error=str(e),
                        )

                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        "Unexpected error during cleanup",
                        file_id=record["drive_file_id"],
                        error=str(e),
                    )

            logger.info("Orphaned file cleanup completed", **stats)
            return stats

        except Exception as e:
            logger.error("Failed to cleanup orphaned files", error=str(e))
            raise


# Global DriveManager instance
drive_manager = None


def get_drive_manager(use_oauth2: Optional[bool] = None, token_file: Optional[str] = None) -> DriveManager:
    """Get the global DriveManager instance.
    
    Args:
        use_oauth2: If True, use OAuth2 authentication. If None, check environment variable.
        token_file: Path to OAuth2 token file
    """
    global drive_manager
    
    if drive_manager is None:
        # Check environment variable if not specified
        if use_oauth2 is None:
            use_oauth2 = os.getenv("GDRIVE_USE_OAUTH2", "true").lower() == "true"
        
        drive_manager = DriveManager(use_oauth2=use_oauth2, token_file=token_file)
    
    return drive_manager


def create_folder_structure_markdown(
    folder_id: str = "12xf8w9kvjTYlsmY0C0wyNtIehtgG8_fL",
    output_file: str = "drive_structure.md",
    max_depth: int = 10
) -> str:
    """Create a markdown file with the folder/file structure of a Google Drive folder.
    
    Args:
        folder_id: Google Drive folder ID to map (defaults to specified parent folder)
        output_file: Output markdown file name
        max_depth: Maximum depth to traverse (prevents infinite recursion)
        
    Returns:
        Path to the created markdown file
    """
    drive = get_drive_manager()
    
    def get_folder_contents(folder_id: str, depth: int = 0, prefix: str = "") -> List[str]:
        """Recursively get folder contents."""
        if depth > max_depth:
            return [f"{prefix}... (max depth reached)"]
            
        try:
            # Get all items in the folder
            query = f"parents in '{folder_id}' and trashed=false"
            results = drive.service.files().list(
                q=query,
                fields="files(id,name,mimeType,size,modifiedTime)",
                orderBy="folder,name"
            ).execute()
            
            files = results.get("files", [])
            structure_lines = []
            
            # Separate folders and files
            folders = [f for f in files if f["mimeType"] == "application/vnd.google-apps.folder"]
            documents = [f for f in files if f["mimeType"] != "application/vnd.google-apps.folder"]
            
            # Process folders first
            for i, folder in enumerate(folders):
                is_last_folder = i == len(folders) - 1 and len(documents) == 0
                folder_prefix = "└── " if is_last_folder else "├── "
                structure_lines.append(f"{prefix}{folder_prefix}📁 **{folder['name']}/**")
                
                # Recursively get subfolder contents
                next_prefix = prefix + ("    " if is_last_folder else "│   ")
                subfolder_contents = get_folder_contents(folder["id"], depth + 1, next_prefix)
                structure_lines.extend(subfolder_contents)
            
            # Process files
            for i, file in enumerate(documents):
                is_last = i == len(documents) - 1
                file_prefix = "└── " if is_last else "├── "
                
                # Format file size
                size = int(file.get("size", 0))
                if size > 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                
                # Get file extension for emoji
                file_ext = Path(file["name"]).suffix.lower()
                emoji = {
                    ".pdf": "📄",
                    ".doc": "📝", ".docx": "📝",
                    ".xls": "📊", ".xlsx": "📊",
                    ".ppt": "📽️", ".pptx": "📽️",
                    ".txt": "📃",
                    ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🖼️",
                    ".mp4": "🎥", ".avi": "🎥", ".mov": "🎥",
                    ".zip": "📦", ".rar": "📦",
                }.get(file_ext, "📄")
                
                # Format modified time
                modified = datetime.fromisoformat(file["modifiedTime"].replace("Z", "+00:00"))
                modified_str = modified.strftime("%Y-%m-%d %H:%M")
                
                structure_lines.append(
                    f"{prefix}{file_prefix}{emoji} {file['name']} *({size_str}, {modified_str})*"
                )
            
            return structure_lines
            
        except HttpError as e:
            logger.error(f"Error accessing folder {folder_id}: {e}")
            return [f"{prefix}❌ Error accessing folder: {e}"]
    
    try:
        # Get root folder info
        root_info = drive.service.files().get(fileId=folder_id, fields="name").execute()
        root_name = root_info.get("name", "Unknown Folder")
        
        logger.info(f"Creating folder structure for: {root_name} ({folder_id})")
        
        # Build the structure
        markdown_lines = [
            f"# Google Drive Folder Structure",
            f"",
            f"**Folder:** {root_name}  ",
            f"**Folder ID:** `{folder_id}`  ",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"",
            f"## Structure",
            f"",
            f"📁 **{root_name}/**"
        ]
        
        # Get folder contents
        contents = get_folder_contents(folder_id, 0, "")
        markdown_lines.extend(contents)
        
        # Add footer
        markdown_lines.extend([
            f"",
            f"---",
            f"*Generated by FDD Pipeline Google Drive Manager*"
        ])
        
        # Write to file
        output_path = Path(output_file)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(markdown_lines))
        
        logger.info(f"Folder structure saved to: {output_path.absolute()}")
        return str(output_path.absolute())
        
    except Exception as e:
        logger.error(f"Failed to create folder structure: {e}")
        raise


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Set up logging for standalone execution
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("Google Drive Manager - Test Operations")
    print("=" * 50)
    
    try:
        # Initialize drive manager
        drive = get_drive_manager()
        
        # Test 1: Verify permissions
        print("1. Verifying Google Drive permissions...")
        if drive.verify_permissions():
            print("✅ Permissions verified successfully")
        else:
            print("❌ Permission verification failed")
            sys.exit(1)
        
        # Test 2: Create folder structure markdown
        print("\n2. Creating folder structure markdown...")
        structure_file = create_folder_structure_markdown()
        print(f"✅ Folder structure saved to: {structure_file}")
        
        # Test 3: Upload test PDF
        print("\n3. Uploading test PDF...")
        test_pdf_path = Path(r"C:\Users\Miller\projects\fdd_pipeline_new\examples\2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf")
        
        if not test_pdf_path.exists():
            print(f"❌ Test PDF not found at: {test_pdf_path}")
            print("Please ensure the file exists or update the path")
        else:
            # Read the PDF file
            with open(test_pdf_path, "rb") as f:
                pdf_content = f.read()
            
            print(f"📄 File size: {len(pdf_content) / (1024*1024):.1f} MB")
            
            # Create test folder structure and upload
            parent_folder_id = "12xf8w9kvjTYlsmY0C0wyNtIehtgG8_fL"
            test_folder_path = "test"
            
            print(f"📁 Creating folder structure: {test_folder_path}")
            folder_id = drive.create_folder_structure(test_folder_path, parent_folder_id)
            
            print(f"📤 Uploading to folder ID: {folder_id}")
            file_id, metadata = drive.upload_file_with_metadata_sync(
                file_content=pdf_content,
                filename=test_pdf_path.name,
                folder_path=test_folder_path,
                document_type="test_upload",
                mime_type="application/pdf"
            )
            
            print(f"✅ Upload successful!")
            print(f"   File ID: {file_id}")
            print(f"   Drive Path: {metadata.drive_path}")
            print(f"   File Size: {metadata.size / (1024*1024):.1f} MB")
        
        # Test 4: Get storage quota
        print("\n4. Checking storage quota...")
        quota = drive.get_storage_quota()
        if quota:
            used_gb = quota.get("usage", 0) / (1024**3)
            limit_gb = quota.get("limit", 0) / (1024**3)
            usage_pct = (quota.get("usage", 0) / quota.get("limit", 1)) * 100 if quota.get("limit") else 0
            
            print(f"📊 Storage Usage: {used_gb:.2f} GB / {limit_gb:.2f} GB ({usage_pct:.1f}%)")
        else:
            print("❌ Could not retrieve storage quota")
        
        print("\n🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        logger.exception("Test execution failed")
        sys.exit(1)
