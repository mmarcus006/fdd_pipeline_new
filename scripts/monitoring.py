#!/usr/bin/env python
"""
FDD Pipeline Monitoring Script

Monitors system health, processing metrics, and alerts on issues.
"""

import asyncio
import json
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

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
        start_time = time.time()
        logger.info("Starting metrics collection")
        logger.debug(f"Collection started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Track timing for each component
        component_times = {}
        
        # Check API health
        t = time.time()
        api_health = await self._check_api_health()
        component_times['api_health'] = time.time() - t
        logger.debug(f"API health check: {api_health} ({component_times['api_health']:.3f}s)")

        # Check database health
        t = time.time()
        database_health = self._check_database_health()
        component_times['database_health'] = time.time() - t
        logger.debug(f"Database health check: {database_health} ({component_times['database_health']:.3f}s)")

        # Check Prefect health
        t = time.time()
        prefect_health = await self._check_prefect_health()
        component_times['prefect_health'] = time.time() - t
        logger.debug(f"Prefect health check: {prefect_health} ({component_times['prefect_health']:.3f}s)")

        # Check Google Drive health
        t = time.time()
        gdrive_health = self._check_gdrive_health()
        component_times['gdrive_health'] = time.time() - t
        logger.debug(f"Google Drive health check: {gdrive_health} ({component_times['gdrive_health']:.3f}s)")

        # Get operational metrics
        logger.debug("Collecting operational metrics...")
        
        t = time.time()
        active_flows = await self._get_active_flows()
        component_times['active_flows'] = time.time() - t
        logger.debug(f"Active flows: {active_flows} ({component_times['active_flows']:.3f}s)")
        
        t = time.time()
        pending_documents = self._get_pending_documents()
        component_times['pending_documents'] = time.time() - t
        logger.debug(f"Pending documents: {pending_documents} ({component_times['pending_documents']:.3f}s)")
        
        t = time.time()
        failed_extractions = self._get_failed_extractions()
        component_times['failed_extractions'] = time.time() - t
        logger.debug(f"Failed extractions (24h): {failed_extractions} ({component_times['failed_extractions']:.3f}s)")
        
        t = time.time()
        processing_rate = self._calculate_processing_rate()
        component_times['processing_rate'] = time.time() - t
        logger.debug(f"Processing rate: {processing_rate:.2f} docs/hr ({component_times['processing_rate']:.3f}s)")
        
        t = time.time()
        error_rate = self._calculate_error_rate()
        component_times['error_rate'] = time.time() - t
        logger.debug(f"Error rate: {error_rate:.2f}% ({component_times['error_rate']:.3f}s)")
        
        t = time.time()
        storage_used_gb = self._get_storage_usage()
        component_times['storage'] = time.time() - t
        logger.debug(f"Storage used: {storage_used_gb:.2f} GB ({component_times['storage']:.3f}s)")

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
        history_size = len(self.metrics_history)
        if history_size > 1440:  # Keep 24 hours at 1-minute intervals
            self.metrics_history.pop(0)
            logger.debug("Pruned oldest metric from history (maintaining 24h window)")
        
        total_time = time.time() - start_time
        logger.info(f"Metrics collection completed in {total_time:.3f}s")
        logger.debug(f"Metrics history size: {history_size}")
        logger.debug(f"Slowest component: {max(component_times.items(), key=lambda x: x[1])}")

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
        logger.debug(f"Checking {len(self.alert_rules)} alert rules")

        for rule in self.alert_rules:
            value = getattr(metrics, rule.metric)
            original_value = value
            
            # Handle string metrics
            if isinstance(value, str):
                if rule.metric.endswith("_health"):
                    value = 0 if value != "healthy" else 1
                    logger.debug(f"Converted {rule.metric} from '{original_value}' to {value}")

            # Check threshold
            triggered = False
            if rule.comparison == "gt" and value > rule.threshold:
                triggered = True
            elif rule.comparison == "lt" and value < rule.threshold:
                triggered = True
            elif rule.comparison == "eq" and value == rule.threshold:
                triggered = True
            
            logger.debug(f"Rule '{rule.name}': {rule.metric}={value} {rule.comparison} {rule.threshold} => {'TRIGGERED' if triggered else 'OK'}")

            if triggered:
                alert_msg = f"[{rule.name}] {rule.message} (current: {original_value})"
                alerts.append(alert_msg)
                logger.warning(f"Alert triggered: {alert_msg}")
        
        logger.debug(f"Total alerts triggered: {len(alerts)}")
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
        logger.debug(f"Alert rules loaded: {len(self.alert_rules)} rules")
        logger.debug(f"Monitoring started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        iteration = 0
        consecutive_errors = 0
        max_consecutive_errors = 5

        while True:
            iteration += 1
            loop_start = time.time()
            
            try:
                logger.debug(f"\n--- Monitoring iteration {iteration} ---")
                
                # Collect metrics
                logger.debug("Collecting metrics...")
                metrics = await self.collect_metrics()
                
                # Check alerts
                logger.debug("Checking alert conditions...")
                alerts = self.check_alerts(metrics)
                
                if alerts:
                    logger.warning(f"Found {len(alerts)} alert(s)")
                    self.send_alerts(alerts)
                else:
                    logger.debug("No alerts triggered")

                # Generate and log report
                report = self.generate_report()
                
                # Log summary
                logger.info(f"Monitoring iteration {iteration} complete")
                logger.info(f"System health: API={metrics.api_health}, DB={metrics.database_health}, Prefect={metrics.prefect_health}")
                logger.info(f"Operations: {metrics.active_flows} active flows, {metrics.pending_documents} pending docs")
                logger.info(f"Performance: {metrics.processing_rate:.1f} docs/hr, {metrics.error_rate:.1f}% errors")
                
                # Reset error counter on success
                consecutive_errors = 0
                
                # Calculate sleep time to maintain interval
                loop_time = time.time() - loop_start
                sleep_time = max(0, interval_seconds - loop_time)
                
                if sleep_time < interval_seconds * 0.9:  # Loop took >10% of interval
                    logger.warning(f"Monitoring loop took {loop_time:.1f}s, may need to increase interval")
                
                logger.debug(f"Sleeping for {sleep_time:.1f}s until next iteration")
                await asyncio.sleep(sleep_time)

            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                logger.debug(f"Stopped after {iteration} iterations")
                break
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Monitoring loop error (attempt {consecutive_errors}): {e}")
                logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors ({consecutive_errors}), stopping monitoring")
                    break
                
                # Exponential backoff on errors
                error_sleep = min(interval_seconds * (2 ** (consecutive_errors - 1)), 300)  # Max 5 min
                logger.debug(f"Waiting {error_sleep}s before retry due to error")
                await asyncio.sleep(error_sleep)
        
        logger.info("Monitoring loop terminated")


async def main():
    """Main entry point for monitoring script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FDD Pipeline Monitoring Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run continuous monitoring (default 60s interval)
  %(prog)s
  
  # Run with custom interval
  %(prog)s --interval 30
  
  # Run once and exit
  %(prog)s --once
  
  # Output as JSON
  %(prog)s --once --json
  
  # Save output to file
  %(prog)s --once --output report.json
  
  # Enable debug logging
  %(prog)s --debug
  
  # Export metrics history
  %(prog)s --export-metrics metrics_history.json
        """
    )
    
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=60,
        help="Monitoring interval in seconds (default: 60)"
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", "-o", help="Save output to file")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--export-metrics", help="Export metrics history to file")
    parser.add_argument(
        "--alert-test", 
        action="store_true", 
        help="Test alert system with dummy alerts"
    )

    args = parser.parse_args()
    
    # Set up logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'monitoring_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        logger.debug("Debug logging enabled")
    elif args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    logger.debug(f"Script started with arguments: {vars(args)}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Python version: {sys.version}")
    
    try:
        logger.info("Initializing monitoring service...")
        monitor = MonitoringService()
        logger.debug(f"Monitoring service initialized with {len(monitor.alert_rules)} alert rules")
        
        if args.alert_test:
            # Test alert system
            logger.info("Testing alert system...")
            test_alerts = [
                "[TEST] API service is not responding",
                "[TEST] Error rate exceeds 5%",
                "[TEST] Database connection failed"
            ]
            monitor.send_alerts(test_alerts)
            print("Alert test completed - check logs for output")
            return
        
        if args.export_metrics:
            # Export metrics history
            if monitor.metrics_history:
                export_data = {
                    "exported_at": datetime.now().isoformat(),
                    "metrics_count": len(monitor.metrics_history),
                    "metrics": [m.dict() for m in monitor.metrics_history]
                }
                with open(args.export_metrics, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
                logger.info(f"Exported {len(monitor.metrics_history)} metrics to {args.export_metrics}")
                print(f"✓ Exported {len(monitor.metrics_history)} metrics to {args.export_metrics}")
            else:
                logger.warning("No metrics history to export")
                print("No metrics history to export")
            return

        if args.once:
            # Run once mode
            logger.info("Running single metrics collection...")
            start_time = time.time()
            
            metrics = await monitor.collect_metrics()
            alerts = monitor.check_alerts(metrics)

            if alerts:
                logger.warning(f"{len(alerts)} alerts triggered")
                monitor.send_alerts(alerts)
                
                if not args.json:
                    print("\n⚠️  ALERTS:")
                    for alert in alerts:
                        print(f"  - {alert}")

            report = monitor.generate_report()
            
            # Add alerts to report
            report['alerts'] = alerts
            
            elapsed = time.time() - start_time
            report['collection_time_seconds'] = round(elapsed, 3)
            
            if args.json or args.output:
                output = json.dumps(report, indent=2)
                if args.output:
                    with open(args.output, 'w') as f:
                        f.write(output)
                    logger.info(f"Report saved to: {args.output}")
                    if not args.json:
                        print(f"\n✓ Report saved to: {args.output}")
                if args.json and not args.output:
                    print(output)
            else:
                # Pretty print report
                print("\nFDD Pipeline Monitoring Report")
                print("=" * 50)
                print(f"Timestamp: {report['timestamp']}")
                print(f"Collection Time: {elapsed:.3f}s")
                
                print("\nSystem Status:")
                for component, status in report['system_status'].items():
                    symbol = "✓" if status == "healthy" else "✗"
                    print(f"  {symbol} {component}: {status}")
                
                print("\nOperational Metrics:")
                for metric, value in report['operational_metrics'].items():
                    print(f"  - {metric}: {value}")
                
                print("\nPerformance Metrics:")
                for metric, value in report['performance_metrics'].items():
                    print(f"  - {metric}: {value:.2f}")
                
                if alerts:
                    print(f"\n⚠️  {len(alerts)} Alert(s) Active")
        else:
            # Continuous monitoring mode
            logger.info("Starting continuous monitoring mode")
            print(f"Starting continuous monitoring (interval: {args.interval}s)")
            print("Press Ctrl+C to stop\n")
            
            await monitor.run_monitoring_loop(args.interval)
            
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user")
        print("\nMonitoring stopped by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
