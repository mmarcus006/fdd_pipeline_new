"""Validation utilities and enhanced functionality.

This module provides additional validation utilities, performance monitoring,
and helper functions for the schema validation system.
"""

import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Type, Callable, Union
from uuid import UUID
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import statistics

from pydantic import BaseModel, ValidationError
from validation.schema_validation import (
    SchemaValidator,
    ValidationResult,
    ValidationReport,
    ValidationSeverity,
    ValidationCategory,
)
from utils.database import DatabaseManager
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationMetrics:
    """Validation performance and quality metrics."""

    total_validations: int = 0
    successful_validations: int = 0
    failed_validations: int = 0
    bypassed_validations: int = 0

    # Performance metrics
    avg_validation_time_ms: float = 0.0
    min_validation_time_ms: float = float("inf")
    max_validation_time_ms: float = 0.0

    # Error analysis
    error_categories: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_fields: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Quality metrics
    success_rate: float = 0.0
    avg_errors_per_validation: float = 0.0

    # Time-based metrics
    validations_per_hour: float = 0.0
    peak_validation_time: Optional[datetime] = None

    def update_from_result(self, result: ValidationResult):
        """Update metrics from a validation result."""
        self.total_validations += 1

        if result.bypass_reason:
            self.bypassed_validations += 1
        elif result.is_valid:
            self.successful_validations += 1
        else:
            self.failed_validations += 1

        # Update timing metrics
        if result.validation_duration_ms:
            self.avg_validation_time_ms = (
                self.avg_validation_time_ms * (self.total_validations - 1)
                + result.validation_duration_ms
            ) / self.total_validations
            self.min_validation_time_ms = min(
                self.min_validation_time_ms, result.validation_duration_ms
            )
            self.max_validation_time_ms = max(
                self.max_validation_time_ms, result.validation_duration_ms
            )

        # Update error metrics
        for error in result.errors + result.warnings + result.info:
            self.error_categories[error.category.value] += 1
            self.error_fields[error.field_name] += 1

        # Calculate derived metrics
        if self.total_validations > 0:
            self.success_rate = (
                self.successful_validations / self.total_validations
            ) * 100
            total_errors = sum(len(r.errors) for r in [result])
            self.avg_errors_per_validation = total_errors / self.total_validations


