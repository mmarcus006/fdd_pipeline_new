"""Configuration management for FDD Pipeline."""

import os
from pathlib import Path
from typing import Optional, List
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str

    # Google Drive
    gdrive_creds_json: str = "gdrive_cred.json"
    gdrive_folder_id: str

    # LLM APIs
    gemini_api_key: str
    openai_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"

    # MinerU Web API
    mineru_auth_file: str = "mineru_auth.json"

    # Section Detection
    use_enhanced_section_detection: bool = True
    enhanced_detection_confidence_threshold: float = 0.7
    enhanced_detection_min_fuzzy_score: int = 80

    # Application
    debug: bool = False
    log_level: str = "INFO"
    max_concurrent_extractions: int = 5

    # Paths
    base_dir: Path = Path(__file__).parent
    logs_dir: Path = base_dir / "logs"
    temp_dir: Path = base_dir / ".temp"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_logs_dir() -> Path:
    """Get logs directory path."""
    settings = get_settings()
    settings.logs_dir.mkdir(exist_ok=True)
    return settings.logs_dir


def get_alert_recipients() -> List[str]:
    """Get alert email recipients."""
    # This could be configured via environment variables
    return []


# Convenience access
settings = get_settings()
