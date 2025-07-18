"""Document models for layout analysis and section detection."""

from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class LayoutElement(BaseModel):
    """Represents a layout element from document analysis."""
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
    mineru_output_dir: Optional[str] = Field(None, description="Path to MinerU output directory")


class SectionBoundary(BaseModel):
    """Represents a detected FDD section boundary."""
    item_no: int = Field(..., ge=0, le=24)
    item_name: str
    start_page: int = Field(..., gt=0)
    end_page: int = Field(..., gt=0)
    confidence: float = Field(..., ge=0.0, le=1.0)


class FDDSectionDetector:
    """Basic FDD section detector for compatibility."""
    
    def detect_sections(self, layout: DocumentLayout) -> List[SectionBoundary]:
        """Detect sections from document layout."""
        # Basic implementation - returns single section for whole document
        return [
            SectionBoundary(
                item_no=0,
                item_name="Complete Document",
                start_page=1,
                end_page=layout.total_pages,
                confidence=0.5
            )
        ]