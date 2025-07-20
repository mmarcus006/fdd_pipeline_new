"""Google Drive operations with OAuth2 authentication for FDD Pipeline."""

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


class DriveManagerOAuth:
    """Manages Google Drive operations using OAuth2 authentication."""

    def __init__(self, credentials_file: Optional[str] = None, token_file: Optional[str] = None):
        """Initialize DriveManager with OAuth2 authentication.
        
        Args:
            credentials_file: Path to OAuth2 credentials JSON file
            token_file: Path to store/load OAuth2 token
        """
        self.settings = get_settings()
        self.credentials_file = credentials_file or self.settings.gdrive_creds_json
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
        """Get authenticated Google Drive service using OAuth2."""
        try:
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
                        self.credentials_file, SCOPES
                    )
                    # Use console-based auth for headless environments
                    creds = flow.run_console()
                
                # Save the credentials for the next run
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
                    logger.info("Saved OAuth2 token for future use")
            
            service = build("drive", "v3", credentials=creds)
            logger.info("Google Drive service initialized successfully with OAuth2")
            return service
            
        except Exception as e:
            logger.error("Failed to initialize Google Drive service", error=str(e))
            raise

    def authenticate_interactive(self, port: int = 0):
        """Run interactive OAuth2 authentication flow with local server.
        
        Args:
            port: Port for local server (0 for automatic)
        """
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file, SCOPES
            )
            # Use local server for browser-based auth
            creds = flow.run_local_server(port=port)
            
            # Save the credentials
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
                logger.info("OAuth2 authentication successful, token saved")
            
            # Clear any existing service to force re-initialization
            with self._service_lock:
                self._service = None
            
            return True
            
        except Exception as e:
            logger.error("OAuth2 authentication failed", error=str(e))
            return False

    def revoke_credentials(self):
        """Revoke stored OAuth2 credentials."""
        try:
            token_path = Path(self.token_file)
            if token_path.exists():
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
                
                if creds and creds.valid:
                    # Revoke the token
                    import requests
                    requests.post('https://oauth2.googleapis.com/revoke',
                        params={'token': creds.token},
                        headers={'content-type': 'application/x-www-form-urlencoded'})
                
                # Delete the token file
                token_path.unlink()
                logger.info("OAuth2 credentials revoked and removed")
                
                # Clear service
                with self._service_lock:
                    self._service = None
                
                return True
            
        except Exception as e:
            logger.error("Failed to revoke credentials", error=str(e))
            return False

    # Include all the same methods from the original DriveManager class
    # (create_folder, folder_exists, get_or_create_folder, upload_file, etc.)
    # The methods remain the same since they use self.service which now uses OAuth2

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

    def verify_permissions(self) -> bool:
        """Verify that OAuth2 credentials have proper permissions.

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

    # Include all other methods from the original class...
    # (The remaining methods would be copied from the original DriveManager class)


# Global DriveManager instance
drive_manager_oauth = None


def get_drive_manager_oauth(credentials_file: Optional[str] = None, token_file: Optional[str] = None) -> DriveManagerOAuth:
    """Get the global OAuth2 DriveManager instance."""
    global drive_manager_oauth
    if drive_manager_oauth is None:
        drive_manager_oauth = DriveManagerOAuth(credentials_file, token_file)
    return drive_manager_oauth


if __name__ == "__main__":
    import sys
    
    print("Google Drive OAuth2 Authentication Setup")
    print("=" * 50)
    
    manager = get_drive_manager_oauth()
    
    if "--auth" in sys.argv:
        print("\nStarting OAuth2 authentication flow...")
        print("A browser window will open for you to authenticate.")
        print("If running on a headless server, use --auth-console instead.")
        
        if manager.authenticate_interactive():
            print("✅ Authentication successful!")
        else:
            print("❌ Authentication failed!")
            sys.exit(1)
    
    elif "--auth-console" in sys.argv:
        print("\nStarting console-based OAuth2 authentication...")
        print("Visit the URL shown and enter the authorization code.")
        
        # This will use the console-based flow automatically
        try:
            service = manager.service  # This will trigger auth if needed
            print("✅ Authentication successful!")
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            sys.exit(1)
    
    elif "--revoke" in sys.argv:
        print("\nRevoking stored credentials...")
        if manager.revoke_credentials():
            print("✅ Credentials revoked successfully!")
        else:
            print("❌ Failed to revoke credentials!")
    
    else:
        # Test the connection
        print("\nTesting Google Drive connection...")
        try:
            if manager.verify_permissions():
                print("✅ Connection successful! Permissions verified.")
            else:
                print("❌ Connection failed! Check permissions.")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            print("\nRun with --auth to authenticate.")