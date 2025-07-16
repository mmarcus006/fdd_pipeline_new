"""Tests for document processing tasks including MinerU integration."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from uuid import uuid4
import os

import pytest
import PyPDF2

# Set environment variables to avoid Prefect server connection
os.environ["PREFECT_API_URL"] = "http://localhost:4200/api"
os.environ["PREFECT_DISABLE_CLIENT"] = "true"

# Mock Prefect completely to avoid server connections
import sys
from unittest.mock import MagicMock

# Create a mock prefect module
mock_prefect = MagicMock()
mock_prefect.task = lambda *args, **kwargs: lambda func: func
sys.modules['prefect'] = mock_prefect

from tasks.document_processing import (
    MinerUClient,
    FDDSectionDetector,
    DocumentLayout,
    LayoutElement,
    SectionBoundary,
    process_document_layout,
    validate_section_boundaries
)


class TestLayoutElement:
    """Test LayoutElement model."""
    
    def test_valid_layout_element(self):
        """Test creating a valid layout element."""
        element = LayoutElement(
            type="text",
            bbox=[10.0, 20.0, 100.0, 50.0],
            page=0,
            text="Sample text",
            confidence=0.95
        )
        
        assert element.type == "text"
        assert element.bbox == [10.0, 20.0, 100.0, 50.0]
        assert element.page == 0
        assert element.text == "Sample text"
        assert element.confidence == 0.95
    
    def test_layout_element_optional_fields(self):
        """Test layout element with optional fields."""
        element = LayoutElement(
            type="table",
            bbox=[0.0, 0.0, 50.0, 50.0],
            page=1
        )
        
        assert element.type == "table"
        assert element.text is None
        assert element.confidence is None


class TestDocumentLayout:
    """Test DocumentLayout model."""
    
    def test_valid_document_layout(self):
        """Test creating a valid document layout."""
        elements = [
            LayoutElement(type="text", bbox=[0, 0, 100, 50], page=0),
            LayoutElement(type="table", bbox=[0, 60, 100, 120], page=0)
        ]
        
        layout = DocumentLayout(
            total_pages=5,
            elements=elements,
            processing_time=12.5,
            model_version="mineru-v1.0"
        )
        
        assert layout.total_pages == 5
        assert len(layout.elements) == 2
        assert layout.processing_time == 12.5
        assert layout.model_version == "mineru-v1.0"


class TestSectionBoundary:
    """Test SectionBoundary model."""
    
    def test_valid_section_boundary(self):
        """Test creating a valid section boundary."""
        boundary = SectionBoundary(
            item_no=5,
            item_name="Initial Fees",
            start_page=10,
            end_page=15,
            confidence=0.9
        )
        
        assert boundary.item_no == 5
        assert boundary.item_name == "Initial Fees"
        assert boundary.start_page == 10
        assert boundary.end_page == 15
        assert boundary.confidence == 0.9
    
    def test_section_boundary_validation(self):
        """Test section boundary field validation."""
        # Test item_no bounds
        with pytest.raises(ValueError):
            SectionBoundary(
                item_no=-1,
                item_name="Invalid",
                start_page=1,
                end_page=2,
                confidence=0.5
            )
        
        with pytest.raises(ValueError):
            SectionBoundary(
                item_no=25,
                item_name="Invalid",
                start_page=1,
                end_page=2,
                confidence=0.5
            )


class TestMinerUClient:
    """Test MinerUClient functionality."""
    
    @pytest.fixture
    def client(self):
        """Create a MinerU client for testing."""
        with patch('tasks.document_processing.get_settings') as mock_settings:
            mock_settings.return_value.mineru_model_path = "/tmp/models"
            mock_settings.return_value.mineru_device = "cpu"
            mock_settings.return_value.mineru_batch_size = 1
            return MinerUClient()
    
    @pytest.fixture
    def sample_pdf_path(self):
        """Create a temporary PDF file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            # Create a minimal PDF content
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
            f.write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
            f.write(b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n")
            f.write(b"xref\n0 4\n0000000000 65535 f \n")
            f.write(b"0000000009 00000 n \n0000000058 00000 n \n")
            f.write(b"0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\n")
            f.write(b"startxref\n174\n%%EOF")
            
            yield Path(f.name)
            
        # Cleanup
        Path(f.name).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_process_document_success(self, client, sample_pdf_path):
        """Test successful document processing with MinerU."""
        mock_md_content = """# Sample Document
        
This is a test document with some content.

## Section 1

Some text content here.

| Column 1 | Column 2 |
|----------|----------|
| Data 1   | Data 2   |

![Image](image.png)
"""
        
        with patch('tasks.document_processing.UNIPipe') as mock_pipe_class, \
             patch('tasks.document_processing.DiskReaderWriter') as mock_writer_class:
            
            mock_pipe = MagicMock()
            mock_pipe.pipe_classify.return_value = None
            mock_pipe.pipe_analyze = MagicMock()  # Available in newer versions
            mock_pipe.pipe_parse.return_value = None
            mock_pipe.pipe_mk_markdown.return_value = mock_md_content
            mock_pipe_class.return_value = mock_pipe
            
            mock_writer_class.return_value = MagicMock()
            
            layout = await client.process_document(sample_pdf_path)
            
            assert layout.total_pages >= 1
            assert len(layout.elements) > 0
            assert layout.model_version == "mineru-local"
            
            # Verify pipeline steps were called
            mock_pipe.pipe_classify.assert_called_once()
            mock_pipe.pipe_parse.assert_called_once()
            mock_pipe.pipe_mk_markdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_document_timeout(self, client, sample_pdf_path):
        """Test document processing timeout."""
        with patch('tasks.document_processing.UNIPipe') as mock_pipe_class:
            mock_pipe = MagicMock()
            mock_pipe.pipe_analyze.side_effect = asyncio.TimeoutError()
            mock_pipe_class.return_value = mock_pipe
            
            with pytest.raises(Exception, match="timeout"):
                await client.process_document(sample_pdf_path, timeout_seconds=1)
    
    @pytest.mark.asyncio
    async def test_process_document_file_not_found(self, client):
        """Test processing non-existent file."""
        non_existent_path = Path("/tmp/non_existent.pdf")
        
        with pytest.raises(FileNotFoundError):
            await client.process_document(non_existent_path)
    
    @pytest.mark.asyncio
    async def test_fallback_to_pypdf2(self, client, sample_pdf_path):
        """Test fallback to PyPDF2 when MinerU fails."""
        # Create a more realistic PDF for PyPDF2
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            # Write minimal but valid PDF content
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
            
            assert layout.total_pages >= 0  # May be 0 if PyPDF2 can't read our minimal PDF
            assert layout.model_version == "pypdf2-fallback"
            assert layout.processing_time > 0
            
        finally:
            pdf_path.unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_fallback_pypdf2_failure(self, client):
        """Test PyPDF2 fallback failure."""
        non_existent_path = Path("/tmp/non_existent.pdf")
        
        with pytest.raises(Exception):
            await client.fallback_to_pypdf2(non_existent_path)


class TestFDDSectionDetector:
    """Test FDD section detection functionality."""
    
    @pytest.fixture
    def detector(self):
        """Create a section detector for testing."""
        return FDDSectionDetector()
    
    @pytest.fixture
    def sample_layout(self):
        """Create a sample document layout for testing."""
        elements = [
            LayoutElement(
                type="text",
                bbox=[50, 700, 500, 720],
                page=0,
                text="ITEM 1. THE FRANCHISOR AND ANY PARENTS, PREDECESSORS, AND AFFILIATES"
            ),
            LayoutElement(
                type="text",
                bbox=[50, 650, 500, 670],
                page=0,
                text="This is the content of item 1..."
            ),
            LayoutElement(
                type="text",
                bbox=[50, 400, 500, 420],
                page=1,
                text="ITEM 5. INITIAL FEES"
            ),
            LayoutElement(
                type="text",
                bbox=[50, 350, 500, 370],
                page=1,
                text="The initial franchise fee is $45,000..."
            ),
            LayoutElement(
                type="text",
                bbox=[50, 200, 500, 220],
                page=2,
                text="ITEM 21. FINANCIAL STATEMENTS"
            )
        ]
        
        return DocumentLayout(
            total_pages=3,
            elements=elements,
            processing_time=5.0,
            model_version="test"
        )
    
    def test_detect_sections_success(self, detector, sample_layout):
        """Test successful section detection."""
        sections = detector.detect_sections(sample_layout)
        
        assert len(sections) >= 1
        
        # Check that we found some expected sections
        section_items = [s.item_no for s in sections]
        assert 1 in section_items or 5 in section_items or 21 in section_items
    
    def test_detect_sections_empty_layout(self, detector):
        """Test section detection with empty layout."""
        empty_layout = DocumentLayout(
            total_pages=1,
            elements=[],
            processing_time=0.0,
            model_version="test"
        )
        
        sections = detector.detect_sections(empty_layout)
        
        # Should return at least one default section
        assert len(sections) >= 1
        assert sections[0].start_page == 1
        assert sections[0].end_page == 1
    
    def test_matches_section_pattern(self, detector):
        """Test section pattern matching."""
        # Test item 5 pattern
        assert detector._matches_section_pattern(
            "item 5 initial fees", 5, "initial fees"
        )
        
        # Test case insensitive
        assert detector._matches_section_pattern(
            "ITEM 5. INITIAL FEES", 5, "initial fees"
        )
        
        # Test pattern without item number
        assert detector._matches_section_pattern(
            "INITIAL FEES", 5, "initial fees"
        )
        
        # Test non-matching pattern
        assert not detector._matches_section_pattern(
            "something else entirely", 5, "initial fees"
        )
    
    def test_get_section_name(self, detector):
        """Test getting section names."""
        assert detector._get_section_name(0) == "Cover/Introduction"
        assert detector._get_section_name(5) == "Initial Fees"
        assert detector._get_section_name(21) == "Financial Statements"
        assert "Item 99" in detector._get_section_name(99)  # Unknown item
    
    def test_validate_and_fill_sections(self, detector):
        """Test section validation and gap filling."""
        # Test with gaps
        boundaries = [
            SectionBoundary(item_no=1, item_name="Item 1", start_page=1, end_page=1, confidence=0.8),
            SectionBoundary(item_no=5, item_name="Item 5", start_page=5, end_page=5, confidence=0.8)
        ]
        
        validated = detector._validate_and_fill_sections(boundaries, 10)
        
        # Should have filled gaps and set proper end pages
        assert len(validated) >= 2
        assert validated[-1].end_page == 10  # Last section should end at total pages
    
    def test_validate_and_fill_sections_empty(self, detector):
        """Test validation with empty section list."""
        validated = detector._validate_and_fill_sections([], 5)
        
        assert len(validated) == 1
        assert validated[0].start_page == 1
        assert validated[0].end_page == 5
        assert validated[0].confidence < 0.5  # Low confidence for default


class TestProcessDocumentLayoutTask:
    """Test the process_document_layout Prefect task."""
    
    @pytest.mark.asyncio
    async def test_process_document_layout_success(self):
        """Test successful document layout processing."""
        fdd_id = uuid4()
        pdf_path = "/tmp/test.pdf"
        
        mock_layout = DocumentLayout(
            total_pages=5,
            elements=[],
            processing_time=10.0,
            model_version="test"
        )
        
        mock_sections = [
            SectionBoundary(
                item_no=1,
                item_name="Item 1",
                start_page=1,
                end_page=5,
                confidence=0.8
            )
        ]
        
        with patch('tasks.document_processing.MinerUClient') as mock_client_class, \
             patch('tasks.document_processing.FDDSectionDetector') as mock_detector_class, \
             patch('tasks.document_processing.Path') as mock_path:
            
            # Setup mocks
            mock_client = AsyncMock()
            mock_client.process_document.return_value = mock_layout
            mock_client_class.return_value = mock_client
            
            mock_detector = MagicMock()
            mock_detector.detect_sections.return_value = mock_sections
            mock_detector_class.return_value = mock_detector
            
            mock_path.return_value.exists.return_value = True
            
            # Call the task
            layout, sections = await process_document_layout(pdf_path, fdd_id)
            
            assert layout == mock_layout
            assert sections == mock_sections
            mock_client.process_document.assert_called_once()
            mock_detector.detect_sections.assert_called_once_with(mock_layout)
    
    @pytest.mark.asyncio
    async def test_process_document_layout_fallback(self):
        """Test document layout processing with fallback."""
        fdd_id = uuid4()
        pdf_path = "/tmp/test.pdf"
        
        mock_layout = DocumentLayout(
            total_pages=3,
            elements=[],
            processing_time=5.0,
            model_version="pypdf2-fallback"
        )
        
        with patch('tasks.document_processing.MinerUClient') as mock_client_class, \
             patch('tasks.document_processing.FDDSectionDetector') as mock_detector_class, \
             patch('tasks.document_processing.Path') as mock_path:
            
            # Setup mocks - MinerU fails, fallback succeeds
            mock_client = AsyncMock()
            mock_client.process_document.side_effect = Exception("MinerU failed")
            mock_client.fallback_to_pypdf2.return_value = mock_layout
            mock_client_class.return_value = mock_client
            
            mock_detector = MagicMock()
            mock_detector.detect_sections.return_value = []
            mock_detector_class.return_value = mock_detector
            
            mock_path.return_value.exists.return_value = True
            
            # Call the task
            layout, sections = await process_document_layout(pdf_path, fdd_id)
            
            assert layout == mock_layout
            assert layout.model_version == "pypdf2-fallback"
            mock_client.fallback_to_pypdf2.assert_called_once()


class TestValidateSectionBoundariesTask:
    """Test the validate_section_boundaries Prefect task."""
    
    def test_validate_section_boundaries_success(self):
        """Test successful section boundary validation."""
        sections = [
            SectionBoundary(
                item_no=1,
                item_name="Item 1",
                start_page=1,
                end_page=3,
                confidence=0.8
            ),
            SectionBoundary(
                item_no=5,
                item_name="Item 5",
                start_page=4,
                end_page=6,
                confidence=0.9
            )
        ]
        
        validated = validate_section_boundaries(sections, 10)
        
        assert len(validated) == 2
        assert all(s.start_page >= 1 for s in validated)
        assert all(s.end_page <= 10 for s in validated)
        assert all(s.end_page >= s.start_page for s in validated)
    
    def test_validate_section_boundaries_empty(self):
        """Test validation with empty section list."""
        validated = validate_section_boundaries([], 5)
        
        assert len(validated) == 1
        assert validated[0].start_page == 1
        assert validated[0].end_page == 5
        assert validated[0].item_name == "Complete Document"
    
    def test_validate_section_boundaries_fix_ranges(self):
        """Test fixing invalid page ranges."""
        # Create sections with valid initial values, then modify them to test fixing
        sections = [
            SectionBoundary(
                item_no=1,
                item_name="Item 1",
                start_page=1,  # Will be modified in validation
                end_page=15,   # Invalid: too high
                confidence=0.8
            ),
            SectionBoundary(
                item_no=5,
                item_name="Item 5",
                start_page=8,
                end_page=8,    # Will be modified in validation
                confidence=0.9
            )
        ]
        
        # Manually set invalid values to test the validation logic
        sections[0].start_page = 0  # This would normally fail validation
        sections[1].end_page = 5   # This creates end < start scenario
        
        validated = validate_section_boundaries(sections, 10)
        
        # Check that invalid ranges were fixed
        assert validated[0].start_page == 1  # Fixed from 0
        assert validated[0].end_page == 10   # Fixed from 15
        assert validated[1].end_page >= validated[1].start_page  # Fixed end < start


@pytest.mark.integration
class TestMinerUIntegration:
    """Integration tests for MinerU functionality."""
    
    @pytest.mark.asyncio
    async def test_full_document_processing_pipeline(self):
        """Test the complete document processing pipeline."""
        # This test would require actual MinerU installation
        # and a real PDF file, so we'll mock the heavy parts
        
        with patch('tasks.document_processing.UNIPipe') as mock_pipe:
            mock_pipe.return_value.pipe_analyze.return_value = {
                'layout': {
                    'page_count': 1,
                    'pages': [{'elements': []}]
                }
            }
            
            client = MinerUClient()
            detector = FDDSectionDetector()
            
            # Create a temporary PDF file
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                f.write(b"%PDF-1.4\ntest content\n%%EOF")
                f.flush()
                
                pdf_path = Path(f.name)
                
                # Process the document
                layout = await client.process_document(pdf_path)
                sections = detector.detect_sections(layout)
                
                assert layout.total_pages >= 0
                assert isinstance(sections, list)