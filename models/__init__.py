"""FDD Pipeline Models."""

# Core models
from .base import Address, ValidationConfig, cents_to_dollars, dollars_to_cents
from .franchisor import Franchisor, FranchisorCreate, FranchisorUpdate, FranchisorBase
from .fdd import FDD, FDDCreate, FDDBase, DocumentType, ProcessingStatus
from .section import FDDSection, FDDSectionBase, ExtractionStatus

# Structured data models
from .item5_fees import Item5Fee, Item5FeesResponse, InitialFeeDiscount, AdditionalFee
from .base_items import FeeFrequency, CalculationBasis, DiscountType, ValidationStatus
from .item6_other_fees import Item6OtherFee, OtherFeeStructure, Item6OtherFeesResponse
from .item7_investment import (
    InvestmentCategory,
    Item7Investment,
    InvestmentItem,
    Item7InvestmentResponse,
    InvestmentSummary,
)
from .item19_fpr import FPRTable, Item19FPR, Item19FPRResponse
from .item20_outlets import (
    OutletType,
    OutletSummary,
    StateCount,
    OutletTable,
    Item20OutletsResponse,
)
from .item21_financials import (
    AuditOpinion,
    StatementType,
    Financials,
    FinancialTable,
    Item21FinancialsResponse,
)

# Operational models
from .scrape_metadata import ScrapeMetadata, ScrapeMetadataBase, ScrapeMetadataCreate, ScrapeStatus
from .drive_files import DriveFile, DriveFileCreate, SyncStatus
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
    "Item5Fee",
    "Item5FeesResponse",
    "InitialFeeDiscount",
    "AdditionalFee",
    "FeeFrequency",
    "CalculationBasis",
    "DiscountType",
    "ValidationStatus",
    "Item6OtherFee",
    "OtherFeeStructure",
    "Item6OtherFeesResponse",
    "InvestmentCategory",
    "Item7Investment",
    "InvestmentItem",
    "Item7InvestmentResponse",
    "InvestmentSummary",
    "FPRTable",
    "Item19FPR",
    "Item19FPRResponse",
    "OutletType",
    "OutletSummary",
    "StateCount",
    "OutletTable",
    "Item20OutletsResponse",
    "AuditOpinion",
    "StatementType",
    "Financials",
    "FinancialTable",
    "Item21FinancialsResponse",
    # Operational models
    "ScrapeMetadata",
    "ScrapeMetadataBase",
    "ScrapeMetadataCreate",
    "ScrapeStatus",
    "DriveFile",
    "DriveFileCreate",
    "SyncStatus",
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
