"""Scraping metadata models."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class ScrapeMetadataBase(BaseModel):
    """Base model for scrape metadata."""

    fdd_id: UUID
    source_name: str  # 'MN', 'WI', etc.
    source_url: str
    filing_metadata: Dict[str, Any] = Field(default_factory=dict)
    prefect_run_id: Optional[UUID] = None

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


class ScrapeMetadata(ScrapeMetadataBase):
    """Scrape metadata with timestamps."""

    id: UUID
    scraped_at: datetime

    model_config = {"from_attributes": True}
