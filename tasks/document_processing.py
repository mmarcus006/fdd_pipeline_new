"""Document processing tasks using MinerU for layout analysis and section detection."""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from prefect import task
import PyPDF2

from config import get_settings
from models.section import FDDSection, ExtractionStatus
from utils.logging import PipelineLogger


class LayoutElement(BaseModel):
    """Represents a layout element from MinerU analysis."""

    type: str = Field(..., description="Element type (text, table, figure, etc.)")
    bbox: List[float] = Field(..., description="Bounding box [x1, y1, x2, y2]")
    page: int = Field(..., description="Page number (0-indexed)")
    text: Optional[str] = Field(None, description="Extracted text content")
    confidence: Optional[float] = Field(None, description="Confidence score")


class DocumentLayout(BaseModel):
    """Complete document layout analysis result."""

    total_pages: int
    elements: List[LayoutElement]
    processing_time: float
    model_version: str


class SectionBoundary(BaseModel):
    """Represents a detected FDD section boundary."""

    item_no: int = Field(..., ge=0, le=24)
    item_name: str
    start_page: int = Field(..., gt=0)
    end_page: int = Field(..., gt=0)
    confidence: float = Field(..., ge=0.0, le=1.0)


class MinerUClient:
    """Client for MinerU document processing with API and local processing support."""

    def __init__(self):
        self.settings = get_settings()
        self.logger = PipelineLogger("mineru_client")
        self.mode = self.settings.mineru_mode

        # API mode configuration
        if self.mode == "api":
            self.api_key = self.settings.mineru_api_key
            self.base_url = self.settings.mineru_base_url
            self.rate_limit = self.settings.mineru_rate_limit
            self._semaphore = asyncio.Semaphore(self.rate_limit)

            if not self.api_key:
                raise ValueError("MinerU API key is required for API mode")

        # Local mode configuration
        else:
            self.model_path = Path(self.settings.mineru_model_path)
            self.device = self.settings.mineru_device
            self.batch_size = self.settings.mineru_batch_size

            # Ensure model directory exists for local mode
            self.model_path.mkdir(parents=True, exist_ok=True)

    async def process_document(
        self, pdf_path: Path, timeout_seconds: int = 300
    ) -> DocumentLayout:
        """
        Process a PDF document using MinerU for layout analysis.

        Args:
            pdf_path: Path to the PDF file
            timeout_seconds: Processing timeout

        Returns:
            DocumentLayout with extracted elements

        Raises:
            Exception: If processing fails
        """
        start_time = time.time()

        try:
            self.logger.info(
                "Starting MinerU document processing",
                pdf_path=str(pdf_path),
                mode=self.mode,
            )

            # Validate input file
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            # Route to appropriate processing method
            if self.mode == "api":
                layout_result = await self._process_via_api(pdf_path, timeout_seconds)
            else:
                layout_result = await self._process_locally(pdf_path, timeout_seconds)

            processing_time = time.time() - start_time

            self.logger.info(
                "MinerU processing completed",
                processing_time=processing_time,
                total_elements=len(layout_result.elements),
                total_pages=layout_result.total_pages,
                mode=self.mode,
            )

            return DocumentLayout(
                total_pages=layout_result.total_pages,
                elements=layout_result.elements,
                processing_time=processing_time,
                model_version=layout_result.model_version,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(
                "MinerU processing failed",
                error=str(e),
                processing_time=processing_time,
                pdf_path=str(pdf_path),
                mode=self.mode,
            )
            raise

    async def _process_via_api(
        self, pdf_path: Path, timeout_seconds: int
    ) -> DocumentLayout:
        """Process document via MinerU API with rate limiting and authentication."""
        async with self._semaphore:  # Rate limiting
            try:
                self.logger.info(
                    "Processing document via MinerU API",
                    pdf_path=str(pdf_path),
                    rate_limit=self.rate_limit,
                )

                # Upload document and get job ID
                job_id = await self._upload_document_to_api(pdf_path, timeout_seconds)

                # Poll for completion
                layout_result = await self._poll_api_job_status(job_id, timeout_seconds)

                return layout_result

            except Exception as e:
                self.logger.error("API processing failed", error=str(e))
                raise

    async def _upload_document_to_api(
        self, pdf_path: Path, timeout_seconds: int
    ) -> str:
        """Upload document to MinerU API and return job ID."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "multipart/form-data",
        }

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            with open(pdf_path, "rb") as pdf_file:
                files = {"file": (pdf_path.name, pdf_file, "application/pdf")}
                data = {
                    "output_format": "json",
                    "include_layout": "true",
                    "include_text": "true",
                }

                response = await client.post(
                    f"{self.base_url}/documents/upload",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data=data,
                )

                if response.status_code != 200:
                    raise Exception(
                        f"API upload failed: {response.status_code} - {response.text}"
                    )

                result = response.json()
                job_id = result.get("job_id")

                if not job_id:
                    raise Exception("No job ID returned from API")

                self.logger.info("Document uploaded to API", job_id=job_id)
                return job_id

    async def _poll_api_job_status(
        self, job_id: str, timeout_seconds: int
    ) -> DocumentLayout:
        """Poll MinerU API for job completion and return results."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        start_time = time.time()
        poll_interval = 5  # Start with 5 second intervals
        max_poll_interval = 30  # Max 30 second intervals

        async with httpx.AsyncClient(timeout=30) as client:
            while time.time() - start_time < timeout_seconds:
                try:
                    response = await client.get(
                        f"{self.base_url}/documents/{job_id}/status", headers=headers
                    )

                    if response.status_code != 200:
                        raise Exception(f"Status check failed: {response.status_code}")

                    status_data = response.json()
                    status = status_data.get("status")

                    self.logger.debug("API job status", job_id=job_id, status=status)

                    if status == "completed":
                        # Get the results
                        return await self._fetch_api_results(job_id, client, headers)

                    elif status == "failed":
                        error_msg = status_data.get("error", "Unknown error")
                        raise Exception(f"API processing failed: {error_msg}")

                    elif status in ["pending", "processing"]:
                        # Wait before next poll, with exponential backoff
                        await asyncio.sleep(poll_interval)
                        poll_interval = min(poll_interval * 1.5, max_poll_interval)
                        continue

                    else:
                        raise Exception(f"Unknown API status: {status}")

                except httpx.TimeoutException:
                    self.logger.warning("API status check timeout, retrying...")
                    await asyncio.sleep(poll_interval)
                    continue

            raise Exception(f"API processing timeout after {timeout_seconds}s")

    async def _fetch_api_results(
        self, job_id: str, client: httpx.AsyncClient, headers: Dict[str, str]
    ) -> DocumentLayout:
        """Fetch and parse API results."""
        response = await client.get(
            f"{self.base_url}/documents/{job_id}/results", headers=headers
        )

        if response.status_code != 200:
            raise Exception(f"Results fetch failed: {response.status_code}")

        results = response.json()

        # Parse API response into our DocumentLayout format
        return self._parse_api_response(results)

    def _parse_api_response(self, api_response: Dict[str, Any]) -> DocumentLayout:
        """Parse MinerU API response into DocumentLayout."""
        try:
            # Extract layout elements from API response
            elements = []
            api_elements = api_response.get("layout", {}).get("elements", [])

            for elem in api_elements:
                elements.append(
                    LayoutElement(
                        type=elem.get("type", "text"),
                        bbox=elem.get("bbox", [0, 0, 0, 0]),
                        page=elem.get("page", 0),
                        text=elem.get("text"),
                        confidence=elem.get("confidence", 0.8),
                    )
                )

            return DocumentLayout(
                total_pages=api_response.get("total_pages", 1),
                elements=elements,
                processing_time=api_response.get("processing_time", 0.0),
                model_version=api_response.get("model_version", "mineru-api"),
            )

        except Exception as e:
            self.logger.error("Failed to parse API response", error=str(e))
            raise Exception(f"API response parsing failed: {e}")

    async def _process_locally(
        self, pdf_path: Path, timeout_seconds: int
    ) -> DocumentLayout:
        """Process document locally using MinerU installation."""
        # Check if MinerU has already processed this file
        pdf_stem = pdf_path.stem
        parent_dir = pdf_path.parent
        
        # Look for existing MinerU output directory
        existing_outputs = list(parent_dir.glob(f"{pdf_stem}*"))
        mineru_output_dir = None
        
        for output_dir in existing_outputs:
            if output_dir.is_dir() and output_dir.name.startswith(pdf_stem):
                # Check if it contains MinerU output files
                if (output_dir / "full.md").exists() or (output_dir / "layout.json").exists():
                    mineru_output_dir = output_dir
                    self.logger.info(
                        "Found existing MinerU output",
                        output_dir=str(mineru_output_dir),
                    )
                    break
        
        if mineru_output_dir:
            # Use existing MinerU output
            return await self._load_existing_mineru_output(mineru_output_dir)
        else:
            # Create temporary output directory
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir) / "output"
                output_dir.mkdir(exist_ok=True)

                # Run local MinerU analysis
                return await self._run_mineru_analysis(
                    pdf_path, output_dir, timeout_seconds
                )

    async def _run_mineru_analysis(
        self, pdf_path: Path, output_dir: Path, timeout_seconds: int
    ) -> DocumentLayout:
        """Run the actual MinerU analysis process following official API."""
        try:
            # Import magic-pdf here to avoid import errors if not installed
            from magic_pdf.pipe.UNIPipe import UNIPipe
            from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
            import os

            # Setup image directory for extracted images
            image_dir = output_dir / "images"
            image_dir.mkdir(exist_ok=True)

            # Initialize image writer
            image_writer = DiskReaderWriter(str(image_dir))

            # Read PDF bytes
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            # Configuration following MinerU documentation
            config = {
                "_pdf_type": "",  # Auto-detect
                "model_list": [],  # Use default models
                "device": self.device,
            }

            # Set environment variables for MinerU
            os.environ["MINERU_DEVICE"] = self.device
            os.environ["MINERU_BATCH_SIZE"] = str(self.batch_size)

            # Initialize UNIPipe with correct parameters
            pipe = UNIPipe(pdf_bytes, config, image_writer)

            # Process the document following the correct pipeline steps
            def run_pipeline():
                # Step 1: Classify PDF type
                pipe.pipe_classify()

                # Step 2: Analyze document structure (added in v0.7.0+)
                if hasattr(pipe, "pipe_analyze"):
                    pipe.pipe_analyze()

                # Step 3: Parse PDF content
                pipe.pipe_parse()

                # Get structured content
                md_content = pipe.pipe_mk_markdown(
                    image_dir=os.path.basename(str(image_dir)), drop_mode="none"
                )

                return md_content, pipe

            # Run pipeline with timeout
            md_content, processed_pipe = await asyncio.wait_for(
                asyncio.to_thread(run_pipeline), timeout=timeout_seconds
            )

            # Extract layout information from the processed content
            layout_elements = self._extract_layout_from_markdown(md_content)

            # Get total pages from PDF
            total_pages = self._get_pdf_page_count(pdf_path)

            return DocumentLayout(
                total_pages=total_pages,
                elements=layout_elements,
                processing_time=0.0,  # Will be set by caller
                model_version="mineru-local",
            )

        except ImportError as e:
            self.logger.error("MinerU not properly installed", error=str(e))
            raise Exception(f"MinerU installation error: {e}")
        except asyncio.TimeoutError:
            self.logger.error("MinerU processing timeout", timeout=timeout_seconds)
            raise Exception(f"MinerU processing timeout after {timeout_seconds}s")
        except Exception as e:
            self.logger.error("MinerU analysis failed", error=str(e))
            raise

    def _extract_layout_from_markdown(self, md_content: str) -> List[LayoutElement]:
        """Extract layout elements from MinerU markdown output."""
        elements = []
        lines = md_content.split("\n")
        current_page = 0
        y_position = 800  # Start from top of page

        for line_idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Detect page breaks (MinerU often includes page markers)
            if "---" in line or "page" in line.lower():
                current_page += 1
                y_position = 800
                continue

            # Determine element type based on markdown formatting
            element_type = "text"
            confidence = 0.8

            if line.startswith("#"):
                element_type = "heading"
                confidence = 0.9
            elif line.startswith("|") and "|" in line[1:]:
                element_type = "table"
                confidence = 0.85
            elif line.startswith("!["):
                element_type = "figure"
                confidence = 0.7

            # Create layout element
            elements.append(
                LayoutElement(
                    type=element_type,
                    bbox=[
                        50,
                        y_position,
                        550,
                        y_position + 20,
                    ],  # Approximate positioning
                    page=current_page,
                    text=line,
                    confidence=confidence,
                )
            )

            y_position -= 25  # Move down for next element
            if y_position < 50:  # Start new page if near bottom
                current_page += 1
                y_position = 800

        return elements

    def _get_pdf_page_count(self, pdf_path: Path) -> int:
        """Get total page count from PDF."""
        try:
            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                return len(pdf_reader.pages)
        except Exception:
            return 1  # Default to 1 page if can't read

    async def _load_existing_mineru_output(
        self, output_dir: Path
    ) -> DocumentLayout:
        """Load existing MinerU output from directory."""
        try:
            self.logger.info(
                "Loading existing MinerU output",
                output_dir=str(output_dir),
            )

            # Load markdown content if available
            md_path = output_dir / "full.md"
            md_content = ""
            if md_path.exists():
                with open(md_path, "r", encoding="utf-8") as f:
                    md_content = f.read()
                    self.logger.info(
                        "Loaded markdown content",
                        size_chars=len(md_content),
                    )

            # Load layout.json if available
            layout_path = output_dir / "layout.json"
            layout_data = {}
            if layout_path.exists():
                with open(layout_path, "r", encoding="utf-8") as f:
                    layout_data = json.load(f)
                    self.logger.info(
                        "Loaded layout data",
                        total_pages=layout_data.get("total_pages", "Unknown"),
                    )

            # Load content_list.json if available
            content_list_files = list(output_dir.glob("*_content_list.json"))
            content_elements = []
            if content_list_files:
                with open(content_list_files[0], "r", encoding="utf-8") as f:
                    content_list = json.load(f)
                    content_elements = content_list
                    self.logger.info(
                        "Loaded content list",
                        total_elements=len(content_elements),
                    )

            # Convert content list to layout elements
            layout_elements = []
            for idx, element in enumerate(content_elements):
                if element.get("type") == "text" and element.get("text"):
                    layout_elements.append(
                        LayoutElement(
                            type="text",
                            bbox=[0, 0, 612, 792],  # Standard page size
                            page=element.get("page_idx", 0),
                            text=element.get("text", ""),
                            confidence=0.9,
                        )
                    )
                elif element.get("type") == "table":
                    layout_elements.append(
                        LayoutElement(
                            type="table",
                            bbox=[0, 0, 612, 792],
                            page=element.get("page_idx", 0),
                            text=str(element.get("table_caption", [])),
                            confidence=0.85,
                        )
                    )

            # Get total pages from layout.json or estimate from content
            total_pages = layout_data.get("total_pages", 1)
            if not total_pages and content_elements:
                max_page = max(
                    (elem.get("page_idx", 0) for elem in content_elements), default=0
                )
                total_pages = max_page + 1

            return DocumentLayout(
                total_pages=total_pages,
                elements=layout_elements,
                processing_time=0.0,
                model_version="mineru-existing",
            )

        except Exception as e:
            self.logger.error(
                "Failed to load existing MinerU output",
                error=str(e),
                output_dir=str(output_dir),
            )
            raise

    async def fallback_to_pypdf2(self, pdf_path: Path) -> DocumentLayout:
        """
        Fallback to PyPDF2 for basic text extraction when MinerU fails.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            DocumentLayout with basic text elements
        """
        start_time = time.time()

        try:
            self.logger.info(
                "Using PyPDF2 fallback for document processing", pdf_path=str(pdf_path)
            )

            elements = []
            total_pages = 0

            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)

                for page_idx, page in enumerate(pdf_reader.pages):
                    try:
                        text = page.extract_text()
                        if text.strip():
                            # Create a single text element for the entire page
                            elements.append(
                                LayoutElement(
                                    type="text",
                                    bbox=[0, 0, 612, 792],  # Standard letter size
                                    page=page_idx,
                                    text=text,
                                    confidence=0.5,  # Lower confidence for fallback
                                )
                            )
                    except Exception as e:
                        self.logger.warning(
                            "Failed to extract text from page",
                            page=page_idx,
                            error=str(e),
                        )

            processing_time = time.time() - start_time

            self.logger.info(
                "PyPDF2 fallback completed",
                processing_time=processing_time,
                total_pages=total_pages,
                total_elements=len(elements),
            )

            return DocumentLayout(
                total_pages=total_pages,
                elements=elements,
                processing_time=processing_time,
                model_version="pypdf2-fallback",
            )

        except Exception as e:
            self.logger.error("PyPDF2 fallback failed", error=str(e))
            raise


