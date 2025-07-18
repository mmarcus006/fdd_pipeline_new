"""Multi-model LLM extraction framework with intelligent routing and fallback chains."""

import asyncio
import logging
import time
from typing import Optional, Type, TypeVar, Union, List, Any, Dict, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
import json
from uuid import UUID

import instructor
from google.generativeai import GenerativeModel
import google.generativeai as genai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from config import get_settings
from models.fdd import FDD
from models.section import FDDSection
from models.franchisor import FranchisorCreate
from models.item5_fees import Item5FeesResponse
from models.item6_other_fees import Item6OtherFeesResponse
from models.item7_investment import Item7InvestmentResponse
from models.item19_fpr import Item19FPRResponse
from models.item20_outlets import Item20OutletsResponse
from models.item21_financials import Item21FinancialsResponse
from utils.prompt_loader import get_prompt_loader
from utils.extraction_monitoring import get_extraction_monitor, MonitoredExtraction
from tasks.exceptions import (
    LLMExtractionException,
    ModelInitializationError,
    TokenLimitExceededError,
    ExtractionTimeoutError,
    InvalidExtractionResultError,
    ModelAPIError,
    RetryableError,
    get_retry_delay,
)

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)
settings = get_settings()


class ModelType(Enum):
    """Supported LLM model types."""

    GEMINI = "gemini"
    OLLAMA = "ollama"
    OPENAI = "openai"


class SectionComplexity(Enum):
    """Section complexity levels for model selection."""

    SIMPLE = "simple"  # Simple structured tables (Items 5, 6, 7)
    COMPLEX = "complex"  # Complex narratives and financials (Items 19, 21)
    MEDIUM = "medium"  # Medium complexity sections


@dataclass
class ModelConfig:
    """Configuration for a specific model."""

    model_type: ModelType
    model_name: str
    max_tokens: int = 4000
    temperature: float = 0.1
    timeout_seconds: int = 60
    cost_per_token: float = 0.0  # Cost per token in USD


