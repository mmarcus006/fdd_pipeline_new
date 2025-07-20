#!/usr/bin/env python
"""
JSON Schema Generator using Genson

This script generates JSON schemas from JSON files using the genson library.
Useful for understanding the structure of complex JSON data.
"""

import json
import sys
import os
import time
import logging
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from genson import SchemaBuilder
except ImportError:
    print("Error: genson library not installed. Run: pip install genson")
    sys.exit(1)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from utils.logging import get_logger
    logger = get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


def analyze_json_structure(json_data: Any) -> Dict[str, Any]:
    """Analyze JSON structure and return statistics."""
    stats = {
        "type": type(json_data).__name__,
        "size_bytes": len(json.dumps(json_data)),
    }
    
    if isinstance(json_data, dict):
        stats["keys"] = len(json_data)
        stats["top_level_keys"] = list(json_data.keys())[:10]  # First 10 keys
    elif isinstance(json_data, list):
        stats["items"] = len(json_data)
        if json_data:
            stats["first_item_type"] = type(json_data[0]).__name__
    
    return stats


def generate_schema_with_genson(
    input_path: Path, 
    output_path: Optional[Path] = None,
    merge_arrays: bool = True,
    add_descriptions: bool = False
) -> Dict[str, Any]:
    """
    Generates a JSON schema from a file using the genson library.

    Args:
        input_path: The path to the input JSON file.
        output_path: The path where the generated schema will be saved (optional).
        merge_arrays: Whether to merge array schemas (default: True).
        add_descriptions: Whether to add placeholder descriptions (default: False).
        
    Returns:
        The generated schema as a dictionary.
    """
    start_time = time.time()
    logger.debug(f"Starting schema generation for: {input_path}")
    
    try:
        # Check file exists and size
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
            
        file_size = input_path.stat().st_size / (1024 * 1024)  # MB
        logger.debug(f"Input file size: {file_size:.2f} MB")
        
        if file_size > 100:
            logger.warning(f"Large file detected ({file_size:.2f} MB), this may take a while...")
        
        # Read JSON file
        logger.info(f"Reading input file: {input_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        
        read_time = time.time() - start_time
        logger.debug(f"File read in {read_time:.2f}s")
        
        # Analyze structure
        stats = analyze_json_structure(json_data)
        logger.debug(f"JSON structure: {stats}")
        
        # Create SchemaBuilder with options
        builder = SchemaBuilder()
        builder.add_schema({"type": "object"})  # Default to object type
        
        # Configure builder options
        if merge_arrays:
            logger.debug("Array merging enabled")
        
        # Add the JSON object to builder
        logger.info("Analyzing JSON structure...")
        schema_start = time.time()
        
        if isinstance(json_data, list):
            # For arrays, analyze all items
            logger.debug(f"Processing array with {len(json_data)} items")
            for i, item in enumerate(json_data):
                builder.add_object(item)
                if i % 100 == 0 and i > 0:
                    logger.debug(f"Processed {i}/{len(json_data)} items")
        else:
            builder.add_object(json_data)
        
        # Generate the final schema
        generated_schema = builder.to_schema()
        
        schema_time = time.time() - schema_start
        logger.debug(f"Schema generated in {schema_time:.2f}s")
        
        # Add metadata
        generated_schema["$id"] = f"file:///{input_path.name}"
        generated_schema["title"] = f"Schema for {input_path.stem}"
        generated_schema["description"] = f"Auto-generated schema from {input_path.name}"
        
        if add_descriptions:
            logger.debug("Adding placeholder descriptions to schema")
            _add_descriptions(generated_schema)
        
        # Write schema if output path provided
        if output_path:
            logger.info(f"Writing schema to: {output_path}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(generated_schema, f, indent=2)
            
            output_size = output_path.stat().st_size / 1024  # KB
            logger.debug(f"Schema file size: {output_size:.2f} KB")
            
            print(f"✓ Schema saved to: {output_path}")
        
        total_time = time.time() - start_time
        logger.info(f"Schema generation completed in {total_time:.2f}s")
        
        # Log schema summary
        logger.debug(f"Schema properties: {len(generated_schema.get('properties', {}))}")
        logger.debug(f"Required fields: {len(generated_schema.get('required', []))}")
        
        return generated_schema

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON file: {e}")
        logger.debug(f"Error at line {e.lineno}, column {e.colno}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        raise


def _add_descriptions(schema: Dict[str, Any], path: str = ""):
    """Recursively add placeholder descriptions to schema properties."""
    if "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            current_path = f"{path}.{prop_name}" if path else prop_name
            if "description" not in prop_schema:
                prop_schema["description"] = f"TODO: Add description for {current_path}"
            _add_descriptions(prop_schema, current_path)
    
    if "items" in schema:
        _add_descriptions(schema["items"], f"{path}[]")


def batch_process(input_dir: Path, output_dir: Path, pattern: str = "*.json") -> None:
    """Process multiple JSON files in a directory."""
    logger.info(f"Batch processing JSON files in: {input_dir}")
    logger.debug(f"File pattern: {pattern}")
    
    json_files = list(input_dir.glob(pattern))
    logger.info(f"Found {len(json_files)} JSON files to process")
    
    if not json_files:
        logger.warning("No JSON files found matching pattern")
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    error_count = 0
    
    for i, json_file in enumerate(json_files, 1):
        logger.info(f"Processing file {i}/{len(json_files)}: {json_file.name}")
        
        try:
            output_file = output_dir / f"{json_file.stem}_schema.json"
            generate_schema_with_genson(json_file, output_file)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to process {json_file.name}: {e}")
            error_count += 1
    
    logger.info(f"Batch processing complete: {success_count} successful, {error_count} failed")
    print(f"\nBatch processing complete:")
    print(f"  ✓ Successful: {success_count}")
    print(f"  ✗ Failed: {error_count}")


def main():
    """Main function to handle command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate JSON Schema from JSON files using Genson",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate schema for a single file
  %(prog)s input.json
  
  # Generate schema and save to specific location
  %(prog)s input.json --output schema.json
  
  # Add placeholder descriptions
  %(prog)s input.json --add-descriptions
  
  # Batch process all JSON files in a directory
  %(prog)s --batch input_dir/ --output-dir schemas/
  
  # Enable debug logging
  %(prog)s input.json --debug
  
  # Process with custom pattern
  %(prog)s --batch logs/ --pattern "*_response.json" --output-dir schemas/
        """
    )
    
    # Input arguments
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Input JSON file path"
    )
    
    # Output arguments
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output schema file path (default: input_schema.json)"
    )
    
    # Batch processing
    parser.add_argument(
        "--batch", "-b",
        type=Path,
        help="Process all JSON files in directory"
    )
    
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("schemas"),
        help="Output directory for batch processing (default: schemas/)"
    )
    
    parser.add_argument(
        "--pattern", "-p",
        default="*.json",
        help="File pattern for batch processing (default: *.json)"
    )
    
    # Options
    parser.add_argument(
        "--add-descriptions",
        action="store_true",
        help="Add placeholder descriptions to schema properties"
    )
    
    parser.add_argument(
        "--no-merge-arrays",
        action="store_true",
        help="Disable array schema merging"
    )
    
    parser.add_argument(
        "--pretty", "-P",
        action="store_true",
        help="Pretty print schema to console"
    )
    
    # Logging options
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'genson_schema_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        logger.debug("Debug logging enabled")
    elif args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    logger.debug(f"Script started with arguments: {vars(args)}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Python version: {sys.version}")
    
    try:
        # Validate arguments
        if not args.input and not args.batch:
            parser.error("Either input file or --batch must be specified")
        
        if args.input and args.batch:
            parser.error("Cannot specify both input file and --batch")
        
        # Process based on mode
        if args.batch:
            # Batch processing mode
            if not args.batch.exists():
                logger.error(f"Batch directory not found: {args.batch}")
                sys.exit(1)
            
            if not args.batch.is_dir():
                logger.error(f"Batch path is not a directory: {args.batch}")
                sys.exit(1)
            
            print(f"Batch processing JSON files in: {args.batch}")
            batch_process(args.batch, args.output_dir, args.pattern)
            
        else:
            # Single file mode
            if not args.input.exists():
                logger.error(f"Input file not found: {args.input}")
                sys.exit(1)
            
            # Determine output path
            if args.output:
                output_path = args.output
            else:
                output_path = args.input.parent / f"{args.input.stem}_schema.json"
            
            print(f"Generating schema for: {args.input}")
            
            # Generate schema
            schema = generate_schema_with_genson(
                args.input,
                output_path if not args.pretty else None,
                merge_arrays=not args.no_merge_arrays,
                add_descriptions=args.add_descriptions
            )
            
            # Pretty print if requested
            if args.pretty:
                print("\nGenerated Schema:")
                print("-" * 40)
                print(json.dumps(schema, indent=2))
                
                if args.output:
                    # Also save to file
                    with open(args.output, "w", encoding="utf-8") as f:
                        json.dump(schema, f, indent=2)
                    print(f"\n✓ Schema also saved to: {args.output}")
            
            print("\n✓ Schema generation complete!")
            
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        print("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
