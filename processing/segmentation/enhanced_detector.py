"""
Enhanced FDD Section Detector - Version 2 with minimum page requirements
"""

import logging
import time
from functools import wraps
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from utils.logging import PipelineLogger

# Import base classes - note these may need adjustment based on actual imports
try:
    from src.processing.enhanced_fdd_section_detector_claude import (
        EnhancedFDDSectionDetector,
        FDDSectionCandidate,
        SectionBoundary,
    )
except ImportError:
    # Fallback for testing when src module isn't available
    from dataclasses import dataclass
    
    @dataclass
    class SectionBoundary:
        item_no: int
        item_name: str
        start_page: int
        end_page: int
        confidence: float = 0.0
    
    @dataclass
    class FDDSectionCandidate:
        item_no: int
        item_name: str
        page_num: int
        confidence: float
        detection_method: str
    
    class EnhancedFDDSectionDetector:
        def __init__(self, confidence_threshold=0.7, min_fuzzy_score=80):
            self.confidence_threshold = confidence_threshold
            self.min_fuzzy_score = min_fuzzy_score
        
        def _create_section_boundaries(self, candidates, total_pages=None):
            # Mock implementation for testing
            boundaries = []
            for i, candidate in enumerate(candidates):
                end_page = candidates[i+1].page_num - 1 if i < len(candidates)-1 else (total_pages or candidate.page_num + 5)
                boundaries.append(SectionBoundary(
                    item_no=candidate.item_no,
                    item_name=candidate.item_name,
                    start_page=candidate.page_num,
                    end_page=end_page,
                    confidence=candidate.confidence
                ))
            return boundaries
        
        def detect_sections_from_mineru_json(self, json_path, total_pages=None):
            # Mock implementation
            return []

# Configure module-level logging
logger = logging.getLogger(__name__)

# Create debug logger that writes to a dedicated file
debug_handler = logging.FileHandler('enhanced_detector_debug.log')
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)
debug_handler.setFormatter(debug_formatter)
logger.addHandler(debug_handler)
logger.setLevel(logging.DEBUG)

# Pipeline logger for structured logging
pipeline_logger = PipelineLogger("enhanced_detector")