class ValidationPerformanceMonitor:
    """Monitors validation performance and provides insights."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.metrics = ValidationMetrics()
        self._validation_times: List[float] = []
        self._hourly_counts: Dict[int, int] = defaultdict(int)
        self._start_time = datetime.utcnow()

    def record_validation(self, result: ValidationResult):
        """Record a validation result for performance monitoring."""
        self.metrics.update_from_result(result)

        if result.validation_duration_ms:
            self._validation_times.append(result.validation_duration_ms)

        # Track hourly validation counts
        hour = result.validated_at.hour
        self._hourly_counts[hour] += 1

        # Update peak time if this is the busiest hour
        current_hour_count = self._hourly_counts[hour]
        if (
            not self.metrics.peak_validation_time
            or current_hour_count
            > self._hourly_counts.get(self.metrics.peak_validation_time.hour, 0)
        ):
            self.metrics.peak_validation_time = result.validated_at

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        runtime_hours = (datetime.utcnow() - self._start_time).total_seconds() / 3600

        summary = {
            "runtime_hours": round(runtime_hours, 2),
            "total_validations": self.metrics.total_validations,
            "success_rate": round(self.metrics.success_rate, 2),
            "avg_validation_time_ms": round(self.metrics.avg_validation_time_ms, 2),
            "validations_per_hour": round(
                self.metrics.total_validations / max(runtime_hours, 0.1), 2
            ),
            "performance_percentiles": self._calculate_percentiles(),
            "top_error_categories": self._get_top_errors("categories"),
            "top_error_fields": self._get_top_errors("fields"),
            "hourly_distribution": dict(self._hourly_counts),
            "peak_hour": (
                self.metrics.peak_validation_time.hour
                if self.metrics.peak_validation_time
                else None
            ),
        }

        return summary

    def _calculate_percentiles(self) -> Dict[str, float]:
        """Calculate validation time percentiles."""
        if not self._validation_times:
            return {}

        return {
            "p50": round(statistics.median(self._validation_times), 2),
            "p90": (
                round(statistics.quantiles(self._validation_times, n=10)[8], 2)
                if len(self._validation_times) >= 10
                else 0
            ),
            "p95": (
                round(statistics.quantiles(self._validation_times, n=20)[18], 2)
                if len(self._validation_times) >= 20
                else 0
            ),
            "p99": (
                round(statistics.quantiles(self._validation_times, n=100)[98], 2)
                if len(self._validation_times) >= 100
                else 0
            ),
        }

    def _get_top_errors(self, error_type: str) -> List[Dict[str, Any]]:
        """Get top validation errors by category or field."""
        if error_type == "categories":
            counter = Counter(self.metrics.error_categories)
        else:
            counter = Counter(self.metrics.error_fields)

        return [
            {
                "name": name,
                "count": count,
                "percentage": round(
                    (count / max(self.metrics.total_validations, 1)) * 100, 2
                ),
            }
            for name, count in counter.most_common(10)
        ]

    async def generate_performance_report(self) -> Dict[str, Any]:
        """Generate detailed performance report with database insights."""
        summary = self.get_performance_summary()

        # Add database-based insights
        try:
            # Get validation trends over time
            trends_query = """
            SELECT 
                DATE_TRUNC('hour', validated_at) as hour,
                COUNT(*) as total_validations,
                COUNT(*) FILTER (WHERE is_valid = true) as successful_validations,
                AVG(validation_duration_ms) as avg_duration
            FROM validation_results 
            WHERE validated_at >= NOW() - INTERVAL '24 hours'
            GROUP BY hour 
            ORDER BY hour
            """

            trends = await self.db.fetch_all(trends_query)
            summary["hourly_trends"] = [
                {
                    "hour": row["hour"].isoformat(),
                    "total": row["total_validations"],
                    "successful": row["successful_validations"],
                    "success_rate": round(
                        (row["successful_validations"] / row["total_validations"])
                        * 100,
                        2,
                    ),
                    "avg_duration_ms": round(float(row["avg_duration"] or 0), 2),
                }
                for row in trends
            ]

            # Get most common validation errors
            errors_query = """
            SELECT 
                category,
                field_name,
                error_message,
                COUNT(*) as frequency
            FROM validation_errors 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY category, field_name, error_message
            ORDER BY frequency DESC
            LIMIT 20
            """

            common_errors = await self.db.fetch_all(errors_query)
            summary["common_errors"] = [
                {
                    "category": row["category"],
                    "field": row["field_name"],
                    "message": row["error_message"],
                    "frequency": row["frequency"],
                }
                for row in common_errors
            ]

        except Exception as e:
            logger.error(f"Error generating database insights: {e}")
            summary["database_insights_error"] = str(e)

        return summary


class ValidationQualityAnalyzer:
    """Analyzes validation quality and provides improvement recommendations."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def analyze_validation_quality(self, days: int = 7) -> Dict[str, Any]:
        """Analyze validation quality over specified time period."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get validation statistics
        stats_query = """
        SELECT 
            entity_type,
            COUNT(*) as total_validations,
            COUNT(*) FILTER (WHERE is_valid = true) as successful_validations,
            COUNT(*) FILTER (WHERE bypass_reason IS NOT NULL) as bypassed_validations,
            AVG(error_count) as avg_errors,
            AVG(warning_count) as avg_warnings,
            AVG(validation_duration_ms) as avg_duration
        FROM validation_results 
        WHERE validated_at >= $1
        GROUP BY entity_type
        ORDER BY total_validations DESC
        """

        stats = await self.db.fetch_all(stats_query, cutoff_date)

        # Analyze error patterns
        error_patterns_query = """
        SELECT 
            ve.category,
            ve.field_name,
            vr.entity_type,
            COUNT(*) as frequency,
            COUNT(DISTINCT vr.entity_id) as affected_entities
        FROM validation_errors ve
        JOIN validation_results vr ON ve.entity_id = vr.entity_id
        WHERE ve.created_at >= $1
        GROUP BY ve.category, ve.field_name, vr.entity_type
        ORDER BY frequency DESC
        LIMIT 50
        """

        error_patterns = await self.db.fetch_all(error_patterns_query, cutoff_date)

        # Calculate quality scores
        quality_analysis = {
            "analysis_period_days": days,
            "entity_quality_scores": [],
            "overall_quality_score": 0.0,
            "error_patterns": [],
            "recommendations": [],
        }

        total_validations = 0
        total_successful = 0

        for stat in stats:
            entity_score = self._calculate_entity_quality_score(stat)
            quality_analysis["entity_quality_scores"].append(
                {
                    "entity_type": stat["entity_type"],
                    "quality_score": entity_score,
                    "total_validations": stat["total_validations"],
                    "success_rate": round(
                        (stat["successful_validations"] / stat["total_validations"])
                        * 100,
                        2,
                    ),
                    "bypass_rate": round(
                        (stat["bypassed_validations"] / stat["total_validations"])
                        * 100,
                        2,
                    ),
                    "avg_errors": round(float(stat["avg_errors"] or 0), 2),
                    "avg_warnings": round(float(stat["avg_warnings"] or 0), 2),
                    "avg_duration_ms": round(float(stat["avg_duration"] or 0), 2),
                }
            )

            total_validations += stat["total_validations"]
            total_successful += stat["successful_validations"]

        # Calculate overall quality score
        if total_validations > 0:
            quality_analysis["overall_quality_score"] = round(
                (total_successful / total_validations) * 100, 2
            )

        # Analyze error patterns
        for pattern in error_patterns:
            quality_analysis["error_patterns"].append(
                {
                    "category": pattern["category"],
                    "field_name": pattern["field_name"],
                    "entity_type": pattern["entity_type"],
                    "frequency": pattern["frequency"],
                    "affected_entities": pattern["affected_entities"],
                    "severity": self._classify_error_severity(pattern),
                }
            )

        # Generate recommendations
        quality_analysis["recommendations"] = self._generate_quality_recommendations(
            quality_analysis["entity_quality_scores"],
            quality_analysis["error_patterns"],
        )

        return quality_analysis

    def _calculate_entity_quality_score(self, stats: Dict[str, Any]) -> float:
        """Calculate quality score for an entity type."""
        total = stats["total_validations"]
        successful = stats["successful_validations"]
        bypassed = stats["bypassed_validations"]
        avg_errors = float(stats["avg_errors"] or 0)
        avg_duration = float(stats["avg_duration"] or 0)

        # Base score from success rate
        success_rate = (successful / total) * 100
        base_score = success_rate

        # Penalty for high bypass rate
        bypass_rate = (bypassed / total) * 100
        bypass_penalty = min(bypass_rate * 0.5, 20)  # Max 20 point penalty

        # Penalty for high error rate
        error_penalty = min(avg_errors * 5, 30)  # Max 30 point penalty

        # Penalty for slow validation
        duration_penalty = 0
        if avg_duration > 1000:  # > 1 second
            duration_penalty = min(
                (avg_duration - 1000) / 100, 10
            )  # Max 10 point penalty

        final_score = max(
            0, base_score - bypass_penalty - error_penalty - duration_penalty
        )
        return round(final_score, 2)

    def _classify_error_severity(self, pattern: Dict[str, Any]) -> str:
        """Classify error pattern severity."""
        frequency = pattern["frequency"]
        affected_entities = pattern["affected_entities"]

        if frequency > 100 or affected_entities > 50:
            return "HIGH"
        elif frequency > 20 or affected_entities > 10:
            return "MEDIUM"
        else:
            return "LOW"

    def _generate_quality_recommendations(
        self, entity_scores: List[Dict[str, Any]], error_patterns: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """Generate quality improvement recommendations."""
        recommendations = []

        # Recommendations based on entity scores
        low_quality_entities = [e for e in entity_scores if e["quality_score"] < 80]
        for entity in low_quality_entities:
            if entity["bypass_rate"] > 10:
                recommendations.append(
                    {
                        "type": "HIGH_BYPASS_RATE",
                        "entity_type": entity["entity_type"],
                        "description": f"High bypass rate ({entity['bypass_rate']:.1f}%) for {entity['entity_type']}. Consider reviewing validation rules.",
                        "priority": "HIGH" if entity["bypass_rate"] > 20 else "MEDIUM",
                    }
                )

            if entity["avg_errors"] > 2:
                recommendations.append(
                    {
                        "type": "HIGH_ERROR_RATE",
                        "entity_type": entity["entity_type"],
                        "description": f"High average error count ({entity['avg_errors']:.1f}) for {entity['entity_type']}. Review data quality or validation rules.",
                        "priority": "HIGH",
                    }
                )

        # Recommendations based on error patterns
        high_frequency_errors = [e for e in error_patterns if e["severity"] == "HIGH"]
        for error in high_frequency_errors[:5]:  # Top 5 high-frequency errors
            recommendations.append(
                {
                    "type": "FREQUENT_ERROR",
                    "field": error["field_name"],
                    "description": f"Frequent validation error in {error['field_name']} ({error['frequency']} occurrences). Consider improving data extraction or validation logic.",
                    "priority": "HIGH",
                }
            )

        return recommendations


class ValidationRuleOptimizer:
    """Optimizes validation rules based on historical data."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def suggest_rule_optimizations(self) -> Dict[str, Any]:
        """Suggest optimizations for validation rules."""
        # Analyze validation performance
        performance_query = """
        SELECT 
            entity_type,
            AVG(validation_duration_ms) as avg_duration,
            COUNT(*) as total_validations,
            COUNT(*) FILTER (WHERE validation_duration_ms > 1000) as slow_validations
        FROM validation_results 
        WHERE validated_at >= NOW() - INTERVAL '30 days'
        GROUP BY entity_type
        HAVING COUNT(*) > 10
        ORDER BY avg_duration DESC
        """

        performance_data = await self.db.fetch_all(performance_query)

        # Analyze false positive rates
        false_positive_query = """
        SELECT 
            ve.field_name,
            ve.category,
            COUNT(*) as error_count,
            COUNT(DISTINCT vb.entity_id) as bypassed_count
        FROM validation_errors ve
        LEFT JOIN validation_bypasses vb ON ve.entity_id = vb.entity_id
        WHERE ve.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY ve.field_name, ve.category
        HAVING COUNT(*) > 5
        ORDER BY (COUNT(DISTINCT vb.entity_id)::float / COUNT(*)) DESC
        """

        false_positive_data = await self.db.fetch_all(false_positive_query)

        optimizations = {
            "performance_optimizations": [],
            "rule_adjustments": [],
            "threshold_recommendations": [],
        }

        # Performance optimizations
        for perf in performance_data:
            if perf["avg_duration"] > 500:  # > 500ms
                slow_rate = (perf["slow_validations"] / perf["total_validations"]) * 100
                optimizations["performance_optimizations"].append(
                    {
                        "entity_type": perf["entity_type"],
                        "avg_duration_ms": round(float(perf["avg_duration"]), 2),
                        "slow_validation_rate": round(slow_rate, 2),
                        "recommendation": "Consider optimizing validation logic or caching validation results",
                    }
                )

        # Rule adjustments for high false positive rates
        for fp in false_positive_data:
            bypass_rate = (fp["bypassed_count"] / fp["error_count"]) * 100
            if bypass_rate > 30:  # High bypass rate indicates potential false positives
                optimizations["rule_adjustments"].append(
                    {
                        "field_name": fp["field_name"],
                        "category": fp["category"],
                        "bypass_rate": round(bypass_rate, 2),
                        "recommendation": "Consider relaxing validation rule or changing severity level",
                    }
                )

        return optimizations


