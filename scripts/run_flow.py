#!/usr/bin/env python
"""
Run State Portal Scraping Flows Directly

This script runs the state portal scraping flows directly without deployment.
Useful for testing and development.

Usage:
    python scripts/run_flow.py --state minnesota
    python scripts/run_flow.py --state wisconsin
    python scripts/run_flow.py --state minnesota --test-mode
    python scripts/run_flow.py --state wisconsin --limit 5
"""

import sys
from pathlib import Path
import click
import asyncio

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows.base_state_flow import scrape_state_flow
from workflows.state_configs import get_state_config
from utils.logging import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--state", 
    type=click.Choice(["minnesota", "wisconsin"]), 
    required=True,
    help="State to scrape"
)
@click.option(
    "--test-mode", 
    is_flag=True, 
    help="Run in test mode (no downloads)"
)
@click.option(
    "--limit", 
    type=int, 
    help="Limit number of documents to process"
)
async def run_flow(state: str, test_mode: bool, limit: int):
    """Run a state scraping flow directly."""
    
    logger.info(f"Running {state} scraper...")
    
    # Get state configuration
    state_config = get_state_config(state)
    
    # Run the flow
    try:
        result = await scrape_state_flow(
            state_config=state_config,
            download_documents=not test_mode,
            max_documents=limit
        )
        
        logger.info(f"Flow completed successfully")
        logger.info(f"Results: {result}")
        
    except Exception as e:
        logger.error(f"Flow failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_flow())