"""Base scraper framework."""

from .base_scraper import BaseScraper, DocumentMetadata, create_scraper
from .exceptions import (
    WebScrapingException,
    NavigationTimeoutError,
    ElementNotFoundError,
    DownloadFailedError,
    RateLimitError,
    DataStorageException,
    DatabaseConnectionError,
    RecordNotFoundError,
    DataSerializationError,
    BatchOperationError,
    RetryableError,
    LLMExtractionException,
    ModelInitializationError,
    TokenLimitExceededError,
    ExtractionTimeoutError,
)

__all__ = [
    "BaseScraper",
    "DocumentMetadata",
    "create_scraper",
    "WebScrapingException",
    "NavigationTimeoutError",
    "ElementNotFoundError",
    "DownloadFailedError",
    "RateLimitError",
    "DataStorageException",
    "DatabaseConnectionError",
    "RecordNotFoundError",
    "DataSerializationError",
    "BatchOperationError",
    "RetryableError",
    "LLMExtractionException",
    "ModelInitializationError",
    "TokenLimitExceededError",
    "ExtractionTimeoutError",
]