"""Tests for document processing integration with LLM extraction."""

import pytest
import asyncio
from pathlib import Path
from uuid import UUID
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from tasks.document_processing_integration import (
    extract_section_content,
    process_document_with_extraction,
    extract_fdd_sections_batch
)
from tasks.document_processing import SectionBoundary, DocumentLayout, LayoutElement
from models.section import FDDSection, ExtractionStatus


class TestExtractSectionContent:
    """Test suite for extract_section_content function."""
    
    @pytest.fixture
    def sample_section(self):
        """Create sample section boundary."""
        return SectionBoundary(
            item_no=5,
            item_name="Initial Fees",
            start_page=10,
            end_page=12,
            confidence=0.9
        )
    
    @pytest.fixture
    def mock_pdf_reader(self):
        """Create mock PDF reader."""
        with patch('tasks.document_processing_integration.PyPDF2.PdfReader') as mock_reader:
            # Setup mock pages
            mock_page1 = Mock()
            mock_page1.extract_text.return_value = "Page 10 content: Initial franchise fee"
            mock_page2 = Mock()
            mock_page2.extract_text.return_value = "Page 11 content: is $45,000"
            mock_page3 = Mock()
            mock_page3.extract_text.return_value = "Page 12 content: due upon signing"
            
            mock_reader_instance = Mock()
            mock_reader_instance.pages = [
                Mock() for _ in range(9)  # Pages 0-8
            ] + [mock_page1, mock_page2, mock_page3]  # Pages 9-11 (0-indexed)
            
            mock_reader.return_value = mock_reader_instance
            yield mock_reader
    
    @pytest.mark.asyncio
    async def test_extract_section_content_success(self, sample_section, mock_pdf_reader):
        """Test successful section content extraction."""
        pdf_path = Path("/tmp/test.pdf")
        
        # Mock file operations
        with patch('builtins.open', mock_open()):
            # Mock FDDSectionExtractor
            with patch('tasks.document_processing_integration.FDDSectionExtractor') as mock_extractor_class:
                mock_extractor = Mock()
                mock_extractor_class.return_value = mock_extractor
                
                # Setup successful extraction
                mock_extractor.extract_section = AsyncMock(return_value={
                    "status": "success",
                    "data": {"base_fee": 45000},
                    "model_used": "gemini"
                })
                
                # Test extraction
                result = await extract_section_content(
                    pdf_path=pdf_path,
                    section=sample_section,
                    primary_model="gemini"
                )
                
                assert result["status"] == "success"
                assert result["model_used"] == "gemini"
                mock_extractor.extract_section.assert_called_once()
                
                # Check that correct pages were extracted
                call_args = mock_extractor.extract_section.call_args
                content = call_args[1]["content"]
                assert "Initial franchise fee" in content
                assert "$45,000" in content
                assert "due upon signing" in content
    
    @pytest.mark.asyncio
    async def test_extract_section_content_no_text(self, sample_section):
        """Test extraction when no text is found."""
        pdf_path = Path("/tmp/test.pdf")
        
        # Mock PDF reader with empty pages
        with patch('tasks.document_processing_integration.PyPDF2.PdfReader') as mock_reader:
            mock_page = Mock()
            mock_page.extract_text.return_value = "   "  # Only whitespace
            
            mock_reader_instance = Mock()
            mock_reader_instance.pages = [mock_page] * 20
            mock_reader.return_value = mock_reader_instance
            
            with patch('builtins.open', mock_open()):
                result = await extract_section_content(
                    pdf_path=pdf_path,
                    section=sample_section,
                    primary_model="gemini"
                )
                
                assert result["status"] == "failed"
                assert result["error"] == "No text content found"
                assert result["section"]["item_no"] == 5
    
    @pytest.mark.asyncio
    async def test_extract_section_content_extraction_error(self, sample_section, mock_pdf_reader):
        """Test handling of extraction errors."""
        pdf_path = Path("/tmp/test.pdf")
        
        with patch('builtins.open', mock_open()):
            with patch('tasks.document_processing_integration.FDDSectionExtractor') as mock_extractor_class:
                mock_extractor = Mock()
                mock_extractor_class.return_value = mock_extractor
                
                # Setup extraction to fail
                mock_extractor.extract_section = AsyncMock(
                    side_effect=Exception("LLM extraction failed")
                )
                
                result = await extract_section_content(
                    pdf_path=pdf_path,
                    section=sample_section,
                    primary_model="gemini"
                )
                
                assert result["status"] == "failed"
                assert "LLM extraction failed" in result["error"]


