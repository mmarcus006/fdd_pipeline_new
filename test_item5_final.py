#!/usr/bin/env python3
"""
Final test of Item 5 detection with detailed output
"""
import sys
import logging
from pathlib import Path

sys.path.append('src')

from src.processing.enhanced_fdd_section_detector_claude import EnhancedFDDSectionDetector

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s | %(message)s'
)

def main():
    print("=== FINAL ITEM 5 DETECTION TEST ===")
    print("=" * 60)
    
    detector = EnhancedFDDSectionDetector(
        confidence_threshold=0.5,
        min_fuzzy_score=75
    )
    
    sample_json_path = Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json")
    
    # Run detection
    sections = detector.detect_sections_from_mineru_json(str(sample_json_path), total_pages=75)
    
    print("\nDETECTION RESULTS:")
    print("-" * 60)
    
    # Show all sections
    for section in sections:
        mark = "***" if section.item_no == 5 else "   "
        print(f"{mark} Item {section.item_no:2d}: Pages {section.start_page:3d}-{section.end_page:3d} | "
              f"conf={section.confidence:.2f} | "
              f"'{section.item_name[:40]}'")
    
    # Analyze Item 5 specifically
    item5 = [s for s in sections if s.item_no == 5]
    if item5:
        s = item5[0]
        print(f"\nITEM 5 ANALYSIS:")
        print(f"  - Start page: {s.start_page} (expected: 17)")
        print(f"  - End page: {s.end_page}")
        print(f"  - Confidence: {s.confidence:.2f}")
        
        if s.start_page != 17:
            print(f"\n  ERROR: Item 5 should start on page 17, not page {s.start_page}")
        else:
            print(f"\n  SUCCESS: Item 5 correctly detected on page 17")

if __name__ == "__main__":
    main()