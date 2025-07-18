"""Unit tests for franchisor extraction functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from models.franchisor import FranchisorCreate
from models.base import Address
from tasks.llm_extraction import LLMExtractor


@pytest.mark.asyncio
async def test_franchisor_extraction_method_exists():
    """Test that the extract_franchisor method exists on LLMExtractor."""
    extractor = LLMExtractor()
    assert hasattr(extractor, 'extract_franchisor')
    assert callable(getattr(extractor, 'extract_franchisor'))


@pytest.mark.asyncio
async def test_franchisor_extraction_success():
    """Test successful franchisor extraction with mocked response."""
    # Create mock response
    mock_address = Address(
        street="100 Valvoline Way",
        city="Lexington", 
        state="KY",
        zip="40509"
    )
    
    mock_franchisor = FranchisorCreate(
        canonical_name="Valvoline Instant Oil Change Franchising, Inc.",
        parent_company="Valvoline Inc.",
        website="https://www.valvoline.com",
        phone="(859) 357-7777",
        email="franchise@valvoline.com",
        address=mock_address,
        dba_names=["VIOC", "Valvoline Express Care"]
    )
    
    # Mock the extract_with_fallback method
    with patch.object(LLMExtractor, 'extract_with_fallback') as mock_extract:
        mock_extract.return_value = (mock_franchisor, "gemini")
        
        extractor = LLMExtractor()
        
        sample_text = """
        VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC.
        A Delaware Corporation
        
        Business Address:
        100 Valvoline Way
        Lexington, KY 40509
        Phone: (859) 357-7777
        Website: www.valvoline.com
        
        Parent Company: Valvoline Inc.
        """
        
        result = await extractor.extract_franchisor(sample_text)
        
        # Verify the result
        assert isinstance(result, FranchisorCreate)
        assert result.canonical_name == "Valvoline Instant Oil Change Franchising, Inc."
        assert result.parent_company == "Valvoline Inc."
        assert result.website == "https://www.valvoline.com"
        assert result.phone == "(859) 357-7777"
        assert result.address.state == "KY"
        assert "VIOC" in result.dba_names
        
        # Verify the method was called correctly
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args
        assert call_args[1]['response_model'] == FranchisorCreate
        assert "franchisor information" in call_args[1]['system_prompt']


@pytest.mark.asyncio
async def test_franchisor_extraction_failure():
    """Test franchisor extraction failure handling."""
    with patch.object(LLMExtractor, 'extract_with_fallback') as mock_extract:
        mock_extract.side_effect = Exception("API Error")
        
        extractor = LLMExtractor()
        result = await extractor.extract_franchisor("Sample text")
        
        # Should return error dict
        assert isinstance(result, dict)
        assert result['status'] == 'failed'
        assert 'API Error' in result['error']
        assert 'error_type' in result
        assert 'attempted_at' in result


@pytest.mark.asyncio
async def test_franchisor_extraction_monitoring():
    """Test that extraction monitoring is properly initialized."""
    from unittest.mock import MagicMock
    from uuid import uuid4
    
    # Mock the monitoring
    mock_monitor = MagicMock()
    mock_monitor.start_extraction = MagicMock(return_value=123.456)
    
    with patch('tasks.llm_extraction.get_extraction_monitor', return_value=mock_monitor):
        with patch.object(LLMExtractor, 'extract_with_fallback') as mock_extract:
            mock_extract.return_value = (MagicMock(spec=FranchisorCreate), "gemini")
            
            extractor = LLMExtractor()
            prefect_id = uuid4()
            
            await extractor.extract_franchisor("Sample text", prefect_run_id=prefect_id)
            
            # Verify monitoring was initialized
            mock_monitor.start_extraction.assert_called_once_with(
                section_item=0,
                fdd_id=str(prefect_id),
                model="gemini"
            )
            mock_monitor.set_success.assert_called_once()