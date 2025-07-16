"""Composite models and views for FDD Pipeline."""

from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

from .franchisor import Franchisor
from .fdd import FDD


class FDDExtractionProgress(BaseModel):
    """View model for extraction progress."""

    fdd_id: UUID
    franchise_id: UUID
    canonical_name: str
    total_sections: int
    extracted_sections: int
    failed_sections: int
    needs_review: int
    success_rate: float

    @property
    def is_complete(self) -> bool:
        return self.extracted_sections == self.total_sections

    @property
    def has_failures(self) -> bool:
        return self.failed_sections > 0


class FranchisorFDDSummary(BaseModel):
    """Summary of FDDs for a franchisor."""

    franchisor: Franchisor
    total_fdds: int
    latest_fdd: Optional[FDD] = None
    states_filed: List[str]
    years_available: List[int]

    @property
    def filing_history_years(self) -> int:
        if self.years_available:
            return max(self.years_available) - min(self.years_available) + 1
        return 0


class SystemHealthSummary(BaseModel):
    """Overall system health metrics."""

    total_franchisors: int
    total_fdds: int
    total_sections: int
    extraction_success_rate: float
    processing_backlog: int
    failed_extractions: int
    needs_manual_review: int

    @property
    def health_score(self) -> float:
        """Calculate overall health score (0-100)."""
        base_score = self.extraction_success_rate

        # Penalize for backlog
        if self.processing_backlog > 100:
            base_score -= min(10, self.processing_backlog / 100)

        # Penalize for failures
        if self.failed_extractions > 50:
            base_score -= min(10, self.failed_extractions / 50)

        return max(0, min(100, base_score))


class ExtractionQualityMetrics(BaseModel):
    """Quality metrics for extraction process."""

    section_id: UUID
    item_no: int
    completeness_score: float  # 0-100
    validation_errors: int
    business_rule_violations: int
    confidence_score: Optional[float] = None  # From LLM
    manual_review_required: bool = False

    @property
    def overall_quality(self) -> str:
        """Categorize overall quality."""
        if self.completeness_score >= 95 and self.validation_errors == 0:
            return "Excellent"
        elif self.completeness_score >= 85 and self.validation_errors <= 2:
            return "Good"
        elif self.completeness_score >= 70:
            return "Fair"
        else:
            return "Poor"