class FDDSectionDetector:
    """Detects FDD section boundaries using layout analysis and pattern matching."""

    # Standard FDD section patterns
    SECTION_PATTERNS = {
        0: ["cover", "introduction", "table of contents"],
        1: "the franchisor",
        2: "business experience",
        3: "litigation",
        4: "bankruptcy",
        5: "initial fees",
        6: "other fees",
        7: "estimated initial investment",
        8: "restrictions on sources",
        9: "financing",
        10: "franchisor's assistance",
        11: "territory",
        12: "trademarks",
        13: "patents",
        14: "obligation to participate",
        15: "termination",
        16: "public figures",
        17: "financial performance representations",
        18: "contacts",
        19: "financial performance representations",
        20: "outlets and franchise information",
        21: "financial statements",
        22: "contracts",
        23: "receipts",
        24: ["appendix", "exhibits"],
    }

    def __init__(self):
        self.logger = PipelineLogger("section_detector")

    def detect_sections(self, layout: DocumentLayout) -> List[SectionBoundary]:
        """
        Detect FDD section boundaries from layout analysis.

        Args:
            layout: Document layout from MinerU

        Returns:
            List of detected section boundaries
        """
        self.logger.info(
            "Starting FDD section detection",
            total_pages=layout.total_pages,
            total_elements=len(layout.elements),
        )

        try:
            # Extract text elements and sort by page/position
            text_elements = [
                elem for elem in layout.elements if elem.type == "text" and elem.text
            ]

            # Sort by page, then by vertical position (y-coordinate)
            text_elements.sort(key=lambda x: (x.page, -x.bbox[1]))

            # Find section headers using pattern matching
            section_boundaries = self._find_section_headers(text_elements)

            # Validate and fill gaps
            section_boundaries = self._validate_and_fill_sections(
                section_boundaries, layout.total_pages
            )

            self.logger.info(
                "Section detection completed", sections_found=len(section_boundaries)
            )

            return section_boundaries

        except Exception as e:
            self.logger.error("Section detection failed", error=str(e))
            raise

    def _find_section_headers(
        self, text_elements: List[LayoutElement]
    ) -> List[SectionBoundary]:
        """Find section headers using pattern matching."""
        boundaries = []

        for element in text_elements:
            text = element.text.lower().strip()

            # Look for "item X" patterns
            for item_no, patterns in self.SECTION_PATTERNS.items():
                if isinstance(patterns, list):
                    pattern_list = patterns
                else:
                    pattern_list = [patterns]

                for pattern in pattern_list:
                    if self._matches_section_pattern(text, item_no, pattern):
                        boundaries.append(
                            SectionBoundary(
                                item_no=item_no,
                                item_name=self._get_section_name(item_no),
                                start_page=element.page + 1,  # Convert to 1-indexed
                                end_page=element.page + 1,  # Will be updated later
                                confidence=0.8,
                            )
                        )
                        break

        return boundaries

    def _matches_section_pattern(self, text: str, item_no: int, pattern: str) -> bool:
        """Check if text matches a section pattern."""
        # Convert to lowercase for case-insensitive matching
        text_lower = text.lower()
        pattern_lower = pattern.lower()

        # Look for "item X" followed by the pattern
        item_text = f"item {item_no}"

        # Special case for item 0 (cover/intro)
        if item_no == 0:
            return any(
                p in text_lower for p in ["cover", "introduction", "table of contents"]
            )

        # Look for item number and pattern
        if item_text in text_lower and pattern_lower in text_lower:
            return True

        # Also check for just the pattern in headers (likely short text)
        if pattern_lower in text_lower and len(text) < 100:  # Likely a header
            return True

        return False

    def _get_section_name(self, item_no: int) -> str:
        """Get the standard name for an FDD section."""
        section_names = {
            0: "Cover/Introduction",
            1: "The Franchisor and Any Parents, Predecessors, and Affiliates",
            2: "Business Experience",
            3: "Litigation",
            4: "Bankruptcy",
            5: "Initial Fees",
            6: "Other Fees",
            7: "Estimated Initial Investment",
            8: "Restrictions on Sources of Products and Services",
            9: "Financing",
            10: "Franchisor's Assistance, Advertising, Computer Systems, and Training",
            11: "Territory",
            12: "Trademarks",
            13: "Patents, Copyrights, and Proprietary Information",
            14: "Obligation to Participate in the Actual Operation of the Franchise Business",
            15: "Termination, Cancellation, and Renewal of the Franchise",
            16: "Public Figures",
            17: "Financial Performance Representations",
            18: "Contacts",
            19: "Financial Performance Representations",
            20: "Outlets and Franchise Information",
            21: "Financial Statements",
            22: "Contracts",
            23: "Receipts",
            24: "Appendix/Exhibits",
        }
        return section_names.get(item_no, f"Item {item_no}")

    def _validate_and_fill_sections(
        self, boundaries: List[SectionBoundary], total_pages: int
    ) -> List[SectionBoundary]:
        """Validate section boundaries and fill gaps."""
        if not boundaries:
            # If no sections detected, create a single section for the entire document
            return [
                SectionBoundary(
                    item_no=0,
                    item_name="Complete Document",
                    start_page=1,
                    end_page=total_pages,
                    confidence=0.3,
                )
            ]

        # Sort by start page
        boundaries.sort(key=lambda x: x.start_page)

        # Update end pages based on next section's start
        for i in range(len(boundaries) - 1):
            boundaries[i].end_page = boundaries[i + 1].start_page - 1

        # Set last section's end page
        boundaries[-1].end_page = total_pages

        # Ensure no gaps or overlaps
        validated_boundaries = []
        current_page = 1

        for boundary in boundaries:
            if boundary.start_page > current_page:
                # Fill gap with unknown section
                validated_boundaries.append(
                    SectionBoundary(
                        item_no=0,
                        item_name="Unknown Section",
                        start_page=current_page,
                        end_page=boundary.start_page - 1,
                        confidence=0.2,
                    )
                )

            # Adjust start page if needed
            boundary.start_page = max(boundary.start_page, current_page)
            validated_boundaries.append(boundary)
            current_page = boundary.end_page + 1

        return validated_boundaries


