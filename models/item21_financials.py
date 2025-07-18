"""Item 21 - Financial Statements models using unified architecture."""

from pydantic import Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from enum import Enum

from .base_items import (
    BaseItemModel, BaseItemResponse, TableBasedItem,
    ValidationStatus, ItemValidator
)
from .base import cents_to_dollars


class AuditOpinion(str, Enum):
    """Types of audit opinions."""
    UNQUALIFIED = "unqualified"
    QUALIFIED = "qualified"
    ADVERSE = "adverse"
    DISCLAIMER = "disclaimer"
    NOT_AUDITED = "not_audited"


class StatementType(str, Enum):
    """Types of financial statements."""
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"
    EQUITY_STATEMENT = "equity_statement"
    NOTES = "notes"


class Financials(BaseItemModel):
    """Database storage model for financial statements."""
    
    # Period information
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_year_end: Optional[date] = None
    period_months: int = Field(12, description="Number of months covered")
    
    # Income Statement
    total_revenue_cents: Optional[int] = Field(None, ge=0)
    franchise_revenue_cents: Optional[int] = Field(None, ge=0)
    royalty_revenue_cents: Optional[int] = Field(None, ge=0)
    advertising_revenue_cents: Optional[int] = Field(None, ge=0)
    product_revenue_cents: Optional[int] = Field(None, ge=0)
    other_revenue_cents: Optional[int] = Field(None, ge=0)
    
    cost_of_goods_cents: Optional[int] = Field(None, ge=0)
    gross_profit_cents: Optional[int] = None
    
    operating_expenses_cents: Optional[int] = Field(None, ge=0)
    general_admin_expenses_cents: Optional[int] = Field(None, ge=0)
    marketing_expenses_cents: Optional[int] = Field(None, ge=0)
    depreciation_amortization_cents: Optional[int] = Field(None, ge=0)
    
    operating_income_cents: Optional[int] = None
    interest_expense_cents: Optional[int] = Field(None, ge=0)
    other_income_expense_cents: Optional[int] = None
    pretax_income_cents: Optional[int] = None
    income_tax_cents: Optional[int] = Field(None, ge=0)
    net_income_cents: Optional[int] = None
    
    # Balance Sheet
    # Assets
    total_assets_cents: Optional[int] = Field(None, ge=0)
    current_assets_cents: Optional[int] = Field(None, ge=0)
    cash_equivalents_cents: Optional[int] = Field(None, ge=0)
    accounts_receivable_cents: Optional[int] = Field(None, ge=0)
    inventory_cents: Optional[int] = Field(None, ge=0)
    
    fixed_assets_cents: Optional[int] = Field(None, ge=0)
    intangible_assets_cents: Optional[int] = Field(None, ge=0)
    goodwill_cents: Optional[int] = Field(None, ge=0)
    
    # Liabilities
    total_liabilities_cents: Optional[int] = Field(None, ge=0)
    current_liabilities_cents: Optional[int] = Field(None, ge=0)
    accounts_payable_cents: Optional[int] = Field(None, ge=0)
    accrued_expenses_cents: Optional[int] = Field(None, ge=0)
    deferred_revenue_cents: Optional[int] = Field(None, ge=0)
    
    long_term_debt_cents: Optional[int] = Field(None, ge=0)
    other_liabilities_cents: Optional[int] = Field(None, ge=0)
    
    # Equity
    total_equity_cents: Optional[int] = None
    retained_earnings_cents: Optional[int] = None
    
    # Cash Flow (key items)
    operating_cash_flow_cents: Optional[int] = None
    investing_cash_flow_cents: Optional[int] = None
    financing_cash_flow_cents: Optional[int] = None
    net_cash_flow_cents: Optional[int] = None
    
    # Audit information
    auditor_name: Optional[str] = None
    audit_opinion: Optional[AuditOpinion] = None
    audit_date: Optional[date] = None
    
    # Supplementary data
    number_of_outlets: Optional[int] = Field(None, ge=0)
    comparable_store_sales_growth: Optional[float] = None
    ebitda_cents: Optional[int] = None
    
    @model_validator(mode="after")
    def validate_accounting_equations(self):
        """Validate basic accounting equations where possible."""
        # Revenue components check
        if self.total_revenue_cents is not None:
            components = [
                self.franchise_revenue_cents or 0,
                self.royalty_revenue_cents or 0,
                self.advertising_revenue_cents or 0,
                self.product_revenue_cents or 0,
                self.other_revenue_cents or 0
            ]
            component_sum = sum(components)
            
            # Only validate if at least some components are specified
            if any(c > 0 for c in components) and component_sum > self.total_revenue_cents:
                raise ValueError(
                    f"Revenue components ({component_sum}) exceed total revenue ({self.total_revenue_cents})"
                )
        
        # Gross profit validation
        if all(v is not None for v in [self.total_revenue_cents, self.cost_of_goods_cents, self.gross_profit_cents]):
            calculated_gross = self.total_revenue_cents - self.cost_of_goods_cents
            if abs(calculated_gross - self.gross_profit_cents) > 100:  # Allow $1 rounding
                raise ValueError(
                    f"Gross profit calculation error: {calculated_gross} != {self.gross_profit_cents}"
                )
        
        # Balance sheet equation
        if all(v is not None for v in [self.total_assets_cents, self.total_liabilities_cents, self.total_equity_cents]):
            calculated_equity = self.total_assets_cents - self.total_liabilities_cents
            if abs(calculated_equity - self.total_equity_cents) > 100:  # Allow $1 rounding
                raise ValueError(
                    f"Balance sheet doesn't balance: A-L={calculated_equity}, E={self.total_equity_cents}"
                )
        
        return self
    
    @field_validator("franchise_revenue_cents")
    @classmethod
    def validate_franchise_revenue(cls, v, info):
        """Ensure franchise revenue doesn't exceed total revenue."""
        if v is not None and "total_revenue_cents" in info.data:
            total = info.data["total_revenue_cents"]
            if total is not None and v > total:
                raise ValueError("Franchise revenue cannot exceed total revenue")
        return v
    
    @property
    def gross_margin(self) -> Optional[float]:
        """Calculate gross margin percentage."""
        if self.total_revenue_cents and self.gross_profit_cents:
            return round((self.gross_profit_cents / self.total_revenue_cents) * 100, 2)
        return None
    
    @property
    def operating_margin(self) -> Optional[float]:
        """Calculate operating margin percentage."""
        if self.total_revenue_cents and self.operating_income_cents:
            return round((self.operating_income_cents / self.total_revenue_cents) * 100, 2)
        return None
    
    @property
    def net_margin(self) -> Optional[float]:
        """Calculate net margin percentage."""
        if self.total_revenue_cents and self.net_income_cents:
            return round((self.net_income_cents / self.total_revenue_cents) * 100, 2)
        return None
    
    @property
    def current_ratio(self) -> Optional[float]:
        """Calculate current ratio."""
        if self.current_assets_cents and self.current_liabilities_cents and self.current_liabilities_cents > 0:
            return round(self.current_assets_cents / self.current_liabilities_cents, 2)
        return None
    
    @property
    def debt_to_equity(self) -> Optional[float]:
        """Calculate debt-to-equity ratio."""
        if self.total_liabilities_cents and self.total_equity_cents and self.total_equity_cents > 0:
            return round(self.total_liabilities_cents / self.total_equity_cents, 2)
        return None


