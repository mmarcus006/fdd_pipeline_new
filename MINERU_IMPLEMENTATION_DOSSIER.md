---
title: "MinerU (magic-pdf) — Implementation Cheat-Sheet"
sections:
  - Overview
  - Installation
  - Quick Start
  - Core API Map
  - Extended Recipes
  - Best Practices
  - Troubleshooting FAQ
  - Edge Cases & Pitfalls
  - Version Matrix
  - Further Reading
metadata:
  lib: MinerU (magic-pdf)
  latest_version: 1.3.12
  generated: 2025-07-16T00:00:00Z
  mcp_sources: [websearch, task]
---

# MinerU (magic-pdf) — Implementation Cheat-Sheet

## Overview

MinerU is a high-quality, GPU-accelerated tool for converting PDF documents to Markdown and JSON formats, preserving document structure while removing distracting elements like headers and footers.

## Installation

### System Requirements
- **GPU**: NVIDIA GPU with Turing architecture or newer (GTX 1060+, 8GB+ VRAM recommended)
- **RAM**: 16GB minimum, 32GB+ recommended  
- **Storage**: 20GB+ free space (15GB for models)
- **Python**: 3.10-3.13
- **CUDA**: Compatible version for GPU acceleration

### Installation Commands
```bash
# Create environment (recommended)
conda create -n MinerU python=3.10
conda activate MinerU

# Install with GPU support (using UV as per project)
uv pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com

# CPU-only version
uv pip install magic-pdf

# Download models (~15GB, one-time setup)
magic-pdf model-download

# Optional: Install PaddlePaddle for OCR acceleration
pip install paddlepaddle-gpu==3.0.0b1 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
```

### Environment Variables
```bash
# Used in this project (see config.py)
MINERU_MODEL_PATH=~/.mineru/models  # Model storage location
MINERU_DEVICE=cuda                  # or 'cpu' for CPU-only mode
MINERU_BATCH_SIZE=2                 # Adjust based on GPU memory
```

## Quick Start

```python
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
import os

# Setup
local_image_dir = "./output/images"
image_writer = DiskReaderWriter(local_image_dir)

# Read PDF
with open("document.pdf", "rb") as f:
    pdf_bytes = f.read()

# Process
pipe = UNIPipe(pdf_bytes, {"_pdf_type": "", "model_list": []}, image_writer)
pipe.pipe_classify()
pipe.pipe_analyze()  # Added in v0.7.0+
pipe.pipe_parse()
md_content = pipe.pipe_mk_markdown(os.path.basename(local_image_dir), drop_mode="none")

print(md_content)
```

## Core API Map

| Class/Function | Purpose | Version Notes |
|----------------|---------|---------------|
| `UNIPipe` | Main pipeline for PDF processing | Core class |
| `OCRPipe` | OCR-specific pipeline | For scanned PDFs |
| `TXTPipe` | Text-only pipeline | For text PDFs |
| `DiskReaderWriter` | Local file I/O handler | Default storage |
| `S3ReaderWriter` | S3 storage handler | Cloud storage option |
| `pipe_classify()` | Classify PDF type | Step 1 |
| `pipe_analyze()` | Analyze document structure | Added in v0.7.0+ |
| `pipe_parse()` | Parse PDF content | Step 3 |
| `pipe_mk_markdown()` | Generate markdown output | Final step |

### CLI Commands
```bash
# Basic conversion
magic-pdf -p input.pdf -o output/ -m auto

# With language specification
magic-pdf -p input.pdf -o output/ -m auto --lang ch

# Batch processing
magic-pdf -p pdf_directory/ -o output/ -m auto

# Note: CLI changing from 'magic-pdf' to 'mineru' in newer versions
```

## Extended Recipes

### Recipe 1: Complete PDF Processing with Error Handling
```python
# Source: Adapted from MinerU documentation
import os
from loguru import logger
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

def process_pdf_with_fallback(pdf_path: str, output_dir: str):
    """Process PDF with GPU/CPU fallback"""
    try:
        # Setup output directories
        os.makedirs(output_dir, exist_ok=True)
        image_dir = os.path.join(output_dir, "images")
        os.makedirs(image_dir, exist_ok=True)
        
        # Initialize writer
        image_writer = DiskReaderWriter(image_dir)
        
        # Read PDF
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        # Configuration with model detection
        config = {
            "_pdf_type": "",
            "model_list": [],
            "device": os.getenv("MINERU_DEVICE", "cuda")
        }
        
        # Process
        pipe = UNIPipe(pdf_bytes, config, image_writer)
        pipe.pipe_classify()
        
        # Check if newer version
        if hasattr(pipe, 'pipe_analyze'):
            pipe.pipe_analyze()
            
        pipe.pipe_parse()
        
        # Generate outputs
        md_content = pipe.pipe_mk_markdown(
            image_dir=os.path.basename(image_dir),
            drop_mode="none"
        )
        
        # Save markdown
        md_path = os.path.join(output_dir, "output.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        logger.info(f"Successfully processed {pdf_path}")
        return md_path
        
    except Exception as e:
        logger.error(f"GPU processing failed: {e}")
        # Fallback to CPU
        os.environ["MINERU_DEVICE"] = "cpu"
        logger.info("Retrying with CPU mode...")
        # Recursive call with CPU mode
        return process_pdf_with_fallback(pdf_path, output_dir)
```

