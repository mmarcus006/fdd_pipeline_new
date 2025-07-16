"""LLM extraction module using Instructor for structured output from FDD documents."""

import asyncio
import logging
from typing import Optional, Type, TypeVar, Union, List, Any, Dict
from datetime import datetime

import instructor
from google.generativeai import GenerativeModel
import google.generativeai as genai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from config import get_settings
from models.fdd import FDD
from models.section import FDDSection
from models.item5_fees import Item5FeesResponse
from models.item6_other_fees import Item6OtherFeesResponse
from models.item7_investment import Item7InvestmentResponse
from models.item19_fpr import Item19FPRResponse
from models.item20_outlets import Item20OutletsResponse
from models.item21_financials import Item21FinancialsResponse
from utils.prompt_loader import get_prompt_loader

T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)
settings = get_settings()


class ExtractionError(Exception):
    """Custom exception for extraction failures."""
    pass


class LLMExtractor:
    """Multi-model LLM extractor with Instructor integration."""
    
    def __init__(self):
        self._initialize_clients()
        
    def _initialize_clients(self):
        """Initialize LLM clients with Instructor wrappers."""
        # Initialize Gemini
        genai.configure(api_key=settings.gemini_api_key)
        self.gemini_model = GenerativeModel("gemini-1.5-pro")
        self.gemini_client = instructor.from_gemini(
            client=genai,
            model=self.gemini_model,
            use_async=True
        )
        
        # Initialize OpenAI (if configured)
        if settings.openai_api_key:
            openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.openai_client = instructor.from_openai(openai_client)
        else:
            self.openai_client = None
            
        # Initialize Ollama
        try:
            from ollama import AsyncClient as OllamaClient
            ollama_client = OllamaClient(host=settings.ollama_base_url)
            self.ollama_client = instructor.from_ollama(ollama_client)
            self.ollama_available = True
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            self.ollama_client = None
            self.ollama_available = False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((ExtractionError, ValidationError))
    )
    async def extract_with_gemini(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        temperature: float = 0.1
    ) -> T:
        """Extract structured data using Gemini Pro."""
        try:
            logger.info(f"Extracting {response_model.__name__} with Gemini")
            
            response = await self.gemini_client.create(
                model="gemini-1.5-pro",
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                temperature=temperature,
                max_retries=2
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            raise ExtractionError(f"Gemini extraction failed: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((ExtractionError, ValidationError))
    )
    async def extract_with_ollama(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        model: str = "llama3.2",
        temperature: float = 0.1
    ) -> T:
        """Extract structured data using local Ollama models."""
        if not self.ollama_available:
            raise ExtractionError("Ollama is not available")
            
        try:
            logger.info(f"Extracting {response_model.__name__} with Ollama ({model})")
            
            response = await self.ollama_client.create(
                model=model,
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                temperature=temperature
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Ollama extraction failed: {e}")
            raise ExtractionError(f"Ollama extraction failed: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((ExtractionError, ValidationError))
    )
    async def extract_with_openai(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.1
    ) -> T:
        """Extract structured data using OpenAI GPT-4."""
        if not self.openai_client:
            raise ExtractionError("OpenAI client not configured")
            
        try:
            logger.info(f"Extracting {response_model.__name__} with OpenAI ({model})")
            
            response = await self.openai_client.create(
                model=model,
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                temperature=temperature,
                max_retries=2
            )
            
            return response
            
        except Exception as e:
            logger.error(f"OpenAI extraction failed: {e}")
            raise ExtractionError(f"OpenAI extraction failed: {e}")

    async def extract_with_fallback(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        primary_model: str = "gemini",
        temperature: float = 0.1
    ) -> tuple[T, str]:
        """
        Extract with automatic fallback between models.
        
        Returns tuple of (extracted_data, model_used)
        """
        model_chain = []
        
        # Build model chain based on primary preference
        if primary_model == "gemini":
            model_chain = [
                ("gemini", self.extract_with_gemini),
                ("ollama", self.extract_with_ollama),
                ("openai", self.extract_with_openai)
            ]
        elif primary_model == "ollama":
            model_chain = [
                ("ollama", self.extract_with_ollama),
                ("gemini", self.extract_with_gemini),
                ("openai", self.extract_with_openai)
            ]
        elif primary_model == "openai":
            model_chain = [
                ("openai", self.extract_with_openai),
                ("gemini", self.extract_with_gemini),
                ("ollama", self.extract_with_ollama)
            ]
        
        last_error = None
        for model_name, extract_func in model_chain:
            try:
                result = await extract_func(
                    content=content,
                    response_model=response_model,
                    system_prompt=system_prompt,
                    temperature=temperature
                )
                logger.info(f"Successfully extracted with {model_name}")
                return result, model_name
            except ExtractionError as e:
                last_error = e
                logger.warning(f"{model_name} failed, trying next model: {e}")
                continue
        
        raise ExtractionError(f"All models failed. Last error: {last_error}")


class FDDSectionExtractor:
    """Specialized extractor for FDD sections."""
    
    def __init__(self, extractor: Optional[LLMExtractor] = None):
        self.extractor = extractor or LLMExtractor()
        self.prompt_loader = get_prompt_loader()
        self.section_models = {
            5: Item5FeesResponse,
            6: Item6OtherFeesResponse,
            7: Item7InvestmentResponse,
            19: Item19FPRResponse,
            20: Item20OutletsResponse,
            21: Item21FinancialsResponse
        }
    
    async def extract_section(
        self,
        section: FDDSection,
        content: str,
        primary_model: str = "gemini"
    ) -> Dict[str, Any]:
        """Extract structured data from a specific FDD section."""
        
        # Get the appropriate response model
        response_model = self.section_models.get(section.item_no)
        if not response_model:
            logger.warning(f"No extraction model defined for Item {section.item_no}")
            return {"status": "skipped", "reason": "No extraction model defined"}
        
        # Get section-specific prompt
        system_prompt = self._get_section_prompt(section.item_no)
        
        try:
            # Extract with fallback
            extracted_data, model_used = await self.extractor.extract_with_fallback(
                content=content,
                response_model=response_model,
                system_prompt=system_prompt,
                primary_model=primary_model
            )
            
            return {
                "status": "success",
                "data": extracted_data.model_dump(),
                "model_used": model_used,
                "extracted_at": datetime.utcnow().isoformat()
            }
            
        except ExtractionError as e:
            logger.error(f"Failed to extract Item {section.item_no}: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "attempted_at": datetime.utcnow().isoformat()
            }
    
    def _get_section_prompt(self, item_no: int) -> str:
        """Get section-specific extraction prompt from YAML templates."""
        prompt_name = self.prompt_loader.get_prompt_for_item(item_no)
        
        if prompt_name:
            try:
                # Load the prompt template and return the system prompt
                return self.prompt_loader.render_system_prompt(prompt_name)
            except Exception as e:
                logger.warning(f"Failed to load prompt for item {item_no}: {e}")
        
        # Fallback to generic prompt
        return "Extract all relevant information from this FDD section."


async def extract_fdd_document(
    fdd: FDD,
    sections: List[FDDSection],
    content_by_section: Dict[int, str],
    primary_model: str = "gemini"
) -> Dict[str, Any]:
    """
    Extract all sections from an FDD document.
    
    Args:
        fdd: The FDD document metadata
        sections: List of sections to extract
        content_by_section: Dict mapping item numbers to content
        primary_model: Primary model to use for extraction
        
    Returns:
        Dict with extraction results for each section
    """
    extractor = FDDSectionExtractor()
    results = {}
    
    # Process sections concurrently
    tasks = []
    for section in sections:
        if section.item_no in content_by_section:
            content = content_by_section[section.item_no]
            task = extractor.extract_section(section, content, primary_model)
            tasks.append((section.item_no, task))
    
    # Gather results
    for item_no, task in tasks:
        try:
            result = await task
            results[f"item_{item_no}"] = result
        except Exception as e:
            logger.error(f"Failed to extract Item {item_no}: {e}")
            results[f"item_{item_no}"] = {
                "status": "failed",
                "error": str(e)
            }
    
    return {
        "fdd_id": str(fdd.id),
        "extraction_timestamp": datetime.utcnow().isoformat(),
        "primary_model": primary_model,
        "sections": results
    }