"""Google Drive files tracking models."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum


class SyncStatus(str, Enum):
    """Drive file sync status."""
    ACTIVE = "active"
    DELETED = "deleted"
    ERROR = "error"


class DriveFileBase(BaseModel):
    """Base model for drive files."""
    
    file_id: str
    file_name: str
    mime_type: str
    parent_folder_id: Optional[str] = None
    size_bytes: Optional[int] = Field(None, ge=0)
    md5_checksum: Optional[str] = None
    web_view_link: Optional[str] = None
    download_link: Optional[str] = None
    
    # Relations
    fdd_id: Optional[UUID] = None
    fdd_section_id: Optional[UUID] = None
    
    # Drive metadata
    created_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None
    
    @field_validator("file_id")
    @classmethod
    def validate_file_id(cls, v):
        """Ensure file_id is not empty."""
        if not v or not v.strip():
            raise ValueError("file_id cannot be empty")
        return v.strip()
    
    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v):
        """Validate MIME type format."""
        if not v or "/" not in v:
            raise ValueError("Invalid MIME type format")
        return v
    
    @field_validator("web_view_link", "download_link")
    @classmethod
    def validate_links(cls, v):
        """Validate Google Drive links."""
        if v and not v.startswith(("https://drive.google.com", "https://docs.google.com")):
            raise ValueError("Invalid Google Drive link")
        return v


class DriveFileCreate(DriveFileBase):
    """Model for creating drive file records."""
    pass


class DriveFile(DriveFileBase):
    """Complete drive file model with database fields."""
    
    id: UUID
    sync_status: SyncStatus = SyncStatus.ACTIVE
    last_synced_at: datetime
    created_at: datetime
    
    model_config = {"from_attributes": True}