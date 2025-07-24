"""Custom exceptions for scrapers."""


class ScraperError(Exception):
    """Base exception for all scraper errors."""
    pass


class NavigationTimeoutError(ScraperError):
    """Raised when page navigation times out."""
    pass


class DownloadError(ScraperError):
    """Raised when PDF download fails."""
    pass


class CacheError(ScraperError):
    """Raised when cache operations fail."""
    pass


class SessionPoolError(ScraperError):
    """Raised when session pool operations fail."""
    pass


class SimilarityError(ScraperError):
    """Raised when similarity calculations fail."""
    pass