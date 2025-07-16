"""Item 20 - Outlet Information models."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from enum import Enum


class OutletType(str, Enum):
    FRANCHISED = "Franchised"
    COMPANY_OWNED = "Company-Owned"


class OutletSummaryBase(BaseModel):
    """Base model for outlet summary by year."""

    fiscal_year: int = Field(..., ge=1900, le=2100)
    outlet_type: OutletType

    # Counts
    count_start: int = Field(..., ge=0)
    opened: int = Field(default=0, ge=0)
    closed: int = Field(default=0, ge=0)
    transferred_in: int = Field(default=0, ge=0)
    transferred_out: int = Field(default=0, ge=0)
    count_end: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_outlet_math(self):
        """Ensure outlet counts balance."""
        start = self.count_start
        opened = self.opened
        closed = self.closed
        transferred_in = self.transferred_in
        transferred_out = self.transferred_out
        end = self.count_end

        calculated_end = start + opened - closed + transferred_in - transferred_out

        if calculated_end != end:
            raise ValueError(
                f"Outlet math doesn't balance: "
                f"{start} + {opened} - {closed} + {transferred_in} - {transferred_out} "
                f"= {calculated_end}, but count_end = {end}"
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


class OutletSummary(OutletSummaryBase):
    """Outlet summary with section reference."""

    section_id: UUID

    model_config = {"from_attributes": True}


class StateCountBase(BaseModel):
    """Base model for state-by-state outlet counts."""

    state_code: str = Field(..., pattern="^[A-Z]{2}$")
    franchised_count: int = Field(default=0, ge=0)
    company_owned_count: int = Field(default=0, ge=0)

    @property
    def total_count(self) -> int:
        return self.franchised_count + self.company_owned_count

    @field_validator("state_code")
    @classmethod
    def validate_state_code(cls, v):
        """Ensure valid US state code."""
        valid_states = {
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
            "MP",  # Include territories
        }
        if v not in valid_states:
            raise ValueError(f"Invalid state code: {v}")
        return v


class StateCount(StateCountBase):
    """State count with section reference."""

    section_id: UUID

    model_config = {"from_attributes": True}


class OutletStateSummary(BaseModel):
    """Aggregated outlet information."""

    section_id: UUID
    states: List[StateCount]
    total_franchised: int = 0
    total_company_owned: int = 0

    @model_validator(mode="after")
    def calculate_totals(self):
        """Calculate totals from states."""
        states = self.states
        self.total_franchised = sum(s.franchised_count for s in states)
        self.total_company_owned = sum(s.company_owned_count for s in states)
        return self


def validate_state_total(
    state_counts: List[StateCount], outlet_summaries: List[OutletSummary]
) -> bool:
    """Validate state counts match outlet summary totals."""
    state_total_franchised = sum(s.franchised_count for s in state_counts)
    state_total_company = sum(s.company_owned_count for s in state_counts)

    # Get most recent year from outlet summaries
    if outlet_summaries:
        recent_year = max(o.fiscal_year for o in outlet_summaries)
        year_summaries = [o for o in outlet_summaries if o.fiscal_year == recent_year]

        outlet_franchised = sum(
            o.count_end
            for o in year_summaries
            if o.outlet_type == OutletType.FRANCHISED
        )
        outlet_company = sum(
            o.count_end
            for o in year_summaries
            if o.outlet_type == OutletType.COMPANY_OWNED
        )

        return (
            state_total_franchised == outlet_franchised
            and state_total_company == outlet_company
        )

    return True


def calculate_outlet_growth_rate(summaries: List[OutletSummary]) -> Optional[float]:
    """Calculate year-over-year outlet growth rate."""
    if len(summaries) < 2:
        return None

    # Sort by fiscal year
    sorted_summaries = sorted(summaries, key=lambda x: x.fiscal_year)

    # Get most recent two years
    current_year = sorted_summaries[-1]
    previous_year = sorted_summaries[-2]

    if previous_year.count_end == 0:
        return None

    growth_rate = (
        (current_year.count_end - previous_year.count_end) / previous_year.count_end
    ) * 100
    return round(growth_rate, 2)
