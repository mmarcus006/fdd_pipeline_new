#!/usr/bin/env python
"""
FDD Pipeline Main Entry Point

This script provides a unified entry point to run the complete FDD processing workflow:
1. Web scraping from state portals
2. Document download and storage
3. PDF processing with MinerU
4. LLM extraction of structured data
5. Validation and database upload

Usage:
    # Run complete pipeline for all states
    python main.py run-all

    # Run specific state scraper
    python main.py scrape --state minnesota
    python main.py scrape --state wisconsin

    # Process a single PDF
    python main.py process-pdf --path /path/to/fdd.pdf

    # Run with Prefect orchestration
    python main.py orchestrate --deploy

    # Check pipeline health
    python main.py health-check
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional, List
import click
from datetime import datetime
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.logging import get_logger
from storage.database.manager import get_database_manager, serialize_for_db
from config import get_settings

logger = get_logger(__name__)


@click.group()
def cli():
    """FDD Pipeline Management CLI"""
    pass


@cli.command()
@click.option(
    "--state", type=click.Choice(["minnesota", "wisconsin", "all"]), default="all"
)
@click.option("--limit", type=int, help="Limit number of franchises to process")
@click.option("--test-mode", is_flag=True, help="Run in test mode with reduced dataset")
async def scrape(state: str, limit: Optional[int], test_mode: bool):
    """Run web scraping for state portals"""
    from workflows.base_state_flow import scrape_state_flow
    from workflows.state_configs import get_state_config

    logger.info(f"Starting scraping for: {state}")

    try:
        if state == "all":
            # Run all states
            for state_name in ["minnesota", "wisconsin"]:
                logger.info(f"Running {state_name} scraper...")
                state_config = get_state_config(state_name)
                await scrape_state_flow(
                    state_config=state_config,
                    download_documents=not test_mode,
                    max_documents=limit,
                )
        else:
            # Run specific state
            logger.info(f"Running {state} scraper...")
            state_config = get_state_config(state)
            await scrape_state_flow(
                state_config=state_config,
                download_documents=not test_mode,
                max_documents=limit,
            )

        logger.info("Scraping completed successfully")

    except Exception as e:
        logger.error(f"Scraping failed: {e}", exc_info=True)
        raise


@cli.command()
@click.option("--path", required=True, help="Path to PDF file")
@click.option(
    "--franchise-name", help="Franchise name (will be extracted if not provided)"
)
@click.option("--skip-db", is_flag=True, help="Skip database operations for testing")
async def process_pdf(path: str, franchise_name: Optional[str], skip_db: bool):
    """Process a single PDF file through the pipeline"""
    # TODO: Implement process_single_pdf workflow
    logger.error("PDF processing workflow not yet implemented")
    click.echo("Error: PDF processing workflow not yet implemented", err=True)
    return

    # from workflows.process_single_pdf import process_single_fdd_flow
    #
    # pdf_path = Path(path)
    # if not pdf_path.exists():
    #     click.echo(f"Error: PDF file not found at {path}", err=True)
    #     return
    #
    # logger.info(f"Processing PDF: {pdf_path}")
    #
    # try:
    #     # The flow will handle all processing steps
    #     await process_single_fdd_flow.fn(str(pdf_path))
    #     logger.info("PDF processing completed successfully")
    #
    # except Exception as e:
    #     logger.error(f"PDF processing failed: {e}", exc_info=True)
    #     raise


@cli.command()
@click.option("--deploy", is_flag=True, help="Deploy flows to Prefect")
@click.option("--schedule", is_flag=True, help="Enable scheduled runs")
@click.option("--run-now", is_flag=True, help="Run immediately after deployment")
async def orchestrate(deploy: bool, schedule: bool, run_now: bool):
    """Set up and run Prefect orchestration

    Note: The Prefect Deployment API has changed. Use one of these methods:
    1. Direct execution: python main.py scrape --state minnesota
    2. Serve locally: python scripts/serve_flows.py --state all
    3. Deploy to Prefect: python scripts/deploy_state_flows.py --state all
    """
    if deploy:
        logger.info("Note: Using new Prefect deployment API...")
        logger.info("For local testing, consider using: python scripts/serve_flows.py")

        # Deploy state flows using new deployment script
        import subprocess

        result = subprocess.run(
            ["python", "scripts/deploy_state_flows.py", "--state", "all"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"State flows deployment failed: {result.stderr}")
            logger.error(
                "Try running flows directly with: python main.py scrape --state all"
            )
            return
        logger.info("State flows deployed successfully")

    if run_now:
        logger.info("Triggering immediate flow runs...")
        # Run flows through Prefect
        from prefect import get_client

        async with get_client() as client:
            # Run state flows with new deployment names
            for state, state_name in [
                ("minnesota", "Minnesota"),
                ("wisconsin", "Wisconsin"),
            ]:
                try:
                    deployment = await client.read_deployment_by_name(
                        f"scrape-state-portal/{state}-scrape"
                    )
                    flow_run = await client.create_flow_run_from_deployment(
                        deployment_id=deployment.id
                    )
                    logger.info(f"Started {state_name} flow run: {flow_run.id}")
                except Exception as e:
                    logger.warning(f"{state_name} flow not deployed: {e}")


@cli.command()
def flow_help():
    """Show help for running flows with the new Prefect API"""
    click.echo(
        """
