# MinerU Integration API Reference

## Overview

This document provides a comprehensive API reference for integrating MinerU (magic-pdf) into the FDD Pipeline. MinerU is used locally for high-performance PDF processing, layout analysis, and content extraction.

## Core Components

### UNIPipe Class

The main pipeline class for processing PDFs with MinerU.

```python
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

# Initialize pipeline
pipe = UNIPipe(
    pdf_bytes: bytes,           # PDF file content
    jso_useful_key: dict,       # Configuration dictionary
    image_writer: DiskReaderWriter  # Image output handler
)
```

#### Methods

##### pipe_classify()
Classifies the PDF document type (text, scan, or mixed).

```python
pipe.pipe_classify()
# Sets internal state for optimal processing strategy
```

##### pipe_analyze()
Analyzes document layout structure (available in v0.7.0+).

```python
pipe.pipe_analyze()
# Performs deep learning-based layout analysis
```

##### pipe_parse()
Parses the PDF content and extracts structured data.

```python
pipe.pipe_parse()
# Extracts text, tables, figures, and formulas
```

##### pipe_mk_markdown()
Generates markdown output with embedded images.

```python
markdown_content = pipe.pipe_mk_markdown(
    image_dir: str,             # Relative path to images
    drop_mode: str = "none"     # Options: "none", "all", "partial"
)
```

### DiskReaderWriter Class

Handles local file I/O for images extracted during processing.

```python
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

# Initialize for local storage
image_writer = DiskReaderWriter(
    path: str  # Local directory path for images
)
```

## Integration Patterns

### Basic PDF Processing

```python
import os
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

def process_pdf(pdf_path: str, output_dir: str) -> dict:
    """
    Process a PDF file with MinerU.
    
    Args:
        pdf_path: Path to input PDF
        output_dir: Directory for output files
        
    Returns:
        Dictionary with markdown content and metadata
    """
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    image_dir = os.path.join(output_dir, "images")
    os.makedirs(image_dir, exist_ok=True)
    
    # Initialize image writer
    image_writer = DiskReaderWriter(image_dir)
    
    # Read PDF
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    
    # Configure pipeline
    config = {
        "_pdf_type": "",  # Auto-detect
        "model_list": []  # Use default models
    }
    
    # Process
    pipe = UNIPipe(pdf_bytes, config, image_writer)
    pipe.pipe_classify()
    
    # Use analyze step if available (v0.7.0+)
    if hasattr(pipe, 'pipe_analyze'):
        pipe.pipe_analyze()
    
    pipe.pipe_parse()
    
    # Generate outputs
    markdown = pipe.pipe_mk_markdown(
        os.path.basename(image_dir),
        drop_mode="none"
    )
    
    # Get additional metadata if available
    metadata = {}
    if hasattr(pipe, 'get_layout_data'):
        metadata['layout'] = pipe.get_layout_data()
    if hasattr(pipe, 'get_json_content'):
        metadata['json'] = pipe.get_json_content()
    
    return {
        'markdown': markdown,
        'metadata': metadata,
        'image_dir': image_dir
    }
```

### Prefect Task Integration

```python
from prefect import task, flow
from typing import Optional
import os

@task(
    name="process_pdf_mineru",
    retries=2,
    retry_delay_seconds=30,
    timeout_seconds=300
)
def process_pdf_with_mineru(
    pdf_path: str,
    fdd_id: str,
    use_gpu: bool = True
) -> dict:
    """
    Prefect task for processing PDFs with MinerU.
    
    Args:
        pdf_path: Path to PDF file
        fdd_id: FDD identifier for output organization
        use_gpu: Whether to use GPU acceleration
        
    Returns:
        Processing results including sections and layout data
    """
    # Set device mode
    os.environ['MINERU_DEVICE'] = 'cuda' if use_gpu else 'cpu'
    
    # Import here to respect environment variable
    from magic_pdf.pipe.UNIPipe import UNIPipe
    from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
    
    output_dir = f"processed/{fdd_id}"
    result = process_pdf(pdf_path, output_dir)
    
    # Extract sections from layout
    sections = extract_fdd_sections(result['metadata'].get('layout', {}))
    
    return {
        'fdd_id': fdd_id,
        'sections': sections,
        'markdown': result['markdown'],
        'output_dir': output_dir
    }

@flow(name="fdd_processing_flow")
def process_fdd_batch(fdd_list: list[dict]):
    """Process multiple FDDs in parallel."""
    results = []
    
    for fdd in fdd_list:
        result = process_pdf_with_mineru(
            pdf_path=fdd['path'],
            fdd_id=fdd['id'],
            use_gpu=True
        )
        results.append(result)
    
    return results
```

### Advanced Configuration

