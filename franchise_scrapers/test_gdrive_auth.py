#!/usr/bin/env python3
"""Test Google Drive OAuth2 authentication."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Set the client_secret.json path BEFORE any imports
os.environ["GDRIVE_CREDS_JSON"] = str(Path(__file__).parent.parent / "storage" / "client_secret.json")

# Now import after setting the environment variable
from storage.google_drive import DriveManager

def test_oauth2_auth():
    """Test OAuth2 authentication with Google Drive."""
    print("Testing Google Drive OAuth2 Authentication")
    print("=" * 50)
    
    try:
        # Check if client_secret.json exists
        client_secret_path = Path(__file__).parent.parent / "storage" / "client_secret.json"
        if not client_secret_path.exists():
            print(f"[ERROR] Error: client_secret.json not found at {client_secret_path}")
            return False
            
        print(f"[SUCCESS] Found client_secret.json at {client_secret_path}")
        
        # Initialize DriveManager with OAuth2
        print("\nInitializing DriveManager with OAuth2...")
        drive_manager = DriveManager(use_oauth2=True, token_file="wi_scraper_token.pickle")
        
        # Test connection by verifying permissions
        print("\nVerifying Google Drive permissions...")
        if drive_manager.verify_permissions():
            print("[SUCCESS] Successfully authenticated and verified permissions!")
            return True
        else:
            print("[ERROR] Failed to verify permissions")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error during authentication: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_oauth2_auth()
    if success:
        print("\n[SUCCESS] OAuth2 authentication test passed! You can now run the WI_Scraper.py")
    else:
        print("\n[WARNING] Please fix the authentication issues before running the scraper")