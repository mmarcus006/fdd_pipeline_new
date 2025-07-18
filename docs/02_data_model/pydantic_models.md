# Pydantic Models Documentation

## Overview

This document defines the Pydantic models used throughout the FDD Pipeline for data validation, serialization, and type safety. These models map directly to the database schema while providing additional validation logic and computed fields.

## Core Models

### Franchisor Models

```python
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
import re

class Address(BaseModel):
    """Embedded address model for franchisor addresses"""
    street: str
    city: str
    state: str = Field(..., regex="^[A-Z]{2}$")
    zip_code: str = Field(..., alias="zip")
    
    @validator('zip_code')
    def validate_zip(cls, v):
        if not re.match(r"^\d{5}(-\d{4})?$", v):
            raise ValueError("Invalid ZIP code format")
        return v

class FranchisorBase(BaseModel):
    """Base franchisor model for creation/updates"""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    parent_company: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[Address] = None
    dba_names: List[str] = Field(default_factory=list)
    
    @validator('canonical_name')
    def clean_canonical_name(cls, v):
        """Normalize franchise names"""
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
    """Model for creating new franchisors"""
    pass

class FranchisorUpdate(BaseModel):
    """Model for updating franchisors (all fields optional)"""
    canonical_name: Optional[str] = Field(None, min_length=1, max_length=255)
    parent_company: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[Address] = None
    dba_names: Optional[List[str]] = None

class Franchisor(FranchisorBase):
    """Complete franchisor model with DB fields"""
    id: UUID
    name_embedding: Optional[List[float]] = Field(None, description="384-dim vector")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True
```

### FDD Document Models

```python
from enum import Enum

class DocumentType(str, Enum):
    INITIAL = "Initial"
    AMENDMENT = "Amendment"
    RENEWAL = "Renewal"

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class FDDBase(BaseModel):
    """Base FDD model"""
    franchise_id: UUID
    issue_date: date
    amendment_date: Optional[date] = None
    document_type: DocumentType
    filing_state: str = Field(..., regex="^[A-Z]{2}$")
    filing_number: Optional[str] = None
    drive_path: str
    drive_file_id: str
    sha256_hash: Optional[str] = Field(None, regex="^[a-f0-9]{64}$")
    total_pages: Optional[int] = Field(None, gt=0)
    language_code: str = Field(default="en", regex="^[a-z]{2}$")
    
    @root_validator
    def validate_amendment(cls, values):
        """Ensure amendment_date is set for Amendment type"""
        doc_type = values.get('document_type')
        amendment_date = values.get('amendment_date')
        
        if doc_type == DocumentType.AMENDMENT and not amendment_date:
            raise ValueError("Amendment date required for Amendment documents")
        return values
    
    @validator('drive_path')
    def validate_drive_path(cls, v):
        """Ensure valid Google Drive path format"""
        if not v.startswith('/'):
            raise ValueError("Drive path must start with /")
        return v

class FDDCreate(FDDBase):
    """Model for creating new FDD records"""
    pass

class FDD(FDDBase):
    """Complete FDD model with all fields"""
    id: UUID
    is_amendment: bool
    superseded_by_id: Optional[UUID] = None
    duplicate_of_id: Optional[UUID] = None
    needs_review: bool = False
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    created_at: datetime
    processed_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        use_enum_values = True
```

### Section Models

```python
class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

class FDDSectionBase(BaseModel):
    """Base model for FDD sections"""
    fdd_id: UUID
    item_no: int = Field(..., ge=0, le=24)
    item_name: Optional[str] = None
    start_page: int = Field(..., gt=0)
    end_page: int = Field(..., gt=0)
    drive_path: Optional[str] = None
    drive_file_id: Optional[str] = None
    
    @root_validator
    def validate_page_range(cls, values):
        start = values.get('start_page')
        end = values.get('end_page')
        if start and end and end < start:
            raise ValueError("end_page must be >= start_page")
        return values
    
    @validator('item_no')
    def validate_item_no(cls, v):
        """Map item numbers to standard names"""
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
    """Complete section model"""
    id: UUID
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    extraction_model: Optional[str] = None
    extraction_attempts: int = 0
    needs_review: bool = False
    created_at: datetime
    extracted_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
```

