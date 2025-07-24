"""Test and manage database integration for franchise scrapers."""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from franchise_scrapers.database_integration import get_scraper_database
from storage.database.manager import get_database_manager
from utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseIntegrationTester:
    """Test and manage database integration functionality."""
    
    def __init__(self):
        self.scraper_db = get_scraper_database()
        self.db_manager = get_database_manager()
    
    def test_database_connection(self) -> bool:
        """Test database connectivity."""
        try:
            logger.info("Testing database connection...")
            health = self.db_manager.health_check.check_connection()
            
            if health["healthy"]:
                logger.info(f"✅ Database connection successful (Response time: {health['response_time_ms']}ms)")
                logger.info(f"   Supabase: {'✅' if health['supabase_connection'] else '❌'}")
                logger.info(f"   SQLAlchemy: {'✅' if health['sqlalchemy_connection'] else '❌'}")
                return True
            else:
                logger.error(f"❌ Database connection failed: {health.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            return False
    
    def check_required_tables(self) -> Dict[str, bool]:
        """Check if required tables exist."""
        required_tables = ["franchisors", "fdds", "drive_files"]
        results = {}
        
        logger.info("Checking required tables...")
        
        for table in required_tables:
            exists = self.db_manager.health_check.check_table_exists(table)
            results[table] = exists
            status = "✅" if exists else "❌"
            logger.info(f"   {table}: {status}")
        
        return results
    
    def get_database_statistics(self) -> Dict[str, Any]:
        """Get current database statistics."""
        try:
            logger.info("Getting database statistics...")
            
            stats = {}
            
            # Count franchisors
            franchisor_count = self.db_manager.count_records("franchisors")
            stats["franchisors"] = franchisor_count
            logger.info(f"   Franchisors: {franchisor_count}")
            
            # Count FDDs
            fdd_count = self.db_manager.count_records("fdds")
            stats["fdds"] = fdd_count
            logger.info(f"   FDDs: {fdd_count}")
            
            # Count FDDs by state
            mn_count = self.db_manager.count_records("fdds", {"filing_state": "MN"})
            wi_count = self.db_manager.count_records("fdds", {"filing_state": "WI"})
            stats["fdds_by_state"] = {"MN": mn_count, "WI": wi_count}
            logger.info(f"   FDDs by state - MN: {mn_count}, WI: {wi_count}")
            
            # Count drive files
            drive_files_count = self.db_manager.count_records("drive_files")
            stats["drive_files"] = drive_files_count
            logger.info(f"   Drive files: {drive_files_count}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting database statistics: {e}")
            return {}
    
    def find_duplicate_fdds(self) -> None:
        """Find and report duplicate FDDs."""
        try:
            logger.info("Searching for duplicate FDDs...")
            duplicates = self.scraper_db.get_duplicate_fdds()
            
            if duplicates:
                logger.info(f"Found {len(duplicates)} sets of duplicate FDDs:")
                for i, duplicate_set in enumerate(duplicates, 1):
                    logger.info(f"   Set {i}: {duplicate_set['count']} duplicates with hash {duplicate_set['sha256_hash'][:16]}...")
                    logger.info(f"      FDD IDs: {duplicate_set['fdd_ids']}")
            else:
                logger.info("✅ No duplicate FDDs found")
                
        except Exception as e:
            logger.error(f"Error finding duplicates: {e}")
    
    def cleanup_duplicates(self, dry_run: bool = True) -> None:
        """Clean up duplicate FDDs."""
        try:
            action = "Would clean up" if dry_run else "Cleaning up"
            logger.info(f"{action} duplicate FDDs...")
            
            stats = self.scraper_db.cleanup_duplicate_fdds(dry_run=dry_run)
            
            logger.info("Cleanup results:")
            logger.info(f"   Duplicate sets found: {stats['duplicate_sets']}")
            logger.info(f"   FDDs to delete: {stats['fdds_to_delete']}")
            if not dry_run:
                logger.info(f"   FDDs deleted: {stats['fdds_deleted']}")
            logger.info(f"   Errors: {stats['errors']}")
            
        except Exception as e:
            logger.error(f"Error cleaning up duplicates: {e}")
    
    def test_franchisor_creation(self) -> None:
        """Test franchisor creation and deduplication."""
        try:
            logger.info("Testing franchisor creation...")
            
            # Test creating a new franchisor
            test_name = "Test Franchise Corp"
            franchisor_id = self.scraper_db.find_or_create_franchisor(
                name=test_name,
                website="https://testfranchise.com",
                phone="555-123-4567"
            )
            
            logger.info(f"✅ Created/found franchisor: {franchisor_id}")
            
            # Test finding the same franchisor (should not create duplicate)
            franchisor_id2 = self.scraper_db.find_or_create_franchisor(name=test_name)
            
            if franchisor_id == franchisor_id2:
                logger.info("✅ Deduplication working - same franchisor returned")
            else:
                logger.error("❌ Deduplication failed - different IDs returned")
            
            # Clean up test data
            self.db_manager.delete_record("franchisors", franchisor_id)
            logger.info("✅ Test franchisor cleaned up")
            
        except Exception as e:
            logger.error(f"Error testing franchisor creation: {e}")
    
    def run_comprehensive_test(self) -> bool:
        """Run comprehensive database integration test."""
        logger.info("="*60)
        logger.info("COMPREHENSIVE DATABASE INTEGRATION TEST")
        logger.info("="*60)
        
        success = True
        
        # Test 1: Database connection
        logger.info("\n1. Testing database connection...")
        if not self.test_database_connection():
            success = False
        
        # Test 2: Check required tables
        logger.info("\n2. Checking required tables...")
        table_results = self.check_required_tables()
        if not all(table_results.values()):
            logger.error("❌ Some required tables are missing")
            success = False
        
        # Test 3: Get database statistics
        logger.info("\n3. Getting database statistics...")
        stats = self.get_database_statistics()
        
        # Test 4: Find duplicates
        logger.info("\n4. Checking for duplicate FDDs...")
        self.find_duplicate_fdds()
        
        # Test 5: Test franchisor creation
        logger.info("\n5. Testing franchisor creation and deduplication...")
        self.test_franchisor_creation()
        
        logger.info("\n" + "="*60)
        if success:
            logger.info("✅ ALL TESTS PASSED - Database integration is ready!")
        else:
            logger.error("❌ SOME TESTS FAILED - Check configuration and database setup")
        logger.info("="*60)
        
        return success


def main():
    """Main function for testing database integration."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test and manage database integration")
    parser.add_argument("--test", action="store_true", help="Run comprehensive test")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--duplicates", action="store_true", help="Find duplicate FDDs")
    parser.add_argument("--cleanup", action="store_true", help="Clean up duplicates (dry run)")
    parser.add_argument("--cleanup-force", action="store_true", help="Clean up duplicates (actual deletion)")
    
    args = parser.parse_args()
    
    tester = DatabaseIntegrationTester()
    
    if args.test:
        tester.run_comprehensive_test()
    elif args.stats:
        tester.get_database_statistics()
    elif args.duplicates:
        tester.find_duplicate_fdds()
    elif args.cleanup:
        tester.cleanup_duplicates(dry_run=True)
    elif args.cleanup_force:
        tester.cleanup_duplicates(dry_run=False)
    else:
        # Default: run comprehensive test
        tester.run_comprehensive_test()


if __name__ == "__main__":
    main()