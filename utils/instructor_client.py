"""Modern Instructor client implementation with proper Google Gemini integration.

This module provides a unified interface for structured LLM extraction using the
latest Instructor library patterns with multiple provider support.
"""

import asyncio
import logging
from typing import Type, TypeVar, Optional, List, Dict, Any, Union, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import instructor
from google import genai
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from config import get_settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)
settings = get_settings()


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    OPENAI = "openai"
    OLLAMA = "ollama"


class ExtractionMode(str, Enum):
    """Extraction input modes."""
    TEXT = "text"
    PDF_FILE = "pdf_file"
    PDF_URL = "pdf_url"
    IMAGE = "image"


@dataclass
class ExtractionConfig:
    """Configuration for extraction operations."""
    model_name: Optional[str] = None
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    max_retries: int = 3
    timeout_seconds: int = 60
    validation_retries: int = 2


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""
    data: BaseModel
    provider_used: LLMProvider
    model_used: str
    tokens_used: Optional[int] = None
    extraction_time_seconds: float = 0.0
    validation_passed: bool = True
    validation_errors: List[str] = Field(default_factory=list)


class InstructorClient:
    """Modern Instructor client with support for multiple providers and input modes."""
    
    def __init__(self, primary_provider: LLMProvider = LLMProvider.GEMINI):
        """Initialize the Instructor client with configured providers.
        
        Args:
            primary_provider: The primary LLM provider to use
        """
        self.primary_provider = primary_provider
        self.clients = {}
        self._initialize_clients()
        
    def _initialize_clients(self):
        """Initialize LLM clients based on configuration."""
        # Initialize Gemini client (recommended approach)
        if settings.gemini_api_key:
            try:
                # Option 1: Simple provider initialization
                self.clients[LLMProvider.GEMINI] = instructor.from_provider(
                    "google/gemini-1.5-flash-latest",
                    mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
                    api_key=settings.gemini_api_key
                )
                logger.info("Initialized Gemini client with structured outputs mode")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                # Fallback to direct initialization
                try:
                    genai_client = genai.Client(api_key=settings.gemini_api_key)
                    self.clients[LLMProvider.GEMINI] = instructor.from_genai(
                        genai_client,
                        mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS
                    )
                    logger.info("Initialized Gemini client using fallback method")
                except Exception as e2:
                    logger.error(f"Failed to initialize Gemini client (fallback): {e2}")
        
        # Initialize OpenAI client
        if settings.openai_api_key:
            try:
                openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
                self.clients[LLMProvider.OPENAI] = instructor.from_openai(openai_client)
                logger.info("Initialized OpenAI client")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        
        # Initialize Ollama client
        if settings.ollama_base_url:
            try:
                # Dynamic import to avoid dependency if not used
                from ollama import AsyncClient as OllamaClient
                ollama_client = OllamaClient(host=settings.ollama_base_url)
                self.clients[LLMProvider.OLLAMA] = instructor.from_ollama(ollama_client)
                logger.info("Initialized Ollama client")
            except Exception as e:
                logger.warning(f"Ollama not available: {e}")
    
    def get_available_providers(self) -> List[LLMProvider]:
        """Get list of available providers."""
        return list(self.clients.keys())
    
    def _get_fallback_chain(self, primary: LLMProvider) -> List[LLMProvider]:
        """Get fallback provider chain."""
        all_providers = [LLMProvider.GEMINI, LLMProvider.OPENAI, LLMProvider.OLLAMA]
        
        # Start with primary, then add others
        chain = [primary]
        for provider in all_providers:
            if provider != primary and provider in self.clients:
                chain.append(provider)
        
        return chain
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(Exception)
    )
    async def extract_from_text(
        self,
        text: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        config: Optional[ExtractionConfig] = None,
        provider: Optional[LLMProvider] = None
    ) -> ExtractionResult:
        """Extract structured data from text.
        
        Args:
            text: The text to extract from
            response_model: Pydantic model defining the expected structure
            system_prompt: Optional system prompt
            config: Extraction configuration
            provider: Specific provider to use (defaults to primary)
            
        Returns:
            ExtractionResult containing the extracted data and metadata
        """
        config = config or ExtractionConfig()
        provider = provider or self.primary_provider
        
        if provider not in self.clients:
            raise ValueError(f"Provider {provider} not available")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text})
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            client = self.clients[provider]
            
            # Provider-specific parameters
            kwargs = {
                "messages": messages,
                "response_model": response_model,
                "temperature": config.temperature,
                "max_retries": config.validation_retries,
            }
            
            # Add provider-specific model names
            if provider == LLMProvider.GEMINI:
                kwargs["model"] = config.model_name or "gemini-1.5-flash-latest"
            elif provider == LLMProvider.OPENAI:
                kwargs["model"] = config.model_name or "gpt-4-turbo-preview"
                if config.max_tokens:
                    kwargs["max_tokens"] = config.max_tokens
            elif provider == LLMProvider.OLLAMA:
                kwargs["model"] = config.model_name or "llama3.2"
            
            # Create the structured response
            response = await client.messages.create(**kwargs)
            
            elapsed_time = asyncio.get_event_loop().time() - start_time
            
            # Validate the response if the model has validation
            validation_errors = []
            if hasattr(response, "validate_extraction"):
                validation_errors = response.validate_extraction()
            
            return ExtractionResult(
                data=response,
                provider_used=provider,
                model_used=kwargs.get("model", "unknown"),
                extraction_time_seconds=elapsed_time,
                validation_passed=len(validation_errors) == 0,
                validation_errors=validation_errors
            )
            
        except Exception as e:
            logger.error(f"Extraction failed with {provider}: {e}")
            raise
    
    async def extract_from_pdf_file(
        self,
        pdf_path: Union[str, Path],
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        config: Optional[ExtractionConfig] = None,
        page_range: Optional[Tuple[int, int]] = None
    ) -> ExtractionResult:
        """Extract structured data from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            response_model: Pydantic model defining the expected structure
            system_prompt: Optional system prompt
            config: Extraction configuration
            page_range: Optional tuple of (start_page, end_page) for partial extraction
            
        Returns:
            ExtractionResult containing the extracted data and metadata
        """
        config = config or ExtractionConfig()
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # For Gemini, we can upload the file directly
        if LLMProvider.GEMINI in self.clients:
            try:
                # Upload the file using genai
                import google.generativeai as genai_upload
                genai_upload.configure(api_key=settings.gemini_api_key)
                
                uploaded_file = genai_upload.upload_file(str(pdf_path))
                logger.info(f"Uploaded PDF file: {uploaded_file.name}")
                
                # Create messages with the file
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                
                # Add user message with file
                user_content = []
                if page_range:
                    user_content.append(f"Extract from pages {page_range[0]} to {page_range[1]} of the following PDF:")
                else:
                    user_content.append("Extract from the following PDF:")
                user_content.append(uploaded_file)
                
                messages.append({"role": "user", "content": user_content})
                
                # Use Gemini client for extraction
                client = self.clients[LLMProvider.GEMINI]
                start_time = asyncio.get_event_loop().time()
                
                response = await client.messages.create(
                    messages=messages,
                    response_model=response_model,
                    model=config.model_name or "gemini-1.5-flash-latest",
                    temperature=config.temperature,
                    max_retries=config.validation_retries
                )
                
                elapsed_time = asyncio.get_event_loop().time() - start_time
                
                # Validate response
                validation_errors = []
                if hasattr(response, "validate_extraction"):
                    validation_errors = response.validate_extraction()
                
                return ExtractionResult(
                    data=response,
                    provider_used=LLMProvider.GEMINI,
                    model_used="gemini-1.5-flash-latest",
                    extraction_time_seconds=elapsed_time,
                    validation_passed=len(validation_errors) == 0,
                    validation_errors=validation_errors
                )
                
            except Exception as e:
                logger.error(f"Failed to process PDF with Gemini: {e}")
                # Fall back to text extraction
                return await self._extract_from_pdf_as_text(
                    pdf_path, response_model, system_prompt, config, page_range
                )
        else:
            # Fall back to text extraction for other providers
            return await self._extract_from_pdf_as_text(
                pdf_path, response_model, system_prompt, config, page_range
            )
    
    async def _extract_from_pdf_as_text(
        self,
        pdf_path: Path,
        response_model: Type[T],
        system_prompt: Optional[str],
        config: ExtractionConfig,
        page_range: Optional[Tuple[int, int]]
    ) -> ExtractionResult:
        """Extract from PDF by converting to text first (fallback method)."""
        # This would use PyPDF2 or similar to extract text
        # For now, raise NotImplementedError
        raise NotImplementedError(
            "Text extraction from PDF not implemented. "
            "Please use Gemini provider for direct PDF processing."
        )
    
    async def extract_from_url(
        self,
        url: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        config: Optional[ExtractionConfig] = None
    ) -> ExtractionResult:
        """Extract structured data from a URL (typically a PDF).
        
        Args:
            url: URL of the document to extract from
            response_model: Pydantic model defining the expected structure
            system_prompt: Optional system prompt
            config: Extraction configuration
            
        Returns:
            ExtractionResult containing the extracted data and metadata
        """
        # For URL-based extraction, we'll need to download first or use web fetch
        # This is a placeholder for the URL functionality
        raise NotImplementedError("URL-based extraction coming soon")
    
    async def extract_with_fallback(
        self,
        content: Union[str, Path],
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        config: Optional[ExtractionConfig] = None,
        mode: ExtractionMode = ExtractionMode.TEXT
    ) -> ExtractionResult:
        """Extract with automatic fallback between providers.
        
        Args:
            content: The content to extract from (text or file path)
            response_model: Pydantic model defining the expected structure
            system_prompt: Optional system prompt
            config: Extraction configuration
            mode: The extraction mode (text, pdf_file, etc.)
            
        Returns:
            ExtractionResult containing the extracted data and metadata
        """
        config = config or ExtractionConfig()
        providers = self._get_fallback_chain(self.primary_provider)
        
        last_error = None
        for provider in providers:
            try:
                if mode == ExtractionMode.TEXT:
                    return await self.extract_from_text(
                        content, response_model, system_prompt, config, provider
                    )
                elif mode == ExtractionMode.PDF_FILE:
                    # PDF file mode only works with Gemini for now
                    if provider == LLMProvider.GEMINI:
                        return await self.extract_from_pdf_file(
                            content, response_model, system_prompt, config
                        )
                    else:
                        continue  # Skip non-Gemini providers for PDF
                else:
                    raise ValueError(f"Unsupported mode: {mode}")
                    
            except Exception as e:
                logger.warning(f"Provider {provider} failed: {e}")
                last_error = e
                continue
        
        raise Exception(f"All providers failed. Last error: {last_error}")
    
    def validate_response(
        self,
        response: BaseModel,
        additional_validators: Optional[List[callable]] = None
    ) -> List[str]:
        """Validate a response using built-in and custom validators.
        
        Args:
            response: The response to validate
            additional_validators: Optional list of additional validation functions
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Built-in validation
        if hasattr(response, "validate_extraction"):
            errors.extend(response.validate_extraction())
        
        # Additional validators
        if additional_validators:
            for validator in additional_validators:
                try:
                    result = validator(response)
                    if result:  # Validator returns error message
                        errors.append(result)
                except Exception as e:
                    errors.append(f"Validator error: {e}")
        
        return errors


# Convenience functions
async def extract_text(
    text: str,
    response_model: Type[T],
    system_prompt: Optional[str] = None,
    **kwargs
) -> T:
    """Simple text extraction with default client."""
    client = InstructorClient()
    result = await client.extract_from_text(
        text, response_model, system_prompt, **kwargs
    )
    return result.data


async def extract_pdf(
    pdf_path: Union[str, Path],
    response_model: Type[T],
    system_prompt: Optional[str] = None,
    **kwargs
) -> T:
    """Simple PDF extraction with default client."""
    client = InstructorClient()
    result = await client.extract_from_pdf_file(
        pdf_path, response_model, system_prompt, **kwargs
    )
    return result.data