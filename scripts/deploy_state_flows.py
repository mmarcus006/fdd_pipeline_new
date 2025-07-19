#!/usr/bin/env python
"""
Deploy State Portal Scraping Flows to Prefect

This script deploys the state portal scraping flows using the new base flow architecture.
Uses the new Prefect flow.deploy() API instead of the deprecated Deployment class.

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
from prefect.schedules import CronSchedule

from workflows.base_state_flow import scrape_state_flow
from workflows.state_configs import MINNESOTA_CONFIG, WISCONSIN_CONFIG, get_state_config
from utils.logging import get_logger

logger = get_logger(__name__)


async def deploy_state_flow(state_code: str, test_mode: bool = False):
    """Deploy a flow for a specific state."""
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

    deployment_name = f"{state_config.state_name.lower()}-{'test' if test_mode else 'scrape'}"
    
    await scrape_state_flow.deploy(
        name=deployment_name,
        description=f"{'Test deployment for' if test_mode else 'Scrape'} {state_config.state_name} {state_config.portal_name} portal",
        tags=[
            "state-scraper",
            state_code.lower(),
            state_config.portal_name.lower(),
            "test" if test_mode else "production",
        ],
        schedules=[schedules.get(state_code)] if not test_mode and state_code in schedules else [],
        parameters={
            "state_config": state_config,
            "download_documents": not test_mode,
            "max_documents": 5 if test_mode else None,
        },
        work_pool_name="default-agent-pool",
        version="2.0-test" if test_mode else "2.0",
    )

    logger.info(f"Deployed {'test ' if test_mode else ''}deployment for {state_config.state_name}")
    return deployment_name




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

    deployment_names = []
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
        try:
            if mode in ["production", "both"]:
                name = await deploy_state_flow(state_code, test_mode=False)
                deployment_names.append(name)

            if mode in ["test", "both"]:
                name = await deploy_state_flow(state_code, test_mode=True)
                deployment_names.append(name)
        except Exception as e:
            logger.error(f"Failed to deploy flow for {state_code}: {e}")

    logger.info(f"Deployed {len(deployment_names)} flows")

    # Serve flows if requested
    if serve_flows:
        logger.info("Starting flow server...")
        # For serving, we need to create the flow instances with parameters
        flows_to_serve = []
        for state_code in states_to_deploy:
            state_config = get_state_config(state_code)
            if mode in ["production", "both"]:
                flows_to_serve.append(
                    scrape_state_flow.with_options(
                        name=f"{state_config.state_name.lower()}-scrape"
                    )
                )
            if mode in ["test", "both"]:
                flows_to_serve.append(
                    scrape_state_flow.with_options(
                        name=f"{state_config.state_name.lower()}-test"
                    )
                )
        
        if flows_to_serve:
            await serve(*flows_to_serve)


if __name__ == "__main__":
    import asyncio

    asyncio.run(deploy())
