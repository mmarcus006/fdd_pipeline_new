"""LLM-based validation utilities for FDD data extraction.

This module provides semantic validation capabilities using LLMs to ensure
data quality beyond simple type checking.
"""

import asyncio
import logging
from typing import Any, Optional, List, Dict, Callable, TypeVar, Union
from functools import wraps
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, BeforeValidator
from typing_extensions import Annotated

from utils.instructor_client import InstructorClient, LLMProvider

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ValidationResult(BaseModel):
    """Result of a validation check."""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class SemanticValidationRequest(BaseModel):
    """Request for semantic validation."""
    content: str = Field(..., description="The content to validate")
    validation_criteria: str = Field(..., description="What to validate for")
    context: Optional[str] = Field(None, description="Additional context")


class SemanticValidationResponse(BaseModel):
    """Response from semantic validation."""
    is_valid: bool = Field(..., description="Whether the content meets the criteria")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the validation")
    issues: List[str] = Field(default_factory=list, description="List of issues found")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions for improvement")
    reasoning: str = Field(..., description="Explanation of the validation decision")


def create_llm_validator(
    validation_prompt: str,
    client: Optional[InstructorClient] = None,
    provider: Optional[LLMProvider] = None
) -> Callable[[Any], Any]:
    """Create a Pydantic validator that uses an LLM for semantic validation.
    
    Args:
        validation_prompt: The validation criteria to check
        client: Optional InstructorClient instance (creates new if not provided)
        provider: Optional provider to use (defaults to Gemini)
        
    Returns:
        A validator function that can be used with Pydantic's BeforeValidator
    """
    if client is None:
        client = InstructorClient(primary_provider=provider or LLMProvider.GEMINI)
    
    def validator(value: Any) -> Any:
        """Validate value using LLM."""
        if not value:
            return value
        
        # Run async validation in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                validate_with_llm(
                    content=str(value),
                    validation_criteria=validation_prompt,
                    client=client
                )
            )
            
            if not result.is_valid:
                error_msg = f"Validation failed: {'; '.join(result.issues)}"
                if result.suggestions:
                    error_msg += f" Suggestions: {'; '.join(result.suggestions)}"
                raise ValueError(error_msg)
            
            return value
        finally:
            loop.close()
    
    return validator


async def validate_with_llm(
    content: str,
    validation_criteria: str,
    context: Optional[str] = None,
    client: Optional[InstructorClient] = None
) -> SemanticValidationResponse:
    """Validate content using an LLM for semantic checks.
    
    Args:
        content: The content to validate
        validation_criteria: What to validate for
        context: Optional additional context
        client: Optional InstructorClient instance
        
    Returns:
        SemanticValidationResponse with validation results
    """
    if client is None:
        client = InstructorClient()
    
    system_prompt = """You are a validation expert for Franchise Disclosure Documents (FDDs).
    Your job is to validate content based on specific criteria and provide detailed feedback.
    Be strict but fair in your validation. Always explain your reasoning."""
    
    user_prompt = f"""Validate the following content:

Content: {content}

Validation Criteria: {validation_criteria}
"""
    
    if context:
        user_prompt += f"\n\nAdditional Context: {context}"
    
    user_prompt += """

Provide a detailed validation response including:
1. Whether the content is valid
2. Your confidence level (0-1)
3. Any issues found
4. Suggestions for improvement
5. Your reasoning"""
    
    result = await client.extract_from_text(
        text=user_prompt,
        response_model=SemanticValidationResponse,
        system_prompt=system_prompt
    )
    
    return result.data


class FDDValidators:
    """Collection of FDD-specific validators."""
    
    @staticmethod
    def validate_franchise_fee(fee_cents: int) -> Optional[str]:
        """Validate franchise fee is within reasonable bounds."""
        if fee_cents < 0:
            return "Franchise fee cannot be negative"
        if fee_cents == 0:
            return "Zero franchise fee requires explanation"
        if fee_cents > 100_000_000:  # $1M
            return "Franchise fee exceeds $1,000,000 - verify accuracy"
        return None
    
    @staticmethod
    def validate_fiscal_year(year: int) -> Optional[str]:
        """Validate fiscal year is reasonable."""
        current_year = datetime.now().year
        if year < 1900:
            return f"Year {year} is too far in the past"
        if year > current_year + 1:
            return f"Year {year} is in the future"
        return None
    
    @staticmethod
    def validate_percentage(value: float, field_name: str = "Percentage") -> Optional[str]:
        """Validate percentage is within 0-100."""
        if value < 0:
            return f"{field_name} cannot be negative"
        if value > 100:
            return f"{field_name} cannot exceed 100%"
        return None
    
    @staticmethod
    def validate_state_code(code: str) -> Optional[str]:
        """Validate US state/territory code."""
        valid_codes = {
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "DC", "PR", "VI", "GU", "AS", "MP"
        }
        if code not in valid_codes:
            return f"Invalid state code: {code}"
        return None
    
    @staticmethod
    async def validate_business_description(
        description: str,
        franchise_name: str,
        client: Optional[InstructorClient] = None
    ) -> ValidationResult:
        """Validate business description using LLM."""
        validation_criteria = f"""
        Check if this business description for {franchise_name}:
        1. Clearly explains what the franchise does
        2. Is professional and appropriate
        3. Contains sufficient detail (at least 50 words)
        4. Does not contain inappropriate content
        5. Is factually consistent
        """
        
        result = await validate_with_llm(
            content=description,
            validation_criteria=validation_criteria,
            context=f"This is for a franchise disclosure document",
            client=client
        )
        
        return ValidationResult(
            is_valid=result.is_valid,
            errors=result.issues,
            suggestions=result.suggestions,
            confidence=result.confidence
        )
    
    @staticmethod
    async def validate_fee_description(
        fee_description: str,
        fee_amount: int,
        client: Optional[InstructorClient] = None
    ) -> ValidationResult:
        """Validate fee description matches the amount and is clear."""
        validation_criteria = f"""
        Check if this fee description:
        1. Clearly explains what the fee of ${fee_amount / 100:,.2f} is for
        2. Uses appropriate financial terminology
        3. Is specific and not vague
        4. Matches the fee amount (not describing a different fee)
        """
        
        result = await validate_with_llm(
            content=fee_description,
            validation_criteria=validation_criteria,
            client=client
        )
        
        return ValidationResult(
            is_valid=result.is_valid,
            errors=result.issues,
            suggestions=result.suggestions,
            confidence=result.confidence
        )


