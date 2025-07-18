#!/usr/bin/env python3
"""Test script for enhanced FDD section detector integration."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tasks.document_processing import process_document_layout
from utils.fdd_section_detector_integration import create_integrated_detector


async def test_enhanced_detector():
    """Test the enhanced section detector with a sample PDF."""
    
    # Sample PDF path - update this to a real FDD PDF in your system
    sample_pdf = Path("examples/sample_fdd.pdf")
    
    if not sample_pdf.exists():
        print(f"❌ Sample PDF not found: {sample_pdf}")
        print("Please update the sample_pdf path to point to a real FDD PDF file.")
        return
    
    print(f"Testing enhanced section detector with: {sample_pdf}")
    print("-" * 60)
    
    try:
        # Test the process_document_layout task
        print("\n1. Testing process_document_layout task...")
        layout, sections = await process_document_layout(
            pdf_path=str(sample_pdf),
            fdd_id=uuid4(),
            timeout_seconds=300
        )
        
        print(f"✅ Layout processing completed")
        print(f"   - Total pages: {layout.total_pages}")
        print(f"   - Model version: {layout.model_version}")
        print(f"   - MinerU output dir: {layout.mineru_output_dir}")
        print(f"   - Sections detected: {len(sections)}")
        
        if sections:
            print("\n   Detected sections:")
            for section in sections[:5]:  # Show first 5
                print(f"   - Item {section.item_no}: {section.item_name}")
                print(f"     Pages {section.start_page}-{section.end_page} (confidence: {section.confidence:.2f})")
        
        # Test the standalone detector if MinerU output exists
        if layout.mineru_output_dir:
            print("\n2. Testing standalone enhanced detector...")
            detector = create_integrated_detector()
            
            layout_json_path = Path(layout.mineru_output_dir) / "layout.json"
            if layout_json_path.exists():
                sections2 = detector.detect_sections(
                    mineru_json_path=str(layout_json_path),
                    total_pages=layout.total_pages
                )
                print(f"✅ Standalone detection completed: {len(sections2)} sections")
            else:
                print(f"⚠️  No layout.json found at: {layout_json_path}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


async def test_detector_methods():
    """Test the detector method availability."""
    print("\n3. Testing detector method availability...")
    
    try:
        detector = create_integrated_detector()
        stats = detector.get_detection_method_stats()
        
        print(f"✅ Detector statistics:")
        print(f"   - Enhanced available: {stats['enhanced_available']}")
        print(f"   - Existing available: {stats['existing_available']}")
        print(f"   - Total methods: {stats['total_methods']}")
        
        if stats.get('enhanced_capabilities'):
            print(f"   - Enhanced capabilities: {', '.join(stats['enhanced_capabilities'][:3])}...")
            
    except Exception as e:
        print(f"❌ Method test failed: {e}")


def main():
    """Run all tests."""
    print("Enhanced FDD Section Detector Integration Test")
    print("=" * 60)
    
    # Run async tests
    asyncio.run(test_enhanced_detector())
    asyncio.run(test_detector_methods())
    
    print("\nTest complete!")


if __name__ == "__main__":
    main()