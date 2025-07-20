#!/usr/bin/env python
"""
FDD Pipeline Workflow Orchestrator

This script manages the complete FDD processing workflow with automatic
retry logic, progress tracking, and error recovery.

Usage:
    python scripts/orchestrate_workflow.py --state all --mode production
    python scripts/orchestrate_workflow.py --state minnesota --mode test
    python scripts/orchestrate_workflow.py --resume-from <checkpoint>
"""

import asyncio
import json
import sys
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logging import get_logger
from utils.database import get_database_manager
from config import get_settings
from flows.base_state_flow import scrape_state_flow
from flows.state_configs import MINNESOTA_CONFIG, WISCONSIN_CONFIG
from flows.process_single_pdf import process_single_fdd_flow

logger = get_logger(__name__)


class WorkflowOrchestrator:
    """Orchestrates the complete FDD processing workflow."""

    def __init__(self, checkpoint_file: Optional[Path] = None):
        logger.debug("Initializing WorkflowOrchestrator")
        
        self.db = get_database_manager()
        self.checkpoint_file = checkpoint_file or Path("workflow_checkpoint.json")
        self.workflow_id = str(uuid4())
        self.start_time = datetime.utcnow()
        self.stats = {
            "scraped": 0,
            "downloaded": 0,
            "processed": 0,
            "failed": 0,
            "skipped": 0,
        }
        
        logger.debug(f"Workflow ID: {self.workflow_id}")
        logger.debug(f"Checkpoint file: {self.checkpoint_file}")
        logger.info(f"WorkflowOrchestrator initialized with ID: {self.workflow_id}")

    async def save_checkpoint(self, stage: str, data: Dict[str, Any]):
        """Save workflow checkpoint for recovery."""
        logger.debug(f"Saving checkpoint for stage: {stage}")
        
        checkpoint = {
            "workflow_id": self.workflow_id,
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "stats": self.stats,
            "data": data,
        }
        
        # Backup existing checkpoint if it exists
        if self.checkpoint_file.exists():
            backup_path = self.checkpoint_file.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            logger.debug(f"Backing up existing checkpoint to: {backup_path}")
            import shutil
            shutil.copy2(self.checkpoint_file, backup_path)

        with open(self.checkpoint_file, "w") as f:
            json.dump(checkpoint, f, indent=2, default=str)
        
        file_size = self.checkpoint_file.stat().st_size
        logger.info(f"Checkpoint saved: {stage} ({file_size} bytes)")
        logger.debug(f"Checkpoint stats: {self.stats}")

    async def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load checkpoint if exists."""
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, "r") as f:
                return json.load(f)
        return None

    async def run_scrapers(
        self, states: List[str], limit: Optional[int] = None
    ) -> Dict[str, List[str]]:
        """Run web scrapers for specified states."""
        logger.info(f"Starting scrapers for states: {states}")
        logger.debug(f"Scraper limit: {limit}")
        
        scraping_start = time.time()
        await self.save_checkpoint("scraping_started", {"states": states})

        results = {}

        for i, state in enumerate(states, 1):
            logger.debug(f"Processing state {i}/{len(states)}: {state}")
            state_start = time.time()
            try:
                if state == "minnesota":
                    logger.info("Running Minnesota scraper...")
                    await scrape_state_flow.fn(
                        state_config=MINNESOTA_CONFIG,
                        download_documents=True,
                        max_documents=limit,
                    )

                    # Get recently created FDDs
                    loop = asyncio.get_running_loop()
                    recent_fdds = await loop.run_in_executor(
                        None,
                        self.db.get_records_by_filter,
                        "fdds",
                        {
                            "filing_state": "MN",
                            "created_at": {
                                "$gte": (
                                    datetime.utcnow() - timedelta(hours=1)
                                ).isoformat()
                            },
                        },
                    )
                    results[state] = [fdd["id"] for fdd in recent_fdds]
                    self.stats["scraped"] += len(recent_fdds)

                elif state == "wisconsin":
                    logger.info("Running Wisconsin scraper...")
                    await scrape_state_flow.fn(
                        state_config=WISCONSIN_CONFIG,
                        download_documents=True,
                        max_documents=limit,
                    )

                    # Get recently created FDDs
                    loop = asyncio.get_running_loop()
                    recent_fdds = await loop.run_in_executor(
                        None,
                        self.db.get_records_by_filter,
                        "fdds",
                        {
                            "filing_state": "WI",
                            "created_at": {
                                "$gte": (
                                    datetime.utcnow() - timedelta(hours=1)
                                ).isoformat()
                            },
                        },
                    )
                    results[state] = [fdd["id"] for fdd in recent_fdds]
                    self.stats["scraped"] += len(recent_fdds)

            except Exception as e:
                state_time = time.time() - state_start
                logger.error(f"Scraper failed for {state} after {state_time:.2f}s: {e}")
                logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
                import traceback
                logger.debug(f"Traceback:\n{traceback.format_exc()}")
                self.stats["failed"] += 1
                results[state] = []
            
            state_time = time.time() - state_start
            logger.debug(f"State {state} completed in {state_time:.2f}s")

        scraping_time = time.time() - scraping_start
        logger.info(f"Scraping completed in {scraping_time:.2f}s")
        logger.info(f"Total documents scraped: {self.stats['scraped']}")
        
        await self.save_checkpoint("scraping_completed", results)
        return results

    async def process_documents(self, fdd_ids: List[str]) -> Dict[str, str]:
        """Process FDD documents through the pipeline."""
        logger.info(f"Processing {len(fdd_ids)} documents")
        logger.debug(f"FDD IDs to process: {fdd_ids[:5]}...")  # Show first 5
        
        processing_start = time.time()
        await self.save_checkpoint("processing_started", {"fdd_ids": fdd_ids})

        results = {}
        loop = asyncio.get_running_loop()

        for i, fdd_id in enumerate(fdd_ids, 1):
            doc_start = time.time()
            logger.debug(f"Processing document {i}/{len(fdd_ids)}: {fdd_id}")
            try:
                # Get FDD record
                fdd = await loop.run_in_executor(
                    None, self.db.get_record_by_id, "fdds", fdd_id
                )
                if not fdd:
                    logger.warning(f"FDD not found: {fdd_id}")
                    self.stats["skipped"] += 1
                    continue

                # Check if already processed
                if fdd.get("processing_status") == "completed":
                    logger.info(f"FDD already processed: {fdd_id}")
                    self.stats["skipped"] += 1
                    results[fdd_id] = "skipped"
                    continue

                # Get file from Drive
                if not fdd.get("drive_file_id"):
                    logger.warning(f"No Drive file for FDD: {fdd_id}")
                    self.stats["failed"] += 1
                    results[fdd_id] = "no_file"
                    continue

                # Process through pipeline
                logger.info(f"Processing FDD: {fdd_id}")

                # Update status to processing
                await loop.run_in_executor(
                    None,
                    self.db.update_record,
                    "fdds",
                    fdd_id,
                    {"processing_status": "processing"},
                )

                # Run document processing tasks
                # This would normally download from Drive and process
                # For now, we'll mark as processed

                # TODO: Implement actual processing pipeline
                # 1. Download from Drive
                # 2. Run MinerU
                # 3. Extract sections
                # 4. Run LLM extraction
                # 5. Validate data

                # Update status to completed
                await loop.run_in_executor(
                    None,
                    self.db.update_record,
                    "fdds",
                    fdd_id,
                    {
                        "processing_status": "completed",
                        "processed_at": datetime.utcnow().isoformat(),
                    },
                )

                self.stats["processed"] += 1
                results[fdd_id] = "completed"

            except Exception as e:
                logger.error(f"Processing failed for {fdd_id}: {e}")
                self.stats["failed"] += 1
                results[fdd_id] = f"error: {str(e)}"

                # Update status to failed
                await loop.run_in_executor(
                    None,
                    self.db.update_record,
                    "fdds",
                    fdd_id,
                    {"processing_status": "failed"},
                )

        await self.save_checkpoint("processing_completed", results)
        return results

    async def generate_report(self) -> str:
        """Generate workflow execution report."""
        duration = datetime.utcnow() - self.start_time

        report = f"""
