#!/usr/bin/env python3
"""
Test to ensure Item 20 (Outlets and Franchisee Information) has at least 3 pages
"""
import sys
import logging
from pathlib import Path

sys.path.append("src")

from src.processing.enhanced_fdd_section_detector_claude import (
    EnhancedFDDSectionDetector,
)

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")


def main():
    print("=== ITEM 20 PAGE COUNT TEST ===")
    print("=" * 60)
    print("Item 20 (Outlets and Franchisee Information) should have at least 3 pages")
    print("This section typically contains detailed tables of franchise locations")
    print("=" * 60)

    detector = EnhancedFDDSectionDetector(confidence_threshold=0.5, min_fuzzy_score=75)

    sample_json_path = Path(
        "examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json"
    )

    # Run detection
    sections = detector.detect_sections_from_mineru_json(
        str(sample_json_path), total_pages=75
    )

    # Find Item 20
    item20 = [s for s in sections if s.item_no == 20]

    if not item20:
        print("\nERROR: Item 20 not found in detection results!")
        return

    s = item20[0]
    page_count = s.end_page - s.start_page + 1

    print(f"\nITEM 20 DETECTION RESULTS:")
    print(f"  - Start page: {s.start_page}")
    print(f"  - End page: {s.end_page}")
    print(f"  - Page count: {page_count}")
    print(f"  - Confidence: {s.confidence:.2f}")
    print(f"  - Section name: '{s.item_name}'")

    if page_count >= 3:
        print(f"\n✓ SUCCESS: Item 20 has {page_count} pages (meets 3-page minimum)")
    else:
        print(
            f"\n✗ FAILURE: Item 20 only has {page_count} page(s) (should have at least 3)"
        )
        print("\nThis likely means:")
        print("  1. The detection is picking up a wrong candidate")
        print("  2. The end page calculation is incorrect")
        print("  3. Item 21 is being detected too early, cutting off Item 20")

        # Show surrounding sections for context
        print("\nSurrounding sections:")
        for sec in sections[18:23]:  # Items 18-22
            pc = sec.end_page - sec.start_page + 1
            print(
                f"  Item {sec.item_no:2d}: Pages {sec.start_page:3d}-{sec.end_page:3d} "
                f"({pc:2d} pages) | conf={sec.confidence:.2f}"
            )

        # Check what candidates exist for Item 20
        print("\nDEBUG: Checking Item 20 candidates...")
        mineru_data = detector._load_mineru_json(str(sample_json_path))
        candidates = detector._extract_section_candidates(mineru_data)
        item20_candidates = [c for c in candidates if c.item_no == 20]

        print(f"Found {len(item20_candidates)} candidates for Item 20:")
        for i, c in enumerate(
            sorted(item20_candidates, key=lambda x: x.page_number)[:5]
        ):
            print(
                f"  {i+1}. Page {c.page_number}: {c.detection_method} | "
                f"type={c.element_type} | conf={c.confidence:.2f} | "
                f"text='{c.text_content[:50]}'"
            )


if __name__ == "__main__":
    main()