```python
def create_mineru_config(
    device: str = "cuda",
    batch_size: int = 2,
    enable_ocr: bool = True,
    enable_formula: bool = True,
    enable_table: bool = True
) -> dict:
    """
    Create MinerU configuration with custom settings.
    
    Args:
        device: "cuda" or "cpu"
        batch_size: Batch size for GPU processing
        enable_ocr: Enable OCR for scanned documents
        enable_formula: Enable formula detection
        enable_table: Enable table extraction
        
    Returns:
        Configuration dictionary
    """
    # Set environment variables
    os.environ['MINERU_DEVICE'] = device
    os.environ['MINERU_BATCH_SIZE'] = str(batch_size)
    
    # Create config structure
    config = {
        "_pdf_type": "",
        "model_list": [],
        "device": device,
        "batch_size": batch_size,
        "parse_config": {
            "ocr": enable_ocr,
            "formula": enable_formula,
            "table": enable_table
        }
    }
    
    return config
```

### Error Handling and Fallbacks

```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def process_pdf_with_fallback(
    pdf_path: str,
    output_dir: str,
    max_retries: int = 3
) -> Optional[dict]:
    """
    Process PDF with automatic GPU/CPU fallback.
    
    Args:
        pdf_path: Input PDF path
        output_dir: Output directory
        max_retries: Maximum retry attempts
        
    Returns:
        Processing results or None if all attempts fail
    """
    devices = ['cuda', 'cpu']  # Try GPU first, then CPU
    
    for device in devices:
        for attempt in range(max_retries):
            try:
                logger.info(f"Processing with {device}, attempt {attempt + 1}")
                os.environ['MINERU_DEVICE'] = device
                
                # Force reimport to pick up new device setting
                import importlib
                import magic_pdf.pipe.UNIPipe
                importlib.reload(magic_pdf.pipe.UNIPipe)
                
                result = process_pdf(pdf_path, output_dir)
                logger.info(f"Successfully processed with {device}")
                return result
                
            except RuntimeError as e:
                if "out of memory" in str(e).lower() and device == 'cuda':
                    logger.warning("GPU out of memory, trying CPU mode")
                    break  # Try CPU
                    
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt == max_retries - 1:
                    break
    
    logger.error("All processing attempts failed")
    return None
```

### Batch Processing with Memory Management

```python
import gc
import torch
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict

def process_pdf_batch(
    pdf_paths: List[str],
    output_base_dir: str,
    max_workers: int = 2,
    gpu_per_worker: float = 0.5
) -> List[Dict]:
    """
    Process multiple PDFs in parallel with memory management.
    
    Args:
        pdf_paths: List of PDF file paths
        output_base_dir: Base directory for outputs
        max_workers: Number of parallel workers
        gpu_per_worker: GPU memory fraction per worker
        
    Returns:
        List of processing results
    """
    def process_single(args):
        pdf_path, output_dir, worker_id = args
        
        # Set GPU for this worker
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            device_id = worker_id % device_count
            os.environ['CUDA_VISIBLE_DEVICES'] = str(device_id)
            
        # Set memory fraction
        os.environ['PYTORCH_CUDA_ALLOC_CONF'] = f'max_split_size_mb:512'
        
        try:
            result = process_pdf(pdf_path, output_dir)
            
            # Clear GPU memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
            return {'success': True, 'result': result, 'path': pdf_path}
            
        except Exception as e:
            return {'success': False, 'error': str(e), 'path': pdf_path}
        
        finally:
            # Force garbage collection
            gc.collect()
    
    # Prepare arguments
    args_list = []
    for i, pdf_path in enumerate(pdf_paths):
        output_dir = os.path.join(
            output_base_dir,
            f"pdf_{i:04d}"
        )
        args_list.append((pdf_path, output_dir, i))
    
    # Process in parallel
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single, args_list))
    
    return results
```

### FDD-Specific Section Extraction

