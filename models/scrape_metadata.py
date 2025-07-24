"""Scraping metadata models."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime, date
from uuid import UUID
from enum import Enum


class ScrapeStatus(str, Enum):
    """Scrape status enum matching database constraints."""
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScrapeMetadataBase(BaseModel):
    """Base model for scrape metadata."""

    fdd_id: UUID
    source_name: str  # 'MN', 'WI', etc.
    source_url: str
    download_url: Optional[str] = None
    portal_id: Optional[str] = None  # State system's ID for the record
    registration_status: Optional[str] = None
    effective_date: Optional[date] = None
    scrape_status: ScrapeStatus = ScrapeStatus.DISCOVERED
    failure_reason: Optional[str] = None
    filing_metadata: Dict[str, Any] = Field(default_factory=dict)
    prefect_run_id: Optional[UUID] = None
    downloaded_at: Optional[datetime] = None

    @field_validator("source_name")
    @classmethod
    def validate_source(cls, v):
        """Ensure known source."""
        valid_sources = {"MN", "WI", "CA", "WA", "MD", "VA", "IL", "MI", "ND"}
        if v not in valid_sources:
            raise ValueError(f"Unknown source: {v}")
        return v

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v):
        """Basic URL validation."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Invalid URL format")
        return v

    @field_validator("download_url")
    @classmethod
    def validate_download_url(cls, v):
        """Validate download URL if provided."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("Invalid download URL format")
        return v


class ScrapeMetadataCreate(ScrapeMetadataBase):
    """Model for creating scrape metadata records."""
    pass


class ScrapeMetadata(ScrapeMetadataBase):
    """Scrape metadata with timestamps."""

    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
