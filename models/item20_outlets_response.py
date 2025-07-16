"""Item 20 - Outlets and Franchisee Information response model."""

from pydantic import BaseModel, Field
from typing import List, Optional

class OutletSummaryTable(BaseModel):
    """A single table summarizing outlet data."""
    table_name: str
    headers: List[str]
    rows: List[List[str]]
    notes: Optional[str] = None

class Item20OutletsResponse(BaseModel):
    """Structured response for Item 20 - Outlets and Franchisee Information."""
    tables: List[OutletSummaryTable]
    summary: Optional[str] = Field(None, description="A summary of the outlet data.")
    notes: Optional[str] = Field(None, description="Additional notes about the outlet data.") 