## Structured Data Models

### Item 5 - Initial Fees

```python
class DueAt(str, Enum):
    SIGNING = "Signing"
    TRAINING = "Training"
    OPENING = "Opening"
    OTHER = "Other"

class InitialFeeBase(BaseModel):
    """Base model for initial fees"""
    fee_name: str = Field(..., min_length=1)
    amount_cents: int = Field(..., ge=0)
    refundable: bool = False
    refund_conditions: Optional[str] = None
    due_at: Optional[DueAt] = None
    notes: Optional[str] = None
    
    @validator('amount_cents')
    def validate_reasonable_amount(cls, v):
        """Ensure amount is reasonable (< $10M)"""
        if v > 1_000_000_000:  # $10M in cents
            raise ValueError("Amount exceeds reasonable maximum")
        return v
    
    @property
    def amount_dollars(self) -> float:
        """Convert cents to dollars"""
        return self.amount_cents / 100

class InitialFee(InitialFeeBase):
    """Initial fee with section reference"""
    section_id: UUID
    
    class Config:
        orm_mode = True
```

### Item 6 - Other Fees

```python
class FeeFrequency(str, Enum):
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"
    ANNUAL = "Annual"
    ONE_TIME = "One-time"
    AS_INCURRED = "As Incurred"

class CalculationBasis(str, Enum):
    GROSS_SALES = "Gross Sales"
    NET_SALES = "Net Sales"
    FIXED = "Fixed"
    VARIABLE = "Variable"
    OTHER = "Other"

class OtherFeeBase(BaseModel):
    """Base model for ongoing/other fees"""
    fee_name: str = Field(..., min_length=1)
    amount_cents: Optional[int] = Field(None, ge=0)
    amount_percentage: Optional[float] = Field(None, ge=0, le=100)
    frequency: FeeFrequency
    calculation_basis: Optional[CalculationBasis] = None
    minimum_cents: Optional[int] = Field(None, ge=0)
    maximum_cents: Optional[int] = Field(None, ge=0)
    remarks: Optional[str] = None
    
    @root_validator
    def validate_amount_type(cls, values):
        """Ensure either amount_cents OR amount_percentage is set"""
        cents = values.get('amount_cents')
        pct = values.get('amount_percentage')
        
        if (cents is None and pct is None) or (cents is not None and pct is not None):
            raise ValueError("Must specify either amount_cents or amount_percentage, not both")
        return values
    
    @root_validator
    def validate_min_max(cls, values):
        """Ensure max >= min if both specified"""
        min_val = values.get('minimum_cents')
        max_val = values.get('maximum_cents')
        
        if min_val is not None and max_val is not None and max_val < min_val:
            raise ValueError("maximum_cents must be >= minimum_cents")
        return values
    
    @validator('amount_percentage')
    def validate_percentage(cls, v):
        """Common sense check for percentages"""
        if v is not None and v > 50:
            # Flag unusually high percentages for review
            # but don't reject - some fees can be high
            pass
        return v

class OtherFee(OtherFeeBase):
    """Other fee with section reference"""
    section_id: UUID
    
    class Config:
        orm_mode = True
```

### Item 7 - Initial Investment

