"""Examples demonstrating the modern Instructor integration with FDD Pipeline.

This module shows various usage patterns for extracting structured data from
FDD documents using text, PDF files, and URLs.
"""

import asyncio
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

# Import our modules
from utils.instructor_client import InstructorClient, ExtractionConfig, LLMProvider
from utils.multimodal_processor import MultimodalProcessor
from utils.llm_validation import (
    FDDValidators,
    create_llm_validator,
    validate_with_llm,
    CrossFieldValidator,
)
from models.item5_fees import Item5FeesResponse
from models.item20_outlets import Item20OutletsResponse


# Example 1: Simple Text Extraction
class FranchiseFee(BaseModel):
    """Simple model for extracting franchise fee information."""

    amount_dollars: int = Field(..., description="The franchise fee amount in dollars")
    payment_terms: str = Field(..., description="When and how the fee is paid")
    refundable: bool = Field(..., description="Whether the fee is refundable")

    @field_validator("amount_dollars")
    @classmethod
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError("Amount cannot be negative")
        if v > 1_000_000:
            raise ValueError("Amount seems unreasonably high")
        return v


async def example_text_extraction():
    """Example of extracting structured data from text."""
    print("\n=== Example 1: Simple Text Extraction ===")

    # Sample text from an FDD
    text = """
    The initial franchise fee is $45,000, which is due upon signing the 
    franchise agreement. This fee is fully earned by us when paid and is 
    not refundable under any circumstances. The fee covers our initial 
    training program, site selection assistance, and grand opening support.
    """

    # Create client
    client = InstructorClient(primary_provider=LLMProvider.GEMINI)

    # Extract structured data
    result = await client.extract_from_text(
        text=text,
        response_model=FranchiseFee,
        system_prompt="Extract the franchise fee information from this FDD excerpt.",
    )

    print(f"Extracted data: {result.data}")
    print(f"Provider used: {result.provider_used}")
    print(f"Validation passed: {result.validation_passed}")

    return result.data


# Example 2: Complex Model with Validation
class ValidatedFranchiseInfo(BaseModel):
    """Model with semantic LLM validation."""

    franchise_name: str = Field(..., min_length=2)
    business_description: str = Field(..., min_length=50)
    initial_investment_min: int = Field(..., ge=0)
    initial_investment_max: int = Field(..., ge=0)

    # Use LLM validation for business description
    @field_validator("business_description")
    @classmethod
    def validate_description(cls, v, info):
        # This would use LLM validation in practice
        if len(v) < 50:
            raise ValueError("Business description too short")
        if "franchise" not in v.lower():
            raise ValueError("Business description should mention franchise")
        return v

    @field_validator("initial_investment_max")
    @classmethod
    def validate_investment_range(cls, v, info):
        if "initial_investment_min" in info.data:
            if v < info.data["initial_investment_min"]:
                raise ValueError("Max investment cannot be less than min investment")
        return v


async def example_complex_extraction_with_validation():
    """Example with complex validation including semantic checks."""
    print("\n=== Example 2: Complex Extraction with Validation ===")

    text = """
    McDonald's Corporation is one of the world's leading quick-service 
    restaurant franchises, operating and franchising McDonald's restaurants. 
    The restaurants serve a varied menu at affordable prices in more than 
    100 countries globally. Our franchisees operate their businesses under 
    the McDonald's system, which has been refined over decades.
    
    The estimated initial investment ranges from $1,366,000 to $2,450,000,
    depending on the restaurant size, location, and other factors.
    """

    client = InstructorClient()
    config = ExtractionConfig(temperature=0.1, validation_retries=3)

    result = await client.extract_from_text(
        text=text,
        response_model=ValidatedFranchiseInfo,
        config=config,
        system_prompt="Extract franchise information including name, description, and investment range.",
    )

    print(f"Franchise: {result.data.franchise_name}")
    print(
        f"Investment range: ${result.data.initial_investment_min:,} - ${result.data.initial_investment_max:,}"
    )
    print(f"Validation errors: {result.validation_errors}")

    # Additional semantic validation
    validation_result = await FDDValidators.validate_business_description(
        result.data.business_description, result.data.franchise_name
    )
    print(f"Semantic validation passed: {validation_result.is_valid}")
    if validation_result.suggestions:
        print(f"Suggestions: {validation_result.suggestions}")

    return result.data