def timing_decorator(func):
    """Decorator to time function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        
        # Log function entry
        logger.debug(f"Entering {func_name}")
        
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


class EnhancedFDDSectionDetectorV2(EnhancedFDDSectionDetector):
    """
    Enhanced version that ensures certain sections have minimum page counts.

    Item 20 (Outlets and Franchisee Information) typically contains detailed tables
    and should have at least 3 pages.
    """
    
    def __init__(self, confidence_threshold=0.7, min_fuzzy_score=80):
        super().__init__(confidence_threshold, min_fuzzy_score)
        logger.debug(
            f"EnhancedFDDSectionDetectorV2 initialized with "
            f"confidence_threshold={confidence_threshold}, "
            f"min_fuzzy_score={min_fuzzy_score}"
        )
        pipeline_logger.info(
            "Enhanced detector initialized",
            confidence_threshold=confidence_threshold,
            min_fuzzy_score=min_fuzzy_score
        )

    # Minimum page requirements for specific sections
    MIN_PAGE_REQUIREMENTS = {
        20: 3,  # Item 20: Outlets and Franchisee Information (tables of locations)
        21: 2,  # Item 21: Financial Statements (audited statements)
        7: 2,  # Item 7: Estimated Initial Investment (detailed table)
        11: 3,  # Item 11: Franchisor's Assistance (lengthy section)
        17: 3,  # Item 17: Renewal, Termination, Transfer (legal details)
        19: 2,  # Item 19: Financial Performance Representations (if present)
    }

    @timing_decorator
    def _create_section_boundaries(
        self, candidates: List[FDDSectionCandidate], total_pages: Optional[int] = None
    ) -> List[SectionBoundary]:
        """
        Override to ensure minimum page requirements are met.
        """
        logger.debug(
            f"Creating section boundaries for {len(candidates)} candidates, "
            f"total_pages={total_pages}"
        )
        
        # First, create initial boundaries using parent method
        boundaries = super()._create_section_boundaries(candidates, total_pages)
        
        logger.debug(f"Initial boundaries created: {len(boundaries)} sections")
        for b in boundaries:
            logger.debug(
                f"  Item {b.item_no}: pages {b.start_page}-{b.end_page} "
                f"({b.end_page - b.start_page + 1} pages)"
            )

        # Then adjust for minimum page requirements
        adjusted_boundaries = self._adjust_for_minimum_pages(boundaries, total_pages)
        
        logger.debug(f"Adjusted boundaries: {len(adjusted_boundaries)} sections")
        
        return adjusted_boundaries

    @timing_decorator
    def _adjust_for_minimum_pages(
        self, boundaries: List[SectionBoundary], total_pages: Optional[int]
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
                logger.info(
                    f"Item {section.item_no} has {current_pages} pages, needs {min_pages}"
                )
                pipeline_logger.warning(
                    "Section below minimum page requirement",
                    item_no=section.item_no,
                    current_pages=current_pages,
                    min_pages=min_pages
                )

                # Calculate how many more pages we need
                pages_needed = min_pages - current_pages

                # Try to extend the end page
                new_end_page = section.end_page + pages_needed

                # Check if this would exceed document bounds
                if new_end_page > total_pages:
                    # Try to start earlier instead
                    if i > 0 and section.start_page > adjusted[i - 1].start_page + 1:
                        # We can move this section's start earlier
                        max_move_back = section.start_page - (
                            adjusted[i - 1].start_page + 1
                        )
                        move_back = min(pages_needed, max_move_back)
                        section.start_page -= move_back
                        if i > 0:
                            adjusted[i - 1].end_page = section.start_page
                        logger.info(
                            f"Moved Item {section.item_no} start back by {move_back} pages"
                        )
                        logger.debug(
                            f"Item {section.item_no} start page: {section.start_page + move_back} -> {section.start_page}"
                        )
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
                        self._shift_sections_forward(
                            adjusted, i + 1, shift, total_pages
                        )

                logger.info(
                    f"Extended Item {section.item_no} from {old_end} to {section.end_page}"
                )
                pipeline_logger.info(
                    "Section boundary extended",
                    item_no=section.item_no,
                    old_end_page=old_end,
                    new_end_page=section.end_page,
                    pages_added=section.end_page - old_end
                )

        # Final validation
        logger.debug("Validating adjusted boundaries...")
        self._validate_boundaries(adjusted)
        
        # Log final boundaries
        for b in adjusted:
            page_count = b.end_page - b.start_page + 1
            min_req = self.MIN_PAGE_REQUIREMENTS.get(b.item_no, 1)
            logger.debug(
                f"Final: Item {b.item_no} - pages {b.start_page}-{b.end_page} "
                f"({page_count} pages, min: {min_req}) - "
                f"{'OK' if page_count >= min_req else 'BELOW MIN'}"
            )

        return adjusted

    @timing_decorator
    def _shift_sections_forward(
        self,
        boundaries: List[SectionBoundary],
        start_idx: int,
        shift_amount: int,
        total_pages: int,
    ) -> None:
        """
        Shift sections forward by the specified amount.
        """
        logger.debug(
            f"Shifting sections forward starting at index {start_idx} "
            f"by {shift_amount} pages, total_pages={total_pages}"
        )
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
                boundaries[i - 1].end_page = section.start_page
                logger.debug(
                    f"Updated Item {boundaries[i-1].item_no} end page to {boundaries[i-1].end_page}"
                )
        
        logger.debug(f"Completed shifting {len(boundaries) - start_idx} sections")


    def _validate_boundaries(self, boundaries: List[SectionBoundary]) -> None:
        """Validate section boundaries for consistency."""
        logger.debug(f"Validating {len(boundaries)} section boundaries")
        
        for i, boundary in enumerate(boundaries):
            # Check page order
            if boundary.start_page > boundary.end_page:
                logger.error(
                    f"Invalid boundary: Item {boundary.item_no} has "
                    f"start_page ({boundary.start_page}) > end_page ({boundary.end_page})"
                )
            
            # Check for gaps between sections
            if i > 0:
                prev_boundary = boundaries[i-1]
                if boundary.start_page != prev_boundary.end_page + 1:
                    gap = boundary.start_page - prev_boundary.end_page - 1
                    if gap > 0:
                        logger.warning(
                            f"Gap of {gap} pages between Item {prev_boundary.item_no} "
                            f"and Item {boundary.item_no}"
                        )
                    else:
                        logger.warning(
                            f"Overlap between Item {prev_boundary.item_no} "
                            f"and Item {boundary.item_no}"
                        )
        
        logger.debug("Boundary validation completed")


def main():
    """Test the enhanced detector with minimum page requirements"""
    import json
    from datetime import datetime

    print("Enhanced FDD Section Detector Testing")
    print("=" * 50)
    
    # Initialize detector
    print("\n1. Initializing Enhanced Detector...")
    detector = EnhancedFDDSectionDetectorV2(
        confidence_threshold=0.5, min_fuzzy_score=75
    )
    print(f"Detector initialized with:")
    print(f"  Confidence threshold: {detector.confidence_threshold}")
    print(f"  Min fuzzy score: {detector.min_fuzzy_score}")
    
    # Test 2: Create mock candidates
    print("\n2. Creating Mock Section Candidates...")
    
    candidates = [
        FDDSectionCandidate(
            item_no=1,
            item_name="The Franchisor and any Parents, Predecessors, and Affiliates",
            page_num=3,
            confidence=0.95,
            detection_method="exact_match"
        ),
        FDDSectionCandidate(
            item_no=5,
            item_name="Initial Fees",
            page_num=10,
            confidence=0.92,
            detection_method="fuzzy_match"
        ),
        FDDSectionCandidate(
            item_no=7,
            item_name="Estimated Initial Investment",
            page_num=15,
            confidence=0.88,
            detection_method="pattern_match"
        ),
        FDDSectionCandidate(
            item_no=11,
            item_name="Franchisor's Assistance, Advertising, Computer Systems, and Training",
            page_num=25,
            confidence=0.90,
            detection_method="exact_match"
        ),
        FDDSectionCandidate(
            item_no=17,
            item_name="Renewal, Termination, Transfer, and Dispute Resolution",
            page_num=40,
            confidence=0.87,
            detection_method="fuzzy_match"
        ),
        FDDSectionCandidate(
            item_no=20,
            item_name="Outlets and Franchisee Information",
            page_num=50,
            confidence=0.93,
            detection_method="exact_match"
        ),
        FDDSectionCandidate(
            item_no=21,
            item_name="Financial Statements",
            page_num=52,  # Only 2 pages from Item 20!
            confidence=0.91,
            detection_method="exact_match"
        )
    ]
    
    print(f"Created {len(candidates)} section candidates:")
    for c in candidates:
        print(f"  Item {c.item_no}: Page {c.page_num}, confidence={c.confidence:.2f}, method={c.detection_method}")
    
    # Test 3: Create boundaries and test adjustment
    print("\n3. Testing Boundary Creation and Adjustment...")
    
    total_pages = 75
    print(f"\nProcessing with total_pages={total_pages}")
    
    start_time = time.time()
    boundaries = detector._create_section_boundaries(candidates, total_pages)
    duration = time.time() - start_time
    
    print(f"\nBoundary creation completed in {duration:.3f}s")
    print("\nFinal Section Boundaries:")
    print("-" * 80)
    
    for section in boundaries:
        page_count = section.end_page - section.start_page + 1
        min_req = detector.MIN_PAGE_REQUIREMENTS.get(section.item_no, 1)
        status = "✓" if page_count >= min_req else "✗"
        
        print(
            f"{status} Item {section.item_no:2d}: Pages {section.start_page:3d}-{section.end_page:3d} "
            f"({page_count:2d} pages, min: {min_req}) | conf={section.confidence:.2f} | "
            f"'{section.item_name[:35]}...'"
        )
    
    # Test 4: Analyze specific sections
    print("\n4. Analyzing Key Sections...")
    
    key_items = [7, 11, 17, 20, 21]
    for item_no in key_items:
        section = next((s for s in boundaries if s.item_no == item_no), None)
        if section:
            page_count = section.end_page - section.start_page + 1
            min_req = detector.MIN_PAGE_REQUIREMENTS.get(item_no, 1)
            print(f"\nItem {item_no} Analysis:")
            print(f"  Pages: {section.start_page}-{section.end_page} ({page_count} pages)")
            print(f"  Minimum required: {min_req} pages")
            print(f"  Status: {'MEETS REQUIREMENT' if page_count >= min_req else 'BELOW MINIMUM'}")
            print(f"  Confidence: {section.confidence:.2f}")
    
    # Test 5: Performance simulation
    print("\n5. Performance Simulation...")
    
    # Simulate processing multiple documents
    doc_times = []
    for i in range(5):
        start = time.time()
        # Simulate detection work
        time.sleep(0.1)
        _ = detector._create_section_boundaries(candidates, total_pages)
        elapsed = time.time() - start
        doc_times.append(elapsed)
        print(f"  Document {i+1}: {elapsed:.3f}s")
    
    avg_time = sum(doc_times) / len(doc_times)
    print(f"\nAverage processing time: {avg_time:.3f}s per document")
    
    # Test 6: Edge cases
    print("\n6. Testing Edge Cases...")
    
    # Test with very few pages
    print("\nTesting with document that has fewer pages than sections need:")
    small_boundaries = detector._create_section_boundaries(candidates[:3], total_pages=20)
    for b in small_boundaries:
        page_count = b.end_page - b.start_page + 1
        print(f"  Item {b.item_no}: pages {b.start_page}-{b.end_page} ({page_count} pages)")
    
    # Test with overlapping requirements
    print("\nTesting with sections that have competing page requirements:")
    overlap_candidates = [
        FDDSectionCandidate(item_no=19, item_name="Financial Performance Representations", 
                          page_num=45, confidence=0.9, detection_method="exact"),
        FDDSectionCandidate(item_no=20, item_name="Outlets and Franchisee Information", 
                          page_num=47, confidence=0.9, detection_method="exact"),
        FDDSectionCandidate(item_no=21, item_name="Financial Statements", 
                          page_num=49, confidence=0.9, detection_method="exact")
    ]
    
    overlap_boundaries = detector._create_section_boundaries(overlap_candidates, total_pages=55)
    for b in overlap_boundaries:
        page_count = b.end_page - b.start_page + 1
        min_req = detector.MIN_PAGE_REQUIREMENTS.get(b.item_no, 1)
        print(f"  Item {b.item_no}: pages {b.start_page}-{b.end_page} ({page_count} pages, min: {min_req})")
    
    print("\n" + "=" * 50)
    print("Enhanced FDD Section Detector testing completed!")
    print(f"Check 'enhanced_detector_debug.log' for detailed debug output")


if __name__ == "__main__":
    main()
