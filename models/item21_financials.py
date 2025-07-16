"""Item 21 - Financial Statements models."""

from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime, date
from uuid import UUID
from enum import Enum


class AuditOpinion(str, Enum):
    UNQUALIFIED = "Unqualified"
    QUALIFIED = "Qualified"
    ADVERSE = "Adverse"
    DISCLAIMER = "Disclaimer"


class FinancialsBase(BaseModel):
    """Base model for financial statements."""

    fiscal_year: Optional[int] = Field(None, ge=1900, le=2100)
    fiscal_year_end: Optional[date] = None

    # Income Statement
    total_revenue_cents: Optional[int] = Field(None, ge=0)
    franchise_revenue_cents: Optional[int] = Field(None, ge=0)
    cost_of_goods_cents: Optional[int] = Field(None, ge=0)
    gross_profit_cents: Optional[int] = None
    operating_expenses_cents: Optional[int] = Field(None, ge=0)
    operating_income_cents: Optional[int] = None
    net_income_cents: Optional[int] = None

    # Balance Sheet
    total_assets_cents: Optional[int] = Field(None, ge=0)
    current_assets_cents: Optional[int] = Field(None, ge=0)
    total_liabilities_cents: Optional[int] = Field(None, ge=0)
    current_liabilities_cents: Optional[int] = Field(None, ge=0)
    total_equity_cents: Optional[int] = None

    # Audit info
    auditor_name: Optional[str] = None
    audit_opinion: Optional[AuditOpinion] = None

    @model_validator(mode="after")
    def validate_accounting_equations(self):
        """Validate basic accounting equations where possible."""
        # Revenue - COGS = Gross Profit
        revenue = self.total_revenue_cents
        cogs = self.cost_of_goods_cents
        gross = self.gross_profit_cents

        if all(v is not None for v in [revenue, cogs, gross]):
            calculated_gross = revenue - cogs
            if abs(calculated_gross - gross) > 100:  # Allow $1 rounding error
                raise ValueError(
                    f"Gross profit calculation error: "
                    f"{revenue} - {cogs} = {calculated_gross}, not {gross}"
                )

        # Assets = Liabilities + Equity
        assets = self.total_assets_cents
        liabilities = self.total_liabilities_cents
        equity = self.total_equity_cents

        if all(v is not None for v in [assets, liabilities, equity]):
            calculated_equity = assets - liabilities
            if abs(calculated_equity - equity) > 100:  # Allow $1 rounding error
                raise ValueError(
                    f"Balance sheet doesn't balance: "
                    f"{assets} - {liabilities} = {calculated_equity}, not {equity}"
                )

        return self

    @model_validator(mode="after")
    def validate_ratios(self):
        """Validate financial ratios are reasonable."""
        # Current ratio check
        current_assets = self.current_assets_cents
        current_liabilities = self.current_liabilities_cents

        if current_assets is not None and current_liabilities is not None:
            if current_liabilities > 0:
                current_ratio = current_assets / current_liabilities
                if current_ratio < 0.1:
                    # Flag for review - very low liquidity
                    pass

        # Franchise revenue shouldn't exceed total revenue
        total_rev = self.total_revenue_cents
        franchise_rev = self.franchise_revenue_cents

        if total_rev is not None and franchise_rev is not None:
            if franchise_rev > total_rev:
                raise ValueError("Franchise revenue cannot exceed total revenue")

        return self


class Financials(FinancialsBase):
    """Financial statements with section reference."""

    section_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
