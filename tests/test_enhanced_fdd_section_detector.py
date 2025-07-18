"""
Tests for Enhanced FDD Section Detection

Tests the enhanced section detection capabilities using real MinerU output
from the Valvoline FDD example.

Author: Claude Code Assistant  
Created: 2025-01-18
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import os

from utils.enhanced_fdd_section_detector import (
    EnhancedFDDSectionDetector,
    FDDSectionCandidate
)
from models.document_models import SectionBoundary


class TestEnhancedFDDSectionDetector:
    """Test suite for enhanced FDD section detection"""
    
    @pytest.fixture
    def detector(self):
        """Create detector instance for testing"""
        return EnhancedFDDSectionDetector(
            confidence_threshold=0.7,
            min_fuzzy_score=80
        )
        
    @pytest.fixture
    def sample_mineru_data(self):
        """Sample MinerU JSON structure for testing"""
        return {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {
                            "type": "title",
                            "bbox": [100, 100, 400, 120],
                            "lines": [
                                {
                                    "spans": [
                                        {
                                            "type": "text",
                                            "content": "FRANCHISE DISCLOSURE DOCUMENT"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "page_idx": 8,
                    "para_blocks": [
                        {
                            "type": "title", 
                            "bbox": [290, 76, 320, 87],
                            "lines": [
                                {
                                    "spans": [
                                        {
                                            "type": "text",
                                            "content": "Item 1"
                                        }
                                    ]
                                }
                            ],
                            "level": 1
                        },
                        {
                            "type": "title",
                            "bbox": [105, 100, 504, 114], 
                            "lines": [
                                {
                                    "spans": [
                                        {
                                            "type": "text",
                                            "content": "THE FRANCHISOR, AND ANY PARENTS, PREDECESSORS AND AFFILIATES"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "page_idx": 10,
                    "para_blocks": [
                        {
                            "type": "title",
                            "bbox": [290, 360, 321, 373],
                            "lines": [
                                {
                                    "spans": [
                                        {
                                            "type": "text", 
                                            "content": "Item 5"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
    @pytest.fixture 
    def valvoline_json_path(self):
        """Path to actual Valvoline example JSON"""
        return Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json")
        
    def test_detector_initialization(self, detector):
        """Test detector initializes properly"""
        assert detector.confidence_threshold == 0.7
        assert detector.min_fuzzy_score == 80
        assert detector._reference_vectors is not None
        assert len(detector.STANDARD_FDD_SECTIONS) == 25
        
    def test_standard_section_definitions(self, detector):
        """Test that all 25 standard sections are defined"""
        sections = detector.STANDARD_FDD_SECTIONS
        
        # Check all items 0-24 are present
        for i in range(25):
            assert i in sections
            assert len(sections[i]) > 0
            
        # Check specific required sections
        assert "Initial Fees" in sections[5]
        assert "Other Fees" in sections[6] 
        assert "Estimated Initial Investment" in sections[7]
        assert "Financial Performance" in sections[19]
        assert "Financial Statements" in sections[21]
        
    def test_load_mineru_json_valid(self, detector, sample_mineru_data):
        """Test loading valid MinerU JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_mineru_data, f)
            temp_path = f.name
            
        try:
            data = detector._load_mineru_json(temp_path)
            assert data is not None
            assert 'pdf_info' in data
            assert len(data['pdf_info']) == 3
        finally:
            os.unlink(temp_path)
            
    def test_load_mineru_json_invalid(self, detector):
        """Test loading invalid JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"invalid": "json structure"}')
            temp_path = f.name
            
        try:
            data = detector._load_mineru_json(temp_path)
            assert data is None
        finally:
            os.unlink(temp_path)
            
    def test_extract_text_from_block(self, detector):
        """Test text extraction from MinerU blocks"""
        block = {
            "lines": [
                {
                    "spans": [
                        {"content": "Item 5"},
                        {"content": "Initial Fees"}
                    ]
                }
            ]
        }
        
        text = detector._extract_text_from_block(block)
        assert text == "Item 5 Initial Fees"
        
    def test_extract_text_from_nested_blocks(self, detector):
        """Test text extraction with nested block structure"""
        block = {
            "blocks": [
                {
                    "lines": [
                        {
                            "spans": [
                                {"content": "Item 7"},
                                {"content": "Investment"}
                            ]
                        }
                    ]
                }
            ]
        }
        
        text = detector._extract_text_from_block(block)
        assert text == "Item 7 Investment"
        
    def test_match_item_pattern_basic(self, detector):
        """Test basic item pattern matching"""
        test_cases = [
            ("Item 1", (1, "Item 1")),
            ("Item 5 Initial Fees", (5, "Initial Fees")),
            ("Item 19: Financial Performance Representations", (19, "Financial Performance Representations")),
            ("ITEM 21 - FINANCIAL STATEMENTS", (21, "FINANCIAL STATEMENTS")),
            ("Not an item", None),
            ("Item 25", None),  # Out of range
        ]
        
        for text, expected in test_cases:
            result = detector._match_item_pattern(text)
            if expected is None:
                assert result is None
            else:
                assert result is not None
                assert result[0] == expected[0]
                # Item name can be normalized, so just check it's not empty
                assert len(result[1]) > 0
                
    def test_find_all_item_patterns(self, detector):
        """Test finding multiple item patterns in text (TOC style)"""
        toc_text = """
        Item 1 THE FRANCHISOR, AND ANY PARENTS 1
        Item 2 BUSINESS EXPERIENCE 4  
        Item 3 LITIGATION 7
        Item 5 INITIAL FEES 9
        """
        
        patterns = detector._find_all_item_patterns(toc_text)
        
        # Should find at least 4 items
        assert len(patterns) >= 4
        
        # Check specific items found
        item_numbers = [p[0] for p in patterns]
        assert 1 in item_numbers
        assert 2 in item_numbers  
        assert 3 in item_numbers
        assert 5 in item_numbers
        
    def test_detect_from_title_elements(self, detector, sample_mineru_data):
        """Test detection from title elements"""
        page_data = sample_mineru_data['pdf_info'][1]  # Page with Item 1
        candidates = detector._detect_from_title_elements(page_data, page_idx=8)
        
        # Should find Item 1
        assert len(candidates) >= 1
        item1_candidate = next((c for c in candidates if c.item_no == 1), None)
        assert item1_candidate is not None
        assert item1_candidate.detection_method == 'title'
        assert item1_candidate.confidence >= 0.9
        assert item1_candidate.page_number == 9  # page_idx + 1
        
    def test_fuzzy_matching(self, detector):
        """Test fuzzy matching functionality"""
        # Test exact match
        result = detector._find_best_fuzzy_match("Initial Fees")
        assert result is not None
        assert result[0] == 5  # Item 5
        assert result[1] >= 90  # High score
        
        # Test partial match with typos
        result = detector._find_best_fuzzy_match("Initail Fee")
        assert result is not None
        assert result[0] == 5
        assert result[1] >= detector.min_fuzzy_score
        
        # Test no match
        result = detector._find_best_fuzzy_match("Completely unrelated text")
        assert result is None
        
    @pytest.mark.skipif(
        not Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3/layout.json").exists(),
        reason="Valvoline example file not found"
    )
    def test_full_detection_valvoline_example(self, detector, valvoline_json_path):
        """Test full detection using real Valvoline FDD data"""
        sections = detector.detect_sections_from_mineru_json(str(valvoline_json_path), total_pages=75)
        
        # Should detect all 25 sections (0-24)
        assert len(sections) == 25
        
        # Check section ordering
        for i in range(len(sections) - 1):
            assert sections[i].start_page <= sections[i + 1].start_page
            
        # Check specific expected sections
        item_5 = next((s for s in sections if s.item_no == 5), None)
        assert item_5 is not None
        assert "Initial Fees" in item_5.item_name or "Fee" in item_5.item_name
        
        item_19 = next((s for s in sections if s.item_no == 19), None)
        assert item_19 is not None
        assert "Financial Performance" in item_19.item_name or "Performance" in item_19.item_name
        
        # All sections should have reasonable page numbers
        for section in sections:
            assert 1 <= section.start_page <= 75
            assert section.start_page <= section.end_page
            
    def test_validation_rules(self, detector):
        """Test validation and conflict resolution"""
        # Create conflicting candidates
        candidates = [
            FDDSectionCandidate(
                item_no=5, item_name="Initial Fees", page_idx=9, page_number=10,
                confidence=0.9, text_content="Item 5", bbox=[0,0,0,0],
                detection_method='title', element_type='title'
            ),
            FDDSectionCandidate(
                item_no=5, item_name="Initial Fees", page_idx=11, page_number=12,
                confidence=0.7, text_content="Item 5", bbox=[0,0,0,0], 
                detection_method='fuzzy', element_type='text'
            ),
            FDDSectionCandidate(
                item_no=6, item_name="Other Fees", page_idx=14, page_number=15,
                confidence=0.8, text_content="Item 6", bbox=[0,0,0,0],
                detection_method='pattern', element_type='title'
            ),
        ]
        
        validated = detector._validate_and_resolve_candidates(candidates, total_pages=50)
        
        # Should resolve to best candidates only
        item_numbers = [c.item_no for c in validated]
        assert 5 in item_numbers
        assert 6 in item_numbers
        
        # Should pick higher confidence Item 5 candidate
        item5 = next(c for c in validated if c.item_no == 5)
        assert item5.confidence == 0.9
        assert item5.page_number == 10
        
    def test_fill_missing_sections(self, detector):
        """Test filling missing sections with interpolation"""
        # Provide sparse sections
        detected = [
            FDDSectionCandidate(
                item_no=1, item_name="Franchisor", page_idx=4, page_number=5,
                confidence=0.9, text_content="Item 1", bbox=[0,0,0,0],
                detection_method='title', element_type='title'
            ),
            FDDSectionCandidate(
                item_no=5, item_name="Initial Fees", page_idx=9, page_number=10,
                confidence=0.9, text_content="Item 5", bbox=[0,0,0,0],
                detection_method='title', element_type='title'  
            ),
        ]
        
        filled = detector._fill_missing_sections(detected, total_pages=50)
        
        # Should have all 25 sections
        assert len(filled) == 25
        
        # Check interpolated sections exist
        item_numbers = [s.item_no for s in filled]
        for i in range(25):
            assert i in item_numbers
            
        # Check interpolated pages are reasonable
        for section in filled:
            assert 1 <= section.page_number <= 50
            
    def test_create_section_boundaries(self, detector):
        """Test conversion to SectionBoundary objects"""
        candidates = [
            FDDSectionCandidate(
                item_no=1, item_name="Franchisor", page_idx=4, page_number=5,
                confidence=0.9, text_content="Item 1", bbox=[0,0,0,0],
                detection_method='title', element_type='title'
            ),
            FDDSectionCandidate(
                item_no=2, item_name="Business Experience", page_idx=7, page_number=8,
                confidence=0.8, text_content="Item 2", bbox=[0,0,0,0],
                detection_method='title', element_type='title'
            ),
        ]
        
        boundaries = detector._create_section_boundaries(candidates, total_pages=50)
        
        assert len(boundaries) == 2
        
        # Check first section
        assert boundaries[0].item_no == 1
        assert boundaries[0].start_page == 5
        assert boundaries[0].end_page == 7  # Next section start - 1
        
        # Check last section
        assert boundaries[1].item_no == 2
        assert boundaries[1].start_page == 8
        assert boundaries[1].end_page == 50  # Document end
        
        # All should be SectionBoundary objects
        for boundary in boundaries:
            assert isinstance(boundary, SectionBoundary)
            
    def test_confidence_scoring(self, detector):
        """Test confidence scoring across different detection methods"""
        page_data = {
            "para_blocks": [
                {
                    "type": "title",
                    "lines": [{"spans": [{"content": "Item 5 Initial Fees"}]}]
                },
                {
                    "type": "text", 
                    "lines": [{"spans": [{"content": "Item 6 Other Fees"}]}]
                }
            ]
        }
        
        # Title elements should have higher confidence
        title_candidates = detector._detect_from_title_elements(page_data, 0)
        pattern_candidates = detector._detect_from_patterns(page_data, 0)
        
        if title_candidates and pattern_candidates:
            title_conf = max(c.confidence for c in title_candidates)
            pattern_conf = max(c.confidence for c in pattern_candidates)
            assert title_conf >= pattern_conf
            
    def test_edge_cases(self, detector):
        """Test edge cases and error handling"""
        # Empty data
        result = detector.detect_sections_from_mineru_json("nonexistent.json")
        assert result == []
        
        # Empty candidates
        validated = detector._validate_and_resolve_candidates([], total_pages=50)
        assert len(validated) == 0
        
        # Invalid item numbers
        result = detector._match_item_pattern("Item 99")
        assert result is None
        
        result = detector._match_item_pattern("Item -1")
        assert result is None
        
    def test_performance_with_large_document(self, detector):
        """Test performance characteristics"""
        # Create large synthetic document
        large_data = {
            "pdf_info": []
        }
        
        # 100 pages with various text blocks
        for page_idx in range(100):
            page_data = {
                "page_idx": page_idx,
                "para_blocks": [
                    {
                        "type": "text",
                        "lines": [
                            {
                                "spans": [
                                    {"content": f"Page {page_idx} content with various text"}
                                ]
                            }
                        ]
                    }
                ]
            }
            
            # Add some section headers
            if page_idx % 10 == 0 and page_idx < 25:
                page_data["para_blocks"].append({
                    "type": "title",
                    "lines": [
                        {
                            "spans": [
                                {"content": f"Item {page_idx // 4} Section Header"}
                            ]
                        }
                    ]
                })
                
            large_data["pdf_info"].append(page_data)
            
        # Write to temp file and test
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(large_data, f)
            temp_path = f.name
            
        try:
            import time
            start_time = time.time()
            
            sections = detector.detect_sections_from_mineru_json(temp_path, total_pages=100)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Should complete in reasonable time (< 10 seconds)
            assert processing_time < 10.0
            
            # Should return reasonable results
            assert len(sections) == 25
            
        finally:
            os.unlink(temp_path)


@pytest.mark.integration
class TestIntegrationWithExistingSystem:
    """Integration tests with existing FDD pipeline components"""
    
    def test_section_boundary_compatibility(self):
        """Test compatibility with existing SectionBoundary model"""
        from models.document_models import SectionBoundary
        
        # Create boundary using new detector
        boundary = SectionBoundary(
            item_no=5,
            item_name="Initial Fees",
            start_page=10,
            end_page=15,
            confidence=0.9
        )
        
        # Should have all required fields
        assert boundary.item_no == 5
        assert boundary.item_name == "Initial Fees" 
        assert boundary.start_page == 10
        assert boundary.end_page == 15
        assert boundary.confidence == 0.9
        
    @patch('utils.enhanced_fdd_section_detector.logger')
    def test_logging_integration(self, mock_logger):
        """Test logging works properly"""
        detector = EnhancedFDDSectionDetector()
        
        # Test with invalid file
        detector.detect_sections_from_mineru_json("nonexistent.json")
        
        # Should have logged error
        mock_logger.error.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])