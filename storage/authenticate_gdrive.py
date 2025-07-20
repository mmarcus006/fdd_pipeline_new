#!/usr/bin/env python
"""Script to authenticate Google Drive with OAuth2."""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from storage.google_drive import get_drive_manager


def main():
    """Run OAuth2 authentication for Google Drive."""
    print("Google Drive OAuth2 Authentication")
    print("=" * 50)
    
    # Force OAuth2 mode
    os.environ["GDRIVE_USE_OAUTH2"] = "true"
    
    print("\nInitializing Google Drive with OAuth2...")
    print("A browser window will open for authentication.")
    print("If running on a server without a browser, the script will provide a URL to visit.")
    print()
    
    try:
        # Get drive manager - this will trigger authentication if needed
        manager = get_drive_manager(use_oauth2=True)
        
        # Test the connection
        print("Testing connection...")
        if manager.verify_permissions():
            print("✅ Authentication successful! Permissions verified.")
            print(f"✅ Token saved to: {manager.token_file}")
        else:
            print("❌ Authentication succeeded but permission test failed.")
            print("   Check that the authenticated account has access to the folder.")
    
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("\nMake sure you have:")
        print("1. Set GDRIVE_CREDS_JSON to your OAuth2 client credentials file")
        print("2. The credentials file is a valid OAuth2 client configuration")
        print("3. Internet connection to complete the OAuth flow")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())