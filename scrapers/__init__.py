"""
Franchise scrapers package for automated FDD document collection.

This package provides a unified interface for scraping FDD documents
from various state franchise portals with enhanced features including
session reuse, PDF caching, and similarity-based deduplication.
"""

from scrapers.base import BaseScraper, DocumentMetadata
from scrapers.states import MinnesotaScraper, WisconsinScraper

__all__ = [
    "BaseScraper",
    "DocumentMetadata", 
    "MinnesotaScraper",
    "WisconsinScraper",
]