@task(name="process_document_layout", retries=3)
async def process_document_layout(
    pdf_path: str, fdd_id: UUID, timeout_seconds: int = 300
) -> Tuple[DocumentLayout, List[SectionBoundary]]:
    """
    Process a PDF document to extract layout and detect sections.

    Args:
        pdf_path: Path to the PDF file
        fdd_id: FDD document ID
        timeout_seconds: Processing timeout

    Returns:
        Tuple of (DocumentLayout, List[SectionBoundary])
    """
    logger = PipelineLogger("process_document_layout").bind(fdd_id=str(fdd_id))

    try:
        logger.info("Starting document layout processing", pdf_path=pdf_path)

        client = MinerUClient()
        detector = FDDSectionDetector()

        pdf_file = Path(pdf_path)

        # Try MinerU processing first
        try:
            layout = await client.process_document(pdf_file, timeout_seconds)
        except Exception as e:
            logger.warning(
                "MinerU processing failed, falling back to PyPDF2", error=str(e)
            )
            layout = await client.fallback_to_pypdf2(pdf_file)

        # Detect section boundaries
        sections = detector.detect_sections(layout)

        logger.info(
            "Document layout processing completed",
            total_pages=layout.total_pages,
            sections_detected=len(sections),
            processing_time=layout.processing_time,
        )

        return layout, sections

    except Exception as e:
        logger.error("Document layout processing failed", error=str(e))
        raise


