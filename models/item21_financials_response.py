"""Item 21 - Financial Statements response model."""

from pydantic import BaseModel, Field
from typing import List, Optional

class FinancialStatementTable(BaseModel):
    """A single table from a financial statement."""
    statement_name: str
    headers: List[str]
    rows: List[List[str]]
    notes: Optional[str] = None

class Item21FinancialsResponse(BaseModel):
    """Structured response for Item 21 - Financial Statements."""
    financial_statements: List[FinancialStatementTable]
    summary: Optional[str] = Field(None, description="A summary of the financial statements.")
    notes: Optional[str] = Field(None, description="Additional notes about the financial statements.") 