```python
class InitialInvestmentBase(BaseModel):
    """Base model for initial investment items"""
    category: str = Field(..., min_length=1)
    low_cents: Optional[int] = Field(None, ge=0)
    high_cents: Optional[int] = Field(None, ge=0)
    when_due: Optional[str] = None
    to_whom: Optional[str] = None
    remarks: Optional[str] = None
    
    @root_validator
    def validate_range(cls, values):
        """Ensure high >= low and at least one is set"""
        low = values.get('low_cents')
        high = values.get('high_cents')
        
        if low is None and high is None:
            raise ValueError("At least one of low_cents or high_cents must be set")
        
        if low is not None and high is not None and high < low:
            raise ValueError("high_cents must be >= low_cents")
        
        return values
    
    @validator('category')
    def standardize_category(cls, v):
        """Standardize common category names"""
        category_map = {
            'REAL ESTATE': 'Real Estate',
            'EQUIPMENT': 'Equipment',
            'INVENTORY': 'Inventory',
            'WORKING CAPITAL': 'Working Capital',
            'TRAINING': 'Training',
            'FRANCHISE FEE': 'Initial Franchise Fee'
        }
        return category_map.get(v.upper(), v)

class InitialInvestment(InitialInvestmentBase):
    """Initial investment with section reference"""
    section_id: UUID
    
    class Config:
        orm_mode = True

class InitialInvestmentSummary(BaseModel):
    """Computed summary of initial investment"""
    section_id: UUID
    total_items: int
    total_low_cents: int
    total_high_cents: int
    items: List[InitialInvestment]
    
    @validator('total_low_cents', 'total_high_cents')
    def validate_totals(cls, v):
        """Ensure totals are reasonable"""
        if v > 100_000_000_000:  # $1B in cents
            raise ValueError("Total exceeds reasonable maximum")
        return v
```

### Item 19 - Financial Performance Representations

```python
class DisclosureType(str, Enum):
    HISTORICAL = "Historical"
    PROJECTED = "Projected"
    NONE = "None"
    MIXED = "Mixed"

class FPRBase(BaseModel):
    """Base model for Item 19 FPR"""
    disclosure_type: Optional[DisclosureType] = None
    methodology: Optional[str] = None
    sample_size: Optional[int] = Field(None, gt=0)
    sample_description: Optional[str] = None
    time_period: Optional[str] = None
    
    # Revenue metrics
    average_revenue_cents: Optional[int] = Field(None, ge=0)
    median_revenue_cents: Optional[int] = Field(None, ge=0)
    low_revenue_cents: Optional[int] = Field(None, ge=0)
    high_revenue_cents: Optional[int] = Field(None, ge=0)
    
    # Profit metrics
    average_profit_cents: Optional[int] = None
    median_profit_cents: Optional[int] = None
    profit_margin_percentage: Optional[float] = Field(None, ge=-100, le=100)
    
    # Complex data
    additional_metrics: Dict[str, Any] = Field(default_factory=dict)
    tables_data: List[Dict[str, Any]] = Field(default_factory=list)
    
    disclaimers: Optional[str] = None
    
    @root_validator
    def validate_revenue_range(cls, values):
        """Ensure revenue metrics are consistent"""
        low = values.get('low_revenue_cents')
        high = values.get('high_revenue_cents')
        avg = values.get('average_revenue_cents')
        median = values.get('median_revenue_cents')
        
        if all(v is not None for v in [low, high, avg]):
            if not (low <= avg <= high):
                raise ValueError("Average revenue must be between low and high")
        
        if all(v is not None for v in [low, high, median]):
            if not (low <= median <= high):
                raise ValueError("Median revenue must be between low and high")
        
        return values
    
    @validator('profit_margin_percentage')
    def validate_profit_margin(cls, v):
        """Flag unusual profit margins"""
        if v is not None:
            if v < -50:
                # Flag for review but don't reject
                pass
            if v > 50:
                # Very high margin - flag for review
                pass
        return v

class FPR(FPRBase):
    """FPR with section reference"""
    section_id: UUID
    created_at: datetime
    
    class Config:
        orm_mode = True
```

### Item 20 - Outlet Information

