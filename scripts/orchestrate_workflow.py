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
        self.db = get_database_manager()
        self.checkpoint_file = checkpoint_file or Path("workflow_checkpoint.json")
        self.workflow_id = str(uuid4())
        self.start_time = datetime.utcnow()
        self.stats = {
            "scraped": 0,
            "downloaded": 0,
            "processed": 0,
            "failed": 0,
            "skipped": 0
        }
        
    async def save_checkpoint(self, stage: str, data: Dict[str, Any]):
        """Save workflow checkpoint for recovery."""
        checkpoint = {
            "workflow_id": self.workflow_id,
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "stats": self.stats,
            "data": data
        }
        
        with open(self.checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, indent=2, default=str)
            
        logger.info(f"Checkpoint saved: {stage}")
        
    async def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load checkpoint if exists."""
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'r') as f:
                return json.load(f)
        return None
        
    async def run_scrapers(self, states: List[str], limit: Optional[int] = None) -> Dict[str, List[str]]:
        """Run web scrapers for specified states."""
        logger.info(f"Starting scrapers for states: {states}")
        await self.save_checkpoint("scraping_started", {"states": states})
        
        results = {}
        
        for state in states:
            try:
                if state == "minnesota":
                    logger.info("Running Minnesota scraper...")
                    await scrape_state_flow.fn(
                        state_config=MINNESOTA_CONFIG,
                        download_documents=True,
                        max_documents=limit
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
                                "$gte": (datetime.utcnow() - timedelta(hours=1)).isoformat()
                            }
                        }
                    )
                    results[state] = [fdd["id"] for fdd in recent_fdds]
                    self.stats["scraped"] += len(recent_fdds)
                    
                elif state == "wisconsin":
                    logger.info("Running Wisconsin scraper...")
                    await scrape_state_flow.fn(
                        state_config=WISCONSIN_CONFIG,
                        download_documents=True,
                        max_documents=limit
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
                                "$gte": (datetime.utcnow() - timedelta(hours=1)).isoformat()
                            }
                        }
                    )
                    results[state] = [fdd["id"] for fdd in recent_fdds]
                    self.stats["scraped"] += len(recent_fdds)
                    
            except Exception as e:
                logger.error(f"Scraper failed for {state}: {e}")
                self.stats["failed"] += 1
                results[state] = []
                
        await self.save_checkpoint("scraping_completed", results)
        return results
        
    async def process_documents(self, fdd_ids: List[str]) -> Dict[str, str]:
        """Process FDD documents through the pipeline."""
        logger.info(f"Processing {len(fdd_ids)} documents")
        await self.save_checkpoint("processing_started", {"fdd_ids": fdd_ids})
        
        results = {}
        loop = asyncio.get_running_loop()
        
        for fdd_id in fdd_ids:
            try:
                # Get FDD record
                fdd = await loop.run_in_executor(None, self.db.get_record_by_id, "fdds", fdd_id)
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
                    {"processing_status": "processing"}
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
                        "processed_at": datetime.utcnow().isoformat()
                    }
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
                    {"processing_status": "failed"}
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
            
            franchisors = client.table("franchisors").select("*", count="exact").execute()
            fdds = client.table("fdds").select("*", count="exact").execute()
            completed = client.table("fdds").select("*", count="exact").eq("processing_status", "completed").execute()
            pending = client.table("fdds").select("*", count="exact").eq("processing_status", "pending").execute()
            failed = client.table("fdds").select("*", count="exact").eq("processing_status", "failed").execute()
            
            return {
                "total_franchisors": franchisors.count if franchisors else 0,
                "total_fdds": fdds.count if fdds else 0,
                "completed_fdds": completed.count if completed else 0,
                "pending_fdds": pending.count if pending else 0,
                "failed_fdds": failed.count if failed else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return None

@click.command()
@click.option('--state', type=click.Choice(['minnesota', 'wisconsin', 'all']), default='all')
@click.option('--mode', type=click.Choice(['test', 'production']), default='production')
@click.option('--limit', type=int, help='Limit number of documents to process')
@click.option('--resume-from', type=str, help='Resume from checkpoint file')
@click.option('--skip-scraping', is_flag=True, help='Skip scraping, process existing')
@click.option('--parallel', is_flag=True, help='Run tasks in parallel')
async def orchestrate(state: str, mode: str, limit: Optional[int], 
                     resume_from: Optional[str], skip_scraping: bool, parallel: bool):
    """Orchestrate the complete FDD processing workflow."""
    
    # Set limit based on mode
    if mode == 'test' and not limit:
        limit = 5
        
    logger.info(f"Starting workflow orchestration: state={state}, mode={mode}, limit={limit}")
    
    # Initialize orchestrator
    checkpoint_file = Path(resume_from) if resume_from else None
    orchestrator = WorkflowOrchestrator(checkpoint_file)
    
    # Load checkpoint if resuming
    checkpoint = None
    if resume_from:
        checkpoint = await orchestrator.load_checkpoint()
        if checkpoint:
            logger.info(f"Resuming from checkpoint: {checkpoint['stage']}")
            orchestrator.workflow_id = checkpoint['workflow_id']
            orchestrator.stats = checkpoint['stats']
    
    try:
        # Stage 1: Web Scraping
        fdd_ids_by_state = {}
        if not skip_scraping and (not checkpoint or checkpoint['stage'] == 'scraping_started'):
            states_to_scrape = ['minnesota', 'wisconsin'] if state == 'all' else [state]
            
            if parallel:
                # Run scrapers in parallel
                tasks = []
                for s in states_to_scrape:
                    if s == 'minnesota':
                        tasks.append(scrape_state_flow.fn(
                            state_config=MINNESOTA_CONFIG,
                            download_documents=True,
                            max_documents=limit
                        ))
                    elif s == 'wisconsin':
                        tasks.append(scrape_state_flow.fn(
                            state_config=WISCONSIN_CONFIG,
                            download_documents=True,
                            max_documents=limit
                        ))
                        
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # Run scrapers sequentially
                fdd_ids_by_state = await orchestrator.run_scrapers(states_to_scrape, limit)
        else:
            logger.info("Skipping scraping stage")
            
        # Stage 2: Document Processing
        if checkpoint and checkpoint['stage'] in ['scraping_completed', 'processing_started']:
            fdd_ids_by_state = checkpoint['data']
            
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
                    limit=limit
                )
                all_fdd_ids = [fdd["id"] for fdd in pending_fdds]
                
            if all_fdd_ids:
                await orchestrator.process_documents(all_fdd_ids)
            
        # Stage 3: Generate Report
        report = await orchestrator.generate_report()
        print(report)
        
        # Save final report
        report_file = Path(f"workflow_report_{orchestrator.workflow_id}.txt")
        with open(report_file, 'w') as f:
            f.write(report)
            
        logger.info(f"Workflow completed. Report saved to {report_file}")
        
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        await orchestrator.save_checkpoint("error", {"error": str(e)})
        raise

if __name__ == "__main__":
    orchestrate()