### Recipe 2: Integration with FDD Pipeline
```python
# Source: Custom implementation for this project
from typing import Dict, Any
import asyncio
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
from models.fdd_models import FDDDocument  # Project model
import instructor

async def extract_fdd_sections(pdf_path: str) -> FDDDocument:
    """Extract FDD sections using MinerU + LLMs"""
    
    # Step 1: Extract structured content with MinerU
    image_writer = DiskReaderWriter("./temp/images")
    
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    
    pipe = UNIPipe(pdf_bytes, {"_pdf_type": "", "model_list": []}, image_writer)
    pipe.pipe_classify()
    if hasattr(pipe, 'pipe_analyze'):
        pipe.pipe_analyze()
    pipe.pipe_parse()
    
    # Get structured content
    md_content = pipe.pipe_mk_markdown("images", drop_mode="none")
    json_content = pipe.get_json_content()  # If available
    
    # Step 2: Use LLMs to extract specific sections
    # (Following project's multi-model pattern)
    client = instructor.from_gemini(...)  # As configured
    
    fdd_doc = await client.create(
        model="gemini-pro",
        response_model=FDDDocument,
        messages=[{
            "role": "user",
            "content": f"Extract FDD sections from:\n{md_content}"
        }]
    )
    
    return fdd_doc
```

### Recipe 3: Batch Processing with Memory Management
```python
# Source: Performance optimization pattern
import os
from concurrent.futures import ProcessPoolExecutor
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

def process_single_pdf(args):
    """Process single PDF in separate process"""
    pdf_path, output_dir = args
    
    # Reduce batch size for memory efficiency
    os.environ["MINERU_BATCH_SIZE"] = "1"
    
    try:
        image_writer = DiskReaderWriter(f"{output_dir}/images")
        
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        pipe = UNIPipe(pdf_bytes, {"_pdf_type": ""}, image_writer)
        pipe.pipe_classify()
        pipe.pipe_parse()
        
        md_content = pipe.pipe_mk_markdown("images")
        
        # Save output
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        with open(f"{output_dir}/{base_name}.md", "w") as f:
            f.write(md_content)
            
        return True, pdf_path
        
    except Exception as e:
        return False, f"{pdf_path}: {str(e)}"

def batch_process_pdfs(pdf_list: list, output_dir: str, max_workers: int = 4):
    """Process multiple PDFs with controlled parallelism"""
    
    # Prepare arguments
    args_list = [(pdf, output_dir) for pdf in pdf_list]
    
    # Process with pool
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_pdf, args_list))
    
    # Report results
    successful = [r for r in results if r[0]]
    failed = [r for r in results if not r[0]]
    
    print(f"Processed: {len(successful)}/{len(pdf_list)} PDFs successfully")
    if failed:
        print("Failed PDFs:")
        for _, error in failed:
            print(f"  - {error}")
```

## Best Practices

### Performance Optimization
- **GPU Memory**: Start with `MINERU_BATCH_SIZE=2`, reduce to 1 if OOM errors occur
- **Multi-GPU**: Use `--tp-size 2` for tensor parallelism across GPUs
- **CPU Fallback**: Always implement try/except with CPU mode fallback
- **Batch Processing**: Use process pools to avoid memory accumulation
- **Document Resolution**: Best performance with ~2000px long side documents

### Security Considerations
- **Input Validation**: Always validate PDF files before processing
- **Resource Limits**: Set timeouts for long-running extractions
- **Sandboxing**: Run in isolated environments when processing untrusted PDFs
- **Output Sanitization**: Clean extracted content before storage

### Testing Guidelines
- **Mock GPU**: Use `MINERU_DEVICE=cpu` for CI/CD pipelines
- **Sample PDFs**: Test with various PDF types (scanned, text, mixed)
- **Memory Testing**: Monitor memory usage with `nvidia-smi` during tests
- **Language Testing**: Verify OCR accuracy across different languages

