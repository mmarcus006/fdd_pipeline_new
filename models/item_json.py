"""Generic JSON storage models for FDD items."""

from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional
from datetime import datetime
from uuid import UUID


class ItemJSONBase(BaseModel):
    """Base model for generic item storage."""
    item_no: int = Field(..., ge=0, le=24)
    data: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = Field(default="1.0")
    
    @field_validator('data')
    @classmethod
    def validate_data_not_empty(cls, v):
        """Ensure data has content."""
        if not v:
            raise ValueError("Data cannot be empty")
        return v


class ItemJSON(ItemJSONBase):
    """JSON storage with metadata."""
    section_id: UUID
    validated: bool = False
    validation_errors: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


# Item-specific JSON schemas for validation
class Item1Schema(BaseModel):
    """The Franchisor and Any Parents, Predecessors, and Affiliates."""
    franchisor_info: Dict[str, Any]
    parent_companies: List[Dict[str, str]]
    predecessors: List[Dict[str, str]]
    affiliates: List[Dict[str, str]]


class Item2Schema(BaseModel):
    """Business Experience."""
    executives: List[Dict[str, Any]]  # name, position, experience


class Item3Schema(BaseModel):
    """Litigation."""
    cases: List[Dict[str, Any]]  # case_name, court, date, status, description


class Item4Schema(BaseModel):
    """Bankruptcy."""
    bankruptcies: List[Dict[str, Any]]  # person, date, court, case_number


class Item8Schema(BaseModel):
    """Restrictions on Sources of Products and Services."""
    restrictions: List[Dict[str, Any]]
    approved_suppliers: List[Dict[str, str]]


class Item9Schema(BaseModel):
    """Financing."""
    financing_options: List[Dict[str, Any]]
    terms_and_conditions: Dict[str, Any]


class Item10Schema(BaseModel):
    """Franchisor's Assistance, Advertising, Computer Systems, and Training."""
    assistance_programs: List[Dict[str, Any]]
    training_requirements: Dict[str, Any]
    advertising_requirements: Dict[str, Any]
    computer_systems: Dict[str, Any]


class Item11Schema(BaseModel):
    """Territory."""
    territory_rights: Dict[str, Any]
    exclusivity: Dict[str, Any]
    population_requirements: Optional[Dict[str, Any]] = None


class Item12Schema(BaseModel):
    """Trademarks."""
    trademarks: List[Dict[str, Any]]
    usage_requirements: Dict[str, Any]


class Item13Schema(BaseModel):
    """Patents, Copyrights, and Proprietary Information."""
    intellectual_property: List[Dict[str, Any]]
    confidentiality_requirements: Dict[str, Any]


class Item14Schema(BaseModel):
    """Obligation to Participate in the Actual Operation of the Franchise Business."""
    participation_requirements: Dict[str, Any]
    management_requirements: Dict[str, Any]


class Item15Schema(BaseModel):
    """Termination, Cancellation, and Renewal of the Franchise."""
    termination_conditions: List[Dict[str, Any]]
    renewal_terms: Dict[str, Any]
    post_termination_obligations: List[Dict[str, Any]]


class Item16Schema(BaseModel):
    """Public Figures."""
    public_figures: List[Dict[str, Any]]
    endorsements: List[Dict[str, Any]]


class Item17Schema(BaseModel):
    """Financial Performance Representations (alternate to Item 19)."""
    # This is typically the same as Item 19
    disclosure_type: str
    representations: List[Dict[str, Any]]


class Item18Schema(BaseModel):
    """Contacts."""
    franchisor_contacts: List[Dict[str, str]]
    franchisee_contacts: List[Dict[str, str]]


class Item22Schema(BaseModel):
    """Contracts."""
    franchise_agreement: Dict[str, Any]
    related_agreements: List[Dict[str, Any]]


class Item23Schema(BaseModel):
    """Receipts."""
    receipt_requirements: Dict[str, Any]
    acknowledgments: List[str]


class Item24Schema(BaseModel):
    """Appendix/Exhibits."""
    exhibits: List[Dict[str, Any]]
    additional_documents: List[Dict[str, str]]