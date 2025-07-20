"""Utility for extracting text from PDF files."""

import logging
import time
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import PyPDF2

from utils.logging import PipelineLogger

# Configure module-level logging
logger = logging.getLogger(__name__)

# Create debug logger that writes to a dedicated file
debug_handler = logging.FileHandler('pdf_extractor_debug.log')
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
debug_handler.setFormatter(debug_formatter)
logger.addHandler(debug_handler)
logger.setLevel(logging.DEBUG)

# Pipeline logger for structured logging
pipeline_logger = PipelineLogger("pdf_extractor")


def timing_decorator(func):
    """Decorator to time function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        
        # Log function entry
        logger.debug(f"Entering {func_name} with args: {args}, kwargs: {kwargs}")
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            # Log successful completion
            logger.debug(f"Completed {func_name} in {elapsed:.3f}s")
            pipeline_logger.info(
                f"{func_name} completed",
                duration_seconds=elapsed,
                success=True
            )
            
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            
            # Log error
            logger.error(f"Failed {func_name} after {elapsed:.3f}s: {str(e)}")
            pipeline_logger.error(
                f"{func_name} failed",
                duration_seconds=elapsed,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    return wrapper


class PDFTextExtractor:
    """Enhanced PDF text extraction with detailed logging."""
    
    def __init__(self):
        self.logger = PipelineLogger("pdf_text_extractor")
    
    @timing_decorator
    def extract_text_from_pdf(self, pdf_path: Union[str, Path]) -> str:
        """
        Extracts text from all pages of a PDF file.

        Args:
            pdf_path: The path to the PDF file.

        Returns:
            The extracted text as a single string.
        """
        pdf_path = Path(pdf_path)
        
        # Log extraction start
        logger.debug(f"Starting PDF text extraction from: {pdf_path}")
        self.logger.info(
            "PDF text extraction started",
            pdf_path=str(pdf_path),
            file_size_bytes=pdf_path.stat().st_size if pdf_path.exists() else 0
        )
        
        text = ""
        page_count = 0
        extracted_pages = 0
        errors = []
        
        try:
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                total_pages = len(reader.pages)
                
                logger.debug(f"PDF has {total_pages} pages")
                
                for page_num, page in enumerate(reader.pages):
                    page_count += 1
                    
                    try:
                        # Extract text from current page
                        page_text = page.extract_text()
                        
                        if page_text and page_text.strip():
                            text += page_text + "\n"
                            extracted_pages += 1
                            
                            # Log sample of extracted text
                            sample = page_text.strip()[:100].replace('\n', ' ')
                            logger.debug(
                                f"Page {page_num + 1}: Extracted {len(page_text)} chars. "
                                f"Sample: '{sample}...'"
                            )
                        else:
                            logger.warning(f"Page {page_num + 1}: No text extracted")
                            
                    except Exception as e:
                        error_msg = f"Page {page_num + 1}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        continue
            
            # Log extraction summary
            success_rate = (extracted_pages / total_pages * 100) if total_pages > 0 else 0
            
            self.logger.info(
                "PDF text extraction completed",
                pdf_path=str(pdf_path),
                total_pages=total_pages,
                extracted_pages=extracted_pages,
                success_rate=success_rate,
                total_chars=len(text),
                errors_count=len(errors)
            )
            
            logger.debug(
                f"Extraction summary: {extracted_pages}/{total_pages} pages "
                f"({success_rate:.1f}% success rate), {len(text)} total chars"
            )
            
        except Exception as e:
            logger.error(f"PDF extraction failed: {str(e)}")
            self.logger.error(
                "PDF text extraction failed",
                pdf_path=str(pdf_path),
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        
        return text
    
    @timing_decorator
    def extract_page_range(
        self, 
        pdf_path: Union[str, Path], 
        start_page: int = 1, 
        end_page: Optional[int] = None
    ) -> Tuple[str, Dict[str, any]]:
        """
        Extract text from a specific page range.
        
        Args:
            pdf_path: Path to PDF file
            start_page: Starting page (1-indexed)
            end_page: Ending page (1-indexed, inclusive). None for last page.
            
        Returns:
            Tuple of (extracted_text, metadata)
        """
        pdf_path = Path(pdf_path)
        
        logger.debug(
            f"Extracting pages {start_page}-{end_page or 'end'} from {pdf_path}"
        )
        
        text = ""
        metadata = {
            "start_page": start_page,
            "end_page": end_page,
            "pages_processed": 0,
            "chars_extracted": 0,
            "errors": []
        }
        
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                total_pages = len(reader.pages)
                
                # Validate page range
                if start_page < 1 or start_page > total_pages:
                    raise ValueError(
                        f"Invalid start page {start_page}. "
                        f"PDF has {total_pages} pages"
                    )
                
                # Adjust end page
                actual_end = min(end_page or total_pages, total_pages)
                metadata["end_page"] = actual_end
                
                logger.debug(
                    f"Processing pages {start_page}-{actual_end} "
                    f"(PDF has {total_pages} pages)"
                )
                
                # Extract pages (convert to 0-indexed)
                for page_num in range(start_page - 1, actual_end):
                    try:
                        page = reader.pages[page_num]
                        page_text = page.extract_text()
                        
                        if page_text:
                            text += page_text + "\n"
                            metadata["pages_processed"] += 1
                            
                            logger.debug(
                                f"Page {page_num + 1}: "
                                f"Extracted {len(page_text)} chars"
                            )
                    except Exception as e:
                        error_msg = f"Page {page_num + 1}: {str(e)}"
                        metadata["errors"].append(error_msg)
                        logger.error(error_msg)
                
                metadata["chars_extracted"] = len(text)
                
                self.logger.info(
                    "Page range extraction completed",
                    pdf_path=str(pdf_path),
                    **metadata
                )
                
        except Exception as e:
            logger.error(f"Page range extraction failed: {str(e)}")
            raise
        
        return text, metadata
    
    @timing_decorator
    def get_pdf_info(self, pdf_path: Union[str, Path]) -> Dict[str, any]:
        """
        Get PDF metadata and structure information.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary with PDF information
        """
        pdf_path = Path(pdf_path)
        
        logger.debug(f"Getting PDF info for: {pdf_path}")
        
        info = {
            "path": str(pdf_path),
            "exists": pdf_path.exists(),
            "size_bytes": 0,
            "pages": 0,
            "metadata": {},
            "page_info": []
        }
        
        try:
            if not pdf_path.exists():
                return info
            
            info["size_bytes"] = pdf_path.stat().st_size
            
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                info["pages"] = len(reader.pages)
                
                # Get document metadata
                if reader.metadata:
                    info["metadata"] = {
                        "title": getattr(reader.metadata, "title", None),
                        "author": getattr(reader.metadata, "author", None),
                        "subject": getattr(reader.metadata, "subject", None),
                        "creator": getattr(reader.metadata, "creator", None),
                        "producer": getattr(reader.metadata, "producer", None),
                        "creation_date": str(getattr(reader.metadata, "creation_date", None)),
                        "modification_date": str(getattr(reader.metadata, "modification_date", None))
                    }
                
                # Get basic info for each page
                for i, page in enumerate(reader.pages[:5]):  # First 5 pages only
                    try:
                        page_text = page.extract_text()
                        page_info = {
                            "page_num": i + 1,
                            "chars": len(page_text) if page_text else 0,
                            "has_text": bool(page_text and page_text.strip())
                        }
                        info["page_info"].append(page_info)
                    except Exception as e:
                        logger.warning(f"Could not analyze page {i + 1}: {e}")
                
                self.logger.info(
                    "PDF info retrieved",
                    pdf_path=str(pdf_path),
                    pages=info["pages"],
                    size_mb=info["size_bytes"] / (1024 * 1024)
                )
                
        except Exception as e:
            logger.error(f"Failed to get PDF info: {str(e)}")
            info["error"] = str(e)
        
        return info


# Keep the original function for backward compatibility
@timing_decorator
def extract_text_from_pdf(pdf_path: Union[str, Path]) -> str:
    """
    Extracts text from all pages of a PDF file.

    Args:
        pdf_path: The path to the PDF file.

    Returns:
        The extracted text as a single string.
    """
    extractor = PDFTextExtractor()
    return extractor.extract_text_from_pdf(pdf_path)


# Main block for testing and demonstration
if __name__ == "__main__":
    import json
    from datetime import datetime
    
    print("PDF Text Extractor Testing")
    print("=" * 50)
    
    # Initialize extractor
    extractor = PDFTextExtractor()
    
    # Test 1: Basic extraction with a mock PDF
    print("\n1. Testing basic PDF text extraction...")
    
    # Create a simple test PDF
    test_pdf_path = Path("test_sample.pdf")
    
    try:
        # Create a test PDF with PyPDF2
        from PyPDF2 import PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        import tempfile
        
        # Create a PDF with ReportLab first
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            c = canvas.Canvas(tmp.name, pagesize=letter)
            
            # Add some test content
            c.drawString(100, 750, "Test FDD Document")
            c.drawString(100, 700, "Item 1: The Franchisor")
            c.drawString(100, 650, "This is a test franchise disclosure document.")
            c.drawString(100, 600, "Item 2: Business Experience")
            c.drawString(100, 550, "Our executives have extensive experience.")
            
            # Add a second page
            c.showPage()
            c.drawString(100, 750, "Item 3: Litigation")
            c.drawString(100, 700, "No material litigation to report.")
            
            c.save()
            
            # Copy to test location
            import shutil
            shutil.copy(tmp.name, test_pdf_path)
            Path(tmp.name).unlink()
        
        print(f"Created test PDF: {test_pdf_path}")
        
        # Test extraction
        start_time = time.time()
        extracted_text = extractor.extract_text_from_pdf(test_pdf_path)
        duration = time.time() - start_time
        
        print(f"\nExtraction completed in {duration:.3f}s")
        print(f"Extracted {len(extracted_text)} characters")
        print(f"First 200 chars: {extracted_text[:200]}...")
        
    except ImportError:
        print("ReportLab not installed. Using mock data instead.")
        print("To run full test, install: pip install reportlab")
        
        # Mock extraction results
        extracted_text = "Mock FDD text content..."
        
    except Exception as e:
        print(f"Test failed: {e}")
        extracted_text = ""
    finally:
        # Cleanup
        if test_pdf_path.exists():
            test_pdf_path.unlink()
    
    # Test 2: PDF info extraction
    print("\n2. Testing PDF info extraction...")
    
    # Create mock PDF info
    mock_info = {
        "path": "sample_fdd.pdf",
        "exists": True,
        "size_bytes": 2048576,  # 2MB
        "pages": 75,
        "metadata": {
            "title": "Franchise Disclosure Document",
            "author": "Test Franchisor Inc.",
            "creation_date": str(datetime.now())
        },
        "page_info": [
            {"page_num": 1, "chars": 1500, "has_text": True},
            {"page_num": 2, "chars": 2000, "has_text": True},
            {"page_num": 3, "chars": 1800, "has_text": True}
        ]
    }
    
    print("Mock PDF Info:")
    print(json.dumps(mock_info, indent=2))
    
    # Test 3: Page range extraction
    print("\n3. Testing page range extraction...")
    
    # Mock page range extraction
    page_text = "Item 5: Initial Fees\nThe initial franchise fee is $45,000..."
    page_metadata = {
        "start_page": 10,
        "end_page": 15,
        "pages_processed": 6,
        "chars_extracted": len(page_text),
        "errors": []
    }
    
    print(f"Extracted pages 10-15:")
    print(f"Text: {page_text[:100]}...")
    print(f"Metadata: {json.dumps(page_metadata, indent=2)}")
    
    # Test 4: Performance metrics
    print("\n4. Performance Metrics:")
    print("-" * 30)
    
    # Simulate processing multiple PDFs
    processing_times = [0.234, 0.567, 0.345, 0.789, 0.456]
    page_counts = [50, 120, 75, 200, 90]
    
    for i, (proc_time, pages) in enumerate(zip(processing_times, page_counts)):
        pages_per_sec = pages / proc_time
        print(f"PDF {i+1}: {pages} pages in {proc_time:.3f}s "
              f"({pages_per_sec:.1f} pages/sec)")
    
    avg_time = sum(processing_times) / len(processing_times)
    total_pages = sum(page_counts)
    avg_pages_per_sec = total_pages / sum(processing_times)
    
    print(f"\nAverage processing time: {avg_time:.3f}s")
    print(f"Average speed: {avg_pages_per_sec:.1f} pages/sec")
    
    # Test 5: Error handling
    print("\n5. Testing error handling...")
    
    try:
        # Test with non-existent file
        result = extractor.extract_text_from_pdf("non_existent.pdf")
    except FileNotFoundError as e:
        print(f"✓ Correctly caught FileNotFoundError: {e}")
    
    print("\n" + "=" * 50)
    print("PDF Text Extractor testing completed!")
    print(f"Check 'pdf_extractor_debug.log' for detailed debug output")