## Troubleshooting FAQ

### 1. GPU Not Detected / CUDA Errors
```bash
# Check CUDA availability
python -c "import torch; print(torch.cuda.is_available())"

# Solution: Use CPU mode
export MINERU_DEVICE=cpu

# Or in Python
os.environ["MINERU_DEVICE"] = "cpu"
```

### 2. Out of Memory (OOM) Errors
```bash
# Reduce batch size
export MINERU_BATCH_SIZE=1

# For sglang mode, reduce KV cache
magic-pdf --mem-fraction-static 0.4

# Use tensor parallelism if multiple GPUs
magic-pdf --tp-size 2
```

### 3. Model Download Issues
```bash
# Re-download models
rm -rf ~/.mineru/models
magic-pdf model-download

# Verify models
ls -la ~/.mineru/models/
# Should see: Layout, MFD, MFR, OCR directories
```

### 4. Import Errors After Installation
```python
# Common issue: conflicting package names
# Solution: Uninstall and reinstall
pip uninstall magic-pdf mineru -y
pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com
```

### 5. Slow Processing Speed
```bash
# Enable torch compile (15% speedup)
export TORCH_COMPILE=1

# Use newer layout model
# In magic-pdf.json:
{
    "layout-config": {
        "model": "doclayout_yolo"  # Faster than layoutlmv3
    }
}
```

## Edge Cases & Pitfalls

### 1. Package Name Migration
- **Issue**: Package transitioning from `magic-pdf` to `mineru`
- **Impact**: Import statements and CLI commands will change
- **Solution**: Check version and use appropriate names

### 2. Memory Leaks in Long-Running Processes
- **Issue**: Memory accumulation when processing many PDFs
- **Solution**: Use process pools or restart workers periodically

### 3. Language Detection Failures
- **Issue**: Incorrect OCR language can severely impact accuracy
- **Solution**: Manually specify language with `--lang` parameter

### 4. Incomplete Model Downloads
- **Issue**: Partial downloads cause cryptic errors
- **Solution**: Verify all model directories have content

### 5. Configuration File Location
- **Issue**: `magic-pdf.json` must be in user home directory
- **Solution**: Check `~/magic-pdf.json` exists and is valid JSON

## Version Matrix

| Version | Breaking Changes | New Features | Notes |
|---------|-----------------|--------------|-------|
| 1.3.12 | - | Torch compile support | Current stable |
| 1.0.0 | Package rename to mineru | New API architecture | Major update |
| 0.7.0 | Added pipe_analyze() step | Dataset class | API change |
| 0.6.1 | - | RapidTable integration | 10x table speed |
| 0.5.0 | - | 8GB GPU support | Memory optimized |

### Migration Guide (0.6.x → 1.x)
```python
# Old (0.6.x)
from magic_pdf.pipe.UNIPipe import UNIPipe
pipe.pipe_classify()
pipe.pipe_parse()

# New (0.7.0+)
from magic_pdf.pipe.UNIPipe import UNIPipe  # Same import
pipe.pipe_classify()
pipe.pipe_analyze()  # NEW STEP
pipe.pipe_parse()

# Future (1.0+)
from mineru.pipe.UNIPipe import UNIPipe  # Package renamed
# CLI: mineru (not magic-pdf)
```

## Further Reading

### Official Resources
- **GitHub Repository**: https://github.com/opendatalab/MinerU
- **Documentation**: https://mineru.readthedocs.io/
- **PyPI Package**: https://pypi.org/project/magic-pdf/
- **Model Download**: https://huggingface.co/opendatalab

### Community Resources
- **Discord**: MinerU community (check GitHub for invite)
- **Issues**: https://github.com/opendatalab/MinerU/issues
- **Discussions**: https://github.com/opendatalab/MinerU/discussions

### Related Projects
- **Marker**: Alternative PDF to Markdown converter
- **PyMuPDF**: Lower-level PDF manipulation
- **Camelot**: Table extraction specialist
- **Tabula**: Java-based table extraction

### Integration Examples
- **LangChain Integration**: Use as document loader
- **LlamaIndex Integration**: PDF parsing component
- **Prefect Workflows**: As shown in this project
- **FastAPI Services**: Wrap as REST API

### Video Tutorials
- **MinerU Quickstart** (YouTube - OpenDataLab channel)
- **GPU Setup Guide** (Bilibili - MinerU官方)
- **Production Deployment** (Check GitHub wiki)

---

This dossier provides comprehensive guidance for implementing MinerU in the FDD Pipeline project. Always refer to the official documentation for the most up-to-date information.