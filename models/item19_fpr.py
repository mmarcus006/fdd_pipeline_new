"""Item 19 - Financial Performance Representations models using unified architecture."""

from pydantic import Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from datetime import datetime

from .base_items import (
    BaseItemModel, BaseItemResponse, TableBasedItem,
    ValidationStatus, ItemValidator
)
from .base import ValidationConfig


class FPRTable(BaseItemModel):
    """A single table of financial performance data."""
    
    table_name: str = Field(..., description="Name/title of the table")
    table_type: Optional[str] = Field(None, description="Type of data (sales, costs, profits, etc.)")
    
    # Table structure
    headers: List[str] = Field(..., description="Column headers")
    rows: List[List[Union[str, int, float]]] = Field(..., description="Table data rows")
    
    # Metadata
    period_covered: Optional[str] = Field(None, description="Time period covered by data")
    unit_count: Optional[int] = Field(None, description="Number of units included")
    data_basis: Optional[str] = Field(None, description="Basis for data (actual, projected, etc.)")
    
    # Additional context
    footnotes: List[str] = Field(default_factory=list, description="Table footnotes")
    assumptions: List[str] = Field(default_factory=list, description="Key assumptions")
    
    @model_validator(mode="after")
    def validate_table_structure(self):
        """Ensure table rows match header count."""
        if self.headers and self.rows:
            header_count = len(self.headers)
            for i, row in enumerate(self.rows):
                if len(row) != header_count:
                    raise ValueError(
                        f"Row {i} has {len(row)} columns, expected {header_count}"
                    )
        return self
    
    def get_column_data(self, column_name: str) -> List[Any]:
        """Extract data for a specific column."""
        if column_name not in self.headers:
            return []
        
        col_index = self.headers.index(column_name)
        return [row[col_index] for row in self.rows if col_index < len(row)]


class Item19FPR(TableBasedItem):
    """Database storage model for Item 19 FPR data."""
    
    # Store tables as JSONB
    performance_tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Financial performance tables"
    )
    
    # Summary statistics
    average_revenue_cents: Optional[int] = Field(None, ge=0)
    median_revenue_cents: Optional[int] = Field(None, ge=0)
    top_quartile_revenue_cents: Optional[int] = Field(None, ge=0)
    bottom_quartile_revenue_cents: Optional[int] = Field(None, ge=0)
    
    # Data coverage
    reporting_period: Optional[str] = Field(None, description="Period covered by data")
    units_reporting: Optional[int] = Field(None, ge=0, description="Number of units included")
    total_units: Optional[int] = Field(None, ge=0, description="Total units in system")
    
    # Disclaimers and notes
    has_fpr: bool = Field(True, description="Whether Item 19 includes FPR")
    disclaimers: List[str] = Field(default_factory=list)
    substantiation_available: bool = Field(True)
    
    @field_validator("average_revenue_cents", "median_revenue_cents")
    @classmethod
    def validate_revenue_amounts(cls, v):
        """Ensure revenue amounts are reasonable."""
        if v is not None and v > ValidationConfig.MAX_REVENUE_AMOUNT:
            raise ValueError(f"Revenue exceeds reasonable maximum")
        return v
    
    def get_coverage_percentage(self) -> Optional[float]:
        """Calculate percentage of units reporting."""
        if self.units_reporting and self.total_units:
            return (self.units_reporting / self.total_units) * 100
        return None


