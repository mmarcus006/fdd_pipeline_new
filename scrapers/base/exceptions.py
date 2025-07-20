"""Custom exceptions for FDD Pipeline tasks.

This module defines specific exceptions for different error scenarios
across the pipeline, enabling better error handling and debugging.
"""

from typing import Optional, Dict, Any
import logging
import traceback
from datetime import datetime

# Create module logger
logger = logging.getLogger(__name__)


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
        self.timestamp = datetime.now().isoformat()
        self.traceback = traceback.format_exc()
        
        # Log exception creation
        logger.debug(
            f"Exception created: {self.__class__.__name__}",
            extra={
                "exception_type": self.__class__.__name__,
                "message": message,
                "correlation_id": correlation_id,
                "context": context,
                "timestamp": self.timestamp,
                "traceback_preview": self.traceback.split('\n')[-3] if self.traceback else None
            }
        )
    
    def __str__(self):
        """Enhanced string representation with context."""
        base_msg = super().__str__()
        if self.correlation_id:
            base_msg = f"[{self.correlation_id}] {base_msg}"
        if self.context:
            base_msg = f"{base_msg} | Context: {self.context}"
        return base_msg


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
    result = isinstance(
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
    
    logger.debug(
        f"is_retryable check",
        extra={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "is_retryable": result,
            "has_retry_after": hasattr(error, "retry_after"),
            "retry_after": getattr(error, "retry_after", None)
        }
    )
    
    return result


def get_retry_delay(error: Exception, attempt: int = 1) -> int:
    """Calculate retry delay based on error type and attempt number."""
    base_delay = 1
    calculated_delay = None
    delay_reason = "default"

    if hasattr(error, "retry_after") and error.retry_after:
        calculated_delay = error.retry_after
        delay_reason = "explicit_retry_after"
    elif isinstance(error, RateLimitError):
        calculated_delay = min(60 * attempt, 300)  # Max 5 minutes
        delay_reason = "rate_limit"
    elif isinstance(error, (DriveAuthenticationError, ModelAPIError)):
        calculated_delay = min(10 * (2**attempt), 120)  # Exponential backoff, max 2 minutes
        delay_reason = "auth_or_api_error"
    else:
        # Default exponential backoff
        calculated_delay = min(base_delay * (2**attempt), 60)
        delay_reason = "default_exponential"
    
    logger.debug(
        f"get_retry_delay calculation",
        extra={
            "error_type": type(error).__name__,
            "attempt": attempt,
            "base_delay": base_delay,
            "calculated_delay": calculated_delay,
            "delay_reason": delay_reason,
            "has_retry_after": hasattr(error, "retry_after")
        }
    )
    
    return calculated_delay


def create_exception_hierarchy_report() -> Dict[str, Any]:
    """Generate a report of the exception hierarchy."""
    hierarchy = {}
    
    def get_subclasses(cls):
        """Recursively get all subclasses."""
        subclasses = {}
        for subclass in cls.__subclasses__():
            subclasses[subclass.__name__] = {
                "module": subclass.__module__,
                "docstring": subclass.__doc__,
                "subclasses": get_subclasses(subclass)
            }
        return subclasses
    
    # Start from TaskException
    hierarchy["TaskException"] = {
        "module": TaskException.__module__,
        "docstring": TaskException.__doc__,
        "subclasses": get_subclasses(TaskException)
    }
    
    logger.info(
        "Exception hierarchy report generated",
        extra={
            "total_exception_types": len(str(hierarchy).split("'module':")),
            "root_exception": "TaskException"
        }
    )
    
    return hierarchy


if __name__ == "__main__":
    import json
    import sys
    
    # Set up detailed logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('exceptions_debug.log')
        ]
    )
    
    print("\n" + "="*60)
    print("EXCEPTION MODULE DEBUG TEST")
    print("="*60 + "\n")
    
    # Test 1: Basic exception creation and logging
    print("Test 1: Basic exception creation")
    print("-" * 40)
    try:
        raise TaskException(
            "Test task exception",
            correlation_id="test-123",
            context={"operation": "test", "value": 42}
        )
    except TaskException as e:
        print(f"✓ Caught TaskException: {e}")
        print(f"  - Correlation ID: {e.correlation_id}")
        print(f"  - Context: {e.context}")
        print(f"  - Timestamp: {e.timestamp}")
    print()
    
    # Test 2: Specialized exceptions
    print("Test 2: Specialized exceptions")
    print("-" * 40)
    
    test_exceptions = [
        (WebScrapingException, "Web scraping failed", {"url": "https://example.com"}),
        (RateLimitError, "Rate limit hit", {"retry_after": 60}),
        (LLMExtractionException, "Extraction failed", {"model": "gpt-4"}),
        (DocumentProcessingException, "PDF processing error", {"file": "test.pdf"}),
    ]
    
    for exc_class, msg, context in test_exceptions:
        try:
            if exc_class == RateLimitError:
                raise exc_class(msg, retry_after=60, context=context)
            else:
                raise exc_class(msg, context=context)
        except TaskException as e:
            print(f"✓ {exc_class.__name__}: {e}")
    print()
    
    # Test 3: Model API Error with status code
    print("Test 3: ModelAPIError with additional attributes")
    print("-" * 40)
    try:
        raise ModelAPIError(
            "API request failed",
            status_code=429,
            model_name="gemini-pro",
            correlation_id="api-test-456"
        )
    except ModelAPIError as e:
        print(f"✓ ModelAPIError: {e}")
        print(f"  - Status code: {e.status_code}")
        print(f"  - Model name: {e.model_name}")
    print()
    
    # Test 4: Retryable error checking
    print("Test 4: Retryable error checking")
    print("-" * 40)
    
    errors_to_test = [
        RetryableError("Retryable error"),
        NonRetryableError("Non-retryable error"),
        RateLimitError("Rate limited", retry_after=30),
        ValidationBypassError("Validation failed"),
        BrowserInitializationError("Browser init failed"),
        ConnectionError("Connection lost"),
    ]
    
    for error in errors_to_test:
        retryable = is_retryable(error)
        print(f"{'✓' if retryable else '✗'} {error.__class__.__name__}: "
              f"{'Retryable' if retryable else 'Not retryable'}")
    print()
    
    # Test 5: Retry delay calculation
    print("Test 5: Retry delay calculation")
    print("-" * 40)
    
    delay_test_errors = [
        (RateLimitError("Rate limited", retry_after=120), 1),
        (RateLimitError("Rate limited"), 3),
        (ModelAPIError("API error"), 2),
        (ConnectionError("Connection error"), 4),
        (RetryableError("Generic retryable", retry_after=45), 1),
    ]
    
    for error, attempt in delay_test_errors:
        delay = get_retry_delay(error, attempt)
        print(f"  {error.__class__.__name__} (attempt {attempt}): {delay}s delay")
    print()
    
    # Test 6: Exception hierarchy report
    print("Test 6: Exception hierarchy")
    print("-" * 40)
    hierarchy = create_exception_hierarchy_report()
    
    def print_hierarchy(data, indent=0):
        """Pretty print the hierarchy."""
        for name, info in data.items():
            if isinstance(info, dict) and "subclasses" in info:
                print(f"{'  ' * indent}├─ {name}")
                if info["subclasses"]:
                    print_hierarchy(info["subclasses"], indent + 1)
    
    print_hierarchy(hierarchy)
    print()
    
    # Test 7: Context propagation
    print("Test 7: Context propagation through exception chain")
    print("-" * 40)
    try:
        try:
            raise ElementNotFoundError(
                "Button not found",
                correlation_id="nav-789",
                context={"selector": "#submit-btn", "timeout": 5000}
            )
        except ElementNotFoundError as e:
            raise WebScrapingException(
                f"Navigation failed due to: {e}",
                correlation_id=e.correlation_id,
                context={**e.context, "previous_error": str(e)}
            )
    except WebScrapingException as e:
        print(f"✓ Context propagated: {e}")
        print(f"  - Original selector: {e.context.get('selector')}")
        print(f"  - Previous error: {e.context.get('previous_error')}")
    print()
    
    # Test 8: Custom validation errors
    print("Test 8: Schema validation exceptions")
    print("-" * 40)
    
    validation_errors = [
        ValidationBypassError("Bypass not allowed", context={"field": "franchise_fee"}),
        CustomValidatorError("Custom rule failed", context={"rule": "min_investment"}),
        CrossFieldValidationError("Fields inconsistent", context={
            "field1": "initial_fee",
            "field2": "total_investment"
        }),
    ]
    
    for error in validation_errors:
        try:
            raise error
        except SchemaValidationException as e:
            print(f"✓ {e.__class__.__name__}: {e}")
    print()
    
    # Save detailed exception report
    report_file = "exception_hierarchy_report.json"
    with open(report_file, 'w') as f:
        json.dump(hierarchy, f, indent=2, default=str)
    print(f"\n✓ Exception hierarchy saved to: {report_file}")
    
    # Summary statistics
    print("\n" + "="*60)
    print("EXCEPTION MODULE STATISTICS")
    print("="*60)
    
    all_exceptions = []
    
    def collect_exceptions(cls):
        all_exceptions.append(cls)
        for subclass in cls.__subclasses__():
            collect_exceptions(subclass)
    
    collect_exceptions(TaskException)
    
    print(f"Total exception classes: {len(all_exceptions)}")
    print(f"Base exceptions: {len([e for e in all_exceptions if len(e.__bases__) == 1])}")
    print(f"Retryable types: {len([e for e in all_exceptions if is_retryable(e('test'))])}")
    
    print("\n" + "="*60)
    print("TEST COMPLETED")
    print("="*60 + "\n")
