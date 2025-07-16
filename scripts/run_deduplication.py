#!/usr/bin/env python
"""
Run Franchise Deduplication

Identifies and merges duplicate franchise entities.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.entity_operations import EntityResolver, deduplicate_all_franchises
from utils.logging import get_logger

logger = get_logger("deduplication")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="FDD Pipeline Franchise Deduplication")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.95,
        help="Similarity threshold for deduplication (0-1, default: 0.95)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of franchises to process at once (default: 100)"
    )
    
    args = parser.parse_args()
    
    logger.info("Starting franchise deduplication process")
    logger.info(f"Settings: threshold={args.threshold}, batch_size={args.batch_size}")
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        
        # Just find duplicates without merging
        resolver = EntityResolver()
        
        # Get all franchises
        from utils.database import DatabaseManager
        db = DatabaseManager()
        franchises = db.read("franchisors", limit=1000)
        
        duplicates_found = 0
        
        for franchise in franchises:
            similar = resolver.find_similar_franchises(
                franchise['canonical_name'],
                threshold=args.threshold,
                limit=5
            )
            
            # Filter out self
            duplicates = [
                s for s in similar
                if s['id'] != franchise['id'] and s.get('similarity', 0) >= args.threshold
            ]
            
            if duplicates:
                duplicates_found += len(duplicates)
                print(f"\nPotential duplicates for '{franchise['canonical_name']}':")
                for dup in duplicates:
                    print(f"  - '{dup['canonical_name']}' (similarity: {dup['similarity']:.3f})")
        
        print(f"\nTotal potential duplicates found: {duplicates_found}")
        
    else:
        # Run actual deduplication
        try:
            stats = deduplicate_all_franchises()
            
            print("\nDeduplication Results:")
            print(f"  Franchises processed: {stats['processed']}")
            print(f"  Duplicates found: {stats['duplicates_found']}")
            print(f"  Duplicates merged: {stats['merged']}")
            print(f"  Errors: {stats['errors']}")
            
            if stats['errors'] > 0:
                logger.warning(f"Completed with {stats['errors']} errors - check logs")
                sys.exit(1)
            else:
                logger.info("Deduplication completed successfully")
                
        except Exception as e:
            logger.error(f"Deduplication failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()