class Item19FPRResponse(TableBasedItem):
    """LLM extraction response for Item 19 - Financial Performance Representations."""
    
    # Primary question
    has_fpr: bool = Field(..., description="Whether franchisor makes FPR claims")
    
    # If no FPR
    no_fpr_statement: Optional[str] = Field(
        None,
        description="Statement if franchisor doesn't make FPR"
    )
    
    # Performance tables
    performance_tables: List[FPRTable] = Field(
        default_factory=list,
        description="All financial performance tables"
    )
    
    # Common financial metrics (if extractable)
    average_gross_revenue_cents: Optional[int] = Field(None, ge=0)
    median_gross_revenue_cents: Optional[int] = Field(None, ge=0)
    average_net_profit_cents: Optional[int] = Field(None, ge=0)
    median_net_profit_cents: Optional[int] = Field(None, ge=0)
    
    # Percentile data
    top_quartile_revenue_cents: Optional[int] = Field(None, ge=0)
    bottom_quartile_revenue_cents: Optional[int] = Field(None, ge=0)
    
    # Coverage information
    reporting_period: Optional[str] = Field(None)
    units_included: Optional[int] = Field(None, ge=0)
    total_system_units: Optional[int] = Field(None, ge=0)
    geographic_scope: Optional[str] = Field(None)
    
    # Important notes
    key_assumptions: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    disclaimers: List[str] = Field(default_factory=list)
    
    # Substantiation
    substantiation_statement: Optional[str] = Field(None)
    substantiation_available: bool = Field(True)
    
    @model_validator(mode="after")
    def validate_fpr_consistency(self):
        """Ensure FPR data is consistent."""
        if not self.has_fpr:
            # If no FPR, should not have performance data
            if self.performance_tables:
                self.extraction_warnings.append(
                    "Found performance tables but has_fpr is False"
                )
            if any([
                self.average_gross_revenue_cents,
                self.median_gross_revenue_cents,
                self.average_net_profit_cents,
                self.median_net_profit_cents
            ]):
                self.extraction_warnings.append(
                    "Found financial metrics but has_fpr is False"
                )
        else:
            # If has FPR, should have some data
            if not self.performance_tables and not any([
                self.average_gross_revenue_cents,
                self.median_gross_revenue_cents
            ]):
                self.extraction_warnings.append(
                    "has_fpr is True but no performance data found"
                )
        
        return self
    
    def extract_summary_metrics(self) -> Dict[str, Any]:
        """Extract key metrics from tables if not directly provided."""
        metrics = {}
        
        # Try to find revenue/sales tables
        for table in self.performance_tables:
            if any(word in table.table_name.lower() for word in ["revenue", "sales", "gross"]):
                # Look for average/median columns
                for header in table.headers:
                    if "average" in header.lower():
                        data = table.get_column_data(header)
                        if data:
                            metrics["extracted_average"] = data
                    elif "median" in header.lower():
                        data = table.get_column_data(header)
                        if data:
                            metrics["extracted_median"] = data
        
        return metrics
    
    def to_storage_model(self) -> Item19FPR:
        """Convert response to storage model."""
        return Item19FPR(
            has_fpr=self.has_fpr,
            performance_tables=[t.to_database_dict() for t in self.performance_tables],
            average_revenue_cents=self.average_gross_revenue_cents,
            median_revenue_cents=self.median_gross_revenue_cents,
            top_quartile_revenue_cents=self.top_quartile_revenue_cents,
            bottom_quartile_revenue_cents=self.bottom_quartile_revenue_cents,
            reporting_period=self.reporting_period,
            units_reporting=self.units_included,
            total_units=self.total_system_units,
            disclaimers=self.disclaimers,
            substantiation_available=self.substantiation_available,
            notes=self.notes or self.no_fpr_statement,
            extraction_confidence=self.extraction_confidence,
            raw_text=self.raw_text
        )
    
    def validate_extraction(self) -> List[str]:
        """Validate the extracted FPR data."""
        issues = super().validate_extraction()
        
        # Validate table structure
        for i, table in enumerate(self.performance_tables):
            table_issues = self.validate_tables()
            issues.extend([f"Table {i}: {issue}" for issue in table_issues])
        
        # Check data coverage
        if self.units_included and self.total_system_units:
            coverage = (self.units_included / self.total_system_units) * 100
            if coverage < 50:
                issues.append(
                    f"Low data coverage: only {coverage:.1f}% of units included"
                )
        
        # Validate financial metrics
        if self.average_gross_revenue_cents:
            revenue_issue = ItemValidator.validate_currency_amount(
                self.average_gross_revenue_cents,
                "Average gross revenue",
                max_value=ValidationConfig.MAX_REVENUE_AMOUNT
            )
            if revenue_issue:
                issues.append(revenue_issue)
        
        # Check for required disclaimers
        if self.has_fpr and not self.disclaimers:
            issues.append("FPR data should include disclaimers")
        
        # Validate quartile consistency
        if all([
            self.bottom_quartile_revenue_cents,
            self.median_gross_revenue_cents,
            self.top_quartile_revenue_cents
        ]):
            if not (
                self.bottom_quartile_revenue_cents <= 
                self.median_gross_revenue_cents <= 
                self.top_quartile_revenue_cents
            ):
                issues.append("Quartile values are not in correct order")
        
        return issues
