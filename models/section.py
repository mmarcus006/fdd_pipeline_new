"""FDD section models for FDD Pipeline."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class FDDSectionBase(BaseModel):
    """Base model for FDD sections."""
    fdd_id: UUID
    item_no: int = Field(..., ge=0, le=24)
    item_name: Optional[str] = None
    start_page: int = Field(..., gt=0)
    end_page: int = Field(..., gt=0)
    drive_path: Optional[str] = None
    drive_file_id: Optional[str] = None
    
    @model_validator(mode='after')
    def validate_page_range(self):
        if self.start_page and self.end_page and self.end_page < self.start_page:
            raise ValueError("end_page must be >= start_page")
        return self
    
    @field_validator('item_no')
    @classmethod
    def validate_item_no(cls, v):
        """Map item numbers to standard names."""
        item_names = {
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
            19: "Financial Performance Representations",  # Note: duplicate with 17
            20: "Outlets and Franchise Information",
            21: "Financial Statements",
            22: "Contracts",
            23: "Receipts",
            24: "Appendix/Exhibits"
        }
        return v


class FDDSection(FDDSectionBase):
    """Complete section model."""
    id: UUID
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    extraction_model: Optional[str] = None
    extraction_attempts: int = 0
    needs_review: bool = False
    created_at: datetime
    extracted_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}