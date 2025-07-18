"""Common utilities for web scraping operations."""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, urlparse

from utils.logging import get_logger

logger = get_logger(__name__)


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Remove characters that are invalid in filenames and ensure reasonable length.
    
    Args:
        name: Original filename
        max_length: Maximum allowed length for filename
        
    Returns:
        Sanitized filename safe for all operating systems
    """
    # Remove invalid filename characters
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name)
    
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    
    # Ensure filename is not empty
    if not sanitized:
        sanitized = "unnamed"
    
    # Truncate if too long (leave room for extension)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip()
    
    return sanitized


def get_default_headers() -> Dict[str, str]:
    """
    Get default HTTP headers for web scraping.
    
    Returns:
        Dictionary of standard HTTP headers
    """
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }


def parse_date_formats(date_string: str) -> Optional[datetime]:
    """
    Parse various date formats commonly found in franchise filings.
    
    Args:
        date_string: Date string to parse
        
    Returns:
        Parsed datetime object or None if parsing fails
    """
    if not date_string:
        return None
        
    # Clean the string
    date_string = date_string.strip()
    
    # Common date formats in franchise filings
    date_formats = [
        "%m/%d/%Y",      # 12/31/2023
        "%m-%d-%Y",      # 12-31-2023
        "%Y-%m-%d",      # 2023-12-31
        "%Y/%m/%d",      # 2023/12/31
        "%B %d, %Y",     # December 31, 2023
        "%b %d, %Y",     # Dec 31, 2023
        "%d-%b-%Y",      # 31-Dec-2023
        "%m/%d/%y",      # 12/31/23
        "%m-%d-%y",      # 12-31-23
        "%Y%m%d",        # 20231231
        "%b %Y",         # Dec 2023
        "%B %Y",         # December 2023
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    # Try to extract year if nothing else works
    year_match = re.search(r'20\d{2}', date_string)
    if year_match:
        try:
            year = int(year_match.group())
            return datetime(year, 1, 1)  # Default to Jan 1st
        except:
            pass
    
    logger.warning(f"Unable to parse date: {date_string}")
    return None


def extract_filing_number(text: str) -> Optional[str]:
    """
    Extract filing number from text using common patterns.
    
    Args:
        text: Text containing potential filing number
        
    Returns:
        Extracted filing number or None
    """
    if not text:
        return None
    
    # Common filing number patterns
    patterns = [
        r'Filing Number[:\s]*#?\s*(\d{4,})',
        r'Registration Number[:\s]*#?\s*(\d{4,})',
        r'File Number[:\s]*#?\s*(\d{4,})',
        r'File No[.:\s]*#?\s*(\d{4,})',
        r'Number[:\s]*#?\s*(\d{4,})',
        r'#\s*(\d{4,})',
        r'\b(\d{6,})\b',  # Any 6+ digit number
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def parse_file_size(size_string: str) -> Optional[int]:
    """
    Parse file size from string to bytes.
    
    Args:
        size_string: File size string (e.g., "2.5 MB", "1024 KB")
        
    Returns:
        Size in bytes or None if parsing fails
    """
    if not size_string:
        return None
    
    # Clean the string
    size_string = size_string.strip().upper()
    
    # Extract number and unit
    match = re.search(r'(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|BYTES?|KILOBYTES?|MEGABYTES?|GIGABYTES?)', size_string)
    if not match:
        return None
    
    size_value = float(match.group(1))
    unit = match.group(2)
    
    # Convert to bytes
    multipliers = {
        'B': 1,
        'BYTE': 1,
        'BYTES': 1,
        'KB': 1024,
        'KILOBYTE': 1024,
        'KILOBYTES': 1024,
        'MB': 1024 * 1024,
        'MEGABYTE': 1024 * 1024,
        'MEGABYTES': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'GIGABYTE': 1024 * 1024 * 1024,
        'GIGABYTES': 1024 * 1024 * 1024,
    }
    
    multiplier = multipliers.get(unit, 1)
    return int(size_value * multiplier)


def normalize_url(url: str, base_url: str) -> str:
    """
    Normalize URL by converting relative URLs to absolute.
    
    Args:
        url: URL to normalize (can be relative or absolute)
        base_url: Base URL for resolving relative URLs
        
    Returns:
        Absolute URL
    """
    if not url:
        return ""
    
    # Already absolute URL
    if url.startswith(('http://', 'https://')):
        return url
    
    # Protocol-relative URL
    if url.startswith('//'):
        parsed_base = urlparse(base_url)
        return f"{parsed_base.scheme}:{url}"
    
    # Relative URL
    return urljoin(base_url, url)


def extract_state_code(text: str) -> Optional[str]:
    """
    Extract US state code from text.
    
    Args:
        text: Text containing potential state information
        
    Returns:
        Two-letter state code or None
    """
    if not text:
        return None
    
    # All US state codes
    state_codes = {
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
        'DC'  # Include DC
    }
    
    # Look for state codes in the text
    words = re.findall(r'\b[A-Z]{2}\b', text.upper())
    for word in words:
        if word in state_codes:
            return word
    
    return None


def clean_text(text: str) -> str:
    """
    Clean text by removing extra whitespace and normalizing.
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Decode HTML entities if present
    text = (text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&#39;", "'")
            .replace("&quot;", '"')
            .replace("&nbsp;", " "))
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def format_franchise_name(name: str) -> str:
    """
    Format franchise name for consistency.
    
    Args:
        name: Raw franchise name
        
    Returns:
        Formatted franchise name
    """
    if not name:
        return "Unknown Franchise"
    
    # Clean the text first
    name = clean_text(name)
    
    # Common patterns to clean up
    name = re.sub(r'\s*,?\s*(LLC|L\.L\.C\.|Inc\.|INC\.|Corp\.|Corporation)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\([^)]*\)$', '', name)  # Remove trailing parentheses
    
    # Ensure proper capitalization for common words
    name = name.title()
    
    # Fix common issues with title case
    name = re.sub(r'\bLlc\b', 'LLC', name)
    name = re.sub(r'\bInc\b', 'Inc', name)
    name = re.sub(r'\bCorp\b', 'Corp', name)
    name = re.sub(r'\bFdd\b', 'FDD', name)
    
    return name