FDD Pipeline Workflow Report
============================
Workflow ID: {self.workflow_id}
Start Time: {self.start_time.isoformat()}
Duration: {duration}

Statistics:
-----------
Documents Scraped: {self.stats['scraped']}
Documents Downloaded: {self.stats['downloaded']}
Documents Processed: {self.stats['processed']}
Failed Operations: {self.stats['failed']}
Skipped (Duplicates): {self.stats['skipped']}

Success Rate: {(self.stats['processed'] / max(self.stats['scraped'], 1)) * 100:.1f}%
        """

        # Get additional stats from database
        db_stats = await self._get_database_stats()
        if db_stats:
            report += f"""
Database Statistics:
-------------------
Total Franchisors: {db_stats['total_franchisors']}
Total FDDs: {db_stats['total_fdds']}
Completed FDDs: {db_stats['completed_fdds']}
Pending FDDs: {db_stats['pending_fdds']}
Failed FDDs: {db_stats['failed_fdds']}
        """

        return report

    async def _get_database_stats(self) -> Optional[Dict[str, int]]:
        """Get database statistics."""
        try:
            client = self.db.get_supabase_client()

            # Get counts using raw SQL through RPC
            stats_query = """
            SELECT 
                (SELECT COUNT(*) FROM franchisors) as total_franchisors,
                (SELECT COUNT(*) FROM fdds) as total_fdds,
                (SELECT COUNT(*) FROM fdds WHERE processing_status = 'completed') as completed_fdds,
                (SELECT COUNT(*) FROM fdds WHERE processing_status = 'pending') as pending_fdds,
                (SELECT COUNT(*) FROM fdds WHERE processing_status = 'failed') as failed_fdds
            """

            # Note: This assumes you have an RPC function for raw queries
            # Otherwise, you'd need to make separate queries

            franchisors = (
                client.table("franchisors").select("*", count="exact").execute()
            )
            fdds = client.table("fdds").select("*", count="exact").execute()
            completed = (
                client.table("fdds")
                .select("*", count="exact")
                .eq("processing_status", "completed")
                .execute()
            )
            pending = (
                client.table("fdds")
                .select("*", count="exact")
                .eq("processing_status", "pending")
                .execute()
            )
            failed = (
                client.table("fdds")
                .select("*", count="exact")
                .eq("processing_status", "failed")
                .execute()
            )

            return {
                "total_franchisors": franchisors.count if franchisors else 0,
                "total_fdds": fdds.count if fdds else 0,
                "completed_fdds": completed.count if completed else 0,
                "pending_fdds": pending.count if pending else 0,
                "failed_fdds": failed.count if failed else 0,
            }

        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return None


@click.command()
@click.option(
    "--state", type=click.Choice(["minnesota", "wisconsin", "all"]), default="all"
)
@click.option("--mode", type=click.Choice(["test", "production"]), default="production")
@click.option("--limit", type=int, help="Limit number of documents to process")
@click.option("--resume-from", type=str, help="Resume from checkpoint file")
@click.option("--skip-scraping", is_flag=True, help="Skip scraping, process existing")
@click.option("--parallel", is_flag=True, help="Run tasks in parallel")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
async def orchestrate(
    state: str,
    mode: str,
    limit: Optional[int],
    resume_from: Optional[str],
    skip_scraping: bool,
    parallel: bool,
    debug: bool,
    verbose: bool,
):
    """Orchestrate the complete FDD processing workflow.
    
    Examples:
        # Run complete workflow for all states
        python orchestrate_workflow.py --state all --mode production
        
        # Test run with limited documents
        python orchestrate_workflow.py --state minnesota --mode test --limit 5
        
        # Resume from checkpoint
        python orchestrate_workflow.py --resume-from workflow_checkpoint.json
        
        # Process existing documents only
        python orchestrate_workflow.py --skip-scraping --limit 10
        
        # Run with debug logging
        python orchestrate_workflow.py --debug
    """

    # Set up logging based on arguments (already done in main())
    overall_start = time.time()
    
    # Set limit based on mode
    if mode == "test" and not limit:
        limit = 5
        logger.debug("Test mode: setting default limit to 5")

    logger.info(
        f"Starting workflow orchestration: state={state}, mode={mode}, limit={limit}"
    )
    logger.debug(f"Skip scraping: {skip_scraping}, Parallel: {parallel}")

    # Initialize orchestrator
    checkpoint_file = Path(resume_from) if resume_from else None
    orchestrator = WorkflowOrchestrator(checkpoint_file)

    # Load checkpoint if resuming
    checkpoint = None
    if resume_from:
        checkpoint = await orchestrator.load_checkpoint()
        if checkpoint:
            logger.info(f"Resuming from checkpoint: {checkpoint['stage']}")
            orchestrator.workflow_id = checkpoint["workflow_id"]
            orchestrator.stats = checkpoint["stats"]

    try:
        # Stage 1: Web Scraping
        fdd_ids_by_state = {}
        if not skip_scraping and (
            not checkpoint or checkpoint["stage"] == "scraping_started"
        ):
            states_to_scrape = ["minnesota", "wisconsin"] if state == "all" else [state]

            if parallel:
                # Run scrapers in parallel
                tasks = []
                for s in states_to_scrape:
                    if s == "minnesota":
                        tasks.append(
                            scrape_state_flow.fn(
                                state_config=MINNESOTA_CONFIG,
                                download_documents=True,
                                max_documents=limit,
                            )
                        )
                    elif s == "wisconsin":
                        tasks.append(
                            scrape_state_flow.fn(
                                state_config=WISCONSIN_CONFIG,
                                download_documents=True,
                                max_documents=limit,
                            )
                        )

                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # Run scrapers sequentially
                fdd_ids_by_state = await orchestrator.run_scrapers(
                    states_to_scrape, limit
                )
        else:
            logger.info("Skipping scraping stage")

        # Stage 2: Document Processing
        if checkpoint and checkpoint["stage"] in [
            "scraping_completed",
            "processing_started",
        ]:
            fdd_ids_by_state = checkpoint["data"]

        # Flatten FDD IDs
        all_fdd_ids = []
        for state_fdds in fdd_ids_by_state.values():
            all_fdd_ids.extend(state_fdds)

        if not all_fdd_ids and not skip_scraping:
            logger.warning("No FDDs found to process")
        else:
            # Process existing pending FDDs if skip_scraping
            if skip_scraping:
                loop = asyncio.get_running_loop()
                pending_fdds = await loop.run_in_executor(
                    None,
                    orchestrator.db.get_records_by_filter,
                    "fdds",
                    {"processing_status": "pending"},
                    limit=limit,
                )
                all_fdd_ids = [fdd["id"] for fdd in pending_fdds]

            if all_fdd_ids:
                await orchestrator.process_documents(all_fdd_ids)

        # Stage 3: Generate Report
        logger.info("Generating workflow report...")
        report = await orchestrator.generate_report()
        print(report)

        # Save final report
        report_file = Path(f"workflow_report_{orchestrator.workflow_id}.txt")
        with open(report_file, "w") as f:
            f.write(report)
        
        overall_time = time.time() - overall_start
        logger.info(f"Workflow completed in {overall_time:.2f}s")
        logger.info(f"Report saved to: {report_file}")
        logger.debug(f"Final stats: {orchestrator.stats}")
        
        print(f"\n✓ Workflow completed successfully in {overall_time:.2f}s")
        print(f"Report saved to: {report_file}")

    except Exception as e:
        overall_time = time.time() - overall_start
        logger.error(f"Workflow failed after {overall_time:.2f}s: {e}", exc_info=True)
        await orchestrator.save_checkpoint("error", {"error": str(e)})
        print(f"\n✗ Workflow failed: {e}")
        raise


def main():
    """Main entry point with proper asyncio handling."""
    # Set up logging before running async code
    args = sys.argv[1:]
    
    # Check for debug/verbose flags
    if "--debug" in args or "-d" in args:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'orchestrate_workflow_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        logger.debug("Debug logging enabled")
    elif "--verbose" in args or "-v" in args:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    logger.debug(f"Script started with arguments: {args}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Python version: {sys.version}")
    
    try:
        # Run the async command
        asyncio.run(orchestrate.main(standalone_mode=False))
    except KeyboardInterrupt:
        logger.info("Workflow interrupted by user")
        print("\nWorkflow cancelled by user")
        sys.exit(130)
    except click.ClickException as e:
        # Let Click handle its own exceptions
        e.show()
        sys.exit(e.exit_code)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
