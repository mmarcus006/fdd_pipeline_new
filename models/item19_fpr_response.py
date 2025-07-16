"""Item 19 - Financial Performance Representations response model."""

from pydantic import BaseModel, Field
from typing import List, Optional

class FinancialPerformanceTable(BaseModel):
    """A single table of financial performance data."""
    table_name: str
    headers: List[str]
    rows: List[List[str]]
    notes: Optional[str] = None

class Item19FPRResponse(BaseModel):
    """Structured response for Item 19 - Financial Performance Representations."""
    tables: List[FinancialPerformanceTable]
    summary: Optional[str] = Field(None, description="A summary of the financial performance representations.")
    notes: Optional[str] = Field(None, description="Additional notes about the FPR.")
