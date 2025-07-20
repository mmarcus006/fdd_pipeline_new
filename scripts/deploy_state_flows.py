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
import os
import time
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime
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
    start_time = time.time()
    logger.debug(f"Starting deployment for state_code={state_code}, test_mode={test_mode}")
    
    try:
        state_config = get_state_config(state_code)
        logger.debug(f"State config loaded: {state_config.state_name} ({state_config.portal_name})")
    except Exception as e:
        logger.error(f"Failed to get state config for {state_code}: {e}")
        raise

    # Define schedule based on state
    schedules = {
        "MN": CronSchedule(
            cron="0 6 * * *", timezone="America/Chicago"
        ),  # 6 AM CT daily
        "WI": CronSchedule(
            cron="0 7 * * *", timezone="America/Chicago"
        ),  # 7 AM CT daily
    }
    
    logger.debug(f"Available schedules: {list(schedules.keys())}")

    deployment_name = (
        f"{state_config.state_name.lower()}-{'test' if test_mode else 'scrape'}"
    )
    logger.debug(f"Deployment name: {deployment_name}")
    
    # Prepare deployment parameters
    deploy_params = {
        "state_config": state_config,
        "download_documents": not test_mode,
        "max_documents": 5 if test_mode else None,
    }
    
    logger.debug(f"Deployment parameters: download_documents={deploy_params['download_documents']}, max_documents={deploy_params['max_documents']}")

    try:
        logger.info(f"Deploying flow: {deployment_name}")
        
        await scrape_state_flow.deploy(
            name=deployment_name,
            description=f"{'Test deployment for' if test_mode else 'Scrape'} {state_config.state_name} {state_config.portal_name} portal",
            tags=[
                "state-scraper",
                state_code.lower(),
                state_config.portal_name.lower(),
                "test" if test_mode else "production",
            ],
            schedules=(
                [schedules.get(state_code)]
                if not test_mode and state_code in schedules
                else []
            ),
            parameters=deploy_params,
            work_pool_name="default-agent-pool",
            version="2.0-test" if test_mode else "2.0",
        )
        
        elapsed = time.time() - start_time
        logger.info(
            f"Successfully deployed {'test ' if test_mode else ''}deployment for {state_config.state_name} in {elapsed:.2f}s"
        )
        
        # Log deployment details
        if not test_mode and state_code in schedules:
            schedule = schedules[state_code]
            logger.debug(f"Scheduled: {schedule.cron} ({schedule.timezone})")
        else:
            logger.debug("No schedule set (test mode or no schedule defined)")
            
        return deployment_name
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Failed to deploy flow after {elapsed:.2f}s: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        raise


@click.command()
@click.option(
    "--state", type=click.Choice(["minnesota", "wisconsin", "all"]), default="all"
)
@click.option(
    "--mode", type=click.Choice(["production", "test", "both"]), default="production"
)
@click.option("--serve-flows", is_flag=True, help="Start serving the deployed flows")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
async def deploy(state: str, mode: str, serve_flows: bool, debug: bool, verbose: bool):
    """Deploy state scraping flows to Prefect.
    
    Examples:
        python deploy_state_flows.py --state all
        python deploy_state_flows.py --state minnesota --mode test
        python deploy_state_flows.py --state wisconsin --mode both --serve-flows
        python deploy_state_flows.py --debug
    """
    # Set up logging based on arguments
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'deploy_state_flows_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        logger.debug("Debug logging enabled")
    elif verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    script_start = time.time()
    logger.debug(f"Script started with arguments: state={state}, mode={mode}, serve_flows={serve_flows}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Python version: {sys.version}")
    
    print(f"Deploying {state} flows in {mode} mode")
    print("=" * 40)

    deployment_names = []
    states_to_deploy = []
    failed_deployments = []

    # Determine which states to deploy
    if state == "all":
        states_to_deploy = ["MN", "WI"]
        logger.debug("Deploying all states: MN, WI")
    elif state == "minnesota":
        states_to_deploy = ["MN"]
        logger.debug("Deploying Minnesota only")
    elif state == "wisconsin":
        states_to_deploy = ["WI"]
        logger.debug("Deploying Wisconsin only")

    logger.info(f"States to deploy: {states_to_deploy}")
    logger.info(f"Deployment mode: {mode}")

    # Create deployments based on mode
    for state_code in states_to_deploy:
        try:
            if mode in ["production", "both"]:
                logger.info(f"Deploying production flow for {state_code}")
                name = await deploy_state_flow(state_code, test_mode=False)
                deployment_names.append(name)
                print(f"✓ Deployed production flow: {name}")

            if mode in ["test", "both"]:
                logger.info(f"Deploying test flow for {state_code}")
                name = await deploy_state_flow(state_code, test_mode=True)
                deployment_names.append(name)
                print(f"✓ Deployed test flow: {name}")
                
        except Exception as e:
            logger.error(f"Failed to deploy flow for {state_code}: {e}")
            logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
            import traceback
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
            failed_deployments.append((state_code, str(e)))
            print(f"✗ Failed to deploy flow for {state_code}: {e}")

    # Summary
    print("\n" + "=" * 40)
    print(f"Deployment Summary:")
    print(f"  Successful: {len(deployment_names)}")
    print(f"  Failed: {len(failed_deployments)}")
    
    if deployment_names:
        print("\nDeployed flows:")
        for name in deployment_names:
            print(f"  - {name}")
    
    if failed_deployments:
        print("\nFailed deployments:")
        for state_code, error in failed_deployments:
            print(f"  - {state_code}: {error}")
    
    elapsed = time.time() - script_start
    logger.info(f"Total deployment time: {elapsed:.2f}s")
    print(f"\nTotal time: {elapsed:.2f}s")

    # Serve flows if requested
    if serve_flows and deployment_names:
        logger.info("Starting flow server...")
        print("\nStarting flow server...")
        
        # For serving, we need to create the flow instances with parameters
        flows_to_serve = []
        for state_code in states_to_deploy:
            try:
                state_config = get_state_config(state_code)
                logger.debug(f"Creating flow instances for {state_config.state_name}")
                
                if mode in ["production", "both"]:
                    flow_name = f"{state_config.state_name.lower()}-scrape"
                    flows_to_serve.append(
                        scrape_state_flow.with_options(name=flow_name)
                    )
                    logger.debug(f"Added production flow: {flow_name}")
                    
                if mode in ["test", "both"]:
                    flow_name = f"{state_config.state_name.lower()}-test"
                    flows_to_serve.append(
                        scrape_state_flow.with_options(name=flow_name)
                    )
                    logger.debug(f"Added test flow: {flow_name}")
                    
            except Exception as e:
                logger.error(f"Failed to create flow instance for {state_code}: {e}")

        if flows_to_serve:
            logger.info(f"Serving {len(flows_to_serve)} flows")
            print(f"Serving {len(flows_to_serve)} flows...")
            try:
                await serve(*flows_to_serve)
            except KeyboardInterrupt:
                logger.info("Flow server stopped by user")
                print("\nFlow server stopped")
            except Exception as e:
                logger.error(f"Error serving flows: {e}")
                print(f"\nError serving flows: {e}")
        else:
            logger.warning("No flows to serve")
            print("No flows to serve")
    elif serve_flows:
        logger.warning("No flows deployed, nothing to serve")
        print("No flows deployed, nothing to serve")


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(deploy())
    except KeyboardInterrupt:
        print("\nDeployment cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        sys.exit(1)
