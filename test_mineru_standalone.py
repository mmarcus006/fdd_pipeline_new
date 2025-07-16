#!/usr/bin/env python3
"""Standalone test for MinerU integration without Prefect dependencies."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
import os

# Add current directory to path
sys.path.insert(0, ".")


# Mock Prefect before importing our modules
def mock_task(*args, **kwargs):
    def decorator(func):
        return func

    return decorator


# Mock the prefect module
mock_prefect = MagicMock()
mock_prefect.task = mock_task
sys.modules["prefect"] = mock_prefect

# Now import our modules
from tasks.document_processing import (
    MinerUClient,
    FDDSectionDetector,
    DocumentLayout,
    LayoutElement,
    SectionBoundary,
)


def test_layout_element():
    """Test LayoutElement model."""
    print("Testing LayoutElement...")

    element = LayoutElement(
        type="text",
        bbox=[10.0, 20.0, 100.0, 50.0],
        page=0,
        text="Sample text",
        confidence=0.95,
    )

    assert element.type == "text"
    assert element.bbox == [10.0, 20.0, 100.0, 50.0]
    assert element.page == 0
    assert element.text == "Sample text"
    assert element.confidence == 0.95
    print("✓ LayoutElement test passed")


def test_document_layout():
    """Test DocumentLayout model."""
    print("Testing DocumentLayout...")

    elements = [
        LayoutElement(type="text", bbox=[0, 0, 100, 50], page=0),
        LayoutElement(type="table", bbox=[0, 60, 100, 120], page=0),
    ]

    layout = DocumentLayout(
        total_pages=5,
        elements=elements,
        processing_time=12.5,
        model_version="mineru-v1.0",
    )

    assert layout.total_pages == 5
    assert len(layout.elements) == 2
    assert layout.processing_time == 12.5
    assert layout.model_version == "mineru-v1.0"
    print("✓ DocumentLayout test passed")


def test_section_boundary():
    """Test SectionBoundary model."""
    print("Testing SectionBoundary...")

    boundary = SectionBoundary(
        item_no=5, item_name="Initial Fees", start_page=10, end_page=15, confidence=0.9
    )

    assert boundary.item_no == 5
    assert boundary.item_name == "Initial Fees"
    assert boundary.start_page == 10
    assert boundary.end_page == 15
    assert boundary.confidence == 0.9
    print("✓ SectionBoundary test passed")


def test_section_detector():
    """Test FDD section detection."""
    print("Testing FDDSectionDetector...")

    detector = FDDSectionDetector()

    # Test pattern matching
    assert detector._matches_section_pattern("item 5 initial fees", 5, "initial fees")

    # Test case insensitive
    assert detector._matches_section_pattern("ITEM 5. INITIAL FEES", 5, "initial fees")

    # Test pattern without item number (should match for short text)
    assert detector._matches_section_pattern("INITIAL FEES", 5, "initial fees")

    # Test non-matching pattern
    assert not detector._matches_section_pattern(
        "something else entirely", 5, "initial fees"
    )

    # Test section names
    assert detector._get_section_name(0) == "Cover/Introduction"
    assert detector._get_section_name(5) == "Initial Fees"
    assert detector._get_section_name(21) == "Financial Statements"

    print("✓ FDDSectionDetector test passed")


def test_section_detection_with_layout():
    """Test section detection with sample layout."""
    print("Testing section detection with layout...")

    detector = FDDSectionDetector()

    elements = [
        LayoutElement(
            type="text",
            bbox=[50, 700, 500, 720],
            page=0,
            text="ITEM 1. THE FRANCHISOR AND ANY PARENTS, PREDECESSORS, AND AFFILIATES",
        ),
        LayoutElement(
            type="text", bbox=[50, 400, 500, 420], page=1, text="ITEM 5. INITIAL FEES"
        ),
        LayoutElement(
            type="text",
            bbox=[50, 200, 500, 220],
            page=2,
            text="ITEM 21. FINANCIAL STATEMENTS",
        ),
    ]

    layout = DocumentLayout(
        total_pages=3, elements=elements, processing_time=5.0, model_version="test"
    )

    sections = detector.detect_sections(layout)

    assert len(sections) >= 1
    section_items = [s.item_no for s in sections]

    # Should detect at least one of our test sections
    found_sections = [item for item in [1, 5, 21] if item in section_items]
    assert (
        len(found_sections) > 0
    ), f"Expected to find sections 1, 5, or 21, but found: {section_items}"

    print(f"✓ Section detection test passed - found sections: {section_items}")


async def test_mineru_client_fallback():
    """Test MinerU client PyPDF2 fallback."""
    print("Testing MinerU client PyPDF2 fallback...")

    with patch("tasks.document_processing.get_settings") as mock_settings:
        mock_settings.return_value.mineru_model_path = "/tmp/models"
        mock_settings.return_value.mineru_device = "cpu"
        mock_settings.return_value.mineru_batch_size = 1

        client = MinerUClient()

        # Create a simple PDF for testing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Hello World) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000204 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
297
%%EOF"""
            f.write(pdf_content)
            pdf_path = Path(f.name)

        try:
            layout = await client.fallback_to_pypdf2(pdf_path)

            assert layout.total_pages >= 0
            assert layout.model_version == "pypdf2-fallback"
            assert layout.processing_time >= 0

            print("✓ MinerU client fallback test passed")

        finally:
            pdf_path.unlink(missing_ok=True)


