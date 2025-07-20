#!/usr/bin/env python3
"""Configuration validation script for FDD Pipeline."""

import sys
import os
import time
import json
import logging
from pathlib import Path
import httpx
from google.oauth2 import service_account
from google.auth.exceptions import GoogleAuthError

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import get_settings

try:
    from utils.database import test_database_connection
except ImportError:
    def test_database_connection():
        return False


try:
    from utils.logging import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def check_supabase_connection() -> bool:
    """Check Supabase database connection."""
    logger.debug("Starting Supabase connection check")
    start_time = time.time()
    
    try:
        settings = get_settings()
        logger.debug(f"Supabase URL configured: {'Yes' if settings.supabase_url else 'No'}")
        logger.debug(f"Service key configured: {'Yes' if settings.supabase_service_key else 'No'}")
        
        success = test_database_connection()
        elapsed = time.time() - start_time
        
        if success:
            logger.debug(f"Database connection test passed in {elapsed:.2f}s")
            print("✓ Supabase connection successful")
            return True
        else:
            logger.error("Database connection test failed")
            print("✗ Supabase connection failed")
            return False
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Supabase connection error after {elapsed:.2f}s: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        print(f"✗ Supabase connection error: {e}")
        return False


def check_google_drive_auth() -> bool:
    """Check Google Drive service account authentication."""
    logger.debug("Starting Google Drive authentication check")
    start_time = time.time()
    
    try:
        settings = get_settings()
        creds_path = Path(settings.gdrive_creds_json)
        logger.debug(f"Credentials file path: {creds_path}")
        
        if not creds_path.exists():
            logger.error(f"Credentials file not found at: {creds_path.absolute()}")
            print(f"✗ Google Drive credentials file not found: {settings.gdrive_creds_json}")
            return False
            
        logger.debug(f"Credentials file size: {creds_path.stat().st_size} bytes")
        
        # Try to parse credentials file to check validity
        with open(creds_path, 'r') as f:
            creds_data = json.load(f)
            logger.debug(f"Service account email: {creds_data.get('client_email', 'Not found')}")
            logger.debug(f"Project ID: {creds_data.get('project_id', 'Not found')}")
        
        credentials = service_account.Credentials.from_service_account_file(
            str(creds_path), scopes=["https://www.googleapis.com/auth/drive"]
        )
        
        elapsed = time.time() - start_time
        logger.debug(f"Credentials loaded successfully in {elapsed:.2f}s")
        logger.debug(f"Credentials valid: {credentials.valid}")
        logger.debug(f"Credentials expired: {credentials.expired}")
        
        print("✓ Google Drive authentication successful")
        return True
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"✗ Google Drive credentials file not found: {settings.gdrive_creds_json}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in credentials file: {e}")
        print(f"✗ Google Drive credentials file is not valid JSON")
        return False
    except GoogleAuthError as e:
        logger.error(f"Google authentication error: {e}")
        print(f"✗ Google Drive authentication failed: {e}")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Unexpected error after {elapsed:.2f}s: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        print(f"✗ Google Drive authentication error: {e}")
        return False


