"""
FDD Pipeline Monitoring Script

Monitors system health, processing metrics, and alerts on issues.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
from pydantic import BaseModel

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from utils.database import DatabaseManager
from utils.logging import get_logger

logger = get_logger("monitoring")


class SystemMetrics(BaseModel):
    """System health metrics."""

    timestamp: datetime
    api_health: str
    database_health: str
    prefect_health: str
    gdrive_health: str
    active_flows: int
    pending_documents: int
    failed_extractions: int
    processing_rate: float  # docs per hour
    error_rate: float  # percentage
    storage_used_gb: float


class AlertRule(BaseModel):
    """Alert rule configuration."""

    name: str
    metric: str
    threshold: float
    comparison: str  # "gt", "lt", "eq"
    message: str


class MonitoringService:
    """Main monitoring service for FDD Pipeline."""

    def __init__(self):
        self.settings = get_settings()
        self.db = DatabaseManager()
        self.alert_rules = self._load_alert_rules()
        self.metrics_history: List[SystemMetrics] = []

    def _load_alert_rules(self) -> List[AlertRule]:
        """Load alert rules configuration."""
        return [
            AlertRule(
                name="API Down",
                metric="api_health",
                threshold=0,
                comparison="eq",
                message="API service is not responding",
            ),
            AlertRule(
                name="Database Down",
                metric="database_health",
                threshold=0,
                comparison="eq",
                message="Database connection failed",
            ),
            AlertRule(
                name="High Error Rate",
                metric="error_rate",
                threshold=5.0,
                comparison="gt",
                message="Error rate exceeds 5%",
            ),
            AlertRule(
                name="Low Processing Rate",
                metric="processing_rate",
                threshold=1.0,
                comparison="lt",
                message="Processing rate below 1 doc/hour",
            ),
            AlertRule(
                name="Too Many Failed Extractions",
                metric="failed_extractions",
                threshold=10,
                comparison="gt",
                message="More than 10 failed extractions",
            ),
        ]

    async def collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        logger.info("Collecting system metrics")

        # Check API health
        api_health = await self._check_api_health()

        # Check database health
        database_health = self._check_database_health()

        # Check Prefect health
        prefect_health = await self._check_prefect_health()

        # Check Google Drive health
        gdrive_health = self._check_gdrive_health()

        # Get operational metrics
        active_flows = await self._get_active_flows()
        pending_documents = self._get_pending_documents()
        failed_extractions = self._get_failed_extractions()
        processing_rate = self._calculate_processing_rate()
        error_rate = self._calculate_error_rate()
        storage_used_gb = self._get_storage_usage()

        metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            api_health=api_health,
            database_health=database_health,
            prefect_health=prefect_health,
            gdrive_health=gdrive_health,
            active_flows=active_flows,
            pending_documents=pending_documents,
            failed_extractions=failed_extractions,
            processing_rate=processing_rate,
            error_rate=error_rate,
            storage_used_gb=storage_used_gb,
        )

        # Store in history
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > 1440:  # Keep 24 hours at 1-minute intervals
            self.metrics_history.pop(0)

        return metrics

    async def _check_api_health(self) -> str:
        """Check internal API health."""
        try:
            api_url = os.getenv("API_URL", "http://localhost:8000")
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{api_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("status", "unknown")
                elif response.status_code == 503:
                    return "degraded"
                else:
                    return "error"
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return "error"

    def _check_database_health(self) -> str:
        """Check database health."""
        try:
            if self.db.health_check():
                return "healthy"
            else:
                return "error"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return "error"

    async def _check_prefect_health(self) -> str:
        """Check Prefect server health."""
        try:
            prefect_url = os.getenv("PREFECT_API_URL", "http://localhost:4200")
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{prefect_url}/health")
                if response.status_code == 200:
                    return "healthy"
                else:
                    return "error"
        except Exception as e:
            logger.error(f"Prefect health check failed: {e}")
            return "error"

    def _check_gdrive_health(self) -> str:
        """Check Google Drive configuration."""
        try:
            creds_path = os.getenv("GDRIVE_CREDS_JSON", "")
            if os.path.exists(creds_path):
                return "healthy"
            else:
                return "not_configured"
        except Exception:
            return "error"

    async def _get_active_flows(self) -> int:
        """Get count of active Prefect flows."""
        try:
            from prefect import get_client
            from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterState

            async with get_client() as client:
                filter_obj = FlowRunFilter(
                    state=FlowRunFilterState(type=["RUNNING", "PENDING", "SCHEDULED"])
                )

                flow_runs = await client.read_flow_runs(
                    flow_run_filter=filter_obj, limit=100
                )

                return len(flow_runs)
        except Exception as e:
            logger.error(f"Failed to get active flows: {e}")
            return 0

    def _get_pending_documents(self) -> int:
        """Get count of pending documents."""
        try:
            result = (
                self.db.query_builder("fdds")
                .select("count")
                .eq("processing_status", "pending")
                .execute()
            )

            return result.data[0]["count"] if result.data else 0
        except Exception as e:
            logger.error(f"Failed to get pending documents: {e}")
            return 0

    def _get_failed_extractions(self) -> int:
        """Get count of failed extractions in last 24 hours."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)

            result = (
                self.db.query_builder("fdd_sections")
                .select("count")
                .eq("extraction_status", "failed")
                .gte("created_at", cutoff_time.isoformat())
                .execute()
            )

            return result.data[0]["count"] if result.data else 0
        except Exception as e:
            logger.error(f"Failed to get failed extractions: {e}")
            return 0

    def _calculate_processing_rate(self) -> float:
        """Calculate documents processed per hour."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=1)

            result = (
                self.db.query_builder("fdds")
                .select("count")
                .eq("processing_status", "completed")
                .gte("processed_at", cutoff_time.isoformat())
                .execute()
            )

            return float(result.data[0]["count"]) if result.data else 0.0
        except Exception as e:
            logger.error(f"Failed to calculate processing rate: {e}")
            return 0.0

    def _calculate_error_rate(self) -> float:
        """Calculate error rate percentage."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)

            # Get total attempts
            total_result = (
                self.db.query_builder("fdd_sections")
                .select("count")
                .gte("created_at", cutoff_time.isoformat())
                .execute()
            )

            total = total_result.data[0]["count"] if total_result.data else 0

            if total == 0:
                return 0.0

            # Get failed attempts
            failed_result = (
                self.db.query_builder("fdd_sections")
                .select("count")
                .eq("extraction_status", "failed")
                .gte("created_at", cutoff_time.isoformat())
                .execute()
            )

            failed = failed_result.data[0]["count"] if failed_result.data else 0

            return (failed / total) * 100.0
        except Exception as e:
            logger.error(f"Failed to calculate error rate: {e}")
            return 0.0

    def _get_storage_usage(self) -> float:
        """Get storage usage in GB (placeholder - would need actual implementation)."""
        # This would need to query Google Drive API for actual usage
        return 0.0

    def check_alerts(self, metrics: SystemMetrics) -> List[str]:
        """Check if any alerts should be triggered."""
        alerts = []

        for rule in self.alert_rules:
            value = getattr(metrics, rule.metric)

            # Handle string metrics
            if isinstance(value, str):
                if rule.metric.endswith("_health"):
                    value = 0 if value != "healthy" else 1

            # Check threshold
            triggered = False
            if rule.comparison == "gt" and value > rule.threshold:
                triggered = True
            elif rule.comparison == "lt" and value < rule.threshold:
                triggered = True
            elif rule.comparison == "eq" and value == rule.threshold:
                triggered = True

            if triggered:
                alert_msg = f"[{rule.name}] {rule.message} (current: {value})"
                alerts.append(alert_msg)
                logger.warning(alert_msg)

        return alerts

    def send_alerts(self, alerts: List[str]):
        """Send alerts (placeholder - would implement email/Slack/etc)."""
        if not alerts:
            return

        logger.error(f"ALERTS TRIGGERED: {len(alerts)} issues detected")
        for alert in alerts:
            logger.error(f"  - {alert}")

        # TODO: Implement actual alerting (email, Slack, PagerDuty, etc)

    def generate_report(self) -> Dict:
        """Generate monitoring report."""
        if not self.metrics_history:
            return {"error": "No metrics collected"}

        latest = self.metrics_history[-1]

        # Calculate averages over last hour
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_metrics = [m for m in self.metrics_history if m.timestamp >= hour_ago]

        if recent_metrics:
            avg_processing_rate = sum(m.processing_rate for m in recent_metrics) / len(
                recent_metrics
            )
            avg_error_rate = sum(m.error_rate for m in recent_metrics) / len(
                recent_metrics
            )
        else:
            avg_processing_rate = latest.processing_rate
            avg_error_rate = latest.error_rate

        return {
            "timestamp": latest.timestamp.isoformat(),
            "system_status": {
                "api": latest.api_health,
                "database": latest.database_health,
                "prefect": latest.prefect_health,
                "gdrive": latest.gdrive_health,
            },
            "operational_metrics": {
                "active_flows": latest.active_flows,
                "pending_documents": latest.pending_documents,
                "failed_extractions": latest.failed_extractions,
            },
            "performance_metrics": {
                "current_processing_rate": latest.processing_rate,
                "avg_processing_rate_1h": avg_processing_rate,
                "current_error_rate": latest.error_rate,
                "avg_error_rate_1h": avg_error_rate,
            },
            "storage": {"used_gb": latest.storage_used_gb},
        }

    async def run_monitoring_loop(self, interval_seconds: int = 60):
        """Run continuous monitoring loop."""
        logger.info(f"Starting monitoring loop with {interval_seconds}s interval")

        while True:
            try:
                # Collect metrics
                metrics = await self.collect_metrics()

                # Check alerts
                alerts = self.check_alerts(metrics)

                # Send alerts if any
                if alerts:
                    self.send_alerts(alerts)

                # Log current status
                report = self.generate_report()
                logger.info(f"System status: {json.dumps(report, indent=2)}")

                # Wait for next interval
                await asyncio.sleep(interval_seconds)

            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(interval_seconds)


async def main():
    """Main entry point for monitoring script."""
    import argparse

    parser = argparse.ArgumentParser(description="FDD Pipeline Monitoring")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Monitoring interval in seconds (default: 60)",
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")

    args = parser.parse_args()

    monitor = MonitoringService()

    if args.once:
        # Run once
        metrics = await monitor.collect_metrics()
        alerts = monitor.check_alerts(metrics)

        if alerts:
            monitor.send_alerts(alerts)

        report = monitor.generate_report()
        print(json.dumps(report, indent=2))
    else:
        # Run continuous loop
        await monitor.run_monitoring_loop(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