class TestProcessDocumentWithExtraction:
    """Test suite for process_document_with_extraction function."""
    
    @pytest.fixture
    def mock_layout(self):
        """Create mock document layout."""
        return DocumentLayout(
            total_pages=100,
            elements=[
                LayoutElement(
                    type="text",
                    bbox=[0, 0, 100, 100],
                    page=0,
                    text="Cover page",
                    confidence=0.9
                )
            ],
            processing_time=5.0,
            model_version="mineru-local"
        )
    
    @pytest.fixture
    def mock_sections(self):
        """Create mock section boundaries."""
        return [
            SectionBoundary(
                item_no=0,
                item_name="Cover",
                start_page=1,
                end_page=5,
                confidence=0.9
            ),
            SectionBoundary(
                item_no=5,
                item_name="Initial Fees",
                start_page=20,
                end_page=22,
                confidence=0.8
            ),
            SectionBoundary(
                item_no=7,
                item_name="Initial Investment",
                start_page=25,
                end_page=30,
                confidence=0.85
            ),
            SectionBoundary(
                item_no=20,
                item_name="Outlets",
                start_page=80,
                end_page=85,
                confidence=0.9
            )
        ]
    
    @pytest.mark.asyncio
    async def test_process_document_with_extraction_success(self, mock_layout, mock_sections):
        """Test successful document processing with extraction."""
        pdf_path = Path("/tmp/test.pdf")
        fdd_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock all the dependencies
        with patch('tasks.document_processing_integration.process_document_layout') as mock_process:
            mock_process.return_value = (mock_layout, mock_sections)
            
            with patch('tasks.document_processing_integration.validate_section_boundaries') as mock_validate:
                mock_validate.return_value = mock_sections
                
                with patch('tasks.document_processing_integration.extract_section_content') as mock_extract:
                    # Setup successful extractions
                    mock_extract.side_effect = [
                        {"status": "success", "data": {"base_fee": 45000}, "model_used": "gemini"},
                        {"status": "success", "data": {"total_low": 100000}, "model_used": "gemini"},
                        {"status": "success", "data": {"outlets": []}, "model_used": "ollama"}
                    ]
                    
                    # Test processing
                    result = await process_document_with_extraction(
                        pdf_path=pdf_path,
                        fdd_id=fdd_id,
                        primary_model="gemini"
                    )
                    
                    assert result["fdd_id"] == str(fdd_id)
                    assert result["layout_analysis"]["total_pages"] == 100
                    assert len(result["sections_detected"]) == 4
                    assert len(result["extraction_results"]) == 3  # Only extractable sections
                    assert result["extraction_summary"]["successful_extractions"] == 3
                    assert result["extraction_summary"]["failed_extractions"] == 0
                    
                    # Verify only extractable sections were processed
                    assert "item_5" in result["extraction_results"]
                    assert "item_7" in result["extraction_results"]
                    assert "item_20" in result["extraction_results"]
                    assert "item_0" not in result["extraction_results"]  # Not extractable
    
    @pytest.mark.asyncio
    async def test_process_document_with_specific_sections(self, mock_layout, mock_sections):
        """Test processing with specific sections only."""
        pdf_path = Path("/tmp/test.pdf")
        fdd_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with patch('tasks.document_processing_integration.process_document_layout') as mock_process:
            mock_process.return_value = (mock_layout, mock_sections)
            
            with patch('tasks.document_processing_integration.validate_section_boundaries') as mock_validate:
                mock_validate.return_value = mock_sections
                
                with patch('tasks.document_processing_integration.extract_section_content') as mock_extract:
                    mock_extract.return_value = {"status": "success", "data": {}, "model_used": "gemini"}
                    
                    # Test with specific sections
                    result = await process_document_with_extraction(
                        pdf_path=pdf_path,
                        fdd_id=fdd_id,
                        extract_sections=[5, 7]  # Only these sections
                    )
                    
                    assert len(result["extraction_results"]) == 2
                    assert "item_5" in result["extraction_results"]
                    assert "item_7" in result["extraction_results"]
                    assert "item_20" not in result["extraction_results"]
    
    @pytest.mark.asyncio
    async def test_process_document_with_failures(self, mock_layout, mock_sections):
        """Test processing with some extraction failures."""
        pdf_path = Path("/tmp/test.pdf")
        fdd_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with patch('tasks.document_processing_integration.process_document_layout') as mock_process:
            mock_process.return_value = (mock_layout, mock_sections)
            
            with patch('tasks.document_processing_integration.validate_section_boundaries') as mock_validate:
                mock_validate.return_value = mock_sections
                
                with patch('tasks.document_processing_integration.extract_section_content') as mock_extract:
                    # Mix of success and failure
                    mock_extract.side_effect = [
                        {"status": "success", "data": {"base_fee": 45000}, "model_used": "gemini"},
                        {"status": "failed", "error": "Extraction failed"},
                        {"status": "success", "data": {"outlets": []}, "model_used": "ollama"}
                    ]
                    
                    result = await process_document_with_extraction(
                        pdf_path=pdf_path,
                        fdd_id=fdd_id
                    )
                    
                    assert result["extraction_summary"]["successful_extractions"] == 2
                    assert result["extraction_summary"]["failed_extractions"] == 1
                    assert result["extraction_results"]["item_7"]["status"] == "failed"


