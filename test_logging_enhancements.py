#!/usr/bin/env python3
"""Test script to verify logging enhancements in processing modules."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_pdf_extractor():
    """Test PDF extractor logging."""
    print("\n" + "="*60)
    print("Testing PDF Extractor Logging")
    print("="*60)
    
    try:
        from processing.pdf.pdf_extractor import PDFTextExtractor
        
        extractor = PDFTextExtractor()
        
        # Test with a non-existent file to trigger error logging
        try:
            result = extractor.extract_text_from_pdf("non_existent_test.pdf")
        except FileNotFoundError as e:
            print(f"✓ Expected error caught: {e}")
        
        # Test PDF info
        info = extractor.get_pdf_info("test_sample.pdf")
        print(f"✓ PDF info retrieved: {info['exists']} exists")
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")


def test_document_segmentation():
    """Test document segmentation logging."""
    print("\n" + "="*60)
    print("Testing Document Segmentation Logging")
    print("="*60)
    
    try:
        from processing.segmentation.document_segmentation import (
            PDFSplitter, SectionMetadataManager, DocumentSegmentationSystem
        )
        
        # Test PDF splitter
        splitter = PDFSplitter()
        print("✓ PDFSplitter initialized")
        
        # Test metadata manager
        metadata_manager = SectionMetadataManager()
        print("✓ SectionMetadataManager initialized")
        
        # Test segmentation system
        seg_system = DocumentSegmentationSystem()
        print("✓ DocumentSegmentationSystem initialized")
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")


def test_enhanced_detector():
    """Test enhanced detector logging."""
    print("\n" + "="*60)
    print("Testing Enhanced Detector Logging")
    print("="*60)
    
    try:
        from processing.segmentation.enhanced_detector import EnhancedFDDSectionDetectorV2
        
        detector = EnhancedFDDSectionDetectorV2(
            confidence_threshold=0.7,
            min_fuzzy_score=80
        )
        print("✓ EnhancedFDDSectionDetectorV2 initialized")
        
        # Test minimum page requirements
        print(f"✓ Minimum page requirements configured: {len(detector.MIN_PAGE_REQUIREMENTS)} items")
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")


def check_log_files():
    """Check if debug log files were created."""
    print("\n" + "="*60)
    print("Checking Debug Log Files")
    print("="*60)
    
    log_files = [
        "pdf_extractor_debug.log",
        "document_segmentation_debug.log",
        "enhanced_detector_debug.log"
    ]
    
    for log_file in log_files:
        path = Path(log_file)
        if path.exists():
            size = path.stat().st_size
            print(f"✓ {log_file}: {size} bytes")
        else:
            print(f"✗ {log_file}: Not found (will be created on first use)")


def main():
    """Run all tests."""
    print("FDD Pipeline - Logging Enhancement Test")
    print("======================================")
    
    test_pdf_extractor()
    test_document_segmentation()
    test_enhanced_detector()
    check_log_files()
    
    print("\n" + "="*60)
    print("Testing completed!")
    print("="*60)
    print("\nTo see full functionality, run the main blocks directly:")
    print("  python processing/pdf/pdf_extractor.py")
    print("  python processing/segmentation/document_segmentation.py")
    print("  python processing/segmentation/enhanced_detector.py")


if __name__ == "__main__":
    main()