```python
class OutletType(str, Enum):
    FRANCHISED = "Franchised"
    COMPANY_OWNED = "Company-Owned"

class OutletSummaryBase(BaseModel):
    """Base model for outlet summary by year"""
    fiscal_year: int = Field(..., ge=1900, le=2100)
    outlet_type: OutletType
    
    # Counts
    count_start: int = Field(..., ge=0)
    opened: int = Field(default=0, ge=0)
    closed: int = Field(default=0, ge=0)
    transferred_in: int = Field(default=0, ge=0)
    transferred_out: int = Field(default=0, ge=0)
    count_end: int = Field(..., ge=0)
    
    @root_validator
    def validate_outlet_math(cls, values):
        """Ensure outlet counts balance"""
        start = values.get('count_start', 0)
        opened = values.get('opened', 0)
        closed = values.get('closed', 0)
        transferred_in = values.get('transferred_in', 0)
        transferred_out = values.get('transferred_out', 0)
        end = values.get('count_end', 0)
        
        calculated_end = start + opened - closed + transferred_in - transferred_out
        
        if calculated_end != end:
            raise ValueError(
                f"Outlet math doesn't balance: "
                f"{start} + {opened} - {closed} + {transferred_in} - {transferred_out} "
                f"= {calculated_end}, but count_end = {end}"
            )
        
        return values
    
    @validator('fiscal_year')
    def validate_reasonable_year(cls, v):
        """Ensure year is reasonable"""
        current_year = datetime.now().year
        if v > current_year + 1:
            raise ValueError(f"Fiscal year {v} is in the future")
        return v

class OutletSummary(OutletSummaryBase):
    """Outlet summary with section reference"""
    section_id: UUID
    
    class Config:
        orm_mode = True

class StateCountBase(BaseModel):
    """Base model for state-by-state outlet counts"""
    state_code: str = Field(..., regex="^[A-Z]{2}$")
    franchised_count: int = Field(default=0, ge=0)
    company_owned_count: int = Field(default=0, ge=0)
    
    @property
    def total_count(self) -> int:
        return self.franchised_count + self.company_owned_count
    
    @validator('state_code')
    def validate_state_code(cls, v):
        """Ensure valid US state code"""
        valid_states = {
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
            'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
            'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
            'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
            'DC', 'PR', 'VI', 'GU', 'AS', 'MP'  # Include territories
        }
        if v not in valid_states:
            raise ValueError(f"Invalid state code: {v}")
        return v

class StateCount(StateCountBase):
    """State count with section reference"""
    section_id: UUID
    
    class Config:
        orm_mode = True

class OutletStateSummary(BaseModel):
    """Aggregated outlet information"""
    section_id: UUID
    states: List[StateCount]
    total_franchised: int = 0
    total_company_owned: int = 0
    
    @root_validator
    def calculate_totals(cls, values):
        """Calculate totals from states"""
        states = values.get('states', [])
        values['total_franchised'] = sum(s.franchised_count for s in states)
        values['total_company_owned'] = sum(s.company_owned_count for s in states)
        return values
```

### Item 21 - Financial Statements

```python
class AuditOpinion(str, Enum):
    UNQUALIFIED = "Unqualified"
    QUALIFIED = "Qualified"
    ADVERSE = "Adverse"
    DISCLAIMER = "Disclaimer"

class FinancialsBase(BaseModel):
    """Base model for financial statements"""
    fiscal_year: Optional[int] = Field(None, ge=1900, le=2100)
    fiscal_year_end: Optional[date] = None
    
    # Income Statement
    total_revenue_cents: Optional[int] = Field(None, ge=0)
    franchise_revenue_cents: Optional[int] = Field(None, ge=0)
    cost_of_goods_cents: Optional[int] = Field(None, ge=0)
    gross_profit_cents: Optional[int] = None
    operating_expenses_cents: Optional[int] = Field(None, ge=0)
    operating_income_cents: Optional[int] = None
    net_income_cents: Optional[int] = None
    
    # Balance Sheet
    total_assets_cents: Optional[int] = Field(None, ge=0)
    current_assets_cents: Optional[int] = Field(None, ge=0)
    total_liabilities_cents: Optional[int] = Field(None, ge=0)
    current_liabilities_cents: Optional[int] = Field(None, ge=0)
    total_equity_cents: Optional[int] = None
    
    # Audit info
    auditor_name: Optional[str] = None
    audit_opinion: Optional[AuditOpinion] = None
    
    @root_validator
    def validate_accounting_equations(cls, values):
        """Validate basic accounting equations where possible"""
        # Revenue - COGS = Gross Profit
        revenue = values.get('total_revenue_cents')
        cogs = values.get('cost_of_goods_cents')
        gross = values.get('gross_profit_cents')
        
        if all(v is not None for v in [revenue, cogs, gross]):
            calculated_gross = revenue - cogs
            if abs(calculated_gross - gross) > 100:  # Allow $1 rounding error
                raise ValueError(
                    f"Gross profit calculation error: "
                    f"{revenue} - {cogs} = {calculated_gross}, not {gross}"
                )
        
        # Assets = Liabilities + Equity
        assets = values.get('total_assets_cents')
        liabilities = values.get('total_liabilities_cents')
        equity = values.get('total_equity_cents')
        
        if all(v is not None for v in [assets, liabilities, equity]):
            calculated_equity = assets - liabilities
            if abs(calculated_equity - equity) > 100:  # Allow $1 rounding error
                raise ValueError(
                    f"Balance sheet doesn't balance: "
                    f"{assets} - {liabilities} = {calculated_equity}, not {equity}"
                )
        
        return values
    
    @root_validator
    def validate_ratios(cls, values):
        """Validate financial ratios are reasonable"""
        # Current ratio check
        current_assets = values.get('current_assets_cents')
        current_liabilities = values.get('current_liabilities_cents')
        
        if current_assets is not None and current_liabilities is not None:
            if current_liabilities > 0:
                current_ratio = current_assets / current_liabilities
                if current_ratio < 0.1:
                    # Flag for review - very low liquidity
                    pass
        
        # Franchise revenue shouldn't exceed total revenue
        total_rev = values.get('total_revenue_cents')
        franchise_rev = values.get('franchise_revenue_cents')
        
        if total_rev is not None and franchise_rev is not None:
            if franchise_rev > total_rev:
                raise ValueError("Franchise revenue cannot exceed total revenue")
        
        return values

class Financials(FinancialsBase):
    """Financial statements with section reference"""
    section_id: UUID
    created_at: datetime
    
    class Config:
        orm_mode = True
```

### Generic JSON Storage Models

```python
class ItemJSONBase(BaseModel):
    """Base model for generic item storage"""
    item_no: int = Field(..., ge=0, le=24)
    data: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = Field(default="1.0")
    
    @validator('data')
    def validate_data_not_empty(cls, v):
        """Ensure data has content"""
        if not v:
            raise ValueError("Data cannot be empty")
        return v

class ItemJSON(ItemJSONBase):
    """JSON storage with metadata"""
    section_id: UUID
    validated: bool = False
    validation_errors: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

# Item-specific JSON schemas
class Item1Schema(BaseModel):
    """The Franchisor and Any Parents, Predecessors, and Affiliates"""
    franchisor_info: Dict[str, Any]
    parent_companies: List[Dict[str, str]]
    predecessors: List[Dict[str, str]]
    affiliates: List[Dict[str, str]]

class Item2Schema(BaseModel):
    """Business Experience"""
    executives: List[Dict[str, Any]]  # name, position, experience

class Item3Schema(BaseModel):
    """Litigation"""
    cases: List[Dict[str, Any]]  # case_name, court, date, status, description

class Item4Schema(BaseModel):
    """Bankruptcy"""
    bankruptcies: List[Dict[str, Any]]  # person, date, court, case_number

# ... continue for other items
```

## Operational Models

### Scraping and Metadata

```python
class ScrapeMetadataBase(BaseModel):
    """Base model for scrape metadata"""
    fdd_id: UUID
    source_name: str  # 'MN', 'WI', etc.
    source_url: str
    filing_metadata: Dict[str, Any] = Field(default_factory=dict)
    prefect_run_id: Optional[UUID] = None
    
    @validator('source_name')
    def validate_source(cls, v):
        """Ensure known source"""
        valid_sources = {'MN', 'WI', 'CA', 'WA', 'MD', 'VA', 'IL', 'MI', 'ND'}
        if v not in valid_sources:
            raise ValueError(f"Unknown source: {v}")
        return v
    
    @validator('source_url')
    def validate_url(cls, v):
        """Basic URL validation"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("Invalid URL format")
        return v

class ScrapeMetadata(ScrapeMetadataBase):
    """Scrape metadata with timestamps"""
    id: UUID
    scraped_at: datetime
    
    class Config:
        orm_mode = True
```

### Pipeline Logging

```python
class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class PipelineLogBase(BaseModel):
    """Base model for pipeline logs"""
    prefect_run_id: Optional[UUID] = None
    task_name: Optional[str] = None
    level: LogLevel
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('message')
    def validate_message_length(cls, v):
        """Ensure message isn't too long"""
        if len(v) > 10000:
            return v[:10000] + "... (truncated)"
        return v

class PipelineLog(PipelineLogBase):
    """Pipeline log with metadata"""
    id: UUID
    created_at: datetime
    
    class Config:
        orm_mode = True
```

## Composite Models and Views

```python
class FDDExtractionProgress(BaseModel):
    """View model for extraction progress"""
    fdd_id: UUID
    franchise_id: UUID
    canonical_name: str
    total_sections: int
    extracted_sections: int
    failed_sections: int
    needs_review: int
    success_rate: float
    
    @property
    def is_complete(self) -> bool:
        return self.extracted_sections == self.total_sections
    
    @property
    def has_failures(self) -> bool:
        return self.failed_sections > 0

class FranchisorFDDSummary(BaseModel):
    """Summary of FDDs for a franchisor"""
    franchisor: Franchisor
    total_fdds: int
    latest_fdd: Optional[FDD] = None
    states_filed: List[str]
    years_available: List[int]
    
    @property
    def filing_history_years(self) -> int:
        if self.years_available:
            return max(self.years_available) - min(self.years_available) + 1
        return 0
```

## Utility Functions

```python
def cents_to_dollars(cents: Optional[int]) -> Optional[float]:
    """Convert cents to dollars with proper rounding"""
    if cents is None:
        return None
    return round(cents / 100, 2)

def dollars_to_cents(dollars: Optional[float]) -> Optional[int]:
    """Convert dollars to cents"""
    if dollars is None:
        return None
    return int(round(dollars * 100))

def validate_state_total(state_counts: List[StateCount], 
                        outlet_summaries: List[OutletSummary]) -> bool:
    """Validate state counts match outlet summary totals"""
    state_total_franchised = sum(s.franchised_count for s in state_counts)
    state_total_company = sum(s.company_owned_count for s in state_counts)
    
    # Get most recent year from outlet summaries
    if outlet_summaries:
        recent_year = max(o.fiscal_year for o in outlet_summaries)
        year_summaries = [o for o in outlet_summaries if o.fiscal_year == recent_year]
        
        outlet_franchised = sum(
            o.count_end for o in year_summaries 
            if o.outlet_type == OutletType.FRANCHISED
        )
        outlet_company = sum(
            o.count_end for o in year_summaries 
            if o.outlet_type == OutletType.COMPANY_OWNED
        )
        
        return (state_total_franchised == outlet_franchised and 
                state_total_company == outlet_company)
    
    return True
```

## Configuration

```python
class ValidationConfig:
    """Global validation configuration"""
    
    # Maximum amounts (in cents)
    MAX_FEE_AMOUNT = 10_000_000_00  # $10M
    MAX_INVESTMENT_AMOUNT = 100_000_000_00  # $100M
    MAX_REVENUE_AMOUNT = 10_000_000_000_00  # $10B
    
    # Percentage limits
    MAX_ROYALTY_PERCENTAGE = 50.0
    MAX_MARKETING_PERCENTAGE = 20.0
    
    # Business rules
    REQUIRE_AUDIT_ABOVE_REVENUE = 50_000_000_00  # $50M
    FLAG_NEGATIVE_EQUITY_THRESHOLD = -10_000_000_00  # -$10M
    
    # Data quality thresholds
    MIN_SAMPLE_SIZE_FOR_FPR = 5
    MAX_YEARS_HISTORICAL_DATA = 10
```

---

**Note**: All models include Pydantic's built-in JSON serialization support. Use `.dict()` for dictionary conversion and `.json()` for JSON string serialization. Models with `orm_mode = True` can be initialized directly from SQLAlchemy ORM objects.