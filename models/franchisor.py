"""Franchisor models for FDD Pipeline."""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID
import re

from .base import Address


class FranchisorBase(BaseModel):
    """Base franchisor model for creation/updates."""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    parent_company: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[Address] = None
    dba_names: List[str] = Field(default_factory=list)
    
    @validator('canonical_name')
    def clean_canonical_name(cls, v):
        """Normalize franchise names."""
        return v.strip().title()
    
    @validator('website')
    def validate_website(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            v = f"https://{v}"
        return v
    
    @validator('phone')
    def validate_phone(cls, v):
        if v:
            # Remove all non-digits
            digits = re.sub(r'\D', '', v)
            if len(digits) == 10:
                return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits[0] == '1':
                return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            else:
                raise ValueError("Invalid phone number format")
        return v
    
    @validator('email')
    def validate_email(cls, v):
        if v and not re.match(r"[^@]+@[^@]+\.[^@]+", v):
            raise ValueError("Invalid email format")
        return v


class FranchisorCreate(FranchisorBase):
    """Model for creating new franchisors."""
    pass


class FranchisorUpdate(BaseModel):
    """Model for updating franchisors (all fields optional)."""
    canonical_name: Optional[str] = Field(None, min_length=1, max_length=255)
    parent_company: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[Address] = None
    dba_names: Optional[List[str]] = None


class Franchisor(FranchisorBase):
    """Complete franchisor model with DB fields."""
    id: UUID
    name_embedding: Optional[List[float]] = Field(None, description="384-dim vector")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True