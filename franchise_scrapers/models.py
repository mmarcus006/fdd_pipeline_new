# franchise_scrapers/models.py
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime
from typing import Optional


class CleanFDDRow(BaseModel):
    """Single record from the Minnesota Commerce Clean FDD table."""
    
    document_id: str = Field(..., description="Unique filing identifier parsed from the PDF URL query param `documentId`.")
    legal_name: str = Field(..., description="Legal franchisor name as shown in column 2.")
    pdf_url: HttpUrl = Field(..., description="Absolute URL to the FDD PDF.")
    scraped_at: datetime = Field(..., description="UTC timestamp when the table row was captured.")
    
    # Optional fields for download tracking
    pdf_status: Optional[str] = Field(None, description="Download status: 'ok' | 'failed' | 'skipped'")
    pdf_path: Optional[str] = Field(None, description="Local path to downloaded PDF if successful")


class WIActiveRow(BaseModel):
    """Row from Wisconsin Active Filings list."""
    
    legal_name: str = Field(..., description="Legal franchisor name.")
    filing_number: str = Field(..., description="Numeric filing # column.")


class WIRegisteredRow(BaseModel):
    """Row produced after the WI search step – only Registered rows are kept."""
    
    filing_number: str = Field(..., description="Same as Active → used to join.")
    legal_name: str = Field(..., description="Name from search results table.")
    details_url: HttpUrl = Field(..., description="Absolute Details page link.")


class WIDetailsRow(BaseModel):
    """Full details of a WI filing plus PDF path."""
    
    filing_number: str = Field(..., description="Primary key across CSVs.")
    status: str = Field(..., description="Filing status label – expected 'Registered'.")
    legal_name: str = Field(..., description="Legal name from Details page.")
    trade_name: Optional[str] = Field(None, description="DBA / trade name if present.")
    contact_email: Optional[str] = Field(None, description="Contact e-mail extracted from Details page.")
    pdf_path: Optional[str] = Field(None, description="Filesystem path of the downloaded PDF relative to `DOWNLOAD_DIR`.")
    pdf_status: str = Field(..., description="'ok' | 'failed' | 'skipped'.")
    scraped_at: datetime = Field(..., description="UTC timestamp for this Details scrape.")