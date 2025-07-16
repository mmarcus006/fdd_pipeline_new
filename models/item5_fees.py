"""Item 5 - Initial Fees models."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from enum import Enum

from .base import ValidationConfig


class DueAt(str, Enum):
    SIGNING = "Signing"
    TRAINING = "Training"
    OPENING = "Opening"
    OTHER = "Other"


class InitialFeeBase(BaseModel):
    """Base model for initial fees."""

    fee_name: str = Field(..., min_length=1)
    amount_cents: int = Field(..., ge=0)
    refundable: bool = False
    refund_conditions: Optional[str] = None
    due_at: Optional[DueAt] = None
    notes: Optional[str] = None

    @field_validator("amount_cents")
    @classmethod
    def validate_reasonable_amount(cls, v):
        """Ensure amount is reasonable (< $10M)."""
        if v > ValidationConfig.MAX_FEE_AMOUNT:
            raise ValueError("Amount exceeds reasonable maximum")
        return v

    @property
    def amount_dollars(self) -> float:
        """Convert cents to dollars."""
        return self.amount_cents / 100


class InitialFee(InitialFeeBase):
    """Initial fee with section reference."""

    section_id: UUID

    model_config = {"from_attributes": True}
