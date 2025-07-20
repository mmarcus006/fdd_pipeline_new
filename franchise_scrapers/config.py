# franchise_scrapers/config.py
from pathlib import Path
from typing import List

from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""
    
    def __init__(self):
        # Browser settings
        self.HEADLESS = os.getenv("HEADLESS", "false").lower() == "false"
        
        # Download settings
        self.DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "./downloads"))
        self.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        # Rate limiting
        self.THROTTLE_SEC = float(os.getenv("THROTTLE_SEC", "0.5"))
        
        # Retry configuration
        self.PDF_RETRY_MAX = int(os.getenv("PDF_RETRY_MAX", "3"))
        self.PDF_RETRY_BACKOFF = self._parse_backoff(
            os.getenv("PDF_RETRY_BACKOFF", "1,2,4")
        )
        
        # Parallelization
        self.MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
        
        # Validate settings
        self._validate()
    
    def _parse_backoff(self, backoff_str: str) -> List[float]:
        """Parse comma-separated backoff delays into list of floats."""
        try:
            return [float(x.strip()) for x in backoff_str.split(",")]
        except ValueError:
            return [1.0, 2.0, 4.0]  # Default fallback
    
    def _validate(self):
        """Validate settings and raise errors for invalid values."""
        if self.THROTTLE_SEC < 0:
            raise ValueError("THROTTLE_SEC must be non-negative")
        
        if self.PDF_RETRY_MAX < 1:
            raise ValueError("PDF_RETRY_MAX must be at least 1")
        
        if len(self.PDF_RETRY_BACKOFF) == 0:
            raise ValueError("PDF_RETRY_BACKOFF must contain at least one value")
        
        if self.MAX_WORKERS < 1:
            raise ValueError("MAX_WORKERS must be at least 1")


# Single instance of settings
settings = Settings()