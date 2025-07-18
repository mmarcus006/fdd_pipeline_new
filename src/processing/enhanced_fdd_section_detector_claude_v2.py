"""
Enhanced FDD Section Detector - Version 2 with minimum page requirements
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from src.processing.enhanced_fdd_section_detector_claude import EnhancedFDDSectionDetector, FDDSectionCandidate, SectionBoundary

logger = logging.getLogger(__name__)


class EnhancedFDDSectionDetectorV2(EnhancedFDDSectionDetector):
    """
    Enhanced version that ensures certain sections have minimum page counts.
    
    Item 20 (Outlets and Franchisee Information) typically contains detailed tables
    and should have at least 3 pages.
    """
    
    # Minimum page requirements for specific sections
    MIN_PAGE_REQUIREMENTS = {
        20: 3,  # Item 20: Outlets and Franchisee Information (tables of locations)
        21: 2,  # Item 21: Financial Statements (audited statements)
        7: 2,   # Item 7: Estimated Initial Investment (detailed table)
        11: 3,  # Item 11: Franchisor's Assistance (lengthy section)
        17: 3,  # Item 17: Renewal, Termination, Transfer (legal details)
        19: 2,  # Item 19: Financial Performance Representations (if present)
    }
    
    def _create_section_boundaries(
        self, 
        candidates: List[FDDSectionCandidate],
        total_pages: Optional[int] = None
    ) -> List[SectionBoundary]:
        """
        Override to ensure minimum page requirements are met.
        """
        # First, create initial boundaries using parent method
        boundaries = super()._create_section_boundaries(candidates, total_pages)
        
        # Then adjust for minimum page requirements
        adjusted_boundaries = self._adjust_for_minimum_pages(boundaries, total_pages)
        
        return adjusted_boundaries
    
    def _adjust_for_minimum_pages(
        self,
        boundaries: List[SectionBoundary],
        total_pages: Optional[int]
    ) -> List[SectionBoundary]:
        """
        Adjust section boundaries to meet minimum page requirements.
        
        Strategy:
        1. Work backwards from the end to avoid cascading issues
        2. For sections needing more pages, extend their end page
        3. Push subsequent sections forward as needed
        """
        total_pages = total_pages or 75
        adjusted = boundaries.copy()
        
        # Work backwards to avoid cascading
        for i in range(len(adjusted) - 1, -1, -1):
            section = adjusted[i]
            min_pages = self.MIN_PAGE_REQUIREMENTS.get(section.item_no, 1)
            current_pages = section.end_page - section.start_page + 1
            
            if current_pages < min_pages:
                logger.info(f"Item {section.item_no} has {current_pages} pages, needs {min_pages}")
                
                # Calculate how many more pages we need
                pages_needed = min_pages - current_pages
                
                # Try to extend the end page
                new_end_page = section.end_page + pages_needed
                
                # Check if this would exceed document bounds
                if new_end_page > total_pages:
                    # Try to start earlier instead
                    if i > 0 and section.start_page > adjusted[i-1].start_page + 1:
                        # We can move this section's start earlier
                        max_move_back = section.start_page - (adjusted[i-1].start_page + 1)
                        move_back = min(pages_needed, max_move_back)
                        section.start_page -= move_back
                        if i > 0:
                            adjusted[i-1].end_page = section.start_page
                        logger.info(f"Moved Item {section.item_no} start back by {move_back} pages")
                    new_end_page = min(new_end_page, total_pages)
                
                # Update this section's end page
                old_end = section.end_page
                section.end_page = new_end_page
                
                # Update the next section's boundaries if needed
                if i < len(adjusted) - 1:
                    next_section = adjusted[i + 1]
                    if next_section.start_page <= new_end_page:
                        # Push the next section forward
                        shift = new_end_page - next_section.start_page + 1
                        self._shift_sections_forward(adjusted, i + 1, shift, total_pages)
                
                logger.info(f"Extended Item {section.item_no} from {old_end} to {section.end_page}")
        
        # Final validation
        self._validate_boundaries(adjusted)
        
        return adjusted
    
    def _shift_sections_forward(
        self,
        boundaries: List[SectionBoundary],
        start_idx: int,
        shift_amount: int,
        total_pages: int
    ) -> None:
        """
        Shift sections forward by the specified amount.
        """
        for i in range(start_idx, len(boundaries)):
            section = boundaries[i]
            
            # Don't push beyond document bounds
            if section.start_page + shift_amount > total_pages:
                # Compress this section if needed
                section.start_page = min(section.start_page + shift_amount, total_pages)
                section.end_page = min(section.end_page + shift_amount, total_pages)
                
                # Ensure at least 1 page
                if section.start_page >= section.end_page:
                    section.end_page = min(section.start_page + 1, total_pages)
            else:
                section.start_page += shift_amount
                section.end_page = min(section.end_page + shift_amount, total_pages)
            
            # Update overlap with previous section
            if i > 0:
                boundaries[i-1].end_page = section.start_page


def main():
    """Test the enhanced detector with minimum page requirements"""
    import sys
    from pathlib import Path
    
    logging.basicConfig(level=logging.INFO)
    
    detector = EnhancedFDDSectionDetectorV2(confidence_threshold=0.5, min_fuzzy_score=75)
    
    sample_json_path = Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json")
    
    sections = detector.detect_sections_from_mineru_json(str(sample_json_path), total_pages=75)
    
    print("\nDETECTION RESULTS WITH MINIMUM PAGE REQUIREMENTS:")
    print("-" * 80)
    
    for section in sections:
        page_count = section.end_page - section.start_page + 1
        min_req = detector.MIN_PAGE_REQUIREMENTS.get(section.item_no, 1)
        status = "✓" if page_count >= min_req else "✗"
        
        print(f"{status} Item {section.item_no:2d}: Pages {section.start_page:3d}-{section.end_page:3d} "
              f"({page_count:2d} pages, min: {min_req}) | conf={section.confidence:.2f} | "
              f"'{section.item_name[:35]}'")
    
    # Check Item 20 specifically
    item20 = [s for s in sections if s.item_no == 20][0]
    page_count = item20.end_page - item20.start_page + 1
    
    print(f"\nItem 20 Analysis:")
    print(f"  Pages: {item20.start_page}-{item20.end_page} ({page_count} pages)")
    print(f"  Meets minimum requirement: {'YES' if page_count >= 3 else 'NO'}")


if __name__ == "__main__":
    main()