@dataclass
class TokenUsage:
    """Token usage tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model_used: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExtractionMetrics:
    """Metrics for extraction performance."""

    total_extractions: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    average_response_time: float = 0.0
    model_usage_count: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add_extraction(self, success: bool, tokens: TokenUsage, response_time: float):
        """Add extraction result to metrics."""
        self.total_extractions += 1
        if success:
            self.successful_extractions += 1
        else:
            self.failed_extractions += 1

        self.total_tokens_used += tokens.total_tokens
        self.total_cost_usd += tokens.cost_usd
        self.model_usage_count[tokens.model_used] += 1

        # Update average response time
        self.average_response_time = (
            self.average_response_time * (self.total_extractions - 1) + response_time
        ) / self.total_extractions

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_extractions == 0:
            return 0.0
        return (self.successful_extractions / self.total_extractions) * 100


# Remove local ExtractionError - we'll use the one from exceptions.py
# The ExtractionError is now imported as LLMExtractionException


class ModelSelector:
    """Intelligent model selection based on section complexity."""

    # Section complexity mapping based on technology_decisions.md
    SECTION_COMPLEXITY = {
        # Simple structured tables - use Ollama for cost efficiency
        5: SectionComplexity.SIMPLE,  # Initial Fees
        6: SectionComplexity.SIMPLE,  # Other Fees
        7: SectionComplexity.SIMPLE,  # Initial Investment
        # Complex narratives and financials - use Gemini Pro
        19: SectionComplexity.COMPLEX,  # Financial Performance Representations
        21: SectionComplexity.COMPLEX,  # Financial Statements
        # Medium complexity sections
        20: SectionComplexity.MEDIUM,  # Outlet Information
    }

    # Model configurations
    MODEL_CONFIGS = {
        ModelType.OLLAMA: ModelConfig(
            model_type=ModelType.OLLAMA,
            model_name="llama3.2",
            max_tokens=4000,
            temperature=0.1,
            timeout_seconds=120,
            cost_per_token=0.0,  # Local model, no cost
        ),
        ModelType.GEMINI: ModelConfig(
            model_type=ModelType.GEMINI,
            model_name="gemini-1.5-pro",
            max_tokens=8000,
            temperature=0.1,
            timeout_seconds=60,
            cost_per_token=0.000125,  # Approximate cost per token
        ),
        ModelType.OPENAI: ModelConfig(
            model_type=ModelType.OPENAI,
            model_name="gpt-4-turbo-preview",
            max_tokens=4000,
            temperature=0.1,
            timeout_seconds=60,
            cost_per_token=0.00003,  # Approximate cost per token
        ),
    }

    @classmethod
    def select_primary_model(cls, section_item: int) -> ModelType:
        """Select primary model based on section complexity."""
        complexity = cls.SECTION_COMPLEXITY.get(section_item, SectionComplexity.MEDIUM)

        if complexity == SectionComplexity.SIMPLE:
            return ModelType.OLLAMA
        elif complexity == SectionComplexity.COMPLEX:
            return ModelType.GEMINI
        else:  # MEDIUM
            return ModelType.GEMINI

    @classmethod
    def get_fallback_chain(cls, primary_model: ModelType) -> List[ModelType]:
        """Get fallback chain for a primary model."""
        if primary_model == ModelType.OLLAMA:
            return [ModelType.OLLAMA, ModelType.GEMINI, ModelType.OPENAI]
        elif primary_model == ModelType.GEMINI:
            return [ModelType.GEMINI, ModelType.OLLAMA, ModelType.OPENAI]
        else:  # OPENAI
            return [ModelType.OPENAI, ModelType.GEMINI, ModelType.OLLAMA]

    @classmethod
    def get_model_config(cls, model_type: ModelType) -> ModelConfig:
        """Get configuration for a model type."""
        return cls.MODEL_CONFIGS[model_type]


class ConnectionPool:
    """Connection pool for async LLM clients."""

    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self.semaphore = asyncio.Semaphore(max_connections)
        self._active_connections = 0

    async def acquire(self):
        """Acquire a connection from the pool."""
        await self.semaphore.acquire()
        self._active_connections += 1
        logger.debug(f"Acquired connection, active: {self._active_connections}")

    def release(self):
        """Release a connection back to the pool."""
        self._active_connections -= 1
        self.semaphore.release()
        logger.debug(f"Released connection, active: {self._active_connections}")

    @property
    def active_connections(self) -> int:
        """Get number of active connections."""
        return self._active_connections


class LLMExtractor:
    """Multi-model LLM extractor with intelligent routing and connection pooling."""

    def __init__(self, max_concurrent_extractions: Optional[int] = None):
        self.max_concurrent = (
            max_concurrent_extractions or settings.max_concurrent_extractions
        )
        self.connection_pool = ConnectionPool(self.max_concurrent)
        self.metrics = ExtractionMetrics()
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize LLM clients with Instructor wrappers."""
        # Initialize Gemini
        genai.configure(api_key=settings.gemini_api_key)
        self.gemini_model = GenerativeModel("gemini-1.5-pro")
        self.gemini_client = instructor.from_gemini(
            client=self.gemini_model, use_async=True
        )

        # Initialize OpenAI (if configured)
        if settings.openai_api_key:
            openai_client = AsyncOpenAI(
                api_key=settings.openai_api_key, max_retries=2, timeout=60.0
            )
            self.openai_client = instructor.from_openai(openai_client)
        else:
            self.openai_client = None
            logger.warning(
                "OpenAI API key not configured - OpenAI fallback unavailable"
            )

        # Initialize Ollama
        try:
            from ollama import AsyncClient as OllamaClient

            ollama_client = OllamaClient(host=settings.ollama_base_url, timeout=120.0)
            # Ollama integration not yet available in instructor
            self.ollama_client = None  # instructor.from_ollama(ollama_client)
            self.ollama_available = True
            logger.info(f"Ollama client initialized: {settings.ollama_base_url}")
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            self.ollama_client = None
            self.ollama_available = False

    def select_model_for_section(self, section_item: int) -> ModelType:
        """Select the best model for a specific section."""
        return ModelSelector.select_primary_model(section_item)

    def get_fallback_chain(self, primary_model: ModelType) -> List[ModelType]:
        """Get fallback chain for model failures."""
        return ModelSelector.get_fallback_chain(primary_model)

    def estimate_tokens(self, content: str, system_prompt: str) -> int:
        """Estimate token count for content and prompt."""
        # Rough estimation: ~4 characters per token
        total_chars = len(content) + len(system_prompt)
        return total_chars // 4

    def calculate_cost(self, tokens: int, model_type: ModelType) -> float:
        """Calculate cost for token usage."""
        config = ModelSelector.get_model_config(model_type)
        return tokens * config.cost_per_token

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((LLMExtractionException, ValidationError, RetryableError)),
    )
    async def extract_with_gemini(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        temperature: float = 0.1,
    ) -> T:
        """Extract structured data using Gemini Pro."""
        try:
            logger.info(f"Extracting {response_model.__name__} with Gemini")

            # Instructor with Gemini uses a different interface
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ]
            
            response = await self.gemini_client.create(
                response_model=response_model,
                messages=messages,
                max_retries=2,
            )

            return response

        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            raise LLMExtractionException(f"Gemini extraction failed: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((LLMExtractionException, ValidationError, RetryableError)),
    )
    async def extract_with_ollama(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        model: str = "llama3.2",
        temperature: float = 0.1,
    ) -> T:
        """Extract structured data using local Ollama models."""
        if not self.ollama_available:
            raise LLMExtractionException("Ollama is not available")

        try:
            logger.info(f"Extracting {response_model.__name__} with Ollama ({model})")

            response = await self.ollama_client.create(
                model=model,
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                temperature=temperature,
            )

            return response

        except Exception as e:
            logger.error(f"Ollama extraction failed: {e}")
            raise LLMExtractionException(f"Ollama extraction failed: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((LLMExtractionException, ValidationError, RetryableError)),
    )
    async def extract_with_openai(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.1,
    ) -> T:
        """Extract structured data using OpenAI GPT-4."""
        if not self.openai_client:
            raise LLMExtractionException("OpenAI client not configured")

        try:
            logger.info(f"Extracting {response_model.__name__} with OpenAI ({model})")

            response = await self.openai_client.create(
                model=model,
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                temperature=temperature,
                max_retries=2,
            )

            return response

        except Exception as e:
            logger.error(f"OpenAI extraction failed: {e}")
            raise LLMExtractionException(f"OpenAI extraction failed: {e}")

    async def extract_with_fallback(
        self,
        content: str,
        response_model: Type[T],
        system_prompt: str,
        primary_model: str = "gemini",
        temperature: float = 0.1,
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
                ("openai", self.extract_with_openai),
            ]
        elif primary_model == "ollama":
            model_chain = [
                ("ollama", self.extract_with_ollama),
                ("gemini", self.extract_with_gemini),
                ("openai", self.extract_with_openai),
            ]
        elif primary_model == "openai":
            model_chain = [
                ("openai", self.extract_with_openai),
                ("gemini", self.extract_with_gemini),
                ("ollama", self.extract_with_ollama),
            ]

        last_error = None
        for model_name, extract_func in model_chain:
            try:
                result = await extract_func(
                    content=content,
                    response_model=response_model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )
                logger.info(f"Successfully extracted with {model_name}")
                return result, model_name
            except LLMExtractionException as e:
                last_error = e
                logger.warning(f"{model_name} failed, trying next model: {e}")
                continue

        raise LLMExtractionException(f"All models failed. Last error: {last_error}")

    async def extract_franchisor(
        self,
        content: str,
        prefect_run_id: Optional[UUID] = None,
    ) -> Union[FranchisorCreate, dict]:
        """
        Extract franchisor information from FDD content.
        
        Args:
            content: Text content containing franchisor information
            prefect_run_id: Optional Prefect run ID for tracking
            
        Returns:
            FranchisorCreate model or error dict
        """
        # Use Gemini as primary model for franchisor extraction
        primary_model = ModelType.GEMINI
        fallback_chain = self.get_fallback_chain(primary_model)
        
        # System prompt for franchisor extraction
        system_prompt = """Extract franchisor information from this FDD document. 
        Focus on identifying:
        - Company name (canonical name)
        - Parent company if mentioned
        - Website, phone, email contact information  
        - Business address (street, city, state, zip)
        - Any DBA (doing business as) names
        
        Ensure addresses follow the format with state as 2-letter code (e.g., "KY" not "Kentucky").
        Ensure zip codes are in the format XXXXX or XXXXX-XXXX."""
        
        # Use extraction monitoring
        extraction_monitor = get_extraction_monitor()
        extraction = extraction_monitor.start_extraction(
            section_item=0,  # Using 0 for franchisor as it's not a numbered section
            fdd_id=str(prefect_run_id) if prefect_run_id else "franchisor_extraction",
            model=primary_model.value,
        )
        
        await self.connection_pool.acquire()
        try:
            # Extract using primary model with fallback
            result, model_used = await self.extract_with_fallback(
                content=content,
                response_model=FranchisorCreate,
                system_prompt=system_prompt,
                primary_model=primary_model.value,
            )
            
            # Estimate tokens for monitoring
            estimated_tokens = self.estimate_tokens(content, system_prompt)
            extraction_monitor.set_success(tokens_used=estimated_tokens)
            return result
            
        except Exception as e:
            logger.error(
                f"Franchisor extraction failed: {e}",
                extra={
                    "error_type": type(e).__name__,
                    "prefect_run_id": str(prefect_run_id) if prefect_run_id else None,
                }
            )
            # ExtractionMonitor doesn't have set_failed, just log the error
            return {
                "status": "failed",
                "error": f"Franchisor extraction failed: {e}",
                "error_type": type(e).__name__,
                "attempted_at": datetime.utcnow().isoformat(),
            }
        finally:
            self.connection_pool.release()


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
            21: Item21FinancialsResponse,
        }

    async def extract_section(
        self, section: FDDSection, content: str, primary_model: str = "gemini"
    ) -> Dict[str, Any]:
        """Extract structured data from a specific FDD section."""

        # Get the appropriate response model
        response_model = self.section_models.get(section.item_no)
        if not response_model:
            logger.warning(f"No extraction model defined for Item {section.item_no}")
            return {"status": "skipped", "reason": "No extraction model defined"}

        # Get section-specific prompt
        system_prompt = self._get_section_prompt(section.item_no)

        # Use monitoring context
        monitor = get_extraction_monitor()
        with MonitoredExtraction(
            section_item=section.item_no,
            fdd_id=section.fdd_id,
            model=primary_model,
            monitor=monitor,
        ) as extraction_monitor:
            try:
                # Extract with fallback
                extracted_data, model_used = await self.extractor.extract_with_fallback(
                    content=content,
                    response_model=response_model,
                    system_prompt=system_prompt,
                    primary_model=primary_model,
                )

                # Estimate tokens (rough approximation)
                estimated_tokens = len(content.split()) + len(system_prompt.split())
                extraction_monitor.set_success(tokens_used=estimated_tokens)

                return {
                    "status": "success",
                    "data": extracted_data.model_dump(),
                    "model_used": model_used,
                    "extracted_at": datetime.utcnow().isoformat(),
                }

            except (LLMExtractionException, ModelAPIError, ExtractionTimeoutError) as e:
                logger.error(
                    f"Failed to extract Item {section.item_no}: {e}",
                    extra={
                        "section_item": section.item_no,
                        "fdd_id": str(section.fdd_id),
                        "error_type": type(e).__name__,
                        "correlation_id": getattr(e, 'correlation_id', None)
                    }
                )
                extraction_monitor.set_failed(str(e))
                return {
                    "status": "failed",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempted_at": datetime.utcnow().isoformat(),
                }
            except Exception as e:
                logger.error(
                    f"Unexpected error extracting Item {section.item_no}: {e}",
                    extra={
                        "section_item": section.item_no,
                        "fdd_id": str(section.fdd_id),
                        "error_type": type(e).__name__
                    }
                )
                extraction_monitor.set_failed(str(e))
                return {
                    "status": "failed",
                    "error": f"Unexpected error: {e}",
                    "error_type": type(e).__name__,
                    "attempted_at": datetime.utcnow().isoformat(),
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
    primary_model: str = "gemini",
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
    monitor = get_extraction_monitor()

    logger.info(
        f"Starting FDD document extraction",
        fdd_id=str(fdd.id),
        sections_count=len(sections),
    )

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
            logger.error(
                f"Failed to extract Item {item_no}: {e}",
                extra={
                    "fdd_id": str(fdd.id),
                    "item_no": item_no,
                    "error_type": type(e).__name__
                }
            )
            results[f"item_{item_no}"] = {
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__
            }

    # Log extraction summary
    successful = sum(1 for r in results.values() if r.get("status") == "success")
    failed = sum(1 for r in results.values() if r.get("status") == "failed")
    logger.info(
        "FDD document extraction completed",
        fdd_id=str(fdd.id),
        total_sections=len(results),
        successful=successful,
        failed=failed,
    )

    # Get session summary from monitor
    session_summary = monitor.get_session_summary()

    return {
        "fdd_id": str(fdd.id),
        "extraction_timestamp": datetime.utcnow().isoformat(),
        "primary_model": primary_model,
        "sections": results,
        "extraction_metrics": {
            "total_sections": len(results),
            "successful": successful,
            "failed": failed,
            "session_summary": session_summary,
        },
    }