FDD Pipeline Flow Execution Guide
=================================

The Prefect Deployment API has changed. Here are the recommended ways to run flows:

1. DIRECT EXECUTION (Simplest for testing):
   python main.py scrape --state minnesota
   python main.py scrape --state wisconsin --limit 5
   python main.py scrape --state all --test-mode

2. LOCAL SERVING (For development with Prefect UI):
   python scripts/serve_flows.py --state all
   # Then trigger runs via Prefect UI at http://localhost:4200

3. RUN FLOWS DIRECTLY (Without deployment):
   python scripts/run_flow.py --state minnesota
   python scripts/run_flow.py --state wisconsin --test-mode --limit 5

4. DEPLOY TO PREFECT (For production):
   python scripts/deploy_state_flows.py --state all --mode production
   python scripts/deploy_state_flows.py --state minnesota --mode test

5. PROCESS SINGLE PDF:
   python main.py process-pdf --path /path/to/fdd.pdf

For more information, see the scripts in the scripts/ directory.
"""
    )


@cli.command()
async def health_check():
    """Check health of all pipeline components"""
    from storage.database.manager import get_database_manager

    logger.info("Running pipeline health check...")

    # Check database connection
    db = get_database_manager()
    db_health = db.health_check.check_connection()

    health_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_health,
        "components": {},
    }

    # Check if required tables exist
    required_tables = [
        "franchisors",
        "fdds",
        "fdd_sections",
        "scrape_metadata",
        "item5_fees",
        "item6_other_fees",
        "item7_investment",
        "item19_fpr",
        "item20_outlets",
        "item21_financials",
    ]

    for table in required_tables:
        exists = db.health_check.check_table_exists(table)
        health_status["components"][f"table_{table}"] = {
            "exists": exists,
            "status": "healthy" if exists else "missing",
        }

    # Check MinerU installation
    try:
        import magic_pdf

        health_status["components"]["mineru"] = {"installed": True, "status": "healthy"}
    except ImportError:
        health_status["components"]["mineru"] = {
            "installed": False,
            "status": "missing",
        }

    # Check Playwright installation
    try:
        from playwright.async_api import async_playwright

        health_status["components"]["playwright"] = {
            "installed": True,
            "status": "healthy",
        }
    except ImportError:
        health_status["components"]["playwright"] = {
            "installed": False,
            "status": "missing",
        }

    # Check API keys
    settings = get_settings()
    health_status["components"]["api_keys"] = {
        "gemini": bool(settings.gemini_api_key),
        "openai": bool(settings.openai_api_key),
        "supabase": bool(settings.supabase_url and settings.supabase_service_key),
    }

    # Print results
    click.echo(json.dumps(health_status, indent=2))

    # Return appropriate exit code
    if not db_health["healthy"]:
        logger.error("Database connection failed")
        sys.exit(1)

    missing_tables = [
        t for t in required_tables if not db.health_check.check_table_exists(t)
    ]
    if missing_tables:
        logger.error(f"Missing database tables: {missing_tables}")
        logger.error("Run the migration script in Supabase")
        sys.exit(1)

    logger.info("Health check passed")


@cli.command()
@click.option("--days", type=int, default=7, help="Process FDDs from last N days")
@click.option(
    "--state", type=click.Choice(["minnesota", "wisconsin", "all"]), default="all"
)
@click.option("--parallel", is_flag=True, help="Run states in parallel")
@click.option("--limit", type=int, help="Limit number of documents to process")
@click.option("--skip-download", is_flag=True, help="Skip downloading documents")
async def run_all(
    days: int, state: str, parallel: bool, limit: Optional[int], skip_download: bool
):
    """Run complete pipeline for all configured states"""
    from datetime import timedelta

    logger.info(f"Running complete pipeline for {state} (last {days} days)")

    # First run health check
    try:
        await health_check()
    except SystemExit:
        logger.error("Health check failed, aborting pipeline")
        return

    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    logger.info(f"Processing period: {start_date.date()} to {end_date.date()}")

    # Set parameters for scraping
    download_documents = not skip_download
    max_documents = limit

    # Run scrapers
    if parallel and state == "all":
        # Run states in parallel
        tasks = []
        # Always include Minnesota when state is "all"
        from workflows.base_state_flow import scrape_state_flow
        from workflows.state_configs import MINNESOTA_CONFIG, WISCONSIN_CONFIG

        tasks.append(
            scrape_state_flow.fn(
                state_config=MINNESOTA_CONFIG,
                download_documents=download_documents,
                max_documents=max_documents,
            )
        )

        # Always include Wisconsin when state is "all"
        tasks.append(
            scrape_state_flow.fn(
                state_config=WISCONSIN_CONFIG,
                download_documents=download_documents,
                max_documents=max_documents,
            )
        )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Flow {i} failed: {result}")
            else:
                logger.info(f"Flow {i} completed successfully")
    else:
        # Run states sequentially
        await scrape(state=state, limit=max_documents, test_mode=skip_download)

    # Get processing statistics
    db = get_database_manager()

    # Count FDDs processed
    fdds_query = f"""
    SELECT 
        COUNT(*) as total_fdds,
        COUNT(*) FILTER (WHERE processing_status = 'completed') as completed,
        COUNT(*) FILTER (WHERE processing_status = 'failed') as failed,
        COUNT(*) FILTER (WHERE processing_status = 'pending') as pending
    FROM fdds
    WHERE created_at >= '{start_date.isoformat()}'
    """

    client = db.get_supabase_client()
    result = client.rpc("query", {"sql": fdds_query}).execute()

    if result.data:
        stats = result.data[0]
        logger.info(
            f"""
