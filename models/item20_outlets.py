"""Item 20 - Outlet Information models using unified architecture."""

from pydantic import Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum

from .base_items import (
    BaseItemModel,
    BaseItemResponse,
    TableBasedItem,
    ValidationStatus,
    ItemValidator,
)


class OutletType(str, Enum):
    """Types of outlets tracked in FDD."""

    FRANCHISED = "franchised"
    COMPANY_OWNED = "company_owned"


class OutletSummary(BaseItemModel):
    """Database storage model for outlet summary by year."""

    # Core data
    fiscal_year: int = Field(..., ge=1900, le=2100)
    outlet_type: OutletType
    state_code: Optional[str] = Field(None, pattern="^[A-Z]{2}$")

    # Counts
    count_start: int = Field(..., ge=0)
    opened: int = Field(0, ge=0)
    closed: int = Field(0, ge=0)
    transferred_in: int = Field(0, ge=0)
    transferred_out: int = Field(0, ge=0)
    count_end: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_outlet_math(self):
        """Ensure outlet counts balance."""
        calculated_end = (
            self.count_start
            + self.opened
            - self.closed
            + self.transferred_in
            - self.transferred_out
        )

        if calculated_end != self.count_end:
            raise ValueError(
                f"Outlet math doesn't balance: "
                f"{self.count_start} + {self.opened} - {self.closed} "
                f"+ {self.transferred_in} - {self.transferred_out} "
                f"= {calculated_end}, but count_end = {self.count_end}"
            )
        return self

    @field_validator("fiscal_year")
    @classmethod
    def validate_reasonable_year(cls, v):
        """Ensure year is reasonable."""
        current_year = datetime.now().year
        if v > current_year + 1:
            raise ValueError(f"Fiscal year {v} is in the future")
        return v

    @property
    def net_change(self) -> int:
        """Calculate net change in outlets for the year."""
        return self.count_end - self.count_start

    @property
    def growth_rate(self) -> Optional[float]:
        """Calculate growth rate if start count > 0."""
        if self.count_start > 0:
            return round((self.net_change / self.count_start) * 100, 2)
        return None


class StateCount(BaseItemModel):
    """Database storage model for state-by-state outlet counts."""

    state_code: str = Field(..., pattern="^[A-Z]{2}$")
    franchised_count: int = Field(0, ge=0)
    company_owned_count: int = Field(0, ge=0)
    as_of_date: Optional[datetime] = None

    @property
    def total_count(self) -> int:
        """Total outlets in state."""
        return self.franchised_count + self.company_owned_count

    @field_validator("state_code")
    @classmethod
    def validate_state_code(cls, v):
        """Ensure valid US state/territory code."""
        valid_codes = {
            "AL",
            "AK",
            "AZ",
            "AR",
            "CA",
            "CO",
            "CT",
            "DE",
            "FL",
            "GA",
            "HI",
            "ID",
            "IL",
            "IN",
            "IA",
            "KS",
            "KY",
            "LA",
            "ME",
            "MD",
            "MA",
            "MI",
            "MN",
            "MS",
            "MO",
            "MT",
            "NE",
            "NV",
            "NH",
            "NJ",
            "NM",
            "NY",
            "NC",
            "ND",
            "OH",
            "OK",
            "OR",
            "PA",
            "RI",
            "SC",
            "SD",
            "TN",
            "TX",
            "UT",
            "VT",
            "VA",
            "WA",
            "WV",
            "WI",
            "WY",
            "DC",
            "PR",
            "VI",
            "GU",
            "AS",
            "MP",
        }
        if v not in valid_codes:
            raise ValueError(f"Invalid state code: {v}")
        return v


class OutletTable(BaseItemModel):
    """Parsed table data from Item 20."""

    table_name: str = Field(..., description="Name/title of the table")
    table_type: str = Field(
        ..., description="Type of data in table (e.g., 'summary', 'by_state')"
    )
    headers: List[str] = Field(..., description="Column headers")
    rows: List[List[Any]] = Field(..., description="Table data rows")
    fiscal_years: Optional[List[int]] = Field(
        None, description="Years covered in table"
    )

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


