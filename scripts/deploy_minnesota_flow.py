#!/usr/bin/env python3
"""
Deployment script for Minnesota scraping flow.

This script demonstrates how to deploy and schedule the Minnesota scraping flow
using Prefect. It creates a deployment that can be scheduled to run weekly.
"""

import asyncio
from datetime import timedelta

from prefect import serve
from prefect.client.schemas.schedules import IntervalSchedule

from flows.scrape_minnesota import scrape_minnesota_flow


async def deploy_minnesota_flow():
    """Deploy the Minnesota scraping flow with weekly scheduling."""
    
    print("Deploying Minnesota scraping flow...")
    
    # Create deployment with weekly schedule
    deployment = await scrape_minnesota_flow.to_deployment(
        name="minnesota-weekly-scrape",
        description="Weekly scraping of Minnesota franchise portal for FDD documents",
        tags=["scraping", "minnesota", "fdd", "weekly"],
        parameters={
            "download_documents": True,
            "max_documents": None,  # No limit for production
        },
        schedule=IntervalSchedule(
            interval=timedelta(weeks=1),
            anchor_date="2024-01-01T09:00:00",  # Monday 9 AM
        ),
        work_pool_name="default",
    )
    
    print(f"✅ Deployment created: {deployment.name}")
    print(f"   Schedule: Weekly on Mondays at 9:00 AM")
    print(f"   Tags: {deployment.tags}")
    
    return deployment


async def test_minnesota_flow():
    """Test the Minnesota flow with limited parameters."""
    
    print("Testing Minnesota scraping flow...")
    
    try:
        # Run with test parameters
        result = await scrape_minnesota_flow(
            download_documents=False,  # Don't download for testing
            max_documents=3,  # Limit to 3 documents for testing
        )
        
        print("✅ Test completed successfully!")
        print(f"   Documents discovered: {result.get('documents_discovered', 0)}")
        print(f"   Metadata records created: {result.get('metadata_records_created', 0)}")
        print(f"   Success: {result.get('success', False)}")
        
        if not result.get('success', False):
            print(f"   Error: {result.get('error', 'Unknown error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return {"success": False, "error": str(e)}


def print_deployment_instructions():
    """Print instructions for deploying and managing the flow."""
    
    print("\n" + "="*60)
    print("MINNESOTA FLOW DEPLOYMENT INSTRUCTIONS")
    print("="*60)
    
    print("\n1. Start Prefect Server (if not already running):")
    print("   prefect server start")
    
    print("\n2. Deploy the flow:")
    print("   python scripts/deploy_minnesota_flow.py")
    
    print("\n3. Start a Prefect Agent:")
    print("   prefect agent start -q default")
    
    print("\n4. Monitor flows in the Prefect UI:")
    print("   http://localhost:4200")
    
    print("\n5. Manual flow execution:")
    print("   prefect deployment run scrape-minnesota-portal/minnesota-weekly-scrape")
    
    print("\n6. View flow runs:")
    print("   prefect flow-run ls")
    
    print("\n" + "="*60)
    print("FLOW CONFIGURATION")
    print("="*60)
    
    print("\nEnvironment Variables Required:")
    print("   - SUPABASE_URL: Your Supabase project URL")
    print("   - SUPABASE_SERVICE_KEY: Your Supabase service key")
    print("   - GDRIVE_FOLDER_ID: Google Drive folder ID for document storage")
    print("   - GDRIVE_CREDS_JSON: Path to Google Drive service account JSON")
    
    print("\nOptional Environment Variables:")
    print("   - GEMINI_API_KEY: For enhanced LLM processing")
    print("   - OPENAI_API_KEY: For fallback LLM processing")
    print("   - OLLAMA_BASE_URL: For local LLM processing")
    
    print("\n" + "="*60)
    print("MONITORING AND ALERTING")
    print("="*60)
    
    print("\nThe flow includes comprehensive monitoring:")
    print("   ✓ Structured logging with context preservation")
    print("   ✓ Performance metrics collection")
    print("   ✓ Error tracking and retry logic")
    print("   ✓ Success/failure rate monitoring")
    print("   ✓ Document processing statistics")
    
    print("\nMetrics are stored in the pipeline_logs table and can be")
    print("queried for operational dashboards and alerting.")


async def main():
    """Main function to demonstrate deployment and testing."""
    
    print("Minnesota Scraping Flow Deployment Tool")
    print("="*50)
    
    # Print deployment instructions
    print_deployment_instructions()
    
    print("\n" + "="*60)
    print("DEPLOYMENT SIMULATION")
    print("="*60)
    
    try:
        # Simulate deployment creation
        deployment = await deploy_minnesota_flow()
        print(f"\n✅ Deployment simulation successful!")
        
    except Exception as e:
        print(f"\n❌ Deployment simulation failed: {e}")
        print("This is expected if Prefect server is not running.")
    
    print("\n" + "="*60)
    print("FLOW TEST SIMULATION")
    print("="*60)
    
    try:
        # Simulate flow test (this will fail without proper setup)
        result = await test_minnesota_flow()
        
    except Exception as e:
        print(f"\n❌ Flow test simulation failed: {e}")
        print("This is expected without proper database and scraper setup.")
    
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    
    print("\n1. Set up your environment variables")
    print("2. Start the Prefect server")
    print("3. Run this script to deploy the flow")
    print("4. Start a Prefect agent")
    print("5. Monitor the flow execution in the Prefect UI")
    
    print(f"\nThe Minnesota scraping flow is ready for deployment!")


if __name__ == "__main__":
    asyncio.run(main())