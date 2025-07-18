#!/usr/bin/env python
"""
Deploy State Portal Scraping Flows to Prefect

This script deploys the state portal scraping flows using the new base flow architecture.

Usage:
    python scripts/deploy_state_flows.py --state all
    python scripts/deploy_state_flows.py --state minnesota
    python scripts/deploy_state_flows.py --state wisconsin
"""

import sys
from pathlib import Path
from typing import List, Optional
import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prefect import serve
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import CronSchedule

from flows.base_state_flow import scrape_state_flow
from flows.state_configs import MINNESOTA_CONFIG, WISCONSIN_CONFIG, get_state_config
from utils.logging import get_logger

logger = get_logger(__name__)


def create_state_deployment(state_code: str) -> Deployment:
    """Create a deployment for a specific state."""
    state_config = get_state_config(state_code)

    # Define schedule based on state
    schedules = {
        "MN": CronSchedule(
            cron="0 6 * * *", timezone="America/Chicago"
        ),  # 6 AM CT daily
        "WI": CronSchedule(
            cron="0 7 * * *", timezone="America/Chicago"
        ),  # 7 AM CT daily
    }

    deployment = scrape_state_flow.to_deployment(
        name=f"{state_config.state_name.lower()}-scrape",
        description=f"Scrape {state_config.state_name} {state_config.portal_name} portal for FDD documents",
        tags=[
            "state-scraper",
            state_code.lower(),
            state_config.portal_name.lower(),
            "production",
        ],
        schedule=schedules.get(state_code),
        parameters={
            "state_config": state_config.model_dump(),
            "download_documents": True,
            "max_documents": None,  # No limit in production
        },
        work_pool_name="default-agent-pool",
        version="2.0",  # Version 2.0 indicates base flow architecture
    )

    logger.info(f"Created deployment for {state_config.state_name}")
    return deployment


def create_test_deployment(state_code: str) -> Deployment:
    """Create a test deployment with limited scraping."""
    state_config = get_state_config(state_code)

    deployment = scrape_state_flow.to_deployment(
        name=f"{state_config.state_name.lower()}-test",
        description=f"Test deployment for {state_config.state_name} scraper",
        tags=["state-scraper", state_code.lower(), "test"],
        parameters={
            "state_config": state_config.model_dump(),
            "download_documents": False,  # Don't download in test mode
            "max_documents": 5,  # Limit to 5 documents for testing
        },
        work_pool_name="default-agent-pool",
        version="2.0-test",
    )

    logger.info(f"Created test deployment for {state_config.state_name}")
    return deployment


@click.command()
@click.option(
    "--state", type=click.Choice(["minnesota", "wisconsin", "all"]), default="all"
)
@click.option(
    "--mode", type=click.Choice(["production", "test", "both"]), default="production"
)
@click.option("--serve-flows", is_flag=True, help="Start serving the deployed flows")
async def deploy(state: str, mode: str, serve_flows: bool):
    """Deploy state scraping flows to Prefect."""

    deployments = []
    states_to_deploy = []

    # Determine which states to deploy
    if state == "all":
        states_to_deploy = ["MN", "WI"]
    elif state == "minnesota":
        states_to_deploy = ["MN"]
    elif state == "wisconsin":
        states_to_deploy = ["WI"]

    # Create deployments based on mode
    for state_code in states_to_deploy:
        if mode in ["production", "both"]:
            deployments.append(create_state_deployment(state_code))

        if mode in ["test", "both"]:
            deployments.append(create_test_deployment(state_code))

    logger.info(f"Created {len(deployments)} deployments")

    # Apply deployments
    for deployment in deployments:
        try:
            deployment_id = await deployment.apply()
            logger.info(f"Applied deployment: {deployment.name} (ID: {deployment_id})")
        except Exception as e:
            logger.error(f"Failed to apply deployment {deployment.name}: {e}")

    # Serve flows if requested
    if serve_flows and deployments:
        logger.info("Starting flow server...")
        await serve(*deployments)


if __name__ == "__main__":
    import asyncio

    asyncio.run(deploy())
