#!/usr/bin/env python3
"""Setup Google Drive folder structure for FDD Pipeline."""

import sys
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class DriveSetup:
    """Setup Google Drive folder structure."""
    
    def __init__(self):
        self.settings = get_settings()
        self.service = self._get_drive_service()
    
    def _get_drive_service(self):
        """Get authenticated Google Drive service."""
        credentials = service_account.Credentials.from_service_account_file(
            self.settings.gdrive_creds_json,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=credentials)
    
    def create_folder(self, name: str, parent_id: str) -> str:
        """Create a folder in Google Drive."""
        try:
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"Created folder '{name}' with ID: {folder_id}")
            return folder_id
            
        except HttpError as e:
            logger.error(f"Failed to create folder '{name}': {e}")
            raise
    
    def folder_exists(self, name: str, parent_id: str) -> str:
        """Check if folder exists and return its ID."""
        try:
            query = f"name='{name}' and parents in '{parent_id}' and mimeType='application/vnd.google-apps.folder'"
            results = self.service.files().list(q=query, fields='files(id, name)').execute()
            files = results.get('files', [])
            
            if files:
                return files[0]['id']
            return None
            
        except HttpError as e:
            logger.error(f"Failed to check folder '{name}': {e}")
            return None
    
    def get_or_create_folder(self, name: str, parent_id: str) -> str:
        """Get existing folder ID or create new folder."""
        folder_id = self.folder_exists(name, parent_id)
        if folder_id:
            logger.info(f"Folder '{name}' already exists with ID: {folder_id}")
            return folder_id
        else:
            return self.create_folder(name, parent_id)
    
    def setup_folder_structure(self) -> dict:
        """Setup the complete folder structure for FDD Pipeline."""
        root_folder_id = self.settings.gdrive_folder_id
        
        logger.info(f"Setting up folder structure in root folder: {root_folder_id}")
        
        # Main folders
        folders = {}
        
        # /fdds - Main FDD storage
        folders['fdds'] = self.get_or_create_folder('fdds', root_folder_id)
        
        # /fdds/raw - Original PDFs by source
        folders['raw'] = self.get_or_create_folder('raw', folders['fdds'])
        folders['raw_mn'] = self.get_or_create_folder('mn', folders['raw'])
        folders['raw_wi'] = self.get_or_create_folder('wi', folders['raw'])
        
        # /fdds/processed - Segmented documents
        folders['processed'] = self.get_or_create_folder('processed', folders['fdds'])
        
        # /fdds/archive - Superseded documents
        folders['archive'] = self.get_or_create_folder('archive', folders['fdds'])
        
        # /temp - Temporary processing files
        folders['temp'] = self.get_or_create_folder('temp', root_folder_id)
        
        logger.info("Folder structure setup complete!")
        return folders
    
    def verify_permissions(self) -> bool:
        """Verify that the service account has proper permissions."""
        try:
            # Try to list files in the root folder
            results = self.service.files().list(
                q=f"parents in '{self.settings.gdrive_folder_id}'",
                fields='files(id, name)'
            ).execute()
            
            logger.info("✓ Service account has read access")
            
            # Try to create a test file
            test_file = {
                'name': 'test_permissions.txt',
                'parents': [self.settings.gdrive_folder_id]
            }
            
            created_file = self.service.files().create(body=test_file).execute()
            file_id = created_file.get('id')
            
            # Delete the test file
            self.service.files().delete(fileId=file_id).execute()
            
            logger.info("✓ Service account has write access")
            return True
            
        except HttpError as e:
            logger.error(f"Permission check failed: {e}")
            return False


def main():
    """Main setup function."""
    print("FDD Pipeline Google Drive Setup")
    print("=" * 40)
    
    try:
        setup = DriveSetup()
        
        print("\nVerifying permissions...")
        if not setup.verify_permissions():
            print("✗ Permission verification failed")
            sys.exit(1)
        
        print("\nSetting up folder structure...")
        folders = setup.setup_folder_structure()
        
        print("\nFolder structure created:")
        for name, folder_id in folders.items():
            print(f"  {name}: {folder_id}")
        
        print("\n✓ Google Drive setup complete!")
        
    except Exception as e:
        print(f"✗ Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()