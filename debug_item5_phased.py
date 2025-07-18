#!/usr/bin/env python3
"""
Debug script to trace Item 5 detection through phased approach
"""
import sys
import logging
from pathlib import Path

sys.path.append('src')

from src.processing.enhanced_fdd_section_detector_claude import EnhancedFDDSectionDetector

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)-8s | %(message)s'
)

def main():
    print("=== ITEM 5 PHASED DETECTION DEBUG ===")
    print("=" * 60)
    
    detector = EnhancedFDDSectionDetector(
        confidence_threshold=0.5,
        min_fuzzy_score=75
    )
    
    sample_json_path = Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json")
    
    # Load data and extract candidates
    mineru_data = detector._load_mineru_json(str(sample_json_path))
    candidates = detector._extract_section_candidates(mineru_data)
    
    # Group by item
    by_item = {}
    for candidate in candidates:
        if candidate.item_no not in by_item:
            by_item[candidate.item_no] = []
        by_item[candidate.item_no].append(candidate)
    
    # Sort candidates within each item by quality
    method_priority = {'title': 4, 'pattern': 3, 'fuzzy': 2, 'cosine': 1}
    for item_no in by_item:
        by_item[item_no].sort(
            key=lambda x: (
                x.confidence, 
                method_priority.get(x.detection_method, 0),
                -x.page_number
            ),
            reverse=True
        )
    
    # Simulate the sequential build for items 0-5
    print("\nSIMULATING SEQUENTIAL BUILD:")
    print("-" * 60)
    
    current_min_page = 1
    
    for item_no in range(6):  # Just items 0-5
        print(f"\nItem {item_no}:")
        print(f"  Current min_page: {current_min_page}")
        
        if item_no not in by_item:
            print(f"  No candidates found")
            continue
            
        # Get max page for this item
        max_page = detector._get_max_page_for_item(item_no, by_item, 75)
        print(f"  Max page: {max_page}")
        
        # Show all candidates for this item
        all_candidates = by_item[item_no]
        print(f"  Total candidates: {len(all_candidates)}")
        
        # Show top 5 candidates
        print(f"  Top candidates:")
        for i, c in enumerate(all_candidates[:5]):
            valid = "✓" if current_min_page <= c.page_number < max_page else "✗"
            print(f"    {i+1}. {valid} Page {c.page_number}: {c.detection_method:8s} | "
                  f"type={c.element_type:10s} | conf={c.confidence:.2f} | "
                  f"text='{c.text_content[:40]}'")
        
        # Test phased detection
        print(f"\n  PHASED DETECTION:")
        
        # Phase 1: Title with "Item X" pattern
        phase1_candidates = [
            c for c in all_candidates
            if c.element_type == 'title'
            and detector._has_exact_item_pattern(c.text_content, item_no)
            and current_min_page <= c.page_number < max_page
        ]
        print(f"    Phase 1 (title with 'Item {item_no}'): {len(phase1_candidates)} candidates")
        
        # Phase 2: Fuzzy matching
        phase2_candidates = [
            c for c in all_candidates
            if c.detection_method == 'fuzzy'
            and current_min_page <= c.page_number < max_page
        ]
        print(f"    Phase 2 (fuzzy): {len(phase2_candidates)} candidates")
        if phase2_candidates:
            # Show title vs non-title breakdown
            title_fuzzy = [c for c in phase2_candidates if c.element_type == 'title']
            print(f"      - Title elements: {len(title_fuzzy)}")
            print(f"      - Other elements: {len(phase2_candidates) - len(title_fuzzy)}")
            if title_fuzzy:
                best_title = max(title_fuzzy, key=lambda x: (x.confidence, -x.page_number))
                print(f"      - Best title: Page {best_title.page_number} '{best_title.text_content}'")
        
        # Phase 3: Pattern
        phase3_candidates = [
            c for c in all_candidates
            if c.detection_method == 'pattern'
            and current_min_page <= c.page_number < max_page
        ]
        print(f"    Phase 3 (pattern): {len(phase3_candidates)} candidates")
        
        # Phase 4: Cosine
        phase4_candidates = [
            c for c in all_candidates
            if c.detection_method == 'cosine'
            and current_min_page <= c.page_number < max_page
        ]
        print(f"    Phase 4 (cosine): {len(phase4_candidates)} candidates")
        
        # Find selected
        selected = detector._find_sequential_section(item_no, by_item, current_min_page, 75)
        print(f"\n  SELECTED: Page {selected.page_number} ({selected.detection_method})")
        
        # Update min page for next iteration
        current_min_page = selected.page_number + 1

if __name__ == "__main__":
    main()