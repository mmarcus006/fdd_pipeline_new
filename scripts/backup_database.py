#!/usr/bin/env python
"""
Database Backup Script

Creates backups of FDD Pipeline database.
"""

import os
import sys
import subprocess
import logging
import time
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from utils.logging import get_logger

logger = get_logger("database_backup")


def backup_database(output_dir: str = "backups", compress: bool = True):
    """Create a database backup."""
    start_time = time.time()
    logger.debug(f"Starting backup_database with output_dir={output_dir}, compress={compress}")
    
    settings = get_settings()
    logger.debug(f"Settings loaded: database_url={'configured' if settings.database_url else 'not configured'}")

    # Create backup directory
    backup_dir = Path(output_dir)
    logger.debug(f"Creating backup directory: {backup_dir.absolute()}")
    backup_dir.mkdir(exist_ok=True)

    # Generate backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"fdd_pipeline_backup_{timestamp}.sql"
    logger.debug(f"Generated backup filename: {backup_file}")

    # Get database URL
    db_url = settings.database_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No database URL configured in settings or environment")
        return False
    
    logger.debug("Database URL found, proceeding with backup")

    try:
        logger.info(f"Starting database backup to {backup_file}")

        # Use pg_dump for PostgreSQL
        cmd = ["pg_dump", db_url, "-f", str(backup_file)]
        logger.debug(f"Executing command: pg_dump [DATABASE_URL] -f {backup_file}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        logger.debug(f"pg_dump completed with return code: {result.returncode}")

        if result.returncode != 0:
            logger.error(f"Backup failed with return code {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            if result.stdout:
                logger.debug(f"stdout: {result.stdout}")
            return False

        # Verify backup file exists
        if not backup_file.exists():
            logger.error(f"Backup file was not created: {backup_file}")
            return False
        
        original_size = backup_file.stat().st_size
        logger.debug(f"Backup file created successfully, size: {original_size / (1024 * 1024):.2f} MB")

        # Compress if requested
        if compress:
            logger.info("Compressing backup...")
            import gzip

            compressed_file = backup_file.with_suffix(".sql.gz")
            logger.debug(f"Compressing to: {compressed_file}")

            compress_start = time.time()
            with open(backup_file, "rb") as f_in:
                with gzip.open(compressed_file, "wb", compresslevel=9) as f_out:
                    f_out.writelines(f_in)
            
            compress_time = time.time() - compress_start
            compressed_size = compressed_file.stat().st_size
            compression_ratio = (1 - compressed_size / original_size) * 100
            
            logger.debug(f"Compression completed in {compress_time:.2f}s")
            logger.debug(f"Compressed size: {compressed_size / (1024 * 1024):.2f} MB")
            logger.debug(f"Compression ratio: {compression_ratio:.1f}%")

            # Remove uncompressed file
            logger.debug(f"Removing uncompressed file: {backup_file}")
            backup_file.unlink()
            backup_file = compressed_file

        # Get final file size
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        elapsed_time = time.time() - start_time

        logger.info(f"Backup completed successfully: {backup_file} ({size_mb:.2f} MB) in {elapsed_time:.2f}s")

        # Clean old backups (keep last 7 days)
        logger.debug("Cleaning old backups...")
        clean_old_backups(backup_dir, days=7)

        return True

    except subprocess.SubprocessError as e:
        logger.error(f"Subprocess error during backup: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during backup: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return False


def clean_old_backups(backup_dir: Path, days: int = 7):
    """Remove backups older than specified days."""
    logger.debug(f"Cleaning backups older than {days} days from {backup_dir}")
    
    cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
    cutoff_date = datetime.fromtimestamp(cutoff_time)
    logger.debug(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    removed_count = 0
    total_size_removed = 0

    try:
        backup_files = list(backup_dir.glob("fdd_pipeline_backup_*.sql*"))
        logger.debug(f"Found {len(backup_files)} backup files to check")
        
        for backup_file in backup_files:
            file_mtime = backup_file.stat().st_mtime
            file_date = datetime.fromtimestamp(file_mtime)
            file_age_days = (datetime.now() - file_date).days
            
            logger.debug(f"Checking {backup_file.name}: age={file_age_days} days")
            
            if file_mtime < cutoff_time:
                file_size = backup_file.stat().st_size
                logger.info(f"Removing old backup: {backup_file.name} (age: {file_age_days} days, size: {file_size / (1024 * 1024):.2f} MB)")
                backup_file.unlink()
                removed_count += 1
                total_size_removed += file_size
            else:
                logger.debug(f"Keeping {backup_file.name} (age: {file_age_days} days)")
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} old backups, freed {total_size_removed / (1024 * 1024):.2f} MB")
        else:
            logger.debug("No old backups to remove")
            
    except Exception as e:
        logger.error(f"Error cleaning old backups: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")


def restore_database(backup_file: str):
    """Restore database from backup."""
    start_time = time.time()
    logger.debug(f"Starting restore_database with backup_file={backup_file}")
    
    settings = get_settings()
    logger.debug(f"Settings loaded: database_url={'configured' if settings.database_url else 'not configured'}")

    backup_path = Path(backup_file)
    if not backup_path.exists():
        logger.error(f"Backup file not found: {backup_file}")
        return False
    
    file_size = backup_path.stat().st_size / (1024 * 1024)
    logger.debug(f"Backup file found: {backup_path.absolute()} ({file_size:.2f} MB)")

    # Get database URL
    db_url = settings.database_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No database URL configured in settings or environment")
        return False
    
    logger.debug("Database URL found, proceeding with restore")

    try:
        # Decompress if needed
        if backup_path.suffix == ".gz":
            logger.info("Decompressing backup...")
            import gzip

            decompressed_file = backup_path.with_suffix("")
            logger.debug(f"Decompressing to: {decompressed_file}")

            decompress_start = time.time()
            with gzip.open(backup_path, "rb") as f_in:
                with open(decompressed_file, "wb") as f_out:
                    while True:
                        chunk = f_in.read(1024 * 1024)  # Read in 1MB chunks
                        if not chunk:
                            break
                        f_out.write(chunk)
            
            decompress_time = time.time() - decompress_start
            decompressed_size = decompressed_file.stat().st_size / (1024 * 1024)
            
            logger.debug(f"Decompression completed in {decompress_time:.2f}s")
            logger.debug(f"Decompressed size: {decompressed_size:.2f} MB")

            backup_path = decompressed_file
            
            # Clean up temporary file after restore
            temp_file_to_remove = decompressed_file
        else:
            temp_file_to_remove = None

        logger.info(f"Restoring database from {backup_path}")
        logger.warning("WARNING: This will overwrite existing database data!")

        # Use psql for restore
        cmd = ["psql", db_url, "-f", str(backup_path)]
        logger.debug(f"Executing command: psql [DATABASE_URL] -f {backup_path}")

        restore_start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        restore_time = time.time() - restore_start
        
        logger.debug(f"psql completed with return code: {result.returncode} in {restore_time:.2f}s")

        if result.returncode != 0:
            logger.error(f"Restore failed with return code {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            if result.stdout:
                logger.debug(f"stdout: {result.stdout}")
            return False

        # Clean up temporary decompressed file
        if temp_file_to_remove and temp_file_to_remove.exists():
            logger.debug(f"Removing temporary decompressed file: {temp_file_to_remove}")
            temp_file_to_remove.unlink()

        elapsed_time = time.time() - start_time
        logger.info(f"Database restored successfully in {elapsed_time:.2f}s")
        
        # Log some restore statistics if available
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            logger.debug(f"Restore output lines: {len(lines)}")
            
        return True

    except subprocess.SubprocessError as e:
        logger.error(f"Subprocess error during restore: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during restore: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FDD Pipeline Database Backup and Restore Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a backup (compressed by default)
  %(prog)s backup
  
  # Create a backup without compression
  %(prog)s backup --no-compress
  
  # Create a backup in a specific directory
  %(prog)s backup --output-dir /path/to/backups
  
  # Restore from a backup file
  %(prog)s restore --file backups/fdd_pipeline_backup_20240115_120000.sql.gz
  
  # Enable debug logging
  %(prog)s backup --debug
        """
    )
    
    parser.add_argument(
        "action", choices=["backup", "restore"], help="Action to perform"
    )
    parser.add_argument("--file", help="Backup file for restore operation")
    parser.add_argument(
        "--output-dir",
        default="backups",
        help="Output directory for backups (default: backups)",
    )
    parser.add_argument(
        "--no-compress", action="store_true", help="Don't compress backup files"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    # Set up logging based on arguments
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'backup_database_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        logger.debug("Debug logging enabled")
    elif args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
    else:
        # Default logging is already configured by get_logger
        pass

    logger.debug(f"Script started with arguments: {vars(args)}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Python version: {sys.version}")

    try:
        if args.action == "backup":
            logger.info("Starting database backup operation")
            success = backup_database(
                output_dir=args.output_dir, compress=not args.no_compress
            )
            
            if success:
                logger.info("✓ Database backup completed successfully")
                print("\n✓ Database backup completed successfully")
            else:
                logger.error("✗ Database backup failed")
                print("\n✗ Database backup failed", file=sys.stderr)
                
            sys.exit(0 if success else 1)

        elif args.action == "restore":
            if not args.file:
                parser.error("--file is required for restore operation")
            
            logger.info(f"Starting database restore from {args.file}")
            
            # Confirm restore operation
            if not args.debug:  # Skip confirmation in debug mode for automation
                print(f"\nWARNING: This will restore the database from '{args.file}'")
                print("This operation will OVERWRITE all existing data in the database!")
                response = input("Are you sure you want to continue? (yes/no): ")
                if response.lower() != 'yes':
                    logger.info("Restore operation cancelled by user")
                    print("Restore operation cancelled")
                    sys.exit(0)

            success = restore_database(args.file)
            
            if success:
                logger.info("✓ Database restore completed successfully")
                print("\n✓ Database restore completed successfully")
            else:
                logger.error("✗ Database restore failed")
                print("\n✗ Database restore failed", file=sys.stderr)
                
            sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        print("\nOperation interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
