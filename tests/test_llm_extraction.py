"""Tests for LLM extraction module using Instructor."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from uuid import UUID

from tasks.llm_extraction import (
    LLMExtractor,
    FDDSectionExtractor,
    ExtractionError,
    extract_fdd_document
)
from models.section import FDDSection, ExtractionStatus
from models.fdd import FDD, DocumentType
from models.item5_fees import Item5FeesResponse
from models.item7_investment import Item7InvestmentResponse


class TestLLMExtractor:
    """Test suite for LLMExtractor class."""
    
    @pytest.fixture
    def extractor(self):
        """Create LLMExtractor instance with mocked clients."""
        with patch('tasks.llm_extraction.genai'):
            with patch('tasks.llm_extraction.instructor'):
                extractor = LLMExtractor()
                # Mock the clients
                extractor.gemini_client = AsyncMock()
                extractor.openai_client = AsyncMock()
                extractor.ollama_client = AsyncMock()
                extractor.ollama_available = True
                return extractor
    
    @pytest.mark.asyncio
    async def test_extract_with_gemini_success(self, extractor):
        """Test successful extraction with Gemini."""
        # Setup mock response
        mock_response = Item5FeesResponse(
            base_fee=45000,
            currency="USD",
            payment_due="upon signing"
        )
        extractor.gemini_client.create.return_value = mock_response
        
        # Test extraction
        result = await extractor.extract_with_gemini(
            content="Initial franchise fee is $45,000",
            response_model=Item5FeesResponse,
            system_prompt="Extract fees"
        )
        
        assert result.base_fee == 45000
        assert result.currency == "USD"
        extractor.gemini_client.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_with_gemini_failure(self, extractor):
        """Test extraction failure with Gemini."""
        # Setup mock to raise exception
        extractor.gemini_client.create.side_effect = Exception("API error")
        
        # Test extraction
        with pytest.raises(ExtractionError, match="Gemini extraction failed"):
            await extractor.extract_with_gemini(
                content="Test content",
                response_model=Item5FeesResponse,
                system_prompt="Extract fees"
            )
    
    @pytest.mark.asyncio
    async def test_extract_with_fallback_gemini_primary(self, extractor):
        """Test fallback logic with Gemini as primary."""
        # Setup mock response
        mock_response = Item5FeesResponse(
            base_fee=50000,
            currency="USD",
            payment_due="immediately"
        )
        extractor.gemini_client.create.return_value = mock_response
        
        # Test extraction
        result, model_used = await extractor.extract_with_fallback(
            content="Franchise fee: $50,000",
            response_model=Item5FeesResponse,
            system_prompt="Extract fees",
            primary_model="gemini"
        )
        
        assert result.base_fee == 50000
        assert model_used == "gemini"
        extractor.gemini_client.create.assert_called_once()
        # Other clients should not be called
        extractor.ollama_client.create.assert_not_called()
        extractor.openai_client.create.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_extract_with_fallback_to_ollama(self, extractor):
        """Test fallback from Gemini to Ollama."""
        # Setup Gemini to fail
        extractor.gemini_client.create.side_effect = Exception("Gemini failed")
        
        # Setup Ollama to succeed
        mock_response = Item5FeesResponse(
            base_fee=45000,
            currency="USD",
            payment_due="upon signing"
        )
        extractor.ollama_client.create.return_value = mock_response
        
        # Test extraction
        result, model_used = await extractor.extract_with_fallback(
            content="Franchise fee: $45,000",
            response_model=Item5FeesResponse,
            system_prompt="Extract fees",
            primary_model="gemini"
        )
        
        assert result.base_fee == 45000
        assert model_used == "ollama"
        extractor.gemini_client.create.assert_called_once()
        extractor.ollama_client.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_with_fallback_all_fail(self, extractor):
        """Test when all models fail."""
        # Setup all to fail
        extractor.gemini_client.create.side_effect = Exception("Gemini failed")
        extractor.ollama_client.create.side_effect = Exception("Ollama failed")
        extractor.openai_client.create.side_effect = Exception("OpenAI failed")
        
        # Test extraction
        with pytest.raises(ExtractionError, match="All models failed"):
            await extractor.extract_with_fallback(
                content="Test content",
                response_model=Item5FeesResponse,
                system_prompt="Extract fees",
                primary_model="gemini"
            )


class TestFDDSectionExtractor:
    """Test suite for FDDSectionExtractor class."""
    
    @pytest.fixture
    def section_extractor(self):
        """Create FDDSectionExtractor with mocked LLMExtractor."""
        mock_llm_extractor = Mock(spec=LLMExtractor)
        mock_llm_extractor.extract_with_fallback = AsyncMock()
        
        with patch('tasks.llm_extraction.get_prompt_loader'):
            extractor = FDDSectionExtractor(extractor=mock_llm_extractor)
            return extractor
    
    @pytest.fixture
    def sample_section(self):
        """Create sample FDD section."""
        return FDDSection(
            id=UUID("12345678-1234-5678-1234-567812345678"),
            fdd_id=UUID("87654321-4321-8765-4321-876543218765"),
            item_no=5,
            item_name="Initial Fees",
            start_page=10,
            end_page=12,
            extraction_status=ExtractionStatus.PENDING,
            created_at=datetime.utcnow()
        )
    
    @pytest.mark.asyncio
    async def test_extract_section_success(self, section_extractor, sample_section):
        """Test successful section extraction."""
        # Setup mock response
        mock_extracted_data = Item5FeesResponse(
            base_fee=45000,
            currency="USD",
            payment_due="upon signing"
        )
        section_extractor.extractor.extract_with_fallback.return_value = (
            mock_extracted_data, "gemini"
        )
        
        # Test extraction
        result = await section_extractor.extract_section(
            section=sample_section,
            content="Initial franchise fee is $45,000",
            primary_model="gemini"
        )
        
        assert result["status"] == "success"
        assert result["model_used"] == "gemini"
        assert result["data"]["base_fee"] == 45000
        assert "extracted_at" in result
    
    @pytest.mark.asyncio
    async def test_extract_section_no_model_defined(self, section_extractor):
        """Test extraction for section without defined model."""
        # Create section for item without model
        section = FDDSection(
            id=UUID("12345678-1234-5678-1234-567812345678"),
            fdd_id=UUID("87654321-4321-8765-4321-876543218765"),
            item_no=2,  # No model defined for item 2
            item_name="Business Experience",
            start_page=5,
            end_page=7,
            extraction_status=ExtractionStatus.PENDING,
            created_at=datetime.utcnow()
        )
        
        # Test extraction
        result = await section_extractor.extract_section(
            section=section,
            content="Business experience content",
            primary_model="gemini"
        )
        
        assert result["status"] == "skipped"
        assert result["reason"] == "No extraction model defined"
    
    @pytest.mark.asyncio
    async def test_extract_section_extraction_error(self, section_extractor, sample_section):
        """Test extraction error handling."""
        # Setup mock to raise error
        section_extractor.extractor.extract_with_fallback.side_effect = ExtractionError(
            "Extraction failed"
        )
        
        # Test extraction
        result = await section_extractor.extract_section(
            section=sample_section,
            content="Test content",
            primary_model="gemini"
        )
        
        assert result["status"] == "failed"
        assert "Extraction failed" in result["error"]
        assert "attempted_at" in result


class TestExtractFDDDocument:
    """Test suite for extract_fdd_document function."""
    
    @pytest.fixture
    def sample_fdd(self):
        """Create sample FDD document."""
        return FDD(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            franchise_id=UUID("22222222-2222-2222-2222-222222222222"),
            issue_date=datetime(2024, 1, 1).date(),
            document_type=DocumentType.INITIAL,
            filing_state="WI",
            drive_path="/fdds/2024/franchise.pdf",
            drive_file_id="drive123",
            is_amendment=False,
            created_at=datetime.utcnow()
        )
    
    @pytest.fixture
    def sample_sections(self):
        """Create sample sections list."""
        return [
            FDDSection(
                id=UUID("33333333-3333-3333-3333-333333333333"),
                fdd_id=UUID("11111111-1111-1111-1111-111111111111"),
                item_no=5,
                item_name="Initial Fees",
                start_page=10,
                end_page=12,
                extraction_status=ExtractionStatus.PENDING,
                created_at=datetime.utcnow()
            ),
            FDDSection(
                id=UUID("44444444-4444-4444-4444-444444444444"),
                fdd_id=UUID("11111111-1111-1111-1111-111111111111"),
                item_no=7,
                item_name="Initial Investment",
                start_page=15,
                end_page=18,
                extraction_status=ExtractionStatus.PENDING,
                created_at=datetime.utcnow()
            )
        ]
    
    @pytest.mark.asyncio
    async def test_extract_fdd_document_success(self, sample_fdd, sample_sections):
        """Test successful FDD document extraction."""
        # Mock content
        content_by_section = {
            5: "Initial franchise fee is $45,000",
            7: "Total investment ranges from $100,000 to $200,000"
        }
        
        # Mock the FDDSectionExtractor
        with patch('tasks.llm_extraction.FDDSectionExtractor') as mock_extractor_class:
            mock_extractor = Mock()
            mock_extractor_class.return_value = mock_extractor
            
            # Setup mock responses
            mock_extractor.extract_section = AsyncMock(side_effect=[
                {
                    "status": "success",
                    "data": {"base_fee": 45000},
                    "model_used": "gemini"
                },
                {
                    "status": "success",
                    "data": {"total_low": 100000, "total_high": 200000},
                    "model_used": "gemini"
                }
            ])
            
            # Test extraction
            result = await extract_fdd_document(
                fdd=sample_fdd,
                sections=sample_sections,
                content_by_section=content_by_section,
                primary_model="gemini"
            )
            
            assert result["fdd_id"] == str(sample_fdd.id)
            assert "extraction_timestamp" in result
            assert result["primary_model"] == "gemini"
            assert len(result["sections"]) == 2
            assert result["sections"]["item_5"]["status"] == "success"
            assert result["sections"]["item_7"]["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_extract_fdd_document_partial_failure(self, sample_fdd, sample_sections):
        """Test FDD extraction with partial failures."""
        content_by_section = {
            5: "Initial franchise fee is $45,000",
            7: ""  # Empty content to trigger failure
        }
        
        with patch('tasks.llm_extraction.FDDSectionExtractor') as mock_extractor_class:
            mock_extractor = Mock()
            mock_extractor_class.return_value = mock_extractor
            
            # Setup mock responses with one failure
            mock_extractor.extract_section = AsyncMock(side_effect=[
                {
                    "status": "success",
                    "data": {"base_fee": 45000},
                    "model_used": "gemini"
                },
                Exception("Extraction failed for item 7")
            ])
            
            # Test extraction
            result = await extract_fdd_document(
                fdd=sample_fdd,
                sections=sample_sections,
                content_by_section=content_by_section,
                primary_model="gemini"
            )
            
            assert result["sections"]["item_5"]["status"] == "success"
            assert "item_7" in result["sections"]
            assert "error" in result["sections"]["item_7"]


class TestPromptLoading:
    """Test prompt loading functionality."""
    
    @pytest.mark.asyncio
    async def test_section_prompt_loading(self):
        """Test that section prompts are loaded correctly."""
        with patch('tasks.llm_extraction.get_prompt_loader') as mock_loader:
            # Setup mock prompt loader
            mock_prompt_loader = Mock()
            mock_loader.return_value = mock_prompt_loader
            mock_prompt_loader.get_prompt_for_item.return_value = "item5_fees"
            mock_prompt_loader.render_system_prompt.return_value = "Extract fees prompt"
            
            # Create extractor
            extractor = FDDSectionExtractor()
            
            # Test prompt loading
            prompt = extractor._get_section_prompt(5)
            
            assert prompt == "Extract fees prompt"
            mock_prompt_loader.get_prompt_for_item.assert_called_with(5)
            mock_prompt_loader.render_system_prompt.assert_called_with("item5_fees")
    
    @pytest.mark.asyncio
    async def test_section_prompt_fallback(self):
        """Test fallback when prompt loading fails."""
        with patch('tasks.llm_extraction.get_prompt_loader') as mock_loader:
            # Setup mock to raise exception
            mock_prompt_loader = Mock()
            mock_loader.return_value = mock_prompt_loader
            mock_prompt_loader.get_prompt_for_item.return_value = "item5_fees"
            mock_prompt_loader.render_system_prompt.side_effect = Exception("Load failed")
            
            # Create extractor
            extractor = FDDSectionExtractor()
            
            # Test prompt loading with fallback
            prompt = extractor._get_section_prompt(5)
            
            assert prompt == "Extract all relevant information from this FDD section."


@pytest.mark.integration
class TestIntegration:
    """Integration tests for the extraction pipeline."""
    
    @pytest.mark.asyncio
    async def test_full_extraction_pipeline(self):
        """Test the full extraction pipeline with real-like data."""
        # This would be an integration test with actual LLM calls
        # For unit tests, we mock everything
        pass