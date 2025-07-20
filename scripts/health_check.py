#!/usr/bin/env python
"""
Health check script for FDD Pipeline components.

Usage:
    python scripts/health_check.py [--json]
"""

import asyncio
import json
import os
import sys
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple

import httpx

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import DatabaseManager, get_supabase_client
from utils.logging import get_logger

logger = get_logger("health_check")


class HealthChecker:
    """Check health of all FDD Pipeline components."""

    def __init__(self):
        self.results = {}

    async def check_api(self) -> Dict[str, Any]:
        """Check API service health."""
        api_url = os.getenv("API_URL", "http://localhost:8000")
        logger.debug(f"Checking API health at: {api_url}")
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                logger.debug("Sending health check request to API...")
                response = await client.get(f"{api_url}/health")
                elapsed = time.time() - start_time
                
                logger.debug(f"API response received in {elapsed:.3f}s, status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"API is healthy, response time: {elapsed:.3f}s")
                    return {"status": "healthy", "details": data, "response_time_ms": int(elapsed * 1000)}
                else:
                    logger.warning(f"API returned unhealthy status: {response.status_code}")
                    return {
                        "status": "unhealthy",
                        "error": f"Status code: {response.status_code}",
                        "response_time_ms": int(elapsed * 1000)
                    }
        except httpx.ConnectError as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to connect to API after {elapsed:.3f}s: {e}")
            return {"status": "error", "error": "Connection refused - is the API running?"}
        except httpx.TimeoutException as e:
            logger.error(f"API health check timed out after 5s")
            return {"status": "error", "error": "Request timed out"}
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Unexpected error checking API after {elapsed:.3f}s: {e}")
            logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def check_prefect(self) -> Dict[str, Any]:
        """Check Prefect server health."""
        prefect_url = os.getenv("PREFECT_API_URL", "http://localhost:4200")
        logger.debug(f"Checking Prefect health at: {prefect_url}")
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                logger.debug("Sending health check request to Prefect...")
                response = await client.get(f"{prefect_url}/health")
                elapsed = time.time() - start_time
                
                logger.debug(f"Prefect response received in {elapsed:.3f}s, status: {response.status_code}")

                if response.status_code == 200:
                    # Get additional info
                    logger.debug("Fetching Prefect version info...")
                    version_response = await client.get(f"{prefect_url}/version")
                    version = (
                        version_response.json()
                        if version_response.status_code == 200
                        else {}
                    )
                    
                    logger.info(f"Prefect is healthy, version: {version.get('version', 'unknown')}")
                    logger.debug(f"Prefect details: {version}")

                    return {
                        "status": "healthy",
                        "details": {"version": version.get("version", "unknown")},
                        "response_time_ms": int(elapsed * 1000)
                    }
                else:
                    logger.warning(f"Prefect returned unhealthy status: {response.status_code}")
                    return {
                        "status": "unhealthy",
                        "error": f"Status code: {response.status_code}",
                        "response_time_ms": int(elapsed * 1000)
                    }
        except httpx.ConnectError as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to connect to Prefect after {elapsed:.3f}s: {e}")
            return {"status": "error", "error": "Connection refused - is Prefect server running?"}
        except httpx.TimeoutException as e:
            logger.error(f"Prefect health check timed out after 5s")
            return {"status": "error", "error": "Request timed out"}
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Unexpected error checking Prefect after {elapsed:.3f}s: {e}")
            logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
            return {"status": "error", "error": str(e)}

    def check_database(self) -> Dict[str, Any]:
        """Check database connectivity."""
        logger.debug("Checking database connectivity...")
        start_time = time.time()
        
        try:
            logger.debug("Initializing DatabaseManager...")
            db = DatabaseManager()
            init_time = time.time() - start_time
            logger.debug(f"DatabaseManager initialized in {init_time:.3f}s")

            logger.debug("Running database health check...")
            health_start = time.time()
            if db.health_check():
                health_time = time.time() - health_start
                logger.debug(f"Health check passed in {health_time:.3f}s")
                
                # Get additional stats
                logger.debug("Fetching database statistics...")
                stats = self._get_database_stats(db)
                
                elapsed = time.time() - start_time
                logger.info(f"Database is healthy, total check time: {elapsed:.3f}s")
                logger.debug(f"Database stats: {stats}")

                return {
                    "status": "healthy", 
                    "details": stats,
                    "response_time_ms": int(elapsed * 1000)
                }
            else:
                elapsed = time.time() - start_time
                logger.error(f"Database health check failed after {elapsed:.3f}s")
                return {"status": "unhealthy", "error": "Health check failed"}
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Database check error after {elapsed:.3f}s: {e}")
            logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
            import traceback
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    def _get_database_stats(self, db: DatabaseManager) -> Dict[str, int]:
        """Get database statistics."""
        stats = {}
        logger.debug("Gathering database statistics...")

        try:
            # Get counts for main tables
            tables = ["franchisors", "fdds", "fdd_sections"]
            
            for table in tables:
                logger.debug(f"Querying count for table: {table}")
                try:
                    start = time.time()
                    result = (
                        db.query_builder(table).select("count", count="exact").execute()
                    )
                    query_time = time.time() - start
                    
                    count = result.count if result else 0
                    stats[f"{table}_count"] = count
                    logger.debug(f"Table {table}: {count} records (query took {query_time:.3f}s)")
                    
                except Exception as e:
                    logger.error(f"Failed to query {table}: {e}")
                    stats[f"{table}_count"] = -1  # Indicate error
                    
            # Get additional metadata tables
            metadata_tables = ["scrape_metadata", "extraction_logs"]
            for table in metadata_tables:
                try:
                    result = db.query_builder(table).select("count", count="exact").execute()
                    count = result.count if result else 0
                    stats[f"{table}_count"] = count
                    logger.debug(f"Metadata table {table}: {count} records")
                except:
                    # These tables might not exist
                    pass

        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")

        return stats

    def check_google_drive(self) -> Dict[str, Any]:
        """Check Google Drive configuration."""
        creds_path = os.getenv("GDRIVE_CREDS_JSON", "")

        if not creds_path:
            return {"status": "not_configured", "error": "GDRIVE_CREDS_JSON not set"}

        if not os.path.exists(creds_path):
            return {
                "status": "error",
                "error": f"Credentials file not found: {creds_path}",
            }

        # TODO: Actually test connection
        return {
            "status": "configured",
            "details": {"credentials_file": os.path.basename(creds_path)},
        }

    def check_llm_apis(self) -> Dict[str, Dict[str, Any]]:
        """Check LLM API configurations."""
        apis = {}

        # Gemini
        if os.getenv("GEMINI_API_KEY"):
            apis["gemini"] = {
                "status": "configured",
                "details": {"key_length": len(os.getenv("GEMINI_API_KEY", ""))},
            }
        else:
            apis["gemini"] = {"status": "not_configured"}

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            apis["openai"] = {
                "status": "configured",
                "details": {"key_length": len(os.getenv("OPENAI_API_KEY", ""))},
            }
        else:
            apis["openai"] = {"status": "not_configured"}

        # Ollama
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        apis["ollama"] = {"status": "configured", "details": {"base_url": ollama_url}}

        return apis

    def check_mineru(self) -> Dict[str, Any]:
        """Check MinerU configuration."""
        mode = os.getenv("MINERU_MODE", "local")

        result = {"mode": mode, "status": "configured"}

        if mode == "local":
            # Check if MinerU is installed
            try:
                import magic_pdf

                result["details"] = {
                    "device": os.getenv("MINERU_DEVICE", "cpu"),
                    "model_path": os.getenv("MINERU_MODEL_PATH", "~/.mineru/models"),
                    "batch_size": os.getenv("MINERU_BATCH_SIZE", "2"),
                }
            except ImportError:
                result["status"] = "not_installed"
                result["error"] = "magic-pdf package not installed"
        else:
            # API mode
            if not os.getenv("MINERU_API_KEY"):
                result["status"] = "not_configured"
                result["error"] = "MINERU_API_KEY not set"
            else:
                result["details"] = {
                    "base_url": os.getenv("MINERU_BASE_URL", "https://api.mineru.ai")
                }

        return result

    def check_file_system(self) -> Dict[str, Any]:
        """Check file system directories."""
        directories = {
            "logs": "logs",
            "models": os.getenv("MINERU_MODEL_PATH", "~/.mineru/models"),
            "temp": "temp",
        }

        results = {}

        for name, path in directories.items():
            full_path = os.path.expanduser(path)

            if os.path.exists(full_path):
                # Get size if directory
                if os.path.isdir(full_path):
                    size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, _, filenames in os.walk(full_path)
                        for filename in filenames
                    ) / (
                        1024 * 1024
                    )  # MB

                    results[name] = {"status": "exists", "size_mb": round(size, 2)}
                else:
                    results[name] = {"status": "exists"}
            else:
                results[name] = {"status": "not_found"}

        return results

    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        overall_start = time.time()
        logger.info("Starting comprehensive health check...")
        logger.debug(f"Running checks at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Run async checks
        logger.debug("Running async checks (API, Prefect)...")
        async_start = time.time()
        api_result, prefect_result = await asyncio.gather(
            self.check_api(), self.check_prefect()
        )
        async_time = time.time() - async_start
        logger.debug(f"Async checks completed in {async_time:.3f}s")

        # Run sync checks
        logger.debug("Running sync checks...")
        sync_start = time.time()
        
        results = {
            "api": api_result,
            "prefect": prefect_result,
            "database": self.check_database(),
            "google_drive": self.check_google_drive(),
            "llm_apis": self.check_llm_apis(),
            "mineru": self.check_mineru(),
            "file_system": self.check_file_system(),
        }
        
        sync_time = time.time() - sync_start
        logger.debug(f"Sync checks completed in {sync_time:.3f}s")

        # Calculate overall status
        statuses = []
        healthy_components = []
        unhealthy_components = []
        
        for component, result in results.items():
            if isinstance(result, dict) and "status" in result:
                status = result["status"]
                statuses.append(status)
                
                if status in ["healthy", "configured", "exists"]:
                    healthy_components.append(component)
                elif status in ["error", "unhealthy"]:
                    unhealthy_components.append(component)

        if all(s in ["healthy", "configured", "exists"] for s in statuses):
            overall_status = "healthy"
        elif any(s in ["error", "unhealthy"] for s in statuses):
            overall_status = "unhealthy"
        else:
            overall_status = "partial"
        
        total_time = time.time() - overall_start
        logger.info(f"Health check completed in {total_time:.3f}s")
        logger.info(f"Overall status: {overall_status}")
        logger.debug(f"Healthy components: {healthy_components}")
        logger.debug(f"Unhealthy components: {unhealthy_components}")

        return {
            "overall_status": overall_status, 
            "components": results,
            "timestamp": datetime.now().isoformat(),
            "total_time_ms": int(total_time * 1000),
            "summary": {
                "healthy": len(healthy_components),
                "unhealthy": len(unhealthy_components),
                "total": len(statuses)
            }
        }

    def print_results(self, results: Dict[str, Any], json_format: bool = False):
        """Print health check results."""
        if json_format:
            print(json.dumps(results, indent=2))
        else:
            print("\n" + "=" * 60)
            print("FDD PIPELINE HEALTH CHECK RESULTS")
            print("=" * 60)

            overall = results["overall_status"]
            status_symbol = {"healthy": "✅", "partial": "⚠️", "unhealthy": "❌"}.get(
                overall, "❓"
            )

            print(f"\nOVERALL STATUS: {status_symbol} {overall.upper()}")
            print("\nCOMPONENT STATUS:")
            print("-" * 60)

            for component, status in results["components"].items():
                if isinstance(status, dict) and "status" in status:
                    symbol = {
                        "healthy": "✅",
                        "configured": "✅",
                        "exists": "✅",
                        "not_configured": "⚠️",
                        "not_found": "⚠️",
                        "not_installed": "⚠️",
                        "unhealthy": "❌",
                        "error": "❌",
                    }.get(status["status"], "❓")

                    print(f"{symbol} {component.upper()}: {status['status']}")

                    if "error" in status:
                        print(f"   Error: {status['error']}")

                    if "details" in status:
                        for key, value in status["details"].items():
                            print(f"   - {key}: {value}")
                else:
                    # Handle nested components like llm_apis
                    print(f"\n{component.upper()}:")
                    for sub_component, sub_status in status.items():
                        if isinstance(sub_status, dict) and "status" in sub_status:
                            symbol = (
                                "✅" if sub_status["status"] == "configured" else "⚠️"
                            )
                            print(f"  {symbol} {sub_component}: {sub_status['status']}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FDD Pipeline Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run basic health check
  %(prog)s
  
  # Output as JSON
  %(prog)s --json
  
  # Save results to file
  %(prog)s --output health_report.json
  
  # Run specific checks only
  %(prog)s --checks api database prefect
  
  # Enable debug logging
  %(prog)s --debug
  
  # Watch mode - run checks continuously
  %(prog)s --watch --interval 30
        """
    )
    
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", "-o", help="Save results to file")
    parser.add_argument(
        "--checks", 
        nargs="+", 
        choices=["api", "prefect", "database", "google_drive", "llm_apis", "mineru", "file_system"],
        help="Run specific checks only"
    )
    parser.add_argument("--watch", "-w", action="store_true", help="Run continuously")
    parser.add_argument("--interval", "-i", type=int, default=60, help="Check interval in seconds (default: 60)")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()
    
    # Set up logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'health_check_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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
        checker = HealthChecker()
        
        if args.watch:
            # Watch mode - run continuously
            logger.info(f"Starting health check in watch mode (interval: {args.interval}s)")
            print(f"Running health checks every {args.interval} seconds. Press Ctrl+C to stop.")
            
            while True:
                try:
                    results = await checker.run_all_checks()
                    
                    # Clear screen for better readability in watch mode
                    if not args.json and not args.output:
                        os.system('cls' if os.name == 'nt' else 'clear')
                    
                    checker.print_results(results, json_format=args.json)
                    
                    if args.output:
                        with open(args.output, 'w') as f:
                            json.dump(results, f, indent=2)
                        logger.debug(f"Results saved to: {args.output}")
                    
                    # Show next check time
                    if not args.json:
                        next_check = datetime.now().timestamp() + args.interval
                        print(f"\nNext check at: {datetime.fromtimestamp(next_check).strftime('%H:%M:%S')}")
                    
                    await asyncio.sleep(args.interval)
                    
                except KeyboardInterrupt:
                    logger.info("Watch mode stopped by user")
                    break
                    
        else:
            # Single run mode
            results = await checker.run_all_checks()
            
            # Filter results if specific checks requested
            if args.checks:
                filtered_components = {
                    k: v for k, v in results["components"].items() 
                    if k in args.checks
                }
                results["components"] = filtered_components
                logger.debug(f"Filtered to checks: {args.checks}")
            
            checker.print_results(results, json_format=args.json)
            
            # Save to file if requested
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"\nResults saved to: {args.output}")
                logger.info(f"Results saved to: {args.output}")

            # Exit with appropriate code
            exit_code = 0
            if results["overall_status"] == "healthy":
                logger.info("All checks passed - exiting with code 0")
                exit_code = 0
            elif results["overall_status"] == "unhealthy":
                logger.warning("Some checks failed - exiting with code 1")
                exit_code = 1
            else:
                logger.warning("Partial health - exiting with code 2")
                exit_code = 2
                
            sys.exit(exit_code)
            
    except KeyboardInterrupt:
        logger.info("Health check interrupted by user")
        print("\nHealth check cancelled by user")
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