@task(name="validate_section_boundaries", retries=1)
def validate_section_boundaries(
    sections: List[SectionBoundary], total_pages: int
) -> List[SectionBoundary]:
    """
    Validate and clean up section boundaries.

    Args:
        sections: List of detected sections
        total_pages: Total pages in document

    Returns:
        Validated list of sections
    """
    logger = PipelineLogger("validate_section_boundaries")

    try:
        logger.info(
            "Validating section boundaries",
            input_sections=len(sections),
            total_pages=total_pages,
        )

        if not sections:
            logger.warning("No sections provided, creating default section")
            return [
                SectionBoundary(
                    item_no=0,
                    item_name="Complete Document",
                    start_page=1,
                    end_page=total_pages,
                    confidence=0.1,
                )
            ]

        # Sort by start page
        sections.sort(key=lambda x: x.start_page)

        # Validate page ranges
        validated_sections = []
        for section in sections:
            # Ensure valid page range
            if section.start_page < 1:
                section.start_page = 1
            if section.end_page > total_pages:
                section.end_page = total_pages
            if section.end_page < section.start_page:
                section.end_page = section.start_page

            validated_sections.append(section)

        logger.info(
            "Section boundary validation completed",
            output_sections=len(validated_sections),
        )

        return validated_sections

    except Exception as e:
        logger.error("Section boundary validation failed", error=str(e))
        raise