class FinancialTable(BaseItemModel):
    """Parsed financial statement table."""
    
    statement_type: StatementType
    statement_name: str = Field(..., description="Name of the financial statement")
    fiscal_year: Optional[int] = Field(None, ge=1900, le=2100)
    headers: List[str] = Field(..., description="Column headers")
    rows: List[List[Any]] = Field(..., description="Table data rows")
    currency: str = Field("USD", description="Currency code")
    units: str = Field("dollars", description="Units (e.g., 'thousands', 'millions')")
    
    @field_validator("rows")
    @classmethod
    def validate_row_consistency(cls, v, info):
        """Ensure all rows have same number of columns as headers."""
        if "headers" in info.data:
            header_count = len(info.data["headers"])
            for i, row in enumerate(v):
                if len(row) != header_count:
                    raise ValueError(
                        f"Row {i} has {len(row)} columns, expected {header_count}"
                    )
        return v
    
    def get_value_by_label(self, label: str, year_column: int = -1) -> Optional[Any]:
        """Extract a value from the table by row label."""
        label_lower = label.lower()
        for row in self.rows:
            if row and str(row[0]).lower() == label_lower:
                if 0 <= year_column < len(row):
                    return row[year_column]
        return None


class Item21FinancialsResponse(TableBasedItem):
    """LLM extraction response for Item 21 - Financial Statements."""
    
    # Extracted financial data
    financials_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted financial data by year"
    )
    
    # Audit information
    audit_opinions: Dict[int, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Audit opinions by fiscal year"
    )
    
    # Key metrics and ratios
    key_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key financial metrics and ratios"
    )
    
    # Narrative information
    going_concern_issues: Optional[str] = Field(
        None,
        description="Any going concern issues mentioned"
    )
    
    material_changes: Optional[str] = Field(
        None,
        description="Material changes in financial condition"
    )
    
    significant_events: List[str] = Field(
        default_factory=list,
        description="Significant events affecting financials"
    )
    
    def to_storage_model(self) -> List[BaseItemModel]:
        """Convert response to storage models."""
        models = []
        
        # Convert financial data by year
        for financial_data in self.financials_data:
            fiscal_year = financial_data.get("fiscal_year")
            if not fiscal_year:
                continue
                
            # Create Financials model
            financials = Financials(
                fiscal_year=fiscal_year,
                fiscal_year_end=financial_data.get("fiscal_year_end"),
                period_months=financial_data.get("period_months", 12),
                
                # Income statement
                total_revenue_cents=self._parse_amount(financial_data.get("total_revenue")),
                franchise_revenue_cents=self._parse_amount(financial_data.get("franchise_revenue")),
                royalty_revenue_cents=self._parse_amount(financial_data.get("royalty_revenue")),
                advertising_revenue_cents=self._parse_amount(financial_data.get("advertising_revenue")),
                product_revenue_cents=self._parse_amount(financial_data.get("product_revenue")),
                other_revenue_cents=self._parse_amount(financial_data.get("other_revenue")),
                
                cost_of_goods_cents=self._parse_amount(financial_data.get("cost_of_goods")),
                gross_profit_cents=self._parse_amount(financial_data.get("gross_profit")),
                
                operating_expenses_cents=self._parse_amount(financial_data.get("operating_expenses")),
                general_admin_expenses_cents=self._parse_amount(financial_data.get("general_admin_expenses")),
                marketing_expenses_cents=self._parse_amount(financial_data.get("marketing_expenses")),
                depreciation_amortization_cents=self._parse_amount(financial_data.get("depreciation_amortization")),
                
                operating_income_cents=self._parse_amount(financial_data.get("operating_income")),
                interest_expense_cents=self._parse_amount(financial_data.get("interest_expense")),
                other_income_expense_cents=self._parse_amount(financial_data.get("other_income_expense")),
                pretax_income_cents=self._parse_amount(financial_data.get("pretax_income")),
                income_tax_cents=self._parse_amount(financial_data.get("income_tax")),
                net_income_cents=self._parse_amount(financial_data.get("net_income")),
                
                # Balance sheet
                total_assets_cents=self._parse_amount(financial_data.get("total_assets")),
                current_assets_cents=self._parse_amount(financial_data.get("current_assets")),
                cash_equivalents_cents=self._parse_amount(financial_data.get("cash_equivalents")),
                accounts_receivable_cents=self._parse_amount(financial_data.get("accounts_receivable")),
                inventory_cents=self._parse_amount(financial_data.get("inventory")),
                
                fixed_assets_cents=self._parse_amount(financial_data.get("fixed_assets")),
                intangible_assets_cents=self._parse_amount(financial_data.get("intangible_assets")),
                goodwill_cents=self._parse_amount(financial_data.get("goodwill")),
                
                total_liabilities_cents=self._parse_amount(financial_data.get("total_liabilities")),
                current_liabilities_cents=self._parse_amount(financial_data.get("current_liabilities")),
                accounts_payable_cents=self._parse_amount(financial_data.get("accounts_payable")),
                accrued_expenses_cents=self._parse_amount(financial_data.get("accrued_expenses")),
                deferred_revenue_cents=self._parse_amount(financial_data.get("deferred_revenue")),
                
                long_term_debt_cents=self._parse_amount(financial_data.get("long_term_debt")),
                other_liabilities_cents=self._parse_amount(financial_data.get("other_liabilities")),
                
                total_equity_cents=self._parse_amount(financial_data.get("total_equity")),
                retained_earnings_cents=self._parse_amount(financial_data.get("retained_earnings")),
                
                # Cash flow
                operating_cash_flow_cents=self._parse_amount(financial_data.get("operating_cash_flow")),
                investing_cash_flow_cents=self._parse_amount(financial_data.get("investing_cash_flow")),
                financing_cash_flow_cents=self._parse_amount(financial_data.get("financing_cash_flow")),
                net_cash_flow_cents=self._parse_amount(financial_data.get("net_cash_flow")),
                
                # Supplementary
                number_of_outlets=financial_data.get("number_of_outlets"),
                comparable_store_sales_growth=financial_data.get("comparable_store_sales_growth"),
                ebitda_cents=self._parse_amount(financial_data.get("ebitda")),
                
                # Audit info
                auditor_name=self.audit_opinions.get(fiscal_year, {}).get("auditor_name"),
                audit_opinion=self._parse_audit_opinion(
                    self.audit_opinions.get(fiscal_year, {}).get("opinion")
                ),
                audit_date=self.audit_opinions.get(fiscal_year, {}).get("audit_date"),
                
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text,
                notes=self.notes
            )
            
            # Add material information if this is the most recent year
            if fiscal_year == max(f.get("fiscal_year", 0) for f in self.financials_data):
                if self.going_concern_issues:
                    financials.notes = (financials.notes or "") + f"\nGoing Concern: {self.going_concern_issues}"
                if self.material_changes:
                    financials.notes = (financials.notes or "") + f"\nMaterial Changes: {self.material_changes}"
            
            models.append(financials)
        
        # Convert tables
        for table in self.tables:
            table_model = FinancialTable(
                statement_type=self._determine_statement_type(table),
                statement_name=table.get("name", table.get("table_name", "Unknown")),
                fiscal_year=self._extract_fiscal_year(table),
                headers=table.get("headers", []),
                rows=table.get("rows", []),
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text
            )
            models.append(table_model)
        
        return models
    
    def _parse_amount(self, value: Any) -> Optional[int]:
        """Parse amount to cents, handling various formats."""
        if value is None:
            return None
        
        if isinstance(value, (int, float)):
            return int(value * 100)
        
        if isinstance(value, str):
            # Remove currency symbols and commas
            cleaned = value.replace("$", "").replace(",", "").strip()
            
            # Handle parentheses for negative numbers
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = "-" + cleaned[1:-1]
            
            # Handle units (thousands, millions)
            multiplier = 1
            if "thousand" in value.lower() or "(000)" in value:
                multiplier = 1000
            elif "million" in value.lower() or "(000,000)" in value:
                multiplier = 1000000
            
            try:
                amount = float(cleaned) * multiplier
                return int(amount * 100)  # Convert to cents
            except ValueError:
                return None
        
        return None
    
    def _parse_audit_opinion(self, opinion: Any) -> Optional[AuditOpinion]:
        """Parse audit opinion string to enum."""
        if not opinion:
            return None
        
        opinion_str = str(opinion).lower()
        if "unqualified" in opinion_str or "clean" in opinion_str:
            return AuditOpinion.UNQUALIFIED
        elif "qualified" in opinion_str:
            return AuditOpinion.QUALIFIED
        elif "adverse" in opinion_str:
            return AuditOpinion.ADVERSE
        elif "disclaimer" in opinion_str:
            return AuditOpinion.DISCLAIMER
        elif "not audited" in opinion_str or "unaudited" in opinion_str:
            return AuditOpinion.NOT_AUDITED
        
        return None
    
    def _determine_statement_type(self, table: Dict[str, Any]) -> StatementType:
        """Determine financial statement type from table content."""
        name = table.get("name", table.get("table_name", "")).lower()
        headers_str = " ".join(str(h).lower() for h in table.get("headers", []))
        
        if any(term in name or term in headers_str for term in ["balance sheet", "assets", "liabilities"]):
            return StatementType.BALANCE_SHEET
        elif any(term in name or term in headers_str for term in ["income", "revenue", "profit loss", "p&l"]):
            return StatementType.INCOME_STATEMENT
        elif any(term in name or term in headers_str for term in ["cash flow", "cash flows"]):
            return StatementType.CASH_FLOW
        elif any(term in name or term in headers_str for term in ["equity", "shareholders", "stockholders"]):
            return StatementType.EQUITY_STATEMENT
        else:
            return StatementType.NOTES
    
    def _extract_fiscal_year(self, table: Dict[str, Any]) -> Optional[int]:
        """Extract fiscal year from table headers or name."""
        import re
        
        # Check table name
        name = table.get("name", table.get("table_name", ""))
        year_match = re.search(r"20\d{2}|19\d{2}", name)
        if year_match:
            return int(year_match.group())
        
        # Check headers
        for header in table.get("headers", []):
            year_match = re.search(r"20\d{2}|19\d{2}", str(header))
            if year_match:
                return int(year_match.group())
        
        return None
    
    def validate_extraction(self) -> List[str]:
        """Validate extracted financial data."""
        issues = super().validate_extraction()
        
        # Check for required financial data
        if not self.financials_data:
            issues.append("No financial data extracted")
        
        # Validate each year's data
        for i, financial_data in enumerate(self.financials_data):
            year = financial_data.get("fiscal_year")
            if not year:
                issues.append(f"Financial data {i} missing fiscal year")
                continue
            
            # Check for basic required fields
            if not financial_data.get("total_revenue") and not financial_data.get("total_assets"):
                issues.append(f"Year {year}: No revenue or assets data found")
            
            # Validate accounting equations if data is present
            try:
                # Create temporary model to trigger validation
                temp_financials = Financials(
                    fiscal_year=year,
                    total_revenue_cents=self._parse_amount(financial_data.get("total_revenue")),
                    cost_of_goods_cents=self._parse_amount(financial_data.get("cost_of_goods")),
                    gross_profit_cents=self._parse_amount(financial_data.get("gross_profit")),
                    total_assets_cents=self._parse_amount(financial_data.get("total_assets")),
                    total_liabilities_cents=self._parse_amount(financial_data.get("total_liabilities")),
                    total_equity_cents=self._parse_amount(financial_data.get("total_equity"))
                )
            except ValueError as e:
                issues.append(f"Year {year}: {str(e)}")
        
        # Check for concerning patterns
        if self.going_concern_issues:
            issues.append("Going concern issues identified - requires review")
        
        # Validate tables
        table_issues = self.validate_tables()
        issues.extend(table_issues)
        
        return issues
    
    def calculate_financial_health_score(self) -> Dict[str, Any]:
        """Calculate financial health metrics."""
        if not self.financials_data:
            return {"error": "No financial data available"}
        
        # Get most recent year
        recent_data = max(self.financials_data, key=lambda x: x.get("fiscal_year", 0))
        
        metrics = {
            "fiscal_year": recent_data.get("fiscal_year"),
            "health_indicators": []
        }
        
        # Revenue growth (if multiple years available)
        if len(self.financials_data) >= 2:
            sorted_data = sorted(self.financials_data, key=lambda x: x.get("fiscal_year", 0))
            prev_revenue = self._parse_amount(sorted_data[-2].get("total_revenue"))
            curr_revenue = self._parse_amount(sorted_data[-1].get("total_revenue"))
            
            if prev_revenue and curr_revenue and prev_revenue > 0:
                growth = ((curr_revenue - prev_revenue) / prev_revenue) * 100
                metrics["revenue_growth"] = round(growth, 2)
                
                if growth > 10:
                    metrics["health_indicators"].append("Strong revenue growth")
                elif growth < -10:
                    metrics["health_indicators"].append("Declining revenue")
        
        # Profitability
        net_income = self._parse_amount(recent_data.get("net_income"))
        total_revenue = self._parse_amount(recent_data.get("total_revenue"))
        
        if net_income and total_revenue and total_revenue > 0:
            net_margin = (net_income / total_revenue) * 100
            metrics["net_margin"] = round(net_margin, 2)
            
            if net_margin > 10:
                metrics["health_indicators"].append("Strong profitability")
            elif net_margin < 0:
                metrics["health_indicators"].append("Operating at a loss")
        
        # Liquidity
        current_assets = self._parse_amount(recent_data.get("current_assets"))
        current_liabilities = self._parse_amount(recent_data.get("current_liabilities"))
        
        if current_assets and current_liabilities and current_liabilities > 0:
            current_ratio = current_assets / current_liabilities
            metrics["current_ratio"] = round(current_ratio, 2)
            
            if current_ratio > 2:
                metrics["health_indicators"].append("Strong liquidity")
            elif current_ratio < 1:
                metrics["health_indicators"].append("Potential liquidity concerns")
        
        # Leverage
        total_liabilities = self._parse_amount(recent_data.get("total_liabilities"))
        total_equity = self._parse_amount(recent_data.get("total_equity"))
        
        if total_liabilities and total_equity and total_equity > 0:
            debt_to_equity = total_liabilities / total_equity
            metrics["debt_to_equity"] = round(debt_to_equity, 2)
            
            if debt_to_equity > 2:
                metrics["health_indicators"].append("High leverage")
            elif debt_to_equity < 0.5:
                metrics["health_indicators"].append("Conservative capital structure")
        
        # Overall score (simplified)
        positive_indicators = len([i for i in metrics["health_indicators"] if "Strong" in i or "Conservative" in i])
        negative_indicators = len([i for i in metrics["health_indicators"] if "concern" in i or "loss" in i or "Declining" in i])
        
        if positive_indicators > negative_indicators:
            metrics["overall_health"] = "Good"
        elif negative_indicators > positive_indicators:
            metrics["overall_health"] = "Concerning"
        else:
            metrics["overall_health"] = "Mixed"
        
        return metrics