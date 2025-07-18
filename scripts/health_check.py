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
from typing import Dict, Any

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

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{api_url}/health")

                if response.status_code == 200:
                    data = response.json()
                    return {"status": "healthy", "details": data}
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"Status code: {response.status_code}",
                    }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def check_prefect(self) -> Dict[str, Any]:
        """Check Prefect server health."""
        prefect_url = os.getenv("PREFECT_API_URL", "http://localhost:4200")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{prefect_url}/health")

                if response.status_code == 200:
                    # Get additional info
                    version_response = await client.get(f"{prefect_url}/version")
                    version = (
                        version_response.json()
                        if version_response.status_code == 200
                        else {}
                    )

                    return {
                        "status": "healthy",
                        "details": {"version": version.get("version", "unknown")},
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"Status code: {response.status_code}",
                    }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def check_database(self) -> Dict[str, Any]:
        """Check database connectivity."""
        try:
            db = DatabaseManager()

            if db.health_check():
                # Get additional stats
                stats = self._get_database_stats(db)

                return {"status": "healthy", "details": stats}
            else:
                return {"status": "unhealthy", "error": "Health check failed"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _get_database_stats(self, db: DatabaseManager) -> Dict[str, int]:
        """Get database statistics."""
        stats = {}

        try:
            # Get counts for main tables
            tables = ["franchisors", "fdds", "fdd_sections"]

            for table in tables:
                result = (
                    db.query_builder(table).select("count", count="exact").execute()
                )
                stats[f"{table}_count"] = result.count if result else 0

        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")

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
        logger.info("Running health checks...")

        # Run async checks
        api_result, prefect_result = await asyncio.gather(
            self.check_api(), self.check_prefect()
        )

        # Run sync checks
        results = {
            "api": api_result,
            "prefect": prefect_result,
            "database": self.check_database(),
            "google_drive": self.check_google_drive(),
            "llm_apis": self.check_llm_apis(),
            "mineru": self.check_mineru(),
            "file_system": self.check_file_system(),
        }

        # Calculate overall status
        statuses = []
        for component, result in results.items():
            if isinstance(result, dict) and "status" in result:
                statuses.append(result["status"])

        if all(s in ["healthy", "configured", "exists"] for s in statuses):
            overall_status = "healthy"
        elif any(s in ["error", "unhealthy"] for s in statuses):
            overall_status = "unhealthy"
        else:
            overall_status = "partial"

        return {"overall_status": overall_status, "components": results}

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

    parser = argparse.ArgumentParser(description="FDD Pipeline Health Check")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    checker = HealthChecker()
    results = await checker.run_all_checks()
    checker.print_results(results, json_format=args.json)

    # Exit with appropriate code
    if results["overall_status"] == "healthy":
        sys.exit(0)
    elif results["overall_status"] == "unhealthy":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