async def test_mineru_client_with_mock():
    """Test MinerU client with mocked MinerU."""
    print("Testing MinerU client with mocked MinerU...")

    with patch("tasks.document_processing.get_settings") as mock_settings:
        mock_settings.return_value.mineru_model_path = "/tmp/models"
        mock_settings.return_value.mineru_device = "cpu"
        mock_settings.return_value.mineru_batch_size = 1

        client = MinerUClient()

        # Create a temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\ntest content\n%%EOF")
            pdf_path = Path(f.name)

        try:
            # Test that MinerU processing fails gracefully and raises exception
            # Since MinerU is not installed, it should raise an exception
            try:
                layout = await client.process_document(pdf_path)
                # If we get here, something unexpected happened
                assert False, "Expected MinerU to fail but it succeeded"
            except Exception as e:
                # This is expected - MinerU should fail
                assert "MinerU installation error" in str(e)
                print(
                    "✓ MinerU client correctly failed as expected (MinerU not installed)"
                )

        finally:
            pdf_path.unlink(missing_ok=True)


def test_validation_functions():
    """Test validation functions."""
    print("Testing validation functions...")

    from tasks.document_processing import validate_section_boundaries

    # Test successful validation
    sections = [
        SectionBoundary(
            item_no=1, item_name="Item 1", start_page=1, end_page=3, confidence=0.8
        ),
        SectionBoundary(
            item_no=5, item_name="Item 5", start_page=4, end_page=6, confidence=0.9
        ),
    ]

    validated = validate_section_boundaries(sections, 10)

    assert len(validated) == 2
    assert all(s.start_page >= 1 for s in validated)
    assert all(s.end_page <= 10 for s in validated)
    assert all(s.end_page >= s.start_page for s in validated)

    # Test empty validation
    validated_empty = validate_section_boundaries([], 5)

    assert len(validated_empty) == 1
    assert validated_empty[0].start_page == 1
    assert validated_empty[0].end_page == 5
    assert validated_empty[0].item_name == "Complete Document"

    print("✓ Validation functions test passed")


async def main():
    """Run all tests."""
    print("Running MinerU integration tests...\n")

    try:
        # Test basic models
        test_layout_element()
        test_document_layout()
        test_section_boundary()

        # Test section detection
        test_section_detector()
        test_section_detection_with_layout()

        # Test MinerU client
        await test_mineru_client_fallback()
        await test_mineru_client_with_mock()

        # Test validation
        test_validation_functions()

        print("\n🎉 All tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
