#!/usr/bin/env python
"""
Serve State Portal Scraping Flows Locally

This script serves the state portal scraping flows using flow.serve() for local development.
This is simpler than deploying and is ideal for testing.

Usage:
    python scripts/serve_flows.py --state all
    python scripts/serve_flows.py --state minnesota
    python scripts/serve_flows.py --state wisconsin
"""

import sys
from pathlib import Path
import click
import asyncio

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prefect import serve
from workflows.base_state_flow import scrape_state_flow
from workflows.state_configs import MINNESOTA_CONFIG, WISCONSIN_CONFIG, get_state_config
from utils.logging import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--state", type=click.Choice(["minnesota", "wisconsin", "all"]), default="all"
)
@click.option("--port", type=int, default=4200, help="Port to serve on")
async def serve_flows(state: str, port: int):
    """Serve state scraping flows locally."""
    
    flows_to_serve = []
    
    # Determine which states to serve
    if state in ["minnesota", "all"]:
        # Create Minnesota flow with parameters
        minnesota_flow = scrape_state_flow.with_options(
            name="minnesota-scraper",
            description="Scrape Minnesota CARDS portal"
        )
        flows_to_serve.append(minnesota_flow)
        logger.info("Added Minnesota scraper to serve list")
    
    if state in ["wisconsin", "all"]:
        # Create Wisconsin flow with parameters
        wisconsin_flow = scrape_state_flow.with_options(
            name="wisconsin-scraper",
            description="Scrape Wisconsin DFI portal"
        )
        flows_to_serve.append(wisconsin_flow)
        logger.info("Added Wisconsin scraper to serve list")
    
    if not flows_to_serve:
        logger.error("No flows to serve")
        return
    
    logger.info(f"Starting flow server on port {port}...")
    logger.info("You can run flows via the Prefect UI or using the CLI:")
    
    if state in ["minnesota", "all"]:
        logger.info("  Run Minnesota: prefect deployment run 'minnesota-scraper/minnesota-scraper'")
    if state in ["wisconsin", "all"]:
        logger.info("  Run Wisconsin: prefect deployment run 'wisconsin-scraper/wisconsin-scraper'")
    
    # Serve the flows
    await serve(
        *flows_to_serve,
        webserver=True,
        port=port,
        pause_on_shutdown=False
    )


if __name__ == "__main__":
    asyncio.run(serve_flows())