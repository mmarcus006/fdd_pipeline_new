#!/usr/bin/env python3
"""Debug script to analyze section detection issues"""

import sys
sys.path.append('src')

from pathlib import Path
from src.processing.enhanced_fdd_section_detector_claude import EnhancedFDDSectionDetector

def debug_section_detection():
    """Debug the section detection to understand page assignment issues"""
    
    detector = EnhancedFDDSectionDetector(confidence_threshold=0.7, min_fuzzy_score=80)
    
    sample_json_path = Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json")
    
    if not sample_json_path.exists():
        print(f"Sample file not found: {sample_json_path}")
        return
        
    # Load the MinerU data
    mineru_data = detector._load_mineru_json(str(sample_json_path))
    if not mineru_data:
        print("Failed to load MinerU data")
        return
        
    # Extract all candidates
    candidates = detector._extract_section_candidates(mineru_data)
    
    print(f"\n=== DETECTED CANDIDATES DEBUG ===")
    print(f"Total candidates found: {len(candidates)}")
    
    # Group by item number and show top candidates
    by_item = {}
    for candidate in candidates:
        if candidate.item_no not in by_item:
            by_item[candidate.item_no] = []
        by_item[candidate.item_no].append(candidate)
    
    # Sort candidates within each item by confidence
    method_priority = {'title': 4, 'pattern': 3, 'fuzzy': 2, 'cosine': 1}
    for item_no in by_item:
        by_item[item_no].sort(
            key=lambda x: (x.confidence, method_priority.get(x.detection_method, 0)),
            reverse=True
        )
    
    # Show top candidates for each item
    for item_no in sorted(by_item.keys()):
        candidates_for_item = by_item[item_no]
        print(f"\nItem {item_no:2d} ({len(candidates_for_item)} candidates):")
        
        # Show top 3 candidates
        for i, candidate in enumerate(candidates_for_item[:3]):
            print(f"  {i+1}. Page {candidate.page_number:3d} | Conf: {candidate.confidence:.2f} | Method: {candidate.detection_method:8s} | Text: {candidate.text_content[:50]}")
    
    print(f"\n=== HIGH PAGE NUMBER ANALYSIS ===")
    high_page_candidates = [c for c in candidates if c.page_number > 50]
    print(f"Candidates with page > 50: {len(high_page_candidates)}")
    
    for candidate in sorted(high_page_candidates, key=lambda x: x.page_number, reverse=True)[:10]:
        print(f"  Item {candidate.item_no:2d} | Page {candidate.page_number:3d} | {candidate.detection_method:8s} | {candidate.text_content[:60]}")
        
    # Run full detection and show sequential building process
    print(f"\n=== SEQUENTIAL BUILDING PROCESS ===")
    sections = detector.detect_sections_from_mineru_json(str(sample_json_path), total_pages=75)
    
    print(f"\nFinal Results:")
    for section in sections:
        print(f"Item {section.item_no:2d}: Pages {section.start_page:3d}-{section.end_page:3d} | Conf: {section.confidence:.2f}")

if __name__ == "__main__":
    debug_section_detection()