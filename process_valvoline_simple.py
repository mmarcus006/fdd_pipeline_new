
"""
Simple script to demonstrate FDD processing pipeline on Valvoline PDF
without requiring full Prefect setup.
"""

import json
from pathlib import Path
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=" * 60)
    print("FDD Processing Pipeline - Valvoline Example")
    print("=" * 60)
    
    # Check if MinerU has already processed the file
    examples_dir = Path("examples")
    valvoline_pdf = examples_dir / "2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf"
    
    # MinerU output directory
    mineru_output = examples_dir / "2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3"
    
    if not valvoline_pdf.exists():
        print(f"ERROR: PDF file not found at {valvoline_pdf}")
        return
        
    print(f"\n[OK] Found Valvoline FDD PDF at: {valvoline_pdf}")
    print(f"  File size: {valvoline_pdf.stat().st_size / (1024*1024):.2f} MB")
    
    # Step 1: Document Layout Analysis (MinerU)
    print("\n" + "-" * 40)
    print("STEP 1: Document Layout Analysis")
    print("-" * 40)
    
    if mineru_output.exists():
        print("[OK] MinerU has already processed this document!")
        
        # Check what MinerU found
        full_md = mineru_output / "full.md"
        layout_json = mineru_output / "layout.json"
        content_list = mineru_output / "bc81f822-c13a-442d-8683-4566b67d255d_content_list.json"
        
        if full_md.exists():
            print(f"  - Full markdown export: {full_md}")
            # Read first 500 chars to show sample
            with open(full_md, 'r', encoding='utf-8') as f:
                sample = f.read(500)
                print(f"\n  Sample content:\n  {sample[:200]}...")
                
        if layout_json.exists():
            print(f"\n  - Layout analysis: {layout_json}")
            with open(layout_json, 'r', encoding='utf-8') as f:
                layout_data = json.load(f)
                print(f"    Total pages: {layout_data.get('total_pages', 'Unknown')}")
                
        if content_list.exists():
            print(f"\n  - Content structure: {content_list}")
            with open(content_list, 'r', encoding='utf-8') as f:
                content_data = json.load(f)
                print(f"    Total elements: {len(content_data)}")
                # Show types of content found
                content_types = {}
                for item in content_data:
                    ct = item.get('category_type', 'unknown')
                    content_types[ct] = content_types.get(ct, 0) + 1
                print("    Content types found:")
                for ct, count in sorted(content_types.items()):
                    print(f"      - {ct}: {count}")
    else:
        print("[X] MinerU output not found. Would need to run MinerU processing.")
        print("  Command: magic-pdf -p 'path/to/pdf' -o 'output/dir' -m auto")
        
    # Step 2: Section Detection
    print("\n" + "-" * 40)
    print("STEP 2: Section Detection")
    print("-" * 40)
    
    # Simulate section detection from the markdown
    if (mineru_output / "full.md").exists():
        with open(mineru_output / "full.md", 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Look for FDD sections
        sections_found = []
        section_keywords = [
            "Item 1:", "Item 2:", "Item 3:", "Item 4:", "Item 5:",
            "Item 6:", "Item 7:", "Item 8:", "Item 9:", "Item 10:",
            "Item 11:", "Item 12:", "Item 13:", "Item 14:", "Item 15:",
            "Item 16:", "Item 17:", "Item 18:", "Item 19:", "Item 20:",
            "Item 21:", "Item 22:", "Item 23:"
        ]
        
        for keyword in section_keywords:
            if keyword in content:
                sections_found.append(keyword)
                
        print(f"[OK] Found {len(sections_found)} FDD sections:")
        for section in sections_found[:10]:  # Show first 10
            print(f"  - {section}")
        if len(sections_found) > 10:
            print(f"  ... and {len(sections_found) - 10} more")
            
    # Step 3: High-Value Section Extraction
    print("\n" + "-" * 40)
    print("STEP 3: High-Value Section Extraction")
    print("-" * 40)
    
    print("Target sections for LLM extraction:")
    high_value_sections = {
        "Item 5:": "Initial Fees",
        "Item 6:": "Other Fees",
        "Item 7:": "Initial Investment",
        "Item 19:": "Financial Performance Representations",
        "Item 20:": "Outlets and Franchise Information",
        "Item 21:": "Financial Statements"
    }
    
    for item, description in high_value_sections.items():
        print(f"  - {item} {description}")
        
    # Show what would be extracted
    if (mineru_output / "full.md").exists():
        with open(mineru_output / "full.md", 'r', encoding='utf-8') as f:
            content = f.read()
            
        print("\nSample extraction from Item 7 (Initial Investment):")
        # Find Item 7 content
        item7_start = content.find("Item 7:")
        if item7_start > -1:
            item7_sample = content[item7_start:item7_start + 500]
            print(f"  {item7_sample}")
        else:
            print("  (Item 7 not found in processed content)")
            
    # Step 4: Data Structure
    print("\n" + "-" * 40)
    print("STEP 4: Expected Output Structure")
    print("-" * 40)
    
    sample_output = {
        "fdd_id": "uuid-here",
        "franchisor": "Valvoline Instant Oil Change",
        "sections_detected": 23,
        "extraction_results": {
            "item_5": {
                "initial_franchise_fee": 73750,
                "discounts": ["veteran", "conversion"],
                "payment_terms": "Due on signing"
            },
            "item_7": {
                "total_investment_low": 192375,
                "total_investment_high": 3483550,
                "categories": [
                    "Real Estate",
                    "Equipment",
                    "Initial Inventory",
                    "Working Capital"
                ]
            }
        }
    }
    
    print("Example output structure:")
    print(json.dumps(sample_output, indent=2))
    
    print("\n" + "=" * 60)
    print("Pipeline Demo Complete!")
    print("=" * 60)
    print("\nNOTE: This is a demonstration of the pipeline steps.")
    print("Full processing would require:")
    print("  1. Running MinerU for layout analysis")
    print("  2. Using LLMs (Gemini/OpenAI) for data extraction")
    print("  3. Storing results in Supabase database")
    print("  4. Uploading documents to Google Drive")

if __name__ == "__main__":
    main()