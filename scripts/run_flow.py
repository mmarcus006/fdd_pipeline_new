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
import os
import time
import logging
from pathlib import Path
from datetime import datetime
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
    type=click.Choice(["minnesota", "wisconsin", "all"]),
    required=True,
    help="State to scrape (or 'all' for both)",
)
@click.option("--test-mode", is_flag=True, help="Run in test mode (no downloads)")
@click.option("--limit", type=int, help="Limit number of documents to process")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
async def run_flow(state: str, test_mode: bool, limit: int, debug: bool, verbose: bool, dry_run: bool):
    """Run a state scraping flow directly.
    
    Examples:
        # Run Minnesota scraper
        python run_flow.py --state minnesota
        
        # Run in test mode (no downloads)
        python run_flow.py --state wisconsin --test-mode
        
        # Limit to 5 documents with debug logging
        python run_flow.py --state minnesota --limit 5 --debug
        
        # Run all states
        python run_flow.py --state all --limit 10
        
        # Dry run to see what would happen
        python run_flow.py --state wisconsin --dry-run
    """
    # Set up logging based on arguments (already handled in main())
    start_time = time.time()
    
    logger.info(f"Starting flow execution for: {state}")
    logger.debug(f"Configuration: test_mode={test_mode}, limit={limit}, dry_run={dry_run}")
    
    if dry_run:
        print("\n=== DRY RUN MODE ===")
        print(f"Would run scraper for: {state}")
        print(f"Test mode: {test_mode}")
        print(f"Download documents: {not test_mode}")
        print(f"Max documents: {limit or 'unlimited'}")
        
        if state == "all":
            print("\nWould process states: minnesota, wisconsin")
        
        print("\nNo actual scraping will be performed.")
        return

    # Determine which states to run
    states_to_run = []
    if state == "all":
        states_to_run = ["minnesota", "wisconsin"]
        logger.info("Running scrapers for all states")
    else:
        states_to_run = [state]
    
    # Track results
    results = {}
    total_scraped = 0
    total_errors = 0

    # Run flows for each state
    for state_name in states_to_run:
        state_start = time.time()
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {state_name} scraper...")
        logger.debug(f"Getting configuration for {state_name}")
        
        try:
            # Get state configuration
            state_config = get_state_config(state_name)
            logger.debug(f"State config loaded: {state_config.state_name} ({state_config.portal_name})")
            
            # Show configuration
            print(f"\n📋 Scraping {state_config.state_name} {state_config.portal_name}")
            print(f"   Mode: {'TEST' if test_mode else 'PRODUCTION'}")
            print(f"   Downloads: {'DISABLED' if test_mode else 'ENABLED'}")
            print(f"   Limit: {limit or 'None'}")
            
            # Run the flow
            logger.debug(f"Executing scrape_state_flow for {state_name}")
            result = await scrape_state_flow(
                state_config=state_config,
                download_documents=not test_mode,
                max_documents=limit,
            )
            
            state_time = time.time() - state_start
            
            # Process results
            if result:
                scraped_count = result.get('scraped', 0)
                downloaded_count = result.get('downloaded', 0)
                error_count = result.get('errors', 0)
                
                total_scraped += scraped_count
                total_errors += error_count
                
                logger.info(f"{state_name} completed in {state_time:.2f}s")
                logger.info(f"Scraped: {scraped_count}, Downloaded: {downloaded_count}, Errors: {error_count}")
                
                print(f"\n✅ {state_name} completed successfully!")
                print(f"   Time: {state_time:.2f}s")
                print(f"   Scraped: {scraped_count}")
                print(f"   Downloaded: {downloaded_count}")
                if error_count > 0:
                    print(f"   ⚠️  Errors: {error_count}")
                
                results[state_name] = {
                    'status': 'success',
                    'scraped': scraped_count,
                    'downloaded': downloaded_count,
                    'errors': error_count,
                    'time_seconds': state_time
                }
            else:
                logger.warning(f"{state_name} returned no results")
                results[state_name] = {
                    'status': 'no_results',
                    'time_seconds': state_time
                }

        except Exception as e:
            state_time = time.time() - state_start
            total_errors += 1
            
            logger.error(f"Flow failed for {state_name} after {state_time:.2f}s: {e}")
            logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
            import traceback
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
            
            print(f"\n❌ {state_name} failed: {e}")
            
            results[state_name] = {
                'status': 'error',
                'error': str(e),
                'time_seconds': state_time
            }
            
            if state != "all":
                # Re-raise if running single state
                raise
    
    # Final summary
    total_time = time.time() - start_time
    logger.info(f"\n{'='*50}")
    logger.info(f"All flows completed in {total_time:.2f}s")
    logger.info(f"Total scraped: {total_scraped}, Total errors: {total_errors}")
    logger.debug(f"Results summary: {results}")
    
    print(f"\n{'='*50}")
    print("FLOW EXECUTION SUMMARY")
    print(f"{'='*50}")
    print(f"Total time: {total_time:.2f}s")
    print(f"States processed: {len(states_to_run)}")
    print(f"Total documents scraped: {total_scraped}")
    if total_errors > 0:
        print(f"⚠️  Total errors: {total_errors}")
    
    # Detailed results
    if len(states_to_run) > 1:
        print("\nDetailed Results:")
        for state_name, result in results.items():
            status_icon = "✅" if result['status'] == 'success' else "❌"
            print(f"\n{status_icon} {state_name}:")
            print(f"   Status: {result['status']}")
            print(f"   Time: {result.get('time_seconds', 0):.2f}s")
            if result['status'] == 'success':
                print(f"   Scraped: {result.get('scraped', 0)}")
                print(f"   Downloaded: {result.get('downloaded', 0)}")
            elif result['status'] == 'error':
                print(f"   Error: {result.get('error', 'Unknown')}")


def main():
    """Main entry point with proper asyncio and logging setup."""
    # Parse args for logging setup before Click processes them
    args = sys.argv[1:]
    
    # Set up logging based on arguments
    if "--debug" in args or "-d" in args:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'run_flow_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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
        asyncio.run(run_flow.main(standalone_mode=False))
    except KeyboardInterrupt:
        logger.info("Flow execution interrupted by user")
        print("\n\nFlow cancelled by user")
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