class Item20OutletsResponse(TableBasedItem):
    """LLM extraction response for Item 20 - Outlets and Information."""

    # Outlet summaries by year and type
    outlet_summaries: List[Dict[str, Any]] = Field(
        default_factory=list, description="Outlet data by year and type"
    )

    # State-by-state counts
    state_counts: List[Dict[str, Any]] = Field(
        default_factory=list, description="Current outlet counts by state"
    )

    # Company-owned outlet details
    company_owned_details: Optional[str] = Field(
        None, description="Details about company-owned outlets"
    )

    # Franchisee information
    total_franchisees: Optional[int] = Field(None, ge=0)
    multi_unit_operators: Optional[int] = Field(None, ge=0)

    # Projections
    projected_openings: Optional[Dict[str, int]] = Field(
        None, description="Projected new outlet openings by year"
    )

    def to_storage_model(self) -> List[BaseItemModel]:
        """Convert response to multiple storage models."""
        models = []

        # Convert outlet summaries
        for summary_data in self.outlet_summaries:
            summary = OutletSummary(
                fiscal_year=summary_data.get("fiscal_year"),
                outlet_type=OutletType(
                    summary_data.get("outlet_type", "")
                    .lower()
                    .replace("-", "_")
                    .replace(" ", "_")
                ),
                count_start=summary_data.get("count_start", 0),
                opened=summary_data.get("opened", 0),
                closed=summary_data.get("closed", 0),
                transferred_in=summary_data.get("transferred_in", 0),
                transferred_out=summary_data.get("transferred_out", 0),
                count_end=summary_data.get("count_end", 0),
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text,
            )
            models.append(summary)

        # Convert state counts
        for state_data in self.state_counts:
            state = StateCount(
                state_code=state_data.get("state_code"),
                franchised_count=state_data.get("franchised_count", 0),
                company_owned_count=state_data.get("company_owned_count", 0),
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text,
            )
            models.append(state)

        # Convert tables if present
        for table in self.tables:
            table_model = OutletTable(
                table_name=table.get("name", table.get("table_name", "Unknown")),
                table_type=self._determine_table_type(table),
                headers=table.get("headers", []),
                rows=table.get("rows", []),
                extraction_confidence=self.extraction_confidence,
                raw_text=self.raw_text,
            )
            models.append(table_model)

        return models

    def _determine_table_type(self, table: Dict[str, Any]) -> str:
        """Determine the type of table based on headers and content."""
        headers_str = " ".join(str(h).lower() for h in table.get("headers", []))
        name = table.get("name", table.get("table_name", "")).lower()

        if "state" in headers_str or "state" in name:
            return "by_state"
        elif "year" in headers_str or "fiscal" in headers_str:
            return "summary"
        elif "projection" in name or "forecast" in name:
            return "projections"
        else:
            return "other"

    def validate_extraction(self) -> List[str]:
        """Validate the extracted outlet data."""
        issues = super().validate_extraction()

        # Validate outlet summaries
        if self.outlet_summaries:
            years_seen = set()
            for summary in self.outlet_summaries:
                year = summary.get("fiscal_year")
                outlet_type = summary.get("outlet_type")

                if year and outlet_type:
                    key = (year, outlet_type)
                    if key in years_seen:
                        issues.append(
                            f"Duplicate outlet summary for {year} {outlet_type}"
                        )
                    years_seen.add(key)

                # Validate the math
                try:
                    temp_summary = OutletSummary(**summary)
                except ValueError as e:
                    issues.append(str(e))

        # Validate state counts total
        if self.state_counts and self.outlet_summaries:
            state_total_franchised = sum(
                s.get("franchised_count", 0) for s in self.state_counts
            )
            state_total_company = sum(
                s.get("company_owned_count", 0) for s in self.state_counts
            )

            # Get most recent year totals
            recent_year = max(s.get("fiscal_year", 0) for s in self.outlet_summaries)
            recent_summaries = [
                s for s in self.outlet_summaries if s.get("fiscal_year") == recent_year
            ]

            outlet_franchised = sum(
                s.get("count_end", 0)
                for s in recent_summaries
                if "franchised" in s.get("outlet_type", "").lower()
            )
            outlet_company = sum(
                s.get("count_end", 0)
                for s in recent_summaries
                if "company" in s.get("outlet_type", "").lower()
            )

            if state_total_franchised != outlet_franchised:
                issues.append(
                    f"State franchised total ({state_total_franchised}) doesn't match "
                    f"outlet summary total ({outlet_franchised})"
                )
            if state_total_company != outlet_company:
                issues.append(
                    f"State company-owned total ({state_total_company}) doesn't match "
                    f"outlet summary total ({outlet_company})"
                )

        # Validate multi-unit operators
        if (
            self.multi_unit_operators is not None
            and self.total_franchisees is not None
            and self.multi_unit_operators > self.total_franchisees
        ):
            issues.append("Multi-unit operators cannot exceed total franchisees")

        # Check table validation
        table_issues = self.validate_tables()
        issues.extend(table_issues)

        return issues

    @property
    def total_outlets_current(self) -> Optional[int]:
        """Calculate total outlets from most recent data."""
        if self.outlet_summaries:
            recent_year = max(s.get("fiscal_year", 0) for s in self.outlet_summaries)
            recent_summaries = [
                s for s in self.outlet_summaries if s.get("fiscal_year") == recent_year
            ]
            return sum(s.get("count_end", 0) for s in recent_summaries)
        elif self.state_counts:
            return sum(
                s.get("franchised_count", 0) + s.get("company_owned_count", 0)
                for s in self.state_counts
            )
        return None

    def calculate_growth_metrics(self) -> Dict[str, Any]:
        """Calculate various growth metrics from the data."""
        metrics = {}

        if len(self.outlet_summaries) >= 2:
            # Sort by year
            sorted_summaries = sorted(
                self.outlet_summaries, key=lambda x: x.get("fiscal_year", 0)
            )

            # Get franchised outlets over time
            franchised_by_year = {}
            company_by_year = {}

            for summary in sorted_summaries:
                year = summary.get("fiscal_year")
                if "franchised" in summary.get("outlet_type", "").lower():
                    franchised_by_year[year] = summary.get("count_end", 0)
                elif "company" in summary.get("outlet_type", "").lower():
                    company_by_year[year] = summary.get("count_end", 0)

            # Calculate growth rates
            if len(franchised_by_year) >= 2:
                years = sorted(franchised_by_year.keys())
                first_year = years[0]
                last_year = years[-1]

                if franchised_by_year[first_year] > 0:
                    total_growth = (
                        (franchised_by_year[last_year] - franchised_by_year[first_year])
                        / franchised_by_year[first_year]
                    ) * 100

                    metrics["franchised_growth_rate"] = round(total_growth, 2)
                    metrics["franchised_cagr"] = round(
                        (
                            pow(
                                franchised_by_year[last_year]
                                / franchised_by_year[first_year],
                                1 / (last_year - first_year),
                            )
                            - 1
                        )
                        * 100,
                        2,
                    )

        # Geographic concentration
        if self.state_counts:
            total_outlets = sum(
                s.get("franchised_count", 0) + s.get("company_owned_count", 0)
                for s in self.state_counts
            )

            if total_outlets > 0:
                # Top 5 states
                sorted_states = sorted(
                    self.state_counts,
                    key=lambda x: x.get("franchised_count", 0)
                    + x.get("company_owned_count", 0),
                    reverse=True,
                )[:5]

                top_5_total = sum(
                    s.get("franchised_count", 0) + s.get("company_owned_count", 0)
                    for s in sorted_states
                )

                metrics["geographic_concentration"] = round(
                    (top_5_total / total_outlets) * 100, 2
                )
                metrics["states_with_presence"] = len(
                    [
                        s
                        for s in self.state_counts
                        if s.get("franchised_count", 0)
                        + s.get("company_owned_count", 0)
                        > 0
                    ]
                )

        return metrics
