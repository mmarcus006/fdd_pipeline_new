"""FDD document models for FDD Pipeline."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime, date
from uuid import UUID
from enum import Enum


class DocumentType(str, Enum):
    INITIAL = "Initial"
    AMENDMENT = "Amendment"
    RENEWAL = "Renewal"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FDDBase(BaseModel):
    """Base FDD model."""

    franchise_id: UUID
    issue_date: date
    amendment_date: Optional[date] = None
    document_type: DocumentType
    filing_state: str = Field(..., pattern="^[A-Z]{2}$")
    filing_number: Optional[str] = None
    drive_path: str
    drive_file_id: str
    sha256_hash: Optional[str] = Field(None, pattern="^[a-f0-9]{64}$")
    total_pages: Optional[int] = Field(None, gt=0)
    language_code: str = Field(default="en", pattern="^[a-z]{2}$")

    @model_validator(mode="after")
    def validate_amendment(self):
        """Ensure amendment_date is set for Amendment type."""
        if self.document_type == DocumentType.AMENDMENT and not self.amendment_date:
            raise ValueError("Amendment date required for Amendment documents")
        return self

    @field_validator("drive_path")
    @classmethod
    def validate_drive_path(cls, v):
        """Ensure valid Google Drive path format."""
        if not v.startswith("/"):
            raise ValueError("Drive path must start with /")
        return v


class FDDCreate(FDDBase):
    """Model for creating new FDD records."""

    pass


class FDD(FDDBase):
    """Complete FDD model with all fields."""

    id: UUID
    is_amendment: bool
    superseded_by_id: Optional[UUID] = None
    duplicate_of_id: Optional[UUID] = None
    needs_review: bool = False
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "use_enum_values": True}
