"""Base scraper components."""

from scrapers.base.base_scraper import BaseScraper, DocumentMetadata
from scrapers.base.session_pool import SessionPool
from scrapers.base.pdf_cache import PDFCache
from scrapers.base.similarity import SimilarityCalculator
from scrapers.base.exceptions import (
    ScraperError,
    NavigationTimeoutError,
    DownloadError,
    CacheError
)

__all__ = [
    "BaseScraper",
    "DocumentMetadata",
    "SessionPool",
    "PDFCache",
    "SimilarityCalculator",
    "ScraperError",
    "NavigationTimeoutError",
    "DownloadError",
    "CacheError",
]