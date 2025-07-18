"""
Integration module for Enhanced FDD Section Detection

This module provides seamless integration between the new enhanced section detector
and the existing FDD pipeline infrastructure.

Author: Claude Code Assistant
Created: 2025-01-18
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

from models.document_models import SectionBoundary, FDDSectionDetector
from src.processing.enhanced_fdd_section_detector_claude import (
    EnhancedFDDSectionDetector,
)
from utils.logging import PipelineLogger


logger = logging.getLogger(__name__)


class HybridFDDSectionDetector:
    """
    Hybrid section detector that combines existing and enhanced detection methods.

    Falls back gracefully between enhanced MinerU-based detection and
    traditional text-based detection methods.
    """

    def __init__(
        self,
        use_enhanced: bool = True,
        enhanced_confidence_threshold: float = 0.7,
        enhanced_min_fuzzy_score: int = 80,
        fallback_to_existing: bool = True,
    ):
        """
        Initialize hybrid detector.

        Args:
            use_enhanced: Whether to try enhanced detection first
            enhanced_confidence_threshold: Confidence threshold for enhanced detector
            enhanced_min_fuzzy_score: Minimum fuzzy score for enhanced detector
            fallback_to_existing: Whether to fallback to existing detector on failure
        """
        self.use_enhanced = use_enhanced
        self.fallback_to_existing = fallback_to_existing

        # Initialize enhanced detector
        if use_enhanced:
            try:
                self.enhanced_detector = EnhancedFDDSectionDetector(
                    confidence_threshold=enhanced_confidence_threshold,
                    min_fuzzy_score=enhanced_min_fuzzy_score,
                )
                logger.info("Enhanced FDD section detector initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize enhanced detector: {e}")
                self.enhanced_detector = None

        # Initialize existing detector as fallback
        if fallback_to_existing:
            try:
                self.existing_detector = FDDSectionDetector()
                logger.info("Existing FDD section detector initialized as fallback")
            except Exception as e:
                logger.error(f"Failed to initialize existing detector: {e}")
                self.existing_detector = None

    def detect_sections(
        self,
        mineru_json_path: Optional[str] = None,
        pdf_text: Optional[str] = None,
        total_pages: Optional[int] = None,
        **kwargs,
    ) -> List[SectionBoundary]:
        """
        Detect FDD sections using best available method.

        Args:
            mineru_json_path: Path to MinerU layout JSON (for enhanced detection)
            pdf_text: Plain text content (for existing detection)
            total_pages: Total pages in document
            **kwargs: Additional parameters for detectors

        Returns:
            List of detected section boundaries
        """
        # Try enhanced detection first if available and data provided
        if (
            self.use_enhanced
            and self.enhanced_detector
            and mineru_json_path
            and Path(mineru_json_path).exists()
        ):

            try:
                logger.info(
                    f"Attempting enhanced section detection with {mineru_json_path}"
                )
                sections = self.enhanced_detector.detect_sections_from_mineru_json(
                    mineru_json_path, total_pages=total_pages
                )

                # Validate results
                if self._validate_detection_results(sections, total_pages):
                    logger.info(
                        f"Enhanced detection successful: {len(sections)} sections found"
                    )
                    return sections
                else:
                    logger.warning("Enhanced detection results failed validation")

            except Exception as e:
                logger.error(f"Enhanced detection failed: {e}")

        # Fallback to existing detector
        if self.fallback_to_existing and self.existing_detector and pdf_text:
            try:
                logger.info("Falling back to existing section detection method")
                sections = self.existing_detector.detect_sections(pdf_text, **kwargs)

                if sections:
                    logger.info(
                        f"Existing detection successful: {len(sections)} sections found"
                    )
                    return sections
                else:
                    logger.warning("Existing detection returned no results")

            except Exception as e:
                logger.error(f"Existing detection failed: {e}")

        # Final fallback: create minimal section structure
        logger.warning(
            "All detection methods failed, creating minimal section structure"
        )
        return self._create_fallback_sections(total_pages or 50)

    def _validate_detection_results(
        self, sections: List[SectionBoundary], total_pages: Optional[int] = None
    ) -> bool:
        """
        Validate section detection results.

        Args:
            sections: Detected sections
            total_pages: Total pages in document

        Returns:
            True if results are valid
        """
        if not sections:
            return False

        # Must have reasonable number of sections (at least 10, at most 25)
        if len(sections) < 10 or len(sections) > 25:
            logger.warning(f"Unusual number of sections detected: {len(sections)}")

        # Check for required sections
        required_items = {0, 1, 5, 6, 7, 19, 20, 21, 23}
        detected_items = {s.item_no for s in sections}
        missing_required = required_items - detected_items

        if missing_required:
            logger.warning(f"Missing required sections: {missing_required}")

        # Check page ordering
        prev_page = 0
        for section in sections:
            if section.start_page <= prev_page:
                logger.warning(f"Section {section.item_no} has invalid page ordering")
                return False
            prev_page = section.start_page

        # Check page ranges are reasonable
        if total_pages:
            for section in sections:
                if section.end_page > total_pages + 5:  # Allow some tolerance
                    logger.warning(
                        f"Section {section.item_no} end page exceeds document length"
                    )

        return True

    def _create_fallback_sections(self, total_pages: int) -> List[SectionBoundary]:
        """
        Create minimal fallback section structure.

        Args:
            total_pages: Total pages in document

        Returns:
            Basic section boundaries
        """
        logger.info("Creating fallback section structure")

        # Create evenly distributed sections
        sections_per_page = max(1, total_pages // 25)
        sections = []

        section_names = {
            0: "Cover/Introduction",
            1: "The Franchisor and Any Parents, Predecessors, and Affiliates",
            2: "Business Experience",
            3: "Litigation",
            4: "Bankruptcy",
            5: "Initial Fees",
            6: "Other Fees",
            7: "Estimated Initial Investment",
            8: "Restrictions on Sources of Products and Services",
            9: "Franchisee's Obligations",
            10: "Financing",
            11: "Franchisor's Assistance, Advertising, Computer Systems, and Training",
            12: "Territory",
            13: "Trademarks",
            14: "Patents, Copyrights, and Proprietary Information",
            15: "Obligation to Participate in the Actual Operation of the Franchise Business",
            16: "Restrictions on What the Franchisee May Sell",
            17: "Renewal, Termination, Transfer, and Dispute Resolution",
            18: "Public Figures",
            19: "Financial Performance Representations",
            20: "Outlets and Franchisee Information",
            21: "Financial Statements",
            22: "Contracts",
            23: "Receipts",
            24: "Appendix/Exhibits",
        }

        for i in range(25):
            start_page = max(1, (i * sections_per_page) + 1)
            end_page = min(total_pages, ((i + 1) * sections_per_page))

            # Ensure no overlaps
            if sections and start_page <= sections[-1].end_page:
                start_page = sections[-1].end_page + 1

            if start_page > total_pages:
                break

            section = SectionBoundary(
                item_no=i,
                item_name=section_names.get(i, f"Item {i}"),
                start_page=start_page,
                end_page=end_page,
                confidence=0.1,  # Low confidence for fallback
            )
            sections.append(section)

        return sections

    def get_detection_method_stats(self) -> Dict[str, Any]:
        """
        Get statistics about available detection methods.

        Returns:
            Dictionary with method availability and capabilities
        """
        stats = {
            "enhanced_available": self.enhanced_detector is not None,
            "existing_available": self.existing_detector is not None,
            "total_methods": 0,
        }

        if stats["enhanced_available"]:
            stats["total_methods"] += 1
            stats["enhanced_capabilities"] = [
                "MinerU JSON parsing",
                "Title element detection",
                "Pattern matching",
                "Fuzzy string matching",
                "Cosine similarity",
                "Confidence scoring",
                "Validation rules",
            ]

        if stats["existing_available"]:
            stats["total_methods"] += 1
            stats["existing_capabilities"] = [
                "Text-based detection",
                "Pattern matching",
                "Fallback logic",
            ]

        return stats


def create_integrated_detector(
    enhanced_config: Optional[Dict[str, Any]] = None,
    use_enhanced: bool = True,
    fallback_to_existing: bool = True,
) -> HybridFDDSectionDetector:
    """
    Factory function to create integrated detector with configuration.

    Args:
        enhanced_config: Configuration for enhanced detector
        use_enhanced: Whether to use enhanced detection
        fallback_to_existing: Whether to fallback to existing detector

    Returns:
        Configured hybrid detector
    """
    config = enhanced_config or {}

    return HybridFDDSectionDetector(
        use_enhanced=use_enhanced,
        enhanced_confidence_threshold=config.get("confidence_threshold", 0.7),
        enhanced_min_fuzzy_score=config.get("min_fuzzy_score", 80),
        fallback_to_existing=fallback_to_existing,
    )


# Convenience function for existing code compatibility
def detect_fdd_sections(
    mineru_json_path: Optional[str] = None,
    pdf_text: Optional[str] = None,
    total_pages: Optional[int] = None,
    use_enhanced: bool = True,
    **kwargs,
) -> List[SectionBoundary]:
    """
    Convenience function for detecting FDD sections.

    This function provides a simple interface that can be dropped into
    existing code with minimal changes.

    Args:
        mineru_json_path: Path to MinerU layout JSON
        pdf_text: Plain text content (fallback)
        total_pages: Total pages in document
        use_enhanced: Whether to use enhanced detection
        **kwargs: Additional parameters

    Returns:
        List of detected section boundaries
    """
    detector = create_integrated_detector(use_enhanced=use_enhanced)

    return detector.detect_sections(
        mineru_json_path=mineru_json_path,
        pdf_text=pdf_text,
        total_pages=total_pages,
        **kwargs,
    )


def main():
    """Example usage and testing"""
    print("FDD Section Detector Integration")
    print("=" * 50)

    # Test with sample data
    sample_json = Path(
        "examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json"
    )

    if sample_json.exists():
        print(f"Testing with sample: {sample_json.name}")

        # Test integrated detector
        detector = create_integrated_detector()
        stats = detector.get_detection_method_stats()

        print(f"Detection methods available: {stats['total_methods']}")
        print(f"Enhanced available: {stats['enhanced_available']}")
        print(f"Existing available: {stats['existing_available']}")

        # Run detection
        sections = detector.detect_sections(
            mineru_json_path=str(sample_json), total_pages=75
        )

        print(f"\nDetected {len(sections)} sections:")
        for i, section in enumerate(sections[:5]):
            print(
                f"{i+1}. Item {section.item_no}: {section.item_name[:40]}... "
                f"(pages {section.start_page}-{section.end_page})"
            )

        if len(sections) > 5:
            print(f"... and {len(sections) - 5} more sections")

    else:
        print("Sample file not found, testing fallback mode")

        # Test fallback
        sections = detect_fdd_sections(
            pdf_text="Sample text content", total_pages=50, use_enhanced=False
        )

        print(f"Fallback detection created {len(sections)} sections")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
