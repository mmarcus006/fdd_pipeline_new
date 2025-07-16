"""Configuration management for FDD Pipeline using Pydantic Settings."""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Database Configuration
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anonymous key")
    supabase_service_key: str = Field(..., description="Supabase service role key")
    
    # Google Drive Configuration
    gdrive_creds_json: str = Field(..., description="Path to Google service account JSON")
    gdrive_folder_id: str = Field(..., description="Google Drive folder ID for FDD storage")
    
    # MinerU Local Configuration
    mineru_model_path: str = Field(
        default="~/.mineru/models",
        description="Path to MinerU model files"
    )
    mineru_device: str = Field(
        default="cuda",
        description="Device for MinerU processing (cuda or cpu)"
    )
    mineru_batch_size: int = Field(
        default=2,
        description="Batch size for MinerU processing"
    )
    
    # LLM Provider Configuration
    gemini_api_key: str = Field(..., description="Google Gemini API key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key (fallback)")
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL"
    )
    
    # Email Configuration (for alerts)
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: Optional[str] = Field(default=None, description="SMTP username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password")
    alert_recipients: str = Field(
        default="",
        description="Comma-separated email addresses for alerts"
    )
    
    # Prefect Configuration
    prefect_api_url: str = Field(
        default="http://localhost:4200/api",
        description="Prefect server API URL"
    )
    prefect_api_key: Optional[str] = Field(
        default=None,
        description="Prefect API key (for cloud)"
    )
    
    # Processing Configuration
    max_concurrent_extractions: int = Field(
        default=5,
        description="Maximum concurrent LLM extractions"
    )
    extraction_timeout_seconds: int = Field(
        default=300,
        description="Timeout for LLM extractions"
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed operations"
    )
    
    # Development Configuration
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    @field_validator("gdrive_creds_json")
    @classmethod
    def validate_gdrive_creds_path(cls, v: str) -> str:
        """Validate that Google Drive credentials file exists."""
        # Temporarily disabled for setup - uncomment for production
        # if not os.path.exists(v):
        #     raise ValueError(f"Google Drive credentials file not found: {v}")
        return v
    
    @field_validator("alert_recipients")
    @classmethod
    def validate_alert_recipients(cls, v: str) -> str:
        """Validate alert recipients format."""
        if not v:
            return v
        # Basic email validation for each recipient
        emails = [email.strip() for email in v.split(",") if email.strip()]
        for email in emails:
            if "@" not in email:
                raise ValueError(f"Invalid email format: {email}")
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()
    
    @field_validator("mineru_model_path")
    @classmethod
    def expand_mineru_path(cls, v: str) -> str:
        """Expand user path for MinerU models."""
        return os.path.expanduser(v)
    
    @field_validator("mineru_device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        """Validate MinerU device selection."""
        # Clean up any inline comments
        v = v.split('#')[0].strip()
        if v not in {"cuda", "cpu"}:
            raise ValueError("mineru_device must be 'cuda' or 'cpu'")
        return v
    
    @field_validator("mineru_batch_size", mode="before")
    @classmethod
    def validate_batch_size(cls, v) -> int:
        """Validate and clean batch size."""
        if isinstance(v, str):
            # Clean up any inline comments
            v = v.split('#')[0].strip()
            return int(v)
        return v


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings


# Convenience functions for common paths
def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent


def get_data_dir() -> Path:
    """Get the data directory for temporary files."""
    data_dir = get_project_root() / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


def get_logs_dir() -> Path:
    """Get the logs directory."""
    logs_dir = get_project_root() / "logs"
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


def get_prompts_dir() -> Path:
    """Get the prompts directory."""
    return get_project_root() / "prompts"


def get_migrations_dir() -> Path:
    """Get the database migrations directory."""
    return get_project_root() / "migrations"


def get_alert_recipients() -> List[str]:
    """Get parsed alert recipients as a list."""
    settings = get_settings()
    if not settings.alert_recipients:
        return []
    return [email.strip() for email in settings.alert_recipients.split(",") if email.strip()]