#!/usr/bin/env python3
"""
Debug script for enhanced FDD section detector with full logging output
"""
import sys
import logging
from pathlib import Path

sys.path.append('src')

from src.processing.enhanced_fdd_section_detector_claude import EnhancedFDDSectionDetector

def main():
    # Set up debug logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(name)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    print("=== ENHANCED FDD SECTION DETECTOR DEBUG ===")
    print("Using relaxed thresholds for less strict detection")
    print("Confidence threshold: 0.5, Min fuzzy score: 75")
    print("=" * 60)
    
    # Create detector with relaxed thresholds
    detector = EnhancedFDDSectionDetector(
        confidence_threshold=0.5,
        min_fuzzy_score=75
    )
    
    sample_json_path = Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json")
    
    if not sample_json_path.exists():
        print(f"Sample file not found: {sample_json_path}")
        return
        
    print(f"\nProcessing: {sample_json_path.name}")
    print("=" * 60)
    
    # Run detection with full debug output
    sections = detector.detect_sections_from_mineru_json(str(sample_json_path), total_pages=75)
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS:")
    print("=" * 60)
    
    for section in sections:
        print(f"Item {section.item_no:2d}: {section.item_name[:50]:<50} "
              f"Pages {section.start_page:3d}-{section.end_page:3d} "
              f"(conf: {section.confidence:.2f})")
    
    print(f"\nDetected {len(sections)} sections total")

if __name__ == "__main__":
    main()