```python
from typing import List, Dict
import re

def extract_fdd_sections(layout_data: dict) -> List[Dict]:
    """
    Extract FDD sections from MinerU layout analysis.
    
    Args:
        layout_data: Layout data from MinerU
        
    Returns:
        List of detected sections with metadata
    """
    sections = []
    
    # Pattern for FDD items
    item_pattern = re.compile(
        r'^\s*(?:ITEM|Item)\s+(\d+)[:\.]?\s*(.+)?',
        re.IGNORECASE | re.MULTILINE
    )
    
    # Process each block
    for block in layout_data.get('blocks', []):
        if block['type'] in ['title', 'header']:
            text = block.get('text', '')
            match = item_pattern.match(text)
            
            if match:
                item_number = int(match.group(1))
                item_title = match.group(2) or ''
                
                sections.append({
                    'item_number': item_number,
                    'title': item_title.strip(),
                    'page_number': block['page_no'],
                    'bbox': block.get('bbox', []),
                    'confidence': block.get('confidence', 0.0)
                })
    
    # Sort by item number
    sections.sort(key=lambda x: x['item_number'])
    
    # Fill in page ranges
    for i, section in enumerate(sections):
        if i < len(sections) - 1:
            section['end_page'] = sections[i + 1]['page_number'] - 1
        else:
            section['end_page'] = layout_data.get('total_pages', section['page_number'])
    
    return sections
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `MINERU_DEVICE` | Processing device | `cuda` | `cuda`, `cpu` |
| `MINERU_BATCH_SIZE` | Batch size for GPU | `2` | `1-8` |
| `MINERU_MODEL_PATH` | Model directory | `~/.mineru/models` | Any valid path |
| `MINERU_MAX_PAGES` | Max pages to process | `500` | Any integer |
| `MINERU_ENABLE_OCR` | Enable OCR | `true` | `true`, `false` |

### Configuration File (magic-pdf.json)

```json
{
    "models-dir": "~/.mineru/models",
    "device-mode": "cuda",
    "layout-config": {
        "model": "doclayout_yolo",
        "confidence_threshold": 0.5
    },
    "formula-config": {
        "mfd_model": "yolo_v8_mfd",
        "mfr_model": "unimernet_small",
        "enable": true
    },
    "table-config": {
        "model": "rapid_table",
        "sub_model": "slanet_plus",
        "enable": true,
        "max_time": 400
    },
    "ocr-config": {
        "lang": "en",
        "det_model": "en_PP-OCRv4_det",
        "rec_model": "en_PP-OCRv4_rec"
    }
}
```

## Performance Optimization

### GPU Memory Management

```python
def optimize_gpu_memory():
    """Optimize GPU memory usage for MinerU."""
    if torch.cuda.is_available():
        # Clear cache
        torch.cuda.empty_cache()
        
        # Set memory fraction
        torch.cuda.set_per_process_memory_fraction(0.8)
        
        # Enable memory efficient mode
        os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'
        
        # Reduce batch size for large documents
        os.environ['MINERU_BATCH_SIZE'] = '1'
```

### Processing Speed Optimization

```python
def configure_for_speed():
    """Configure MinerU for maximum speed."""
    config = {
        # Use fastest layout model
        "layout-config": {
            "model": "doclayout_yolo"
        },
        # Disable optional features for speed
        "formula-config": {
            "enable": False  # Disable if not needed
        },
        # Use faster table model
        "table-config": {
            "model": "rapid_table",
            "enable": True
        }
    }
    return config
```

## Testing

### Unit Test Example

```python
import pytest
from unittest.mock import Mock, patch
import os

@pytest.fixture
def mock_mineru():
    """Mock MinerU for testing."""
    with patch('magic_pdf.pipe.UNIPipe.UNIPipe') as mock:
        instance = Mock()
        instance.pipe_mk_markdown.return_value = "# Test Content"
        mock.return_value = instance
        yield mock

def test_process_pdf(mock_mineru, tmp_path):
    """Test PDF processing."""
    # Create test PDF
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"fake pdf content")
    
    # Process
    result = process_pdf(
        str(test_pdf),
        str(tmp_path / "output")
    )
    
    # Verify
    assert result['markdown'] == "# Test Content"
    assert mock_mineru.called
```

### Integration Test

```python
def test_mineru_integration():
    """Test actual MinerU integration."""
    # Download small test PDF
    test_pdf_url = "https://arxiv.org/pdf/2308.00352.pdf"
    test_pdf_path = "test_integration.pdf"
    
    # Download file
    import urllib.request
    urllib.request.urlretrieve(test_pdf_url, test_pdf_path)
    
    try:
        # Process with MinerU
        result = process_pdf(test_pdf_path, "test_output")
        
        # Verify results
        assert result['markdown'] is not None
        assert len(result['markdown']) > 100
        assert os.path.exists("test_output/images")
        
    finally:
        # Cleanup
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)
        if os.path.exists("test_output"):
            import shutil
            shutil.rmtree("test_output")
```

## Troubleshooting

For common issues and solutions, see the [Troubleshooting Guide](../04_operations/troubleshooting.md#7-mineru-processing-issues).

## Further Reading

- [MinerU GitHub Repository](https://github.com/opendatalab/MinerU)
- [MinerU Documentation](https://mineru.readthedocs.io/)
- [Technology Decisions](../01_architecture/technology_decisions.md#document-processing)
- [Setup Guide](../03_implementation/setup_guide.md#33-mineru-local-setup)