"""Monitoring and error tracking for LLM extraction performance."""

import time
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from pathlib import Path
import asyncio
from uuid import UUID

from utils.logging import PipelineLogger
from config import get_logs_dir


@dataclass
class ExtractionMetrics:
    """Metrics for a single extraction operation."""

    section_item: int
    fdd_id: str
    model_used: str
    status: str  # success, failed, skipped
    start_time: float
    end_time: float
    duration_seconds: float
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    confidence_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["timestamp"] = datetime.fromtimestamp(self.start_time).isoformat()
        return data


@dataclass
class ModelPerformance:
    """Performance statistics for a specific model."""

    model_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_seconds: float = 0.0
    total_tokens_used: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def average_duration(self) -> float:
        """Calculate average request duration."""
        if self.total_requests == 0:
            return 0.0
        return self.total_duration_seconds / self.total_requests

    @property
    def average_tokens_per_request(self) -> float:
        """Calculate average tokens per request."""
        if self.successful_requests == 0:
            return 0.0
        return self.total_tokens_used / self.successful_requests


class ExtractionMonitor:
    """Monitor and track LLM extraction performance."""

    def __init__(self, log_dir: Optional[Path] = None):
        """Initialize the extraction monitor.

        Args:
            log_dir: Directory for storing metrics logs
        """
        self.logger = PipelineLogger("extraction_monitor")
        self.log_dir = log_dir or get_logs_dir()
        self.metrics_file = self.log_dir / "extraction_metrics.jsonl"

        # In-memory metrics
        self.current_session_metrics: List[ExtractionMetrics] = []
        self.model_performance: Dict[str, ModelPerformance] = defaultdict(
            lambda: ModelPerformance(model_name="unknown")
        )
        self.section_performance: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {"success": 0, "failed": 0, "skipped": 0}
        )

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_extraction(self, section_item: int, fdd_id: str, model: str) -> float:
        """Record the start of an extraction.

        Args:
            section_item: FDD section item number
            fdd_id: FDD document ID
            model: Model being used

        Returns:
            Start timestamp
        """
        start_time = time.time()
        self.logger.info(
            "Starting extraction", section_item=section_item, fdd_id=fdd_id, model=model
        )
        return start_time

    def record_extraction(
        self,
        section_item: int,
        fdd_id: str,
        model_used: str,
        status: str,
        start_time: float,
        end_time: Optional[float] = None,
        tokens_used: Optional[int] = None,
        error_message: Optional[str] = None,
        retry_count: int = 0,
        confidence_score: Optional[float] = None,
    ) -> ExtractionMetrics:
        """Record extraction metrics.

        Args:
            section_item: FDD section item number
            fdd_id: FDD document ID
            model_used: Model that was used
            status: Extraction status (success, failed, skipped)
            start_time: Start timestamp
            end_time: End timestamp (defaults to current time)
            tokens_used: Number of tokens consumed
            error_message: Error message if failed
            retry_count: Number of retries
            confidence_score: Confidence in extraction

        Returns:
            ExtractionMetrics object
        """
        if end_time is None:
            end_time = time.time()

        duration = end_time - start_time

        metrics = ExtractionMetrics(
            section_item=section_item,
            fdd_id=str(fdd_id),
            model_used=model_used,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            tokens_used=tokens_used,
            error_message=error_message,
            retry_count=retry_count,
            confidence_score=confidence_score,
        )

        # Update in-memory tracking
        self.current_session_metrics.append(metrics)
        self._update_model_performance(metrics)
        self._update_section_performance(metrics)

        # Log to file
        self._log_metrics_to_file(metrics)

        # Log summary
        self.logger.info(
            "Extraction completed",
            section_item=section_item,
            model=model_used,
            status=status,
            duration=f"{duration:.2f}s",
            tokens=tokens_used,
        )

        return metrics

    def _update_model_performance(self, metrics: ExtractionMetrics):
        """Update model performance statistics."""
        perf = self.model_performance[metrics.model_used]
        perf.model_name = metrics.model_used
        perf.total_requests += 1
        perf.total_duration_seconds += metrics.duration_seconds

        if metrics.status == "success":
            perf.successful_requests += 1
            if metrics.tokens_used:
                perf.total_tokens_used += metrics.tokens_used
        elif metrics.status == "failed":
            perf.failed_requests += 1
            if metrics.error_message:
                perf.errors.append(metrics.error_message)

    def _update_section_performance(self, metrics: ExtractionMetrics):
        """Update section-specific performance statistics."""
        self.section_performance[metrics.section_item][metrics.status] += 1

    def _log_metrics_to_file(self, metrics: ExtractionMetrics):
        """Append metrics to JSONL file."""
        try:
            with open(self.metrics_file, "a") as f:
                json.dump(metrics.to_dict(), f)
                f.write("\n")
        except Exception as e:
            self.logger.error(f"Failed to write metrics to file: {e}")

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of current session performance."""
        if not self.current_session_metrics:
            return {"message": "No extractions recorded in this session"}

        total_extractions = len(self.current_session_metrics)
        successful = sum(
            1 for m in self.current_session_metrics if m.status == "success"
        )
        failed = sum(1 for m in self.current_session_metrics if m.status == "failed")
        skipped = sum(1 for m in self.current_session_metrics if m.status == "skipped")

        total_duration = sum(m.duration_seconds for m in self.current_session_metrics)
        avg_duration = (
            total_duration / total_extractions if total_extractions > 0 else 0
        )

        # Model usage breakdown
        model_usage = defaultdict(int)
        for m in self.current_session_metrics:
            model_usage[m.model_used] += 1

        return {
            "session_metrics": {
                "total_extractions": total_extractions,
                "successful": successful,
                "failed": failed,
                "skipped": skipped,
                "success_rate": (
                    successful / total_extractions if total_extractions > 0 else 0
                ),
                "total_duration_seconds": total_duration,
                "average_duration_seconds": avg_duration,
                "model_usage": dict(model_usage),
            },
            "model_performance": {
                model: {
                    "total_requests": perf.total_requests,
                    "success_rate": perf.success_rate,
                    "average_duration": perf.average_duration,
                    "average_tokens": perf.average_tokens_per_request,
                }
                for model, perf in self.model_performance.items()
            },
            "section_performance": dict(self.section_performance),
        }

    def log_session_summary(self):
        """Log a summary of the session performance."""
        summary = self.get_session_summary()
        self.logger.info("Session extraction summary", **summary)

        # Also write to a summary file
        summary_file = (
            self.log_dir
            / f"extraction_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        try:
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to write summary file: {e}")

    def get_error_analysis(self) -> Dict[str, Any]:
        """Analyze errors from failed extractions."""
        errors_by_model = defaultdict(list)
        errors_by_section = defaultdict(list)

        for metrics in self.current_session_metrics:
            if metrics.status == "failed" and metrics.error_message:
                errors_by_model[metrics.model_used].append(metrics.error_message)
                errors_by_section[metrics.section_item].append(metrics.error_message)

        # Find most common errors
        all_errors = []
        for errors in errors_by_model.values():
            all_errors.extend(errors)

        error_counts = defaultdict(int)
        for error in all_errors:
            # Normalize errors for counting
            normalized = error.lower().strip()
            error_counts[normalized] += 1

        most_common_errors = sorted(
            error_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "total_errors": len(all_errors),
            "errors_by_model": dict(errors_by_model),
            "errors_by_section": dict(errors_by_section),
            "most_common_errors": most_common_errors,
        }


# Global monitor instance
_extraction_monitor: Optional[ExtractionMonitor] = None


def get_extraction_monitor() -> ExtractionMonitor:
    """Get the global extraction monitor instance."""
    global _extraction_monitor
    if _extraction_monitor is None:
        _extraction_monitor = ExtractionMonitor()
    return _extraction_monitor


# Context manager for monitoring extractions
class MonitoredExtraction:
    """Context manager for monitoring an extraction operation."""

    def __init__(
        self,
        section_item: int,
        fdd_id: str,
        model: str,
        monitor: Optional[ExtractionMonitor] = None,
    ):
        self.section_item = section_item
        self.fdd_id = str(fdd_id)
        self.model = model
        self.monitor = monitor or get_extraction_monitor()
        self.start_time = None
        self.status = "failed"
        self.error_message = None
        self.tokens_used = None
        self.retry_count = 0

    def __enter__(self):
        """Start monitoring."""
        self.start_time = self.monitor.start_extraction(
            self.section_item, self.fdd_id, self.model
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Record extraction metrics."""
        if exc_type is None:
            # If no exception, assume success unless explicitly set
            if self.status == "failed":
                self.status = "success"
        else:
            self.status = "failed"
            self.error_message = str(exc_val)

        self.monitor.record_extraction(
            section_item=self.section_item,
            fdd_id=self.fdd_id,
            model_used=self.model,
            status=self.status,
            start_time=self.start_time,
            tokens_used=self.tokens_used,
            error_message=self.error_message,
            retry_count=self.retry_count,
        )

        # Don't suppress exceptions
        return False

    def set_success(self, tokens_used: Optional[int] = None):
        """Mark extraction as successful."""
        self.status = "success"
        self.tokens_used = tokens_used

    def set_failed(self, error_message: str):
        """Mark extraction as failed."""
        self.status = "failed"
        self.error_message = error_message

    def set_skipped(self, reason: str):
        """Mark extraction as skipped."""
        self.status = "skipped"
        self.error_message = reason

    def increment_retry(self):
        """Increment retry counter."""
        self.retry_count += 1