def check_mineru_auth() -> bool:
    """Check MinerU authentication file."""
    logger.debug("Starting MinerU authentication check")
    
    try:
        settings = get_settings()
        auth_file = Path(settings.mineru_auth_file)
        logger.debug(f"MinerU auth file path: {auth_file.absolute()}")

        if auth_file.exists():
            file_size = auth_file.stat().st_size
            logger.debug(f"Auth file exists, size: {file_size} bytes")
            
            # Try to validate JSON structure
            try:
                with open(auth_file, 'r') as f:
                    auth_data = json.load(f)
                    logger.debug(f"Auth file contains {len(auth_data)} entries")
            except json.JSONDecodeError:
                logger.warning("Auth file exists but is not valid JSON")
            
            print("✓ MinerU auth file found")
            return True
        else:
            logger.info(f"MinerU auth file not found at: {auth_file.absolute()}")
            logger.debug("This is expected for first-time setup")
            print(
                f"⚠ MinerU auth file not found: {auth_file} (will be created on first use)"
            )
            return True  # Not critical for initial setup
    except Exception as e:
        logger.error(f"MinerU auth check error: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        print(f"✗ MinerU auth check error: {e}")
        return False


def check_gemini_api() -> bool:
    """Check Gemini API key validity."""
    logger.debug("Starting Gemini API validation")
    start_time = time.time()
    
    try:
        try:
            import google.generativeai as genai
            logger.debug("Google Generative AI package imported successfully")
        except ImportError as e:
            logger.error(f"Failed to import google.generativeai: {e}")
            print("✗ Google Generative AI package not installed")
            return False

        settings = get_settings()
        api_key_configured = bool(settings.gemini_api_key)
        logger.debug(f"Gemini API key configured: {api_key_configured}")
        
        if not api_key_configured:
            logger.error("No Gemini API key found in configuration")
            print("✗ Gemini API key not configured")
            return False

        logger.debug("Configuring Gemini API...")
        genai.configure(api_key=settings.gemini_api_key)  # type: ignore

        # Try to list models to validate API key
        logger.debug("Attempting to list available models...")
        models = genai.list_models()  # type: ignore
        model_list = list(models)
        
        elapsed = time.time() - start_time
        logger.debug(f"Model list retrieved in {elapsed:.2f}s")
        logger.debug(f"Found {len(model_list)} models")
        
        if model_list:
            # Log available models
            for model in model_list[:5]:  # Log first 5 models
                logger.debug(f"  - {getattr(model, 'name', 'Unknown')}")
            
            print(f"✓ Gemini API validated ({len(model_list)} models available)")
            return True
        else:
            logger.error("No models available with current API key")
            print("✗ Gemini API key invalid or no models available")
            return False
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Gemini API validation failed after {elapsed:.2f}s: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        print(f"✗ Gemini API validation failed: {e}")
        return False


def check_ollama_server() -> bool:
    """Check Ollama server connectivity."""
    logger.debug("Starting Ollama server check")
    start_time = time.time()
    
    try:
        settings = get_settings()
        ollama_url = settings.ollama_base_url
        logger.debug(f"Ollama base URL: {ollama_url}")
        
        api_endpoint = f"{ollama_url}/api/tags"
        logger.debug(f"Checking endpoint: {api_endpoint}")

        with httpx.Client(timeout=5.0) as client:
            logger.debug("Sending request to Ollama server...")
            response = client.get(api_endpoint)
            
        elapsed = time.time() - start_time
        logger.debug(f"Response received in {elapsed:.2f}s")
        logger.debug(f"Status code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            logger.debug(f"Server response parsed successfully")
            logger.debug(f"Available models: {len(models)}")
            
            # Log model details
            for model in models:
                name = model.get('name', 'Unknown')
                size = model.get('size', 0) / (1024**3)  # Convert to GB
                logger.debug(f"  - {name} ({size:.2f} GB)")
            
            print(f"✓ Ollama server running ({len(models)} models available)")
            return True
        else:
            logger.error(f"Unexpected status code: {response.status_code}")
            logger.debug(f"Response body: {response.text[:200]}...")
            print(f"✗ Ollama server returned status {response.status_code}")
            return False
            
    except httpx.ConnectError as e:
        elapsed = time.time() - start_time
        logger.error(f"Failed to connect to Ollama server after {elapsed:.2f}s")
        logger.debug(f"Connection error: {e}")
        print("✗ Ollama server not accessible (is it running?)")
        return False
    except httpx.RequestError as e:
        elapsed = time.time() - start_time
        logger.error(f"Request error after {elapsed:.2f}s: {e}")
        print("✗ Ollama server not accessible (is it running?)")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Unexpected error after {elapsed:.2f}s: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        print(f"✗ Ollama server error: {e}")
        return False


def check_smtp_configuration() -> bool:
    """Check SMTP configuration."""
    logger.debug("Checking SMTP configuration")
    
    try:
        settings = get_settings()
        
        # Check if SMTP settings exist
        smtp_configured = (
            hasattr(settings, 'smtp_server') and 
            hasattr(settings, 'smtp_port') and 
            hasattr(settings, 'smtp_username')
        )
        
        if smtp_configured:
            logger.debug(f"SMTP server: {getattr(settings, 'smtp_server', 'Not set')}")
            logger.debug(f"SMTP port: {getattr(settings, 'smtp_port', 'Not set')}")
            logger.debug(f"SMTP username: {getattr(settings, 'smtp_username', 'Not set')}")
            logger.info("SMTP configuration found")
        else:
            logger.info("SMTP configuration not found (optional)")
            
    except Exception as e:
        logger.debug(f"Error checking SMTP config: {e}")
    
    print("⚠ SMTP configuration not implemented (optional for development)")
    return True  # Non-critical for development


def check_environment_file() -> bool:
    """Check if .env file exists."""
    logger.debug("Checking for .env file")
    
    env_file = project_root / ".env"
    env_template = project_root / ".env.template"
    
    logger.debug(f"Project root: {project_root}")
    logger.debug(f"Looking for .env at: {env_file.absolute()}")
    
    if env_file.exists():
        file_size = env_file.stat().st_size
        logger.debug(f".env file found, size: {file_size} bytes")
        
        # Count number of lines/variables
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()
                var_count = sum(1 for line in lines if '=' in line and not line.strip().startswith('#'))
                logger.debug(f".env file contains {var_count} variables across {len(lines)} lines")
        except Exception as e:
            logger.debug(f"Error reading .env file: {e}")
            
        print("✓ .env file found")
        return True
    else:
        logger.error(f".env file not found at: {env_file.absolute()}")
        
        if env_template.exists():
            logger.info(f".env.template exists at: {env_template.absolute()}")
            print("✗ .env file not found (copy from .env.template)")
        else:
            logger.warning(".env.template also not found")
            print("✗ .env file not found (no template available)")
            
        return False


def main():
    """Run all configuration checks."""
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(
        description="FDD Pipeline Configuration Validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all configuration checks
  %(prog)s
  
  # Run with debug logging
  %(prog)s --debug
  
  # Save results to file
  %(prog)s --output results.txt
  
  # Check specific components only
  %(prog)s --checks database gdrive gemini
        """
    )
    
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--output", "-o", help="Save results to file"
    )
    parser.add_argument(
        "--checks", nargs="+", 
        choices=["env", "database", "gdrive", "mineru", "gemini", "ollama", "smtp"],
        help="Run specific checks only"
    )
    
    args = parser.parse_args()
    
    # Set up logging based on arguments
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'config_check_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        logger.debug("Debug logging enabled")
    elif args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    logger.debug(f"Script started with arguments: {vars(args)}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Project root: {project_root}")
    logger.debug(f"Python version: {sys.version}")
    
    start_time = time.time()
    
    print("FDD Pipeline Configuration Check")
    print("=" * 40)
    
    # Define all checks
    all_checks = {
        "env": ("Environment file", check_environment_file),
        "database": ("Supabase connection", check_supabase_connection),
        "gdrive": ("Google Drive auth", check_google_drive_auth),
        "mineru": ("MinerU auth", check_mineru_auth),
        "gemini": ("Gemini API", check_gemini_api),
        "ollama": ("Ollama server", check_ollama_server),
        "smtp": ("SMTP configuration", check_smtp_configuration),
    }
    
    # Filter checks if specific ones requested
    if args.checks:
        checks = [(all_checks[check][0], all_checks[check][1]) for check in args.checks]
        logger.debug(f"Running specific checks: {args.checks}")
    else:
        checks = [all_checks[key] for key in ["env", "database", "gdrive", "mineru", "gemini", "ollama", "smtp"]]
        logger.debug("Running all checks")

    results = []
    check_times = []
    
    for name, check_func in checks:
        print(f"\nChecking {name}...")
        check_start = time.time()
        
        try:
            logger.debug(f"Starting check: {name}")
            result = check_func()
            check_time = time.time() - check_start
            check_times.append((name, check_time))
            
            logger.debug(f"Check '{name}' completed in {check_time:.2f}s with result: {result}")
            results.append((name, result, None))
            
        except Exception as e:
            check_time = time.time() - check_start
            check_times.append((name, check_time))
            
            logger.error(f"Check '{name}' failed with exception after {check_time:.2f}s: {e}")
            logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
            import traceback
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
            
            print(f"✗ {name} check failed with exception: {e}")
            results.append((name, False, str(e)))

    print("\n" + "=" * 40)
    
    # Generate summary
    passed = sum(1 for _, result, _ in results if result)
    total = len(results)
    total_time = time.time() - start_time
    
    logger.debug(f"All checks completed in {total_time:.2f}s")
    logger.debug(f"Check times: {check_times}")
    
    # Print summary
    print("\nSummary:")
    print("-" * 40)
    for name, result, error in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}", end="")
        if error:
            print(f" ({error})")
        else:
            print()
    
    print("-" * 40)
    print(f"Total: {passed}/{total} checks passed")
    print(f"Time: {total_time:.2f}s")
    
    # Save results if requested
    if args.output:
        try:
            with open(args.output, 'w') as f:
                f.write(f"FDD Pipeline Configuration Check Results\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'=' * 40}\n\n")
                
                for name, result, error in results:
                    status = "PASS" if result else "FAIL"
                    f.write(f"{status}: {name}\n")
                    if error:
                        f.write(f"  Error: {error}\n")
                
                f.write(f"\n{'=' * 40}\n")
                f.write(f"Total: {passed}/{total} checks passed\n")
                f.write(f"Time: {total_time:.2f}s\n")
                
            logger.info(f"Results saved to: {args.output}")
            print(f"\nResults saved to: {args.output}")
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            print(f"\nWarning: Failed to save results: {e}")

    if passed == total:
        print(f"\n✓ All {total} checks passed! Configuration is ready.")
        sys.exit(0)
    else:
        print(f"\n✗ {passed}/{total} checks passed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
