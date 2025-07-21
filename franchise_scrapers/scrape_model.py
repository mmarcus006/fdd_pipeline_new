"""Single flat model for franchise documents from all states."""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl

class FranchiseDocument(BaseModel):
    """Single database model for franchise documents from any state portal."""
    
    # Required fields (common to all states)
    source_state: str = Field(..., description="State code: MN or WI")
    filing_number: str = Field(..., description="State filing/file number")
    legal_name: str = Field(..., description="Legal franchisor name")
    scraped_at: datetime = Field(default_factory=datetime.now)
    
    # URLs (both states)
    pdf_url: Optional[HttpUrl] = None
    details_url: Optional[HttpUrl] = None
    
    # Name variations
    trade_name: Optional[str] = None  # WI
    
    # Status and type
    status: Optional[str] = None  # WI: "Registered"
    document_type: Optional[str] = None  # MN: "Clean FDD"
    document_year: Optional[int] = None  # MN
    
    # Dates
    effective_date: Optional[date] = None  # WI
    expiration_date: Optional[date] = None  # WI
    received_date: Optional[date] = None  # MN
    added_date: Optional[date] = None  # MN
    
    # Additional info
    business_address: Optional[str] = None  # WI details
    states_filed: Optional[List[str]] = Field(default_factory=list)  # WI details
    notes: Optional[str] = None  # MN
    
    class Config:
        orm_mode = True  # For database ORM compatibility