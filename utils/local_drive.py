"""Local filesystem-based DriveManager for development and testing."""

import os
import hashlib
from pathlib import Path
from typing import Tuple
from uuid import UUID
from datetime import datetime

from tasks.drive_operations import DriveFileMetadata


class LocalDriveManager:
    """A local version of the DriveManager that saves files to the filesystem."""

    def __init__(self, base_dir: str = "local_drive"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        print(f"LocalDriveManager initialized at: {self.base_dir.resolve()}")

    def upload_file_with_metadata_sync(
        self,
        file_content: bytes,
        filename: str,
        folder_path: str,
        fdd_id: UUID,
        document_type: str,
        mime_type: str,
    ) -> Tuple[str, "DriveFileMetadata"]:
        """
        Saves a file to the local filesystem and returns metadata.
        """
        # Create the folder structure
        target_folder = self.base_dir / folder_path
        target_folder.mkdir(parents=True, exist_ok=True)

        # Define the file path
        file_path = target_folder / filename

        # Write the file
        with open(file_path, "wb") as f:
            f.write(file_content)

        # Create metadata
        file_id = str(file_path.resolve())
        now = datetime.utcnow()
        metadata = DriveFileMetadata(
            id=file_id,
            name=filename,
            size=len(file_content),
            created_time=now,
            modified_time=now,
            mime_type=mime_type,
            parents=[str(target_folder.resolve())],
            drive_path=str(file_path.relative_to(self.base_dir)),
        )

        print(f"Saved file to {file_path.resolve()}")

        return file_id, metadata


# Singleton instance
local_drive_manager = LocalDriveManager()


def get_local_drive_manager() -> LocalDriveManager:
    """Returns the singleton instance of the LocalDriveManager."""
    return local_drive_manager