class CrossFieldValidator:
    """Validator for cross-field consistency checks."""
    
    @staticmethod
    def validate_outlet_math(
        count_start: int,
        opened: int,
        closed: int,
        transferred_in: int,
        transferred_out: int,
        count_end: int
    ) -> Optional[str]:
        """Validate outlet count mathematics."""
        calculated = count_start + opened - closed + transferred_in - transferred_out
        if calculated != count_end:
            return (
                f"Outlet math doesn't balance: "
                f"{count_start} + {opened} - {closed} + {transferred_in} - {transferred_out} "
                f"= {calculated}, but count_end = {count_end}"
            )
        return None
    
    @staticmethod
    def validate_fee_relationships(fees: List[Dict[str, Any]]) -> List[str]:
        """Validate relationships between different fees."""
        issues = []
        
        # Find primary franchise fee
        franchise_fee = None
        for fee in fees:
            if "franchise" in fee.get("fee_name", "").lower():
                franchise_fee = fee.get("amount_cents", 0)
                break
        
        if not franchise_fee:
            issues.append("No primary franchise fee found")
            return issues
        
        # Check other fees against franchise fee
        for fee in fees:
            if fee.get("amount_cents", 0) > franchise_fee * 2:
                issues.append(
                    f"Fee '{fee.get('fee_name')}' is more than double the franchise fee"
                )
        
        return issues
    
    @staticmethod
    async def validate_year_over_year_growth(
        outlet_data: List[Dict[str, Any]],
        client: Optional[InstructorClient] = None
    ) -> ValidationResult:
        """Validate year-over-year growth patterns are reasonable."""
        # Sort by year
        sorted_data = sorted(outlet_data, key=lambda x: x.get("fiscal_year", 0))
        
        # Calculate growth rates
        growth_rates = []
        for i in range(1, len(sorted_data)):
            prev_count = sorted_data[i-1].get("count_end", 0)
            curr_count = sorted_data[i].get("count_end", 0)
            
            if prev_count > 0:
                growth_rate = ((curr_count - prev_count) / prev_count) * 100
                growth_rates.append({
                    "year": sorted_data[i].get("fiscal_year"),
                    "growth_rate": growth_rate
                })
        
        # Use LLM to validate growth patterns
        validation_criteria = """
        Analyze these year-over-year growth rates for a franchise:
        1. Are the growth rates realistic for a franchise business?
        2. Are there any suspicious patterns (e.g., exactly 10% every year)?
        3. Do any years show unrealistic growth (>100% or < -50%)?
        4. Is the overall trend consistent with a healthy franchise?
        """
        
        result = await validate_with_llm(
            content=str(growth_rates),
            validation_criteria=validation_criteria,
            context="Franchise outlet growth analysis",
            client=client
        )
        
        return ValidationResult(
            is_valid=result.is_valid,
            errors=result.issues,
            warnings=result.suggestions,
            confidence=result.confidence
        )


# Example usage with Pydantic models
class ValidatedFranchiseFee(BaseModel):
    """Example of a model with LLM validation."""
    
    amount_cents: int = Field(..., ge=0)
    description: Annotated[
        str,
        BeforeValidator(
            create_llm_validator(
                "The description must clearly explain what the franchise fee covers, "
                "be professional, and contain at least 20 words"
            )
        )
    ]
    
    @field_validator("amount_cents")
    @classmethod
    def validate_amount(cls, v):
        error = FDDValidators.validate_franchise_fee(v)
        if error:
            raise ValueError(error)
        return v


# Validation decorator for methods
def validate_output(
    validation_criteria: str,
    client: Optional[InstructorClient] = None
):
    """Decorator to validate method output using LLM.
    
    Args:
        validation_criteria: What to validate in the output
        client: Optional InstructorClient instance
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Validate the result
            validation = await validate_with_llm(
                content=str(result),
                validation_criteria=validation_criteria,
                client=client
            )
            
            if not validation.is_valid:
                logger.warning(
                    f"Validation failed for {func.__name__}: {validation.issues}"
                )
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            # Run async validation in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                validation = loop.run_until_complete(
                    validate_with_llm(
                        content=str(result),
                        validation_criteria=validation_criteria,
                        client=client
                    )
                )
                
                if not validation.is_valid:
                    logger.warning(
                        f"Validation failed for {func.__name__}: {validation.issues}"
                    )
            finally:
                loop.close()
            
            return result
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator