#!/usr/bin/env python3
"""
Demo script to process the Valvoline FDD through the complete pipeline.
This demonstrates each step using MinerU locally.
"""

import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime
import hashlib

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings
from utils.logging import get_logger
from tasks.document_processing import process_pdf_with_mineru_local
from tasks.document_segmentation import detect_fdd_sections
from tasks.llm_extraction import LLMExtractor
from models.fdd import FDDCreate
from models.franchisor import FranchisorCreate
from models.section import FDDSectionCreate
from utils.database import get_supabase_client

# Initialize logger
logger = get_logger(__name__)

async def main():
    """Process Valvoline FDD through complete pipeline."""
    
    # Setup
    settings = get_settings()
    pdf_path = Path("examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf")
    
    if not pdf_path.exists():
        logger.error(f"PDF not found at {pdf_path}")
        return
    
    logger.info(f"Starting pipeline for: {pdf_path.name}")
    
    # Step 1: Calculate document hash
    logger.info("Step 1: Calculating document hash...")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
        doc_hash = hashlib.sha256(pdf_bytes).hexdigest()
    logger.info(f"Document hash: {doc_hash}")
    
    # Step 2: Check for duplicates (simplified for demo)
    logger.info("Step 2: Checking for duplicates...")
    client = get_supabase_client()
    existing = client.table("fdds").select("id").eq("sha256_hash", doc_hash).execute()
    if existing.data:
        logger.warning("Document already exists in database!")
        # Continue anyway for demo
    
    # Step 3: Create franchisor record
    logger.info("Step 3: Creating franchisor record...")
    franchisor_data = FranchisorCreate(
        canonical_name="Valvoline Instant Oil Change",
        parent_company="Valvoline Inc.",
        dba_names=["VIOC", "Valvoline"]
    )
    
    # Insert franchisor (simplified - no dedup for demo)
    franchisor_response = client.table("franchisors").insert(
        franchisor_data.model_dump()
    ).execute()
    franchisor_id = franchisor_response.data[0]["id"]
    logger.info(f"Created franchisor: {franchisor_id}")
    
    # Step 4: Create FDD record
    logger.info("Step 4: Creating FDD record...")
    fdd_data = FDDCreate(
        franchise_id=franchisor_id,
        issue_date="2024-12-04",
        document_type="Initial",
        filing_state="WI",
        filing_number="32722-2024",
        drive_path=f"/fdds/raw/{pdf_path.name}",
        drive_file_id="demo-file-id",  # Would be real Google Drive ID
        sha256_hash=doc_hash,
        total_pages=300  # Approximate
    )
    
    fdd_response = client.table("fdds").insert(
        fdd_data.model_dump()
    ).execute()
    fdd_id = fdd_response.data[0]["id"]
    logger.info(f"Created FDD record: {fdd_id}")
    
    # Step 5: Process with MinerU (Local)
    logger.info("Step 5: Processing with MinerU locally...")
    logger.info(f"MinerU mode: {settings.mineru_mode}")
    logger.info(f"MinerU device: {settings.mineru_device}")
    logger.info(f"MinerU batch size: {settings.mineru_batch_size}")
    
    try:
        # Process PDF with MinerU
        mineru_result = await process_pdf_with_mineru_local(
            pdf_path=str(pdf_path),
            output_dir=f"output/{fdd_id}"
        )
        
        logger.info(f"MinerU processing complete. Sections found: {len(mineru_result.get('sections', []))}")
        
        # Save MinerU output
        output_dir = Path(f"output/{fdd_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(output_dir / "mineru_result.json", "w") as f:
            json.dump(mineru_result, f, indent=2)
        
        # Step 6: Detect FDD sections
        logger.info("Step 6: Detecting FDD sections...")
        sections = detect_fdd_sections(mineru_result)
        logger.info(f"Detected {len(sections)} FDD sections")
        
        # Create section records
        for section in sections:
            section_data = FDDSectionCreate(
                fdd_id=fdd_id,
                item_no=section.item_no,
                item_name=section.item_name,
                start_page=section.start_page,
                end_page=section.end_page,
                drive_path=f"/fdds/processed/{fdd_id}/section_{section.item_no:02d}.pdf",
                drive_file_id=f"section-{section.item_no}-demo"
            )
            
            section_response = client.table("fdd_sections").insert(
                section_data.model_dump()
            ).execute()
            section_id = section_response.data[0]["id"]
            logger.info(f"Created section {section.item_no}: {section_id}")
        
        # Step 7: Extract structured data (demo with Item 5)
        logger.info("Step 7: Extracting structured data with LLMs...")
        
        # Initialize LLM extractor
        extractor = LLMExtractor()
        
        # Get Item 5 content from MinerU markdown
        item5_content = mineru_result.get("markdown", "")
        # In real implementation, we'd extract just Item 5 content
        
        # Extract Item 5 fees
        from models.item5_fees_response import Item5FeesResponse
        
        try:
            logger.info("Extracting Item 5 (Initial Fees)...")
            item5_response = await extractor.extract_item_5(
                content=item5_content[:5000],  # First 5000 chars for demo
                franchise_name="Valvoline Instant Oil Change"
            )
            
            logger.info(f"Extracted initial franchise fee: ${item5_response.initial_franchise_fee:,.2f}")
            
            # Save extraction result
            with open(output_dir / "item5_extraction.json", "w") as f:
                f.write(item5_response.model_dump_json(indent=2))
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
        
        # Step 8: Summary
        logger.info("\n=== Pipeline Summary ===")
        logger.info(f"✓ Document hash calculated: {doc_hash[:16]}...")
        logger.info(f"✓ Franchisor created: {franchisor_id}")
        logger.info(f"✓ FDD record created: {fdd_id}")
        logger.info(f"✓ MinerU processing complete")
        logger.info(f"✓ {len(sections)} sections detected")
        logger.info(f"✓ LLM extraction attempted")
        logger.info(f"✓ Results saved to: output/{fdd_id}/")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())