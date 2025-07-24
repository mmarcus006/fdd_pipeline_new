"""PDF caching system for deduplication and faster processing."""

import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta

from utils.logging import get_logger
from scrapers.base.exceptions import CacheError


class PDFCache:
    """Manages PDF caching for deduplication and faster processing.
    
    Features:
    - SHA256 hash-based deduplication
    - URL-based cache lookups
    - Persistent cache index
    - Automatic cache expiration
    - Size-based cache management
    """
    
    def __init__(
        self, 
        cache_dir: Path = Path(".cache/pdfs"),
        max_size_gb: float = 10.0,
        expiry_days: int = 30
    ):
        self.cache_dir = cache_dir
        self.max_size_gb = max_size_gb
        self.expiry_days = expiry_days
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._hash_index: Dict[str, Dict] = {}  # hash -> {path, url, timestamp}
        self._url_index: Dict[str, str] = {}  # URL -> hash mapping
        self.logger = get_logger(__name__)
        
        self._index_file = self.cache_dir / "index.json"
        self._load_index()
        self._cleanup_expired()
    
    def _load_index(self):
        """Load cache index from disk."""
        if self._index_file.exists():
            try:
                with open(self._index_file) as f:
                    data = json.load(f)
                    self._hash_index = data.get("hashes", {})
                    self._url_index = data.get("urls", {})
                    self.logger.info(f"Loaded cache index with {len(self._hash_index)} entries")
            except Exception as e:
                self.logger.error(f"Failed to load cache index: {e}")
                self._hash_index = {}
                self._url_index = {}
    
    def _save_index(self):
        """Save cache index to disk."""
        try:
            with open(self._index_file, 'w') as f:
                json.dump({
                    "hashes": self._hash_index,
                    "urls": self._url_index,
                    "version": "1.0",
                    "updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            raise CacheError(f"Failed to save cache index: {e}")
    
    def _cleanup_expired(self):
        """Remove expired cache entries."""
        now = datetime.now()
        expired = []
        
        for hash_value, info in self._hash_index.items():
            timestamp = datetime.fromisoformat(info["timestamp"])
            if now - timestamp > timedelta(days=self.expiry_days):
                expired.append(hash_value)
        
        for hash_value in expired:
            self._remove_entry(hash_value)
        
        if expired:
            self.logger.info(f"Cleaned up {len(expired)} expired cache entries")
            self._save_index()
    
    def _remove_entry(self, hash_value: str):
        """Remove a cache entry."""
        if hash_value in self._hash_index:
            info = self._hash_index[hash_value]
            path = Path(info["path"])
            
            # Remove file
            if path.exists():
                path.unlink()
            
            # Remove from URL index
            if info["url"] in self._url_index:
                del self._url_index[info["url"]]
            
            # Remove from hash index
            del self._hash_index[hash_value]
    
    def _check_size_limit(self):
        """Check and enforce cache size limit."""
        total_size = sum(
            Path(info["path"]).stat().st_size 
            for info in self._hash_index.values() 
            if Path(info["path"]).exists()
        )
        
        if total_size > self.max_size_gb * 1024 * 1024 * 1024:
            # Remove oldest entries until under limit
            sorted_entries = sorted(
                self._hash_index.items(),
                key=lambda x: x[1]["timestamp"]
            )
            
            while total_size > self.max_size_gb * 1024 * 1024 * 1024 * 0.9:  # 90% threshold
                if not sorted_entries:
                    break
                    
                hash_value, info = sorted_entries.pop(0)
                file_size = Path(info["path"]).stat().st_size
                self._remove_entry(hash_value)
                total_size -= file_size
            
            self._save_index()
    
    def calculate_hash(self, content: bytes) -> str:
        """Calculate SHA256 hash of content."""
        return hashlib.sha256(content).hexdigest()
    
    def get_by_url(self, url: str) -> Optional[Path]:
        """Get cached PDF by URL."""
        if url in self._url_index:
            hash_value = self._url_index[url]
            if hash_value in self._hash_index:
                path = Path(self._hash_index[hash_value]["path"])
                if path.exists():
                    self.logger.debug(f"Cache hit for URL: {url}")
                    return path
                else:
                    # File missing, cleanup index
                    self._remove_entry(hash_value)
                    self._save_index()
        return None
    
    def get_by_hash(self, hash_value: str) -> Optional[Path]:
        """Get cached PDF by hash."""
        if hash_value in self._hash_index:
            path = Path(self._hash_index[hash_value]["path"])
            if path.exists():
                self.logger.debug(f"Cache hit for hash: {hash_value[:8]}...")
                return path
            else:
                # File missing, cleanup index
                self._remove_entry(hash_value)
                self._save_index()
        return None
    
    def exists(self, url: str = None, hash_value: str = None) -> bool:
        """Check if PDF exists in cache."""
        if url:
            return self.get_by_url(url) is not None
        if hash_value:
            return self.get_by_hash(hash_value) is not None
        return False
    
    def add(self, content: bytes, url: str, filename: str) -> Tuple[Path, str]:
        """Add PDF to cache and return path and hash."""
        hash_value = self.calculate_hash(content)
        
        # Check if already cached
        if hash_value in self._hash_index:
            self.logger.info(f"PDF already cached: {hash_value[:8]}...")
            path = Path(self._hash_index[hash_value]["path"])
            if path.exists():
                return path, hash_value
        
        # Create safe filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")[:100]
        file_path = self.cache_dir / f"{hash_value[:8]}_{safe_filename}"
        
        # Save to cache
        try:
            with open(file_path, 'wb') as f:
                f.write(content)
        except Exception as e:
            raise CacheError(f"Failed to write cache file: {e}")
        
        # Update indices
        self._hash_index[hash_value] = {
            "path": str(file_path),
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "filename": filename,
            "size": len(content)
        }
        self._url_index[url] = hash_value
        
        self._save_index()
        self._check_size_limit()
        
        self.logger.info(f"Cached PDF: {filename} -> {hash_value[:8]}...")
        return file_path, hash_value
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_size = sum(
            Path(info["path"]).stat().st_size 
            for info in self._hash_index.values() 
            if Path(info["path"]).exists()
        )
        
        return {
            "total_entries": len(self._hash_index),
            "unique_urls": len(self._url_index),
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "size_limit_gb": self.max_size_gb,
            "expiry_days": self.expiry_days,
            "cache_dir": str(self.cache_dir)
        }