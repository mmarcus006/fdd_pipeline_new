"""Custom exceptions for FDD Pipeline tasks.

This module defines specific exceptions for different error scenarios
across the pipeline, enabling better error handling and debugging.
"""

from typing import Optional, Dict, Any


class TaskException(Exception):
    """Base exception for all task-related errors."""

    def __init__(
        self,
        message: str,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.correlation_id = correlation_id
        self.context = context or {}


# Data Storage Exceptions
class DataStorageException(TaskException):
    """Base exception for data storage operations."""

    pass


class DatabaseConnectionError(DataStorageException):
    """Raised when database connection fails."""

    pass


class RecordNotFoundError(DataStorageException):
    """Raised when expected record is not found in database."""

    pass


class DataSerializationError(DataStorageException):
    """Raised when data cannot be serialized for storage."""

    pass


class BatchOperationError(DataStorageException):
    """Raised when batch database operation fails."""

    pass


# Document Processing Exceptions
class DocumentProcessingException(TaskException):
    """Base exception for document processing operations."""

    pass


class PDFReadError(DocumentProcessingException):
    """Raised when PDF cannot be read or parsed."""

    pass


class MinerUConnectionError(DocumentProcessingException):
    """Raised when MinerU service connection fails."""

    pass


class MinerUProcessingError(DocumentProcessingException):
    """Raised when MinerU processing fails."""

    pass


class LayoutAnalysisError(DocumentProcessingException):
    """Raised when document layout analysis fails."""

    pass


class SectionDetectionError(DocumentProcessingException):
    """Raised when FDD section detection fails."""

    pass


# LLM Extraction Exceptions
class LLMExtractionException(TaskException):
    """Base exception for LLM extraction operations."""

    pass


class ModelInitializationError(LLMExtractionException):
    """Raised when LLM model cannot be initialized."""

    pass


class TokenLimitExceededError(LLMExtractionException):
    """Raised when content exceeds model token limits."""

    pass


class ExtractionTimeoutError(LLMExtractionException):
    """Raised when extraction operation times out."""

    pass


class InvalidExtractionResultError(LLMExtractionException):
    """Raised when extraction result doesn't match expected schema."""

    pass


class ModelAPIError(LLMExtractionException):
    """Raised when LLM API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        model_name: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.model_name = model_name


# Web Scraping Exceptions
class WebScrapingException(TaskException):
    """Base exception for web scraping operations."""

    pass


class BrowserInitializationError(WebScrapingException):
    """Raised when Playwright browser cannot be initialized."""

    pass


class NavigationTimeoutError(WebScrapingException):
    """Raised when page navigation times out."""

    pass


class ElementNotFoundError(WebScrapingException):
    """Raised when expected page element is not found."""

    pass


class LoginFailedError(WebScrapingException):
    """Raised when portal login fails."""

    pass


class DownloadFailedError(WebScrapingException):
    """Raised when document download fails."""

    pass


class RateLimitError(WebScrapingException):
    """Raised when scraping hits rate limits."""

    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


# Document Segmentation Exceptions
class DocumentSegmentationException(TaskException):
    """Base exception for document segmentation operations."""

    pass


class InvalidPageRangeError(DocumentSegmentationException):
    """Raised when page range is invalid."""

    pass


class PDFSplitError(DocumentSegmentationException):
    """Raised when PDF splitting fails."""

    pass


class SectionValidationError(DocumentSegmentationException):
    """Raised when section validation fails."""

    pass


# Drive Operations Exceptions
class DriveOperationException(TaskException):
    """Base exception for Google Drive operations."""

    pass


class DriveAuthenticationError(DriveOperationException):
    """Raised when Google Drive authentication fails."""

    pass


class DriveUploadError(DriveOperationException):
    """Raised when file upload to Drive fails."""

    pass


class DriveDownloadError(DriveOperationException):
    """Raised when file download from Drive fails."""

    pass


class DriveQuotaExceededError(DriveOperationException):
    """Raised when Drive storage quota is exceeded."""

    pass


class FileNotFoundInDriveError(DriveOperationException):
    """Raised when file is not found in Drive."""

    pass


# Schema Validation Exceptions
class SchemaValidationException(TaskException):
    """Base exception for schema validation operations."""

    pass


class ValidationBypassError(SchemaValidationException):
    """Raised when validation bypass check fails."""

    pass


class CustomValidatorError(SchemaValidationException):
    """Raised when custom validation rule fails."""

    pass


class CrossFieldValidationError(SchemaValidationException):
    """Raised when cross-field validation fails."""

    pass


# Integration Exceptions
class IntegrationException(TaskException):
    """Base exception for integration operations."""

    pass


class PipelineCoordinationError(IntegrationException):
    """Raised when pipeline coordination fails."""

    pass


class DependencyNotMetError(IntegrationException):
    """Raised when task dependencies are not met."""

    pass


# Retry and Recovery Helpers
class RetryableError(TaskException):
    """Base class for errors that should trigger retries."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        max_retries: int = 3,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        self.max_retries = max_retries


class NonRetryableError(TaskException):
    """Base class for errors that should not trigger retries."""

    pass


# Utility functions for error handling
def is_retryable(error: Exception) -> bool:
    """Check if an error is retryable."""
    return isinstance(
        error,
        (
            RetryableError,
            ConnectionError,
            TimeoutError,
            RateLimitError,
            DriveAuthenticationError,
            MinerUConnectionError,
            BrowserInitializationError,
            ModelAPIError,
        ),
    )


def get_retry_delay(error: Exception, attempt: int = 1) -> int:
    """Calculate retry delay based on error type and attempt number."""
    base_delay = 1

    if hasattr(error, "retry_after") and error.retry_after:
        return error.retry_after

    if isinstance(error, RateLimitError):
        return min(60 * attempt, 300)  # Max 5 minutes

    if isinstance(error, (DriveAuthenticationError, ModelAPIError)):
        return min(10 * (2**attempt), 120)  # Exponential backoff, max 2 minutes

    # Default exponential backoff
    return min(base_delay * (2**attempt), 60)
