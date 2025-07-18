#!/usr/bin/env python3
"""Debug script to analyze sequential section building"""

import sys
sys.path.append('src')

from pathlib import Path
from src.processing.enhanced_fdd_section_detector_claude import EnhancedFDDSectionDetector

def debug_sequential_building():
    """Debug the sequential building process"""
    
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
    
    # Group by item number for analysis
    by_item = {}
    for candidate in candidates:
        if candidate.item_no not in by_item:
            by_item[candidate.item_no] = []
        by_item[candidate.item_no].append(candidate)
    
    # Sort candidates within each item by quality (same as in the actual algorithm)
    method_priority = {'title': 4, 'pattern': 3, 'fuzzy': 2, 'cosine': 1}
    for item_no in by_item:
        by_item[item_no].sort(
            key=lambda x: (
                x.confidence, 
                method_priority.get(x.detection_method, 0),
                -x.page_number  # Prefer earlier pages
            ),
            reverse=True
        )
    
    print("=== SEQUENTIAL BUILDING SIMULATION ===")
    current_min_page = 1
    
    for item_no in range(25):
        if item_no in by_item:
            print(f"\nItem {item_no:2d} (current min_page: {current_min_page}):")
            
            # Show top 3 candidates
            for i, candidate in enumerate(by_item[item_no][:3]):
                valid = "✓" if candidate.page_number >= current_min_page else "✗"
                print(f"  {i+1}. {valid} Page {candidate.page_number:3d} | Conf: {candidate.confidence:.2f} | {candidate.detection_method:8s} | {candidate.text_content[:60]}")
            
            # Find the selected candidate (first one that meets min_page requirement)
            selected = None
            for candidate in by_item[item_no]:
                if candidate.page_number >= current_min_page:
                    selected = candidate
                    break
            
            if selected:
                print(f"  SELECTED: Page {selected.page_number} (conf: {selected.confidence:.2f})")
                current_min_page = selected.page_number + 1
            else:
                # Would be interpolated
                best = by_item[item_no][0]
                print(f"  WOULD INTERPOLATE: Best candidate on page {best.page_number} < min_page {current_min_page}")
                # Simulate interpolation
                estimated_page = max(current_min_page, int(1 + (75 - 1) * (item_no / 24)))
                interpolated_page = min(estimated_page, 75 - (24 - item_no))
                interpolated_page = max(interpolated_page, current_min_page)
                print(f"  INTERPOLATED: Page {interpolated_page}")
                current_min_page = interpolated_page + 1
        else:
            print(f"\nItem {item_no:2d}: No candidates found")
            # Simulate interpolation
            estimated_page = max(current_min_page, int(1 + (75 - 1) * (item_no / 24)))
            interpolated_page = min(estimated_page, 75 - (24 - item_no))
            interpolated_page = max(interpolated_page, current_min_page)
            print(f"  INTERPOLATED: Page {interpolated_page}")
            current_min_page = interpolated_page + 1

if __name__ == "__main__":
    debug_sequential_building()