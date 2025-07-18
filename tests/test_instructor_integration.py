"""Tests for the modern Instructor integration module."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from typing import List

from pydantic import BaseModel, Field
from utils.instructor_client import (
    InstructorClient, LLMProvider, ExtractionConfig, 
    ExtractionResult, ExtractionMode
)
from utils.llm_validation import (
    FDDValidators, create_llm_validator, SemanticValidationResponse,
    ValidationResult, validate_with_llm, CrossFieldValidator
)
from utils.multimodal_processor import (
    MultimodalProcessor, FileType, ProcessedFile, FileChunk
)


# Test models
class SimpleModel(BaseModel):
    """Simple test model."""
    name: str
    value: int


class ComplexModel(BaseModel):
    """Complex test model with validation."""
    franchise_name: str = Field(..., min_length=2)
    fee_amount: int = Field(..., ge=0, le=1000000)
    description: str = Field(..., min_length=10)
    
    def validate_extraction(self) -> List[str]:
        """Custom validation method."""
        errors = []
        if self.fee_amount == 0:
            errors.append("Fee amount should not be zero")
        if "franchise" not in self.franchise_name.lower():
            errors.append("Franchise name should contain 'franchise'")
        return errors


class TestInstructorClient:
    """Tests for InstructorClient."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        with patch("utils.instructor_client.settings") as mock:
            mock.gemini_api_key = "test-gemini-key"
            mock.openai_api_key = "test-openai-key"
            mock.ollama_base_url = "http://localhost:11434"
            yield mock
    
    @pytest.fixture
    async def client(self, mock_settings):
        """Create test client."""
        with patch("utils.instructor_client.instructor") as mock_instructor:
            # Mock the provider initialization
            mock_instructor.from_provider.return_value = AsyncMock()
            mock_instructor.Mode.GENAI_STRUCTURED_OUTPUTS = "structured"
            
            client = InstructorClient()
            yield client
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, mock_settings):
        """Test client initialization with different providers."""
        with patch("utils.instructor_client.instructor") as mock_instructor:
            mock_instructor.from_provider.return_value = AsyncMock()
            mock_instructor.Mode.GENAI_STRUCTURED_OUTPUTS = "structured"
            
            # Test Gemini initialization
            client = InstructorClient(primary_provider=LLMProvider.GEMINI)
            assert client.primary_provider == LLMProvider.GEMINI
            mock_instructor.from_provider.assert_called()
    
    @pytest.mark.asyncio
    async def test_extract_from_text(self, client):
        """Test text extraction."""
        # Mock the client response
        mock_response = SimpleModel(name="Test", value=42)
        client.clients[LLMProvider.GEMINI] = AsyncMock()
        client.clients[LLMProvider.GEMINI].messages.create = AsyncMock(
            return_value=mock_response
        )
        
        result = await client.extract_from_text(
            text="Extract test data",
            response_model=SimpleModel,
            system_prompt="Test prompt"
        )
        
        assert isinstance(result, ExtractionResult)
        assert result.data == mock_response
        assert result.provider_used == LLMProvider.GEMINI
        assert result.validation_passed
    
    @pytest.mark.asyncio
    async def test_extract_with_validation_errors(self, client):
        """Test extraction with validation errors."""
        mock_response = ComplexModel(
            franchise_name="Test Company",  # Missing 'franchise'
            fee_amount=0,  # Zero fee
            description="Short desc"
        )
        
        client.clients[LLMProvider.GEMINI] = AsyncMock()
        client.clients[LLMProvider.GEMINI].messages.create = AsyncMock(
            return_value=mock_response
        )
        
        result = await client.extract_from_text(
            text="Extract test data",
            response_model=ComplexModel
        )
        
        assert isinstance(result, ExtractionResult)
        assert not result.validation_passed
        assert len(result.validation_errors) == 2
        assert "Fee amount should not be zero" in result.validation_errors
    
    @pytest.mark.asyncio
    async def test_extract_with_fallback(self, client):
        """Test extraction with provider fallback."""
        # Mock Gemini to fail
        client.clients[LLMProvider.GEMINI] = AsyncMock()
        client.clients[LLMProvider.GEMINI].messages.create = AsyncMock(
            side_effect=Exception("Gemini failed")
        )
        
        # Mock OpenAI to succeed
        mock_response = SimpleModel(name="Fallback", value=99)
        client.clients[LLMProvider.OPENAI] = AsyncMock()
        client.clients[LLMProvider.OPENAI].messages.create = AsyncMock(
            return_value=mock_response
        )
        
        result = await client.extract_with_fallback(
            content="Test content",
            response_model=SimpleModel,
            mode=ExtractionMode.TEXT
        )
        
        assert result.provider_used == LLMProvider.OPENAI
        assert result.data.name == "Fallback"
    
    @pytest.mark.asyncio
    async def test_pdf_extraction_not_implemented(self, client):
        """Test PDF extraction raises NotImplementedError for non-Gemini."""
        # Remove Gemini from clients
        client.clients = {LLMProvider.OPENAI: AsyncMock()}
        
        with pytest.raises(NotImplementedError):
            await client.extract_from_pdf_file(
                pdf_path="test.pdf",
                response_model=SimpleModel
            )