def create_document_filename(
    franchise_name: str,
    year: Optional[str] = None,
    filing_number: Optional[str] = None,
    document_type: str = "FDD",
    extension: str = ".pdf",
    uuid: Optional[str] = None
) -> str:
    """
    Create a standardized filename for franchise documents.
    
    Args:
        franchise_name: Name of the franchise
        year: Year of the document
        filing_number: Filing number if available
        document_type: Type of document (FDD, Amendment, etc.)
        extension: File extension
        uuid: Optional UUID to include in filename for tracking
        
    Returns:
        Standardized filename
    """
    parts = []
    
    # Add UUID if available (for unique identification)
    if uuid:
        parts.append(str(uuid))
    
    # Add year if available
    if year:
        parts.append(str(year))
    
    # Add franchise name
    clean_name = sanitize_filename(franchise_name)
    parts.append(clean_name)
    
    # Add document type if not default
    if document_type and document_type != "FDD":
        parts.append(document_type)
    
    # Add filing number if available
    if filing_number:
        parts.append(f"#{filing_number}")
    
    # Join parts and add extension
    filename = "_".join(parts)
    
    # Ensure extension
    if not filename.endswith(extension):
        filename += extension
    
    return filename


def extract_year_from_text(text: str) -> Optional[str]:
    """
    Extract year from text.
    
    Args:
        text: Text containing potential year
        
    Returns:
        Four-digit year string or None
    """
    if not text:
        return None
    
    # Look for 4-digit years (2000-2099)
    year_match = re.search(r'20\d{2}', text)
    if year_match:
        return year_match.group()
    
    # Look for 2-digit years (00-99) with context
    match = re.search(r"'(\d{2})|(?:19|20)(\d{2})", text)
    if match:
        year_suffix = match.group(1) or match.group(2)
        year_int = int(year_suffix)
        # Assume 00-30 means 2000-2030, 31-99 means 1931-1999
        if year_int <= 30:
            return f"20{year_suffix:02d}"
        else:
            return f"19{year_suffix:02d}"
    
    return None


def parse_address(address_text: str) -> Dict[str, str]:
    """
    Parse address text into components.
    
    Args:
        address_text: Full address text
        
    Returns:
        Dictionary with address components
    """
    result = {
        "full_address": clean_text(address_text),
        "street": "",
        "city": "",
        "state": "",
        "zip": ""
    }
    
    if not address_text:
        return result
    
    # Extract ZIP code
    zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', address_text)
    if zip_match:
        result["zip"] = zip_match.group(1)
        address_text = address_text.replace(zip_match.group(0), "")
    
    # Extract state
    state_code = extract_state_code(address_text)
    if state_code:
        result["state"] = state_code
        # Remove state from text for further parsing
        address_text = re.sub(rf'\b{state_code}\b', '', address_text, flags=re.IGNORECASE)
    
    # Split remaining text
    parts = [p.strip() for p in address_text.split(',')]
    if len(parts) >= 2:
        result["street"] = parts[0]
        result["city"] = parts[1] if len(parts) > 1 else ""
    elif parts:
        # If no commas, try to guess
        result["street"] = parts[0]
    
    return result


def calculate_retry_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Calculate exponential backoff delay for retries.
    
    Args:
        attempt: Current attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        
    Returns:
        Delay in seconds
    """
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)