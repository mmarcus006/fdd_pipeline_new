"""FDD Pipeline Models."""

# Core models
from .base import Address, ValidationConfig, cents_to_dollars, dollars_to_cents
from .franchisor import Franchisor, FranchisorCreate, FranchisorUpdate, FranchisorBase
from .fdd import FDD, FDDCreate, FDDBase, DocumentType, ProcessingStatus
from .section import FDDSection, FDDSectionBase, ExtractionStatus

# Structured data models
from .item5_fees import InitialFee, InitialFeeBase, DueAt
from .item6_other_fees import OtherFee, OtherFeeBase, FeeFrequency, CalculationBasis
from .item7_investment import InitialInvestment, InitialInvestmentBase, InitialInvestmentSummary
from .item19_fpr import FPR, FPRBase, DisclosureType
from .item20_outlets import (
    OutletSummary, OutletSummaryBase, StateCount, StateCountBase, 
    OutletStateSummary, OutletType, validate_state_total
)
from .item21_financials import Financials, FinancialsBase, AuditOpinion

__all__ = [
    # Base
    "Address", "ValidationConfig", "cents_to_dollars", "dollars_to_cents",
    
    # Core models
    "Franchisor", "FranchisorCreate", "FranchisorUpdate", "FranchisorBase",
    "FDD", "FDDCreate", "FDDBase", "DocumentType", "ProcessingStatus",
    "FDDSection", "FDDSectionBase", "ExtractionStatus",
    
    # Structured data models
    "InitialFee", "InitialFeeBase", "DueAt",
    "OtherFee", "OtherFeeBase", "FeeFrequency", "CalculationBasis",
    "InitialInvestment", "InitialInvestmentBase", "InitialInvestmentSummary",
    "FPR", "FPRBase", "DisclosureType",
    "OutletSummary", "OutletSummaryBase", "StateCount", "StateCountBase",
    "OutletStateSummary", "OutletType", "validate_state_total",
    "Financials", "FinancialsBase", "AuditOpinion",
]