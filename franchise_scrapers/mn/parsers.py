# franchise_scrapers/mn/parsers.py
"""Parsers for extracting data from Minnesota CARDS portal table rows."""

import re
from typing import Optional, Dict, Any
from urllib.parse import unquote
from playwright.async_api import ElementHandle


async def parse_row(row: ElementHandle) -> Optional[Dict[str, Any]]:
    """Extract data from a Minnesota CARDS table row.
    
    The Minnesota CARDS table has 9 columns:
    0: # (row number) - this is a th element
    1: Document (contains download link)
    2: Franchisor
    3: Franchise names
    4: Document types
    5: Year
    6: File number
    7: Notes
    8: Received date/Added on
    
    Args:
        row: Playwright ElementHandle for a table row
        
    Returns:
        Dictionary with extracted data or None if row is invalid
    """
    try:
        # Get all cells in the row
        cells = await row.query_selector_all("td, th")
        
        # Skip header row or rows with insufficient cells
        if len(cells) < 9:
            return None
            
        # Check if this is the header row by examining first cell
        first_cell_text = await cells[0].inner_text()
        if first_cell_text.strip().lower() == "#":
            return None
        
        # Extract download link and document title from Document column (index 1)
        download_link_elem = await cells[1].query_selector("a")
        if not download_link_elem:
            return None
            
        download_url = await download_link_elem.get_attribute("href")
        if not download_url:
            return None
            
        document_title = await download_link_elem.inner_text()
        
        # Extract other fields
        franchisor = await cells[2].inner_text()
        franchise_names = await cells[3].inner_text()
        document_types = await cells[4].inner_text()
        year = await cells[5].inner_text()
        file_number = await cells[6].inner_text()
        notes = await cells[7].inner_text()
        received_date = await cells[8].inner_text()
        
        # Clean extracted text
        franchisor = franchisor.strip()
        franchise_names = franchise_names.strip()
        document_types = document_types.strip()
        year = year.strip()
        file_number = file_number.strip()
        notes = notes.strip()
        received_date = received_date.strip()
        document_title = document_title.strip()
        
        # Only process Clean FDD documents
        if "Clean FDD" not in document_types:
            return None
        
        return {
            "download_url": download_url,
            "document_title": document_title,
            "franchisor": franchisor,
            "franchise_names": franchise_names,
            "document_types": document_types,
            "year": year,
            "file_number": file_number,
            "notes": notes,
            "received_date": received_date,
        }
        
    except Exception as e:
        print(f"Error parsing row: {e}")
        return None


def extract_document_id(url: str) -> Optional[str]:
    """Extract document ID from Minnesota CARDS download URL.
    
    The URL format contains: documentId=%7B{uuid}%7D
    where %7B and %7D are URL-encoded { and }
    
    Args:
        url: Download URL from Minnesota CARDS
        
    Returns:
        Document ID (UUID) or None if not found
    """
    try:
        # Look for the documentId parameter
        match = re.search(r"documentId=%7B(.+?)%7D", url)
        if match:
            return match.group(1)
        
        # Alternative: look for unencoded format
        match = re.search(r"documentId=\{(.+?)\}", url)
        if match:
            return match.group(1)
            
        # Try URL decoding first
        decoded_url = unquote(url)
        match = re.search(r"documentId=\{(.+?)\}", decoded_url)
        if match:
            return match.group(1)
            
        return None
        
    except Exception as e:
        print(f"Error extracting document ID from {url}: {e}")
        return None


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """Sanitize text to create a safe filename.
    
    Args:
        text: Text to sanitize (typically franchisor name)
        max_length: Maximum length of filename (without extension)
        
    Returns:
        Sanitized filename-safe string
    """
    # Remove or replace invalid filename characters
    # Keep alphanumeric, spaces, hyphens, and underscores
    sanitized = re.sub(r'[^\w\s\-]', '', text)
    
    # Replace multiple spaces with single underscore
    sanitized = re.sub(r'\s+', '_', sanitized)
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip('_')
    
    # Ensure we have a valid filename
    if not sanitized:
        sanitized = "unknown_franchise"
        
    return sanitized


def clean_text(text: str) -> str:
    """Clean text by removing extra whitespace and normalizing.
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Remove non-printable characters
    text = ''.join(char for char in text if char.isprintable() or char.isspace())
    
    return text


def parse_year(year_text: str) -> Optional[int]:
    """Parse year from text.
    
    Args:
        year_text: Text containing year
        
    Returns:
        Year as integer or None if invalid
    """
    try:
        # Clean the text
        year_text = year_text.strip()
        
        # Extract 4-digit year
        match = re.search(r'\b(20\d{2})\b', year_text)
        if match:
            return int(match.group(1))
            
        # Try direct conversion
        if year_text.isdigit() and len(year_text) == 4:
            year = int(year_text)
            if 2000 <= year <= 2100:  # Reasonable range
                return year
                
        return None
        
    except Exception:
        return None


def parse_date(date_text: str) -> Optional[str]:
    """Parse date from text into standardized format.
    
    Args:
        date_text: Text containing date
        
    Returns:
        Date in YYYY-MM-DD format or None if invalid
    """
    try:
        # Clean the text
        date_text = date_text.strip()
        
        # Common date patterns
        patterns = [
            # MM/DD/YYYY or MM-DD-YYYY
            (r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', '{2}-{0:02d}-{1:02d}'),
            # YYYY-MM-DD
            (r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', '{0}-{1:02d}-{2:02d}'),
            # MMM DD, YYYY
            (r'([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', None),  # Needs special handling
        ]
        
        for pattern, format_str in patterns:
            match = re.search(pattern, date_text)
            if match:
                if format_str:
                    groups = [int(g) for g in match.groups()]
                    return format_str.format(*groups)
                else:
                    # Handle month name
                    month_names = {
                        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
                        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
                        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                    }
                    month_str = match.group(1).lower()[:3]
                    if month_str in month_names:
                        month = month_names[month_str]
                        day = int(match.group(2))
                        year = int(match.group(3))
                        return f"{year}-{month:02d}-{day:02d}"
        
        return None
        
    except Exception:
        return None


def is_valid_fdd(document_types: str, notes: str = "") -> bool:
    """Check if a document is a valid FDD for processing.
    
    Args:
        document_types: Document types field from table
        notes: Notes field from table
        
    Returns:
        True if document should be processed
    """
    # Must contain "Clean FDD"
    if "Clean FDD" not in document_types:
        return False
    
    # Skip amendments or supplements if noted
    notes_lower = notes.lower()
    skip_keywords = ['amendment', 'supplement', 'addendum', 'correction']
    if any(keyword in notes_lower for keyword in skip_keywords):
        return False
    
    return True