# Convenience functions for validation utilities
async def get_validation_health_check(db_manager: DatabaseManager) -> Dict[str, Any]:
    """Get overall validation system health check."""
    monitor = ValidationPerformanceMonitor(db_manager)
    analyzer = ValidationQualityAnalyzer(db_manager)

    # Get recent validation stats
    recent_query = """
    SELECT 
        COUNT(*) as total_recent,
        COUNT(*) FILTER (WHERE is_valid = true) as successful_recent,
        AVG(validation_duration_ms) as avg_duration_recent
    FROM validation_results 
    WHERE validated_at >= NOW() - INTERVAL '1 hour'
    """

    recent_stats = await db_manager.fetch_one(recent_query)

    # Get quality analysis
    quality_analysis = await analyzer.analyze_validation_quality(days=1)

    health_check = {
        "status": "HEALTHY",
        "timestamp": datetime.utcnow().isoformat(),
        "recent_activity": {
            "total_validations_last_hour": (
                recent_stats["total_recent"] if recent_stats else 0
            ),
            "success_rate_last_hour": (
                round(
                    (
                        recent_stats["successful_recent"]
                        / max(recent_stats["total_recent"], 1)
                    )
                    * 100,
                    2,
                )
                if recent_stats and recent_stats["total_recent"] > 0
                else 0
            ),
            "avg_duration_ms": (
                round(float(recent_stats["avg_duration_recent"] or 0), 2)
                if recent_stats
                else 0
            ),
        },
        "overall_quality_score": quality_analysis["overall_quality_score"],
        "high_priority_issues": len(
            [
                r
                for r in quality_analysis["recommendations"]
                if r.get("priority") == "HIGH"
            ]
        ),
    }

    # Determine overall health status
    if health_check["overall_quality_score"] < 70:
        health_check["status"] = "DEGRADED"
    elif health_check["high_priority_issues"] > 5:
        health_check["status"] = "WARNING"

    return health_check


@asynccontextmanager
async def validation_batch_processor(
    db_manager: DatabaseManager, batch_size: int = 100, max_concurrent: int = 10
):
    """Context manager for efficient batch validation processing."""
    validator = SchemaValidator(db_manager)
    monitor = ValidationPerformanceMonitor(db_manager)

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_batch(batch_items):
        """Process a batch of validation items."""
        async with semaphore:
            results = []
            for item in batch_items:
                try:
                    result = await validator.validate_model(
                        item["data"], item["model_class"], item.get("entity_id")
                    )
                    monitor.record_validation(result)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Batch validation error: {e}")
            return results

    try:
        yield process_batch
    finally:
        # Log final performance summary
        summary = monitor.get_performance_summary()
        logger.info("Batch validation completed", extra=summary)
