"""FDD Pipeline Models."""

# Core models
from .base import Address, ValidationConfig, cents_to_dollars, dollars_to_cents
from .franchisor import Franchisor, FranchisorCreate, FranchisorUpdate, FranchisorBase
from .fdd import FDD, FDDCreate, FDDBase, DocumentType, ProcessingStatus
from .section import FDDSection, FDDSectionBase, ExtractionStatus

# Structured data models
from .item5_fees import InitialFee, InitialFeeBase, DueAt
from .item6_other_fees import OtherFee, OtherFeeBase, FeeFrequency, CalculationBasis
from .item7_investment import (
    InitialInvestment,
    InitialInvestmentBase,
    InitialInvestmentSummary,
)
from .item19_fpr import FPR, FPRBase, DisclosureType
from .item20_outlets import (
    OutletSummary,
    OutletSummaryBase,
    StateCount,
    StateCountBase,
    OutletStateSummary,
    OutletType,
    validate_state_total,
    calculate_outlet_growth_rate,
)
from .item21_financials import Financials, FinancialsBase, AuditOpinion

# Operational models
from .scrape_metadata import ScrapeMetadata, ScrapeMetadataBase
from .pipeline_log import (
    PipelineLog,
    PipelineLogBase,
    PrefectRun,
    PrefectRunBase,
    LogLevel,
)

# Generic JSON storage
from .item_json import (
    ItemJSON,
    ItemJSONBase,
    Item1Schema,
    Item2Schema,
    Item3Schema,
    Item4Schema,
    Item8Schema,
    Item9Schema,
    Item10Schema,
    Item11Schema,
    Item12Schema,
    Item13Schema,
    Item14Schema,
    Item15Schema,
    Item16Schema,
    Item17Schema,
    Item18Schema,
    Item22Schema,
    Item23Schema,
    Item24Schema,
)

# Composite models
from .composite import (
    FDDExtractionProgress,
    FranchisorFDDSummary,
    SystemHealthSummary,
    ExtractionQualityMetrics,
)

__all__ = [
    # Base
    "Address",
    "ValidationConfig",
    "cents_to_dollars",
    "dollars_to_cents",
    # Core models
    "Franchisor",
    "FranchisorCreate",
    "FranchisorUpdate",
    "FranchisorBase",
    "FDD",
    "FDDCreate",
    "FDDBase",
    "DocumentType",
    "ProcessingStatus",
    "FDDSection",
    "FDDSectionBase",
    "ExtractionStatus",
    # Structured data models
    "InitialFee",
    "InitialFeeBase",
    "DueAt",
    "OtherFee",
    "OtherFeeBase",
    "FeeFrequency",
    "CalculationBasis",
    "InitialInvestment",
    "InitialInvestmentBase",
    "InitialInvestmentSummary",
    "FPR",
    "FPRBase",
    "DisclosureType",
    "OutletSummary",
    "OutletSummaryBase",
    "StateCount",
    "StateCountBase",
    "OutletStateSummary",
    "OutletType",
    "validate_state_total",
    "calculate_outlet_growth_rate",
    "Financials",
    "FinancialsBase",
    "AuditOpinion",
    # Operational models
    "ScrapeMetadata",
    "ScrapeMetadataBase",
    "PipelineLog",
    "PipelineLogBase",
    "PrefectRun",
    "PrefectRunBase",
    "LogLevel",
    # Generic JSON storage
    "ItemJSON",
    "ItemJSONBase",
    "Item1Schema",
    "Item2Schema",
    "Item3Schema",
    "Item4Schema",
    "Item8Schema",
    "Item9Schema",
    "Item10Schema",
    "Item11Schema",
    "Item12Schema",
    "Item13Schema",
    "Item14Schema",
    "Item15Schema",
    "Item16Schema",
    "Item17Schema",
    "Item18Schema",
    "Item22Schema",
    "Item23Schema",
    "Item24Schema",
    # Composite models
    "FDDExtractionProgress",
    "FranchisorFDDSummary",
    "SystemHealthSummary",
    "ExtractionQualityMetrics",
]