class TestLLMValidation:
    """Tests for LLM validation utilities."""
    
    def test_fdd_validators(self):
        """Test FDD-specific validators."""
        # Test franchise fee validation
        assert FDDValidators.validate_franchise_fee(50000_00) is None
        assert FDDValidators.validate_franchise_fee(-100) is not None
        assert FDDValidators.validate_franchise_fee(0) is not None
        assert FDDValidators.validate_franchise_fee(200_000_000) is not None
        
        # Test fiscal year validation
        assert FDDValidators.validate_fiscal_year(2023) is None
        assert FDDValidators.validate_fiscal_year(1899) is not None
        assert FDDValidators.validate_fiscal_year(2050) is not None
        
        # Test percentage validation
        assert FDDValidators.validate_percentage(50.0) is None
        assert FDDValidators.validate_percentage(-1.0) is not None
        assert FDDValidators.validate_percentage(101.0) is not None
        
        # Test state code validation
        assert FDDValidators.validate_state_code("CA") is None
        assert FDDValidators.validate_state_code("XX") is not None
    
    def test_cross_field_validator(self):
        """Test cross-field validation."""
        # Test outlet math
        assert CrossFieldValidator.validate_outlet_math(
            count_start=100,
            opened=20,
            closed=5,
            transferred_in=2,
            transferred_out=1,
            count_end=116
        ) is None
        
        assert CrossFieldValidator.validate_outlet_math(
            count_start=100,
            opened=20,
            closed=5,
            transferred_in=0,
            transferred_out=0,
            count_end=120  # Wrong!
        ) is not None
        
        # Test fee relationships
        fees = [
            {"fee_name": "Initial Franchise Fee", "amount_cents": 50000_00},
            {"fee_name": "Training Fee", "amount_cents": 5000_00},
            {"fee_name": "Excessive Fee", "amount_cents": 150000_00}  # 3x franchise fee
        ]
        
        issues = CrossFieldValidator.validate_fee_relationships(fees)
        assert len(issues) == 1
        assert "more than double" in issues[0]
    
    @pytest.mark.asyncio
    async def test_semantic_validation(self):
        """Test semantic validation with mocked LLM."""
        with patch("utils.llm_validation.InstructorClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.extract_from_text = AsyncMock(
                return_value=Mock(
                    data=SemanticValidationResponse(
                        is_valid=False,
                        confidence=0.9,
                        issues=["Description too vague"],
                        suggestions=["Add more detail"],
                        reasoning="The description lacks specificity"
                    )
                )
            )
            
            result = await validate_with_llm(
                content="A business",
                validation_criteria="Must be detailed",
                client=mock_client
            )
            
            assert not result.is_valid
            assert result.confidence == 0.9
            assert len(result.issues) == 1


class TestMultimodalProcessor:
    """Tests for MultimodalProcessor."""
    
    @pytest.fixture
    async def processor(self, tmp_path):
        """Create test processor."""
        processor = MultimodalProcessor(temp_dir=tmp_path)
        yield processor
        await processor.cleanup_temp_files()
    
    def test_file_type_detection(self, processor, tmp_path):
        """Test file type detection."""
        # Create test files
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test content")
        
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Plain text content")
        
        # Test detection
        file_type, mime_type = processor._detect_file_type(pdf_file)
        assert file_type == FileType.PDF
        assert mime_type == "application/pdf"
        
        file_type, mime_type = processor._detect_file_type(txt_file)
        assert file_type == FileType.TEXT
        assert mime_type == "text/plain"
    
    @pytest.mark.asyncio
    async def test_process_text_file(self, processor, tmp_path):
        """Test processing text file."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_content = "This is a test document with franchise information."
        test_file.write_text(test_content)
        
        # Process file
        result = await processor.process_file(test_file)
        
        assert isinstance(result, ProcessedFile)
        assert result.file_type == FileType.TEXT
        assert result.extracted_text == test_content
        assert result.size_bytes == len(test_content)
    
    @pytest.mark.asyncio
    async def test_prepare_content_for_llm(self, processor):
        """Test preparing content for LLM."""
        # Create processed file
        processed = ProcessedFile(
            original_path=Path("test.pdf"),
            file_type=FileType.PDF,
            extracted_text="Test content",
            chunks=[
                FileChunk(
                    chunk_index=0,
                    total_chunks=2,
                    content="Chunk 1 content",
                    page_range=(1, 10)
                ),
                FileChunk(
                    chunk_index=1,
                    total_chunks=2,
                    content="Chunk 2 content",
                    page_range=(11, 20)
                )
            ]
        )
        
        # Test full content
        content = processor.prepare_content_for_llm(processed)
        assert len(content) == 2
        assert "test.pdf" in content[0]
        assert content[1] == "Test content"
        
        # Test specific chunk
        content = processor.prepare_content_for_llm(processed, chunk_index=0)
        assert "Chunk 1 of 2" in content[1]
        assert "pages 1-10" in content[1]
        assert content[2] == "Chunk 1 content"


# Integration test
@pytest.mark.asyncio
async def test_end_to_end_extraction():
    """Test end-to-end extraction flow."""
    with patch("utils.instructor_client.instructor") as mock_instructor:
        # Setup mocks
        mock_instructor.from_provider.return_value = AsyncMock()
        mock_instructor.Mode.GENAI_STRUCTURED_OUTPUTS = "structured"
        
        # Create client
        client = InstructorClient()
        
        # Mock successful extraction
        mock_response = ComplexModel(
            franchise_name="Test Franchise Co",
            fee_amount=50000,
            description="A comprehensive franchise opportunity in food service"
        )
        
        client.clients[LLMProvider.GEMINI] = AsyncMock()
        client.clients[LLMProvider.GEMINI].messages.create = AsyncMock(
            return_value=mock_response
        )
        
        # Extract
        result = await client.extract_from_text(
            text="Sample FDD text describing fees and franchise details",
            response_model=ComplexModel,
            config=ExtractionConfig(temperature=0.1, max_retries=2)
        )
        
        # Verify
        assert result.validation_passed
        assert result.data.franchise_name == "Test Franchise Co"
        assert result.data.fee_amount == 50000
        assert len(result.validation_errors) == 0