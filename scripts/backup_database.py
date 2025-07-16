#!/usr/bin/env python
"""
Database Backup Script

Creates backups of FDD Pipeline database.
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from utils.logging import get_logger

logger = get_logger("database_backup")


def backup_database(output_dir: str = "backups", compress: bool = True):
    """Create a database backup."""
    settings = get_settings()
    
    # Create backup directory
    backup_dir = Path(output_dir)
    backup_dir.mkdir(exist_ok=True)
    
    # Generate backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"fdd_pipeline_backup_{timestamp}.sql"
    
    # Get database URL
    db_url = settings.database_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No database URL configured")
        return False
    
    try:
        logger.info(f"Starting database backup to {backup_file}")
        
        # Use pg_dump for PostgreSQL
        cmd = ["pg_dump", db_url, "-f", str(backup_file)]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Backup failed: {result.stderr}")
            return False
        
        # Compress if requested
        if compress:
            logger.info("Compressing backup...")
            import gzip
            
            compressed_file = backup_file.with_suffix(".sql.gz")
            
            with open(backup_file, 'rb') as f_in:
                with gzip.open(compressed_file, 'wb') as f_out:
                    f_out.writelines(f_in)
            
            # Remove uncompressed file
            backup_file.unlink()
            backup_file = compressed_file
        
        # Get file size
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        
        logger.info(f"Backup completed successfully: {backup_file} ({size_mb:.2f} MB)")
        
        # Clean old backups (keep last 7 days)
        clean_old_backups(backup_dir, days=7)
        
        return True
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        return False


def clean_old_backups(backup_dir: Path, days: int = 7):
    """Remove backups older than specified days."""
    cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
    
    for backup_file in backup_dir.glob("fdd_pipeline_backup_*.sql*"):
        if backup_file.stat().st_mtime < cutoff_time:
            logger.info(f"Removing old backup: {backup_file}")
            backup_file.unlink()


def restore_database(backup_file: str):
    """Restore database from backup."""
    settings = get_settings()
    
    backup_path = Path(backup_file)
    if not backup_path.exists():
        logger.error(f"Backup file not found: {backup_file}")
        return False
    
    # Get database URL
    db_url = settings.database_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No database URL configured")
        return False
    
    try:
        # Decompress if needed
        if backup_path.suffix == ".gz":
            logger.info("Decompressing backup...")
            import gzip
            
            decompressed_file = backup_path.with_suffix("")
            
            with gzip.open(backup_path, 'rb') as f_in:
                with open(decompressed_file, 'wb') as f_out:
                    f_out.writelines(f_in)
            
            backup_path = decompressed_file
        
        logger.info(f"Restoring database from {backup_path}")
        
        # Use psql for restore
        cmd = ["psql", db_url, "-f", str(backup_path)]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Restore failed: {result.stderr}")
            return False
        
        logger.info("Database restored successfully")
        return True
        
    except Exception as e:
        logger.error(f"Restore error: {e}")
        return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="FDD Pipeline Database Backup")
    parser.add_argument(
        "action",
        choices=["backup", "restore"],
        help="Action to perform"
    )
    parser.add_argument(
        "--file",
        help="Backup file for restore operation"
    )
    parser.add_argument(
        "--output-dir",
        default="backups",
        help="Output directory for backups (default: backups)"
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Don't compress backup files"
    )
    
    args = parser.parse_args()
    
    if args.action == "backup":
        success = backup_database(
            output_dir=args.output_dir,
            compress=not args.no_compress
        )
        sys.exit(0 if success else 1)
        
    elif args.action == "restore":
        if not args.file:
            parser.error("--file is required for restore operation")
        
        success = restore_database(args.file)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()