class TestExtractFDDSectionsBatch:
    """Test suite for extract_fdd_sections_batch function."""
    
    @pytest.fixture
    def sample_sections(self):
        """Create sample section boundaries."""
        return [
            SectionBoundary(
                item_no=5,
                item_name="Initial Fees",
                start_page=10,
                end_page=12,
                confidence=0.9
            ),
            SectionBoundary(
                item_no=7,
                item_name="Initial Investment",
                start_page=15,
                end_page=18,
                confidence=0.85
            )
        ]
    
    @pytest.mark.asyncio
    async def test_extract_batch_with_provided_content(self, sample_sections):
        """Test batch extraction with pre-extracted content."""
        pdf_path = Path("/tmp/test.pdf")
        fdd_id = UUID("12345678-1234-5678-1234-567812345678")
        
        content_by_section = {
            5: "Initial franchise fee is $45,000",
            7: "Total investment ranges from $100,000 to $200,000"
        }
        
        with patch('tasks.document_processing_integration.extract_fdd_document') as mock_extract:
            mock_extract.return_value = {
                "fdd_id": str(fdd_id),
                "sections": {
                    "item_5": {"status": "success"},
                    "item_7": {"status": "success"}
                }
            }
            
            result = await extract_fdd_sections_batch(
                fdd_id=fdd_id,
                pdf_path=pdf_path,
                sections=sample_sections,
                content_by_section=content_by_section,
                primary_model="gemini"
            )
            
            assert result["fdd_id"] == str(fdd_id)
            assert len(result["sections"]) == 2
            mock_extract.assert_called_once()
            
            # Verify correct content was passed
            call_args = mock_extract.call_args
            assert call_args[1]["content_by_section"] == content_by_section
    
    @pytest.mark.asyncio
    async def test_extract_batch_extract_content(self, sample_sections):
        """Test batch extraction that extracts content from PDF."""
        pdf_path = Path("/tmp/test.pdf")
        fdd_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock PDF reading
        with patch('tasks.document_processing_integration.PyPDF2.PdfReader') as mock_reader:
            mock_pages = []
            for i in range(20):
                page = Mock()
                page.extract_text.return_value = f"Page {i+1} content"
                mock_pages.append(page)
            
            mock_reader_instance = Mock()
            mock_reader_instance.pages = mock_pages
            mock_reader.return_value = mock_reader_instance
            
            with patch('builtins.open', mock_open()):
                with patch('tasks.document_processing_integration.extract_fdd_document') as mock_extract:
                    mock_extract.return_value = {"sections": {}}
                    
                    result = await extract_fdd_sections_batch(
                        fdd_id=fdd_id,
                        pdf_path=pdf_path,
                        sections=sample_sections,
                        content_by_section=None,  # Force extraction
                        primary_model="gemini"
                    )
                    
                    # Verify content was extracted
                    call_args = mock_extract.call_args
                    content_dict = call_args[1]["content_by_section"]
                    assert 5 in content_dict
                    assert 7 in content_dict
                    assert "Page 10" in content_dict[5]
                    assert "Page 15" in content_dict[7]


def mock_open(read_data=None):
    """Helper to create a mock file object."""
    m = MagicMock()
    m.__enter__ = lambda self: self
    m.__exit__ = lambda self, *args: None
    m.read.return_value = read_data or b"mock pdf content"
    return MagicMock(return_value=m)