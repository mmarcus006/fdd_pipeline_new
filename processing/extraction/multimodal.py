"""Multimodal processing utilities for handling PDFs, images, and URLs.

This module provides utilities for processing various file types and URLs
for extraction with Instructor and Gemini.
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, BinaryIO, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib
import mimetypes

import httpx
import PyPDF2
from PIL import Image
import google.generativeai as genai_upload

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Configure genai for file uploads
genai_upload.configure(api_key=settings.gemini_api_key)


class FileType(str, Enum):
    """Supported file types for multimodal processing."""

    PDF = "pdf"
    IMAGE = "image"
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


@dataclass
class ProcessedFile:
    """Represents a processed file ready for LLM extraction."""

    original_path: Optional[Path] = None
    original_url: Optional[str] = None
    file_type: FileType = FileType.UNKNOWN
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    hash_sha256: str = ""

    # For Gemini uploads
    gemini_file: Optional[Any] = None  # genai.File object

    # For text extraction
    extracted_text: Optional[str] = None
    page_count: Optional[int] = None

    # For chunking large files
    chunks: List["FileChunk"] = None

    def __post_init__(self):
        if self.chunks is None:
            self.chunks = []


@dataclass
class FileChunk:
    """Represents a chunk of a larger file."""

    chunk_index: int
    total_chunks: int
    content: Union[str, bytes]
    page_range: Optional[Tuple[int, int]] = None  # For PDFs
    byte_range: Optional[Tuple[int, int]] = None  # For binary data


class MultimodalProcessor:
    """Handles processing of various file types for LLM extraction."""

    # File size limits
    MAX_INLINE_SIZE = 20 * 1024 * 1024  # 20MB for inline content
    MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB for Gemini uploads

    # Supported MIME types
    SUPPORTED_MIME_TYPES = {
        # PDFs
        "application/pdf": FileType.PDF,
        # Images
        "image/jpeg": FileType.IMAGE,
        "image/png": FileType.IMAGE,
        "image/gif": FileType.IMAGE,
        "image/webp": FileType.IMAGE,
        "image/bmp": FileType.IMAGE,
        # Text
        "text/plain": FileType.TEXT,
        "text/html": FileType.TEXT,
        "text/markdown": FileType.TEXT,
        # Audio
        "audio/mpeg": FileType.AUDIO,
        "audio/mp3": FileType.AUDIO,
        "audio/wav": FileType.AUDIO,
        "audio/ogg": FileType.AUDIO,
        # Video
        "video/mp4": FileType.VIDEO,
        "video/mpeg": FileType.VIDEO,
        "video/quicktime": FileType.VIDEO,
        "video/x-msvideo": FileType.VIDEO,
    }

    def __init__(self, temp_dir: Optional[Path] = None):
        """Initialize the processor.

        Args:
            temp_dir: Optional directory for temporary files
        """
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "fdd_multimodal"
        self.temp_dir.mkdir(exist_ok=True)
        self._http_client = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0), follow_redirects=True
            )
        return self._http_client

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._http_client:
            await self._http_client.aclose()

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _detect_file_type(self, file_path: Path) -> Tuple[FileType, str]:
        """Detect file type and MIME type."""
        mime_type, _ = mimetypes.guess_type(str(file_path))

        if mime_type is None:
            # Try to detect from file content
            with open(file_path, "rb") as f:
                header = f.read(16)

            # Check for PDF
            if header.startswith(b"%PDF"):
                mime_type = "application/pdf"
            # Check for PNG
            elif header.startswith(b"\x89PNG\r\n\x1a\n"):
                mime_type = "image/png"
            # Check for JPEG
            elif header.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            else:
                mime_type = "application/octet-stream"

        file_type = self.SUPPORTED_MIME_TYPES.get(mime_type, FileType.UNKNOWN)
        return file_type, mime_type

    async def process_file(
        self,
        file_path: Union[str, Path],
        extract_text: bool = True,
        chunk_size: Optional[int] = None,
    ) -> ProcessedFile:
        """Process a local file for multimodal extraction.

        Args:
            file_path: Path to the file
            extract_text: Whether to extract text (for PDFs and text files)
            chunk_size: Optional chunk size for large files

        Returns:
            ProcessedFile object ready for extraction
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get file info
        file_size = file_path.stat().st_size
        file_type, mime_type = self._detect_file_type(file_path)
        file_hash = self._calculate_file_hash(file_path)

        processed = ProcessedFile(
            original_path=file_path,
            file_type=file_type,
            mime_type=mime_type,
            size_bytes=file_size,
            hash_sha256=file_hash,
        )

        # Handle based on file type
        if file_type == FileType.PDF:
            await self._process_pdf(processed, extract_text, chunk_size)
        elif file_type == FileType.IMAGE:
            await self._process_image(processed)
        elif file_type == FileType.TEXT:
            await self._process_text(processed)
        else:
            # For other types, just prepare for upload
            if file_size <= self.MAX_UPLOAD_SIZE:
                processed.gemini_file = await self._upload_to_gemini(file_path)

        return processed

    async def _process_pdf(
        self, processed: ProcessedFile, extract_text: bool, chunk_size: Optional[int]
    ):
        """Process a PDF file."""
        file_path = processed.original_path

        # Extract text if requested
        if extract_text:
            try:
                with open(file_path, "rb") as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    processed.page_count = len(pdf_reader.pages)

                    # Extract text from all pages
                    text_parts = []
                    for page_num, page in enumerate(pdf_reader.pages):
                        try:
                            text = page.extract_text()
                            if text.strip():
                                text_parts.append(
                                    f"--- Page {page_num + 1} ---\n{text}"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to extract text from page {page_num + 1}: {e}"
                            )

                    processed.extracted_text = "\n\n".join(text_parts)
            except Exception as e:
                logger.error(f"Failed to extract text from PDF: {e}")

        # Upload to Gemini if within size limit
        if processed.size_bytes <= self.MAX_UPLOAD_SIZE:
            try:
                processed.gemini_file = await self._upload_to_gemini(file_path)
            except Exception as e:
                logger.warning(f"Failed to upload PDF to Gemini: {e}")

        # Create chunks if needed
        if chunk_size and processed.page_count and processed.page_count > chunk_size:
            await self._chunk_pdf(processed, chunk_size)

    async def _process_image(self, processed: ProcessedFile):
        """Process an image file."""
        file_path = processed.original_path

        # Get image dimensions
        try:
            with Image.open(file_path) as img:
                width, height = img.size
                processed.extracted_text = (
                    f"Image: {width}x{height} pixels, format: {img.format}"
                )
        except Exception as e:
            logger.warning(f"Failed to read image metadata: {e}")

        # Upload to Gemini if within size limit
        if processed.size_bytes <= self.MAX_UPLOAD_SIZE:
            try:
                processed.gemini_file = await self._upload_to_gemini(file_path)
            except Exception as e:
                logger.warning(f"Failed to upload image to Gemini: {e}")

    async def _process_text(self, processed: ProcessedFile):
        """Process a text file."""
        file_path = processed.original_path

        # Read text content
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                processed.extracted_text = f.read()
        except Exception as e:
            logger.error(f"Failed to read text file: {e}")

    async def _upload_to_gemini(self, file_path: Path) -> Any:
        """Upload file to Gemini and return file object."""
        logger.info(f"Uploading file to Gemini: {file_path.name}")

        # Upload file
        uploaded_file = genai_upload.upload_file(str(file_path))

        # Wait for processing to complete
        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(0.5)
            uploaded_file = genai_upload.get_file(uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            raise Exception(f"File upload failed: {uploaded_file.state.name}")

        logger.info(f"Successfully uploaded file: {uploaded_file.name}")
        return uploaded_file

    async def _chunk_pdf(self, processed: ProcessedFile, pages_per_chunk: int):
        """Split PDF into chunks."""
        file_path = processed.original_path

        with open(file_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            total_pages = len(pdf_reader.pages)
            total_chunks = (total_pages + pages_per_chunk - 1) // pages_per_chunk

            for chunk_idx in range(total_chunks):
                start_page = chunk_idx * pages_per_chunk
                end_page = min(start_page + pages_per_chunk, total_pages)

                # Extract text for this chunk
                chunk_text_parts = []
                for page_num in range(start_page, end_page):
                    try:
                        text = pdf_reader.pages[page_num].extract_text()
                        if text.strip():
                            chunk_text_parts.append(
                                f"--- Page {page_num + 1} ---\n{text}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract text from page {page_num + 1}: {e}"
                        )

                chunk = FileChunk(
                    chunk_index=chunk_idx,
                    total_chunks=total_chunks,
                    content="\n\n".join(chunk_text_parts),
                    page_range=(start_page + 1, end_page),  # 1-indexed for display
                )
                processed.chunks.append(chunk)
                
                logger.debug(
                    f"Created chunk {chunk_idx + 1}/{total_chunks} - "
                    f"Pages {start_page + 1}-{end_page}, "
                    f"Text length: {len(chunk.content)} chars"
                )
        
        logger.info(
            f"PDF chunking completed - Total chunks: {len(processed.chunks)}"
        )
        pipeline_logger.info(
            "PDF chunks created",
            total_chunks=len(processed.chunks),
            pages_per_chunk=pages_per_chunk,
            total_pages=processed.page_count
        )

    async def process_url(
        self, url: str, extract_text: bool = True, chunk_size: Optional[int] = None
    ) -> ProcessedFile:
        """Download and process a file from URL.

        Args:
            url: URL of the file to process
            extract_text: Whether to extract text
            chunk_size: Optional chunk size for large files

        Returns:
            ProcessedFile object ready for extraction
        """
        logger.info(f"Downloading file from URL: {url}")

        # Download file
        response = await self.http_client.get(url)
        response.raise_for_status()

        # Determine file name and type from URL and headers
        content_type = response.headers.get("content-type", "application/octet-stream")
        file_type = self.SUPPORTED_MIME_TYPES.get(content_type, FileType.UNKNOWN)

        # Extract filename from URL or generate one
        url_path = Path(url.split("?")[0])
        file_name = (
            url_path.name or f"download_{hashlib.md5(url.encode()).hexdigest()[:8]}"
        )

        # Save to temp file
        temp_path = self.temp_dir / file_name
        with open(temp_path, "wb") as f:
            f.write(response.content)

        # Process the downloaded file
        processed = await self.process_file(temp_path, extract_text, chunk_size)
        processed.original_url = url

        return processed

    async def prepare_for_extraction(
        self,
        file_or_url: Union[str, Path],
        mode: str = "auto",
        extract_text: bool = True,
        chunk_size: Optional[int] = None,
    ) -> ProcessedFile:
        """Prepare a file or URL for extraction.

        Args:
            file_or_url: File path or URL
            mode: "file", "url", or "auto" (auto-detect)
            extract_text: Whether to extract text
            chunk_size: Optional chunk size for large files

        Returns:
            ProcessedFile object ready for extraction
        """
        # Auto-detect mode
        if mode == "auto":
            file_or_url_str = str(file_or_url)
            if file_or_url_str.startswith(("http://", "https://")):
                mode = "url"
            else:
                mode = "file"

        # Process based on mode
        if mode == "url":
            return await self.process_url(str(file_or_url), extract_text, chunk_size)
        else:
            return await self.process_file(file_or_url, extract_text, chunk_size)

    def prepare_content_for_llm(
        self,
        processed: ProcessedFile,
        include_text: bool = True,
        chunk_index: Optional[int] = None,
    ) -> List[Union[str, Any]]:
        """Prepare content for LLM input.

        Args:
            processed: ProcessedFile object
            include_text: Whether to include extracted text
            chunk_index: Optional specific chunk to use

        Returns:
            List of content items for LLM input
        """
        content = []

        # Add description
        if processed.original_path:
            content.append(f"Processing file: {processed.original_path.name}")
        elif processed.original_url:
            content.append(f"Processing URL: {processed.original_url}")

        # Handle chunks
        if chunk_index is not None and processed.chunks:
            if 0 <= chunk_index < len(processed.chunks):
                chunk = processed.chunks[chunk_index]
                content.append(
                    f"Chunk {chunk.chunk_index + 1} of {chunk.total_chunks} "
                    f"(pages {chunk.page_range[0]}-{chunk.page_range[1]})"
                )
                if include_text and isinstance(chunk.content, str):
                    content.append(chunk.content)
            else:
                raise ValueError(f"Invalid chunk index: {chunk_index}")
        else:
            # Use full content
            if processed.gemini_file:
                content.append(processed.gemini_file)
            elif include_text and processed.extracted_text:
                content.append(processed.extracted_text)

        return content

    async def cleanup_temp_files(self):
        """Clean up temporary files."""
        for file_path in self.temp_dir.iterdir():
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temp file {file_path}: {e}")


# Convenience functions
async def process_pdf_for_extraction(
    pdf_path: Union[str, Path],
    extract_text: bool = True,
    pages_per_chunk: Optional[int] = 10,
) -> ProcessedFile:
    """Process a PDF file for extraction.

    Args:
        pdf_path: Path to PDF file
        extract_text: Whether to extract text
        pages_per_chunk: Pages per chunk for large PDFs

    Returns:
        ProcessedFile ready for extraction
    """
    async with MultimodalProcessor() as processor:
        return await processor.process_file(
            pdf_path, extract_text=extract_text, chunk_size=pages_per_chunk
        )


async def process_url_for_extraction(
    url: str, extract_text: bool = True
) -> ProcessedFile:
    """Process a URL for extraction.

    Args:
        url: URL to process
        extract_text: Whether to extract text

    Returns:
        ProcessedFile ready for extraction
    """
    async with MultimodalProcessor() as processor:
        return await processor.process_url(url, extract_text=extract_text)
