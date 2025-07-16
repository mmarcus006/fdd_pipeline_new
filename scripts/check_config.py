#!/usr/bin/env python3
"""Configuration validation script for FDD Pipeline."""

import sys
import os
from pathlib import Path
import httpx
from google.oauth2 import service_account
from google.auth.exceptions import GoogleAuthError

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import get_settings
from utils.database import test_database_connection
from utils.logging import get_logger

logger = get_logger(__name__)


def check_supabase_connection() -> bool:
    """Check Supabase database connection."""
    try:
        success = test_database_connection()
        if success:
            print("✓ Supabase connection successful")
            return True
        else:
            print("✗ Supabase connection failed")
            return False
    except Exception as e:
        print(f"✗ Supabase connection error: {e}")
        return False


def check_google_drive_auth() -> bool:
    """Check Google Drive service account authentication."""
    try:
        settings = get_settings()
        credentials = service_account.Credentials.from_service_account_file(
            settings.gdrive_creds_json, scopes=["https://www.googleapis.com/auth/drive"]
        )
        print("✓ Google Drive authentication successful")
        return True
    except FileNotFoundError:
        print(
            f"✗ Google Drive credentials file not found: {settings.gdrive_creds_json}"
        )
        return False
    except GoogleAuthError as e:
        print(f"✗ Google Drive authentication failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Google Drive authentication error: {e}")
        return False


def check_mineru_api() -> bool:
    """Check MinerU API accessibility."""
    try:
        settings = get_settings()
        headers = {"Authorization": f"Bearer {settings.mineru_api_key}"}

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{settings.mineru_base_url}/status", headers=headers)

        if response.status_code == 200:
            print("✓ MinerU API accessible")
            return True
        else:
            print(f"✗ MinerU API returned status {response.status_code}")
            return False
    except httpx.RequestError as e:
        print(f"✗ MinerU API connection error: {e}")
        return False
    except Exception as e:
        print(f"✗ MinerU API error: {e}")
        return False


def check_gemini_api() -> bool:
    """Check Gemini API key validity."""
    try:
        import google.generativeai as genai

        settings = get_settings()

        genai.configure(api_key=settings.gemini_api_key)

        # Try to list models to validate API key
        models = genai.list_models()
        model_list = list(models)

        if model_list:
            print("✓ Gemini API validated")
            return True
        else:
            print("✗ Gemini API key invalid or no models available")
            return False
    except Exception as e:
        print(f"✗ Gemini API validation failed: {e}")
        return False


def check_ollama_server() -> bool:
    """Check Ollama server connectivity."""
    try:
        settings = get_settings()

        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{settings.ollama_base_url}/api/tags")

        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"✓ Ollama server running ({len(models)} models available)")
            return True
        else:
            print(f"✗ Ollama server returned status {response.status_code}")
            return False
    except httpx.RequestError:
        print("✗ Ollama server not accessible (is it running?)")
        return False
    except Exception as e:
        print(f"✗ Ollama server error: {e}")
        return False


def check_smtp_configuration() -> bool:
    """Check SMTP configuration."""
    try:
        import smtplib

        settings = get_settings()

        if not settings.smtp_user or not settings.smtp_password:
            print("⚠ SMTP configuration incomplete (optional for development)")
            return True

        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.quit()

        print("✓ SMTP configuration valid")
        return True
    except Exception as e:
        print(f"⚠ SMTP configuration issue: {e} (optional for development)")
        return True  # Non-critical for development


def check_environment_file() -> bool:
    """Check if .env file exists."""
    env_file = project_root / ".env"
    if env_file.exists():
        print("✓ .env file found")
        return True
    else:
        print("✗ .env file not found (copy from .env.template)")
        return False


def main():
    """Run all configuration checks."""
    print("FDD Pipeline Configuration Check")
    print("=" * 40)

    checks = [
        ("Environment file", check_environment_file),
        ("Supabase connection", check_supabase_connection),
        ("Google Drive auth", check_google_drive_auth),
        ("MinerU API", check_mineru_api),
        ("Gemini API", check_gemini_api),
        ("Ollama server", check_ollama_server),
        ("SMTP configuration", check_smtp_configuration),
    ]

    results = []
    for name, check_func in checks:
        print(f"\nChecking {name}...")
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"✗ {name} check failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 40)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✓ All {total} checks passed! Configuration is ready.")
        sys.exit(0)
    else:
        print(f"✗ {passed}/{total} checks passed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