Pipeline Statistics:
- Total FDDs: {stats['total_fdds']}
- Completed: {stats['completed']}
- Failed: {stats['failed']}
- Pending: {stats['pending']}
        """
        )


def main():
    """Main entry point with async support"""
    # For async commands, we need to handle them specially
    if len(sys.argv) > 1:
        command = sys.argv[1]
        async_commands = [
            "scrape",
            "process-pdf",
            "orchestrate",
            "health-check",
            "run-all",
        ]

        if command in async_commands:
            # Extract the command and run it async
            import click.testing

            runner = click.testing.CliRunner()

            # Create an async wrapper
            async def run_async():
                # Use Click's built-in context handling
                with cli.make_context("main", sys.argv[1:]) as ctx:
                    # Get the command and its context
                    cmd = cli.commands[command]
                    # Invoke the command with its parsed parameters
                    with cmd.make_context(command, ctx.args, parent=ctx) as cmd_ctx:
                        await cmd.callback(**cmd_ctx.params)

            # Run the async command
            try:
                asyncio.run(run_async())
            except KeyboardInterrupt:
                logger.info("Pipeline interrupted by user")
                sys.exit(1)
            except Exception as e:
                logger.error(f"Pipeline failed: {e}", exc_info=True)
                sys.exit(1)
        else:
            # Non-async command, run normally
            cli()
    else:
        cli()


if __name__ == "__main__":
    main()