# Example 3: PDF File Processing
async def example_pdf_extraction():
    """Example of extracting from a PDF file."""
    print("\n=== Example 3: PDF File Extraction ===")

    # This would use an actual PDF file
    pdf_path = Path("sample_fdd_section.pdf")

    # Check if file exists (for demo purposes)
    if not pdf_path.exists():
        print(f"Skipping PDF example - file not found: {pdf_path}")
        return None

    # Process PDF file
    processor = MultimodalProcessor()
    processed = await processor.process_file(
        pdf_path, extract_text=True, chunk_size=10  # 10 pages per chunk for large PDFs
    )

    print(f"PDF processed: {processed.page_count} pages")
    print(f"File size: {processed.size_bytes / 1024 / 1024:.2f} MB")

    # Extract using the actual Item5 model
    client = InstructorClient()

    # If file was uploaded to Gemini
    if processed.gemini_file:
        content = processor.prepare_content_for_llm(processed)

        result = await client.extract_from_text(
            text=str(content),  # Convert to string for compatibility
            response_model=Item5FeesResponse,
            system_prompt="Extract all fee information from this FDD Item 5 section.",
        )

        print(
            f"Initial franchise fee: ${result.data.initial_franchise_fee_cents / 100:,.2f}"
        )
        print(f"Additional fees: {len(result.data.additional_fees)}")

        # Validate extraction
        validation_errors = result.data.validate_extraction()
        if validation_errors:
            print(f"Validation issues: {validation_errors}")

    return processed


# Example 4: URL-based Extraction
async def example_url_extraction():
    """Example of extracting from a URL."""
    print("\n=== Example 4: URL-based Extraction ===")

    # Example URL (would be a real FDD PDF in practice)
    url = "https://example.com/sample-fdd.pdf"

    try:
        async with MultimodalProcessor() as processor:
            processed = await processor.process_url(url)

            print(f"Downloaded and processed from URL")
            print(f"File type: {processed.file_type}")

            # Extract data
            client = InstructorClient()

            if processed.extracted_text:
                result = await client.extract_from_text(
                    text=processed.extracted_text[:5000],  # First 5000 chars
                    response_model=FranchiseFee,
                    system_prompt="Extract franchise fee information.",
                )

                print(f"Extracted fee: ${result.data.amount_dollars:,}")

    except Exception as e:
        print(f"URL extraction failed (expected for demo): {e}")


# Example 5: Multi-section Extraction with Fallback
async def example_multi_section_extraction():
    """Example of extracting multiple sections with provider fallback."""
    print("\n=== Example 5: Multi-section Extraction with Fallback ===")

    # Sample data for multiple sections
    sections = {
        5: """Initial franchise fee is $50,000 payable on signing. 
              Veterans receive a 10% discount. Fee is non-refundable.""",
        20: """Outlet Summary for 2021-2023:
               2021: Started with 100 franchised, opened 20, closed 5, ended with 115
               2022: Started with 115 franchised, opened 25, closed 3, ended with 137
               2023: Started with 137 franchised, opened 30, closed 2, ended with 165""",
    }

    client = InstructorClient(primary_provider=LLMProvider.GEMINI)

    results = {}

    for item_no, text in sections.items():
        print(f"\nProcessing Item {item_no}...")

        # Use appropriate model based on section
        if item_no == 5:
            response_model = Item5FeesResponse
            system_prompt = "Extract all fee information from this FDD Item 5."
        elif item_no == 20:
            response_model = Item20OutletsResponse
            system_prompt = "Extract outlet statistics from this FDD Item 20."
        else:
            continue

        # Extract with fallback
        try:
            result = await client.extract_with_fallback(
                content=text,
                response_model=response_model,
                system_prompt=system_prompt,
                mode="text",
            )

            results[item_no] = result
            print(f"Successfully extracted with {result.provider_used}")

            # Validate
            if hasattr(result.data, "validate_extraction"):
                errors = result.data.validate_extraction()
                if errors:
                    print(f"Validation errors: {errors}")

        except Exception as e:
            print(f"Failed to extract Item {item_no}: {e}")

    return results


# Example 6: Batch Processing with Chunks
async def example_batch_chunk_processing():
    """Example of processing large PDFs in chunks."""
    print("\n=== Example 6: Batch Processing with Chunks ===")

    # Simulate chunks from a large PDF
    chunks = [
        "Page 1-10: Franchise overview and initial fees...",
        "Page 11-20: Territory rights and obligations...",
        "Page 21-30: Training and support programs...",
    ]

    client = InstructorClient()

    # Simple model for chunk summaries
    class ChunkSummary(BaseModel):
        pages: str
        key_topics: List[str]
        has_fee_information: bool
        summary: str

    summaries = []

    for i, chunk_text in enumerate(chunks):
        print(f"\nProcessing chunk {i+1}/{len(chunks)}...")

        result = await client.extract_from_text(
            text=chunk_text,
            response_model=ChunkSummary,
            system_prompt="Summarize this section of the FDD document.",
        )

        summaries.append(result.data)
        print(f"Key topics: {', '.join(result.data.key_topics)}")

    return summaries


# Main function to run all examples
async def main():
    """Run all examples."""
    print("=== FDD Instructor Integration Examples ===")
    print(f"Running at: {datetime.now()}")

    # Run examples
    await example_text_extraction()
    await example_complex_extraction_with_validation()
    await example_pdf_extraction()
    await example_url_extraction()
    await example_multi_section_extraction()
    await example_batch_chunk_processing()

    print("\n=== All examples completed ===")


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
