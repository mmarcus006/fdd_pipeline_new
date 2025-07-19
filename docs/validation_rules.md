# Validation Rules Documentation

## Overview

The FDD Pipeline implements a three-tier validation system to ensure data quality and consistency:

1. **Schema Validation** - Pydantic models enforce data types, formats, and basic constraints
2. **Business Rules** - Domain-specific logic validates relationships and calculations
3. **Quality Checks** - Statistical and anomaly detection for data quality assurance

## Validation Tiers

### Tier 1: Schema Validation (Automatic)

Applied automatically when creating or updating records through Pydantic models.

| Category | Rules | Implementation |
|----------|-------|----------------|
| **Data Types** | All fields must match defined types | Pydantic type annotations |
| **Required Fields** | Non-optional fields must be present | Pydantic Field() definitions |
| **Format Validation** | Strings match expected patterns | Regex validators |
| **Range Validation** | Numbers within acceptable bounds | Field constraints (ge, le, gt, lt) |
| **Enum Validation** | Values from predefined sets | Enum classes |

### Tier 2: Business Rules (Contextual)

Applied during data processing to ensure business logic compliance.

| Category | Rules | Severity |
|----------|-------|----------|
| **Cross-field Dependencies** | Related fields must be consistent | ERROR |
| **Calculation Validation** | Totals and formulas must balance | ERROR |
| **Temporal Consistency** | Dates must follow logical order | WARNING |
| **Reference Integrity** | Foreign keys must exist | ERROR |
| **Domain Constraints** | Business-specific requirements | VARIES |

### Tier 3: Quality Checks (Statistical)

Applied periodically to identify anomalies and quality issues.

| Category | Rules | Action |
|----------|-------|--------|
| **Outlier Detection** | Values beyond statistical norms | FLAG_FOR_REVIEW |
| **Completeness** | Missing expected data | REPORT |
| **Consistency** | Cross-document validation | INVESTIGATE |
| **Trend Analysis** | Unusual patterns over time | ALERT |

## Field-Specific Validation Rules

### Currency Fields

All monetary values are stored as cents (integer) to avoid floating-point precision issues.

```python
# Validation Rules
- Must be non-negative (except where explicitly allowed)
- Maximum reasonable amounts enforced
- Conversion: dollars * 100 = cents
- Display: cents / 100 = dollars (rounded to 2 decimals)

# Examples
amount_cents: int = Field(..., ge=0)  # Non-negative
revenue_cents: int = Field(..., ge=0, le=10_000_000_000_00)  # Max $10B
```

### Percentage Fields

```python
# Validation Rules
- Range: 0.0 to 100.0 (unless explicitly allowing negative)
- Precision: Up to 2 decimal places
- Storage: As NUMERIC(5,2) in database

# Common Limits
royalty_percentage: float = Field(..., ge=0, le=50)  # Max 50%
marketing_percentage: float = Field(..., ge=0, le=20)  # Max 20%
profit_margin_percentage: float = Field(..., ge=-100, le=100)  # Can be negative
```

### Date Fields

```python
# Validation Rules
- Format: ISO 8601 (YYYY-MM-DD)
- Logical ordering enforced
- Future dates restricted where appropriate

# Examples
issue_date <= amendment_date (if amendment exists)
fiscal_year_end must be within fiscal_year
issue_date cannot be more than 1 year in future
```

### State Codes

```python
# Validation Rules
- Format: 2-letter uppercase (e.g., "CA", "NY")
- Must be valid US state or territory code
- Includes: 50 states + DC + territories (PR, VI, GU, AS, MP)
```

## Item-Specific Validation Rules

### Item 5: Initial Fees

| Field | Validation Rules | Error Handling |
|-------|------------------|----------------|
| `fee_name` | - Required, non-empty<br>- Standardized names preferred | Normalize common variations |
| `amount_cents` | - Non-negative<br>- Maximum: $10M<br>- Must be > 0 for required fees | Reject negative, flag high amounts |
| `refundable` | - If true, `refund_conditions` recommended | Warning if conditions missing |
| `due_at` | - Must be valid enum value<br>- Consistent with fee type | Validate against fee_name |

### Item 6: Other Fees

| Field | Validation Rules | Error Handling |
|-------|------------------|----------------|
| `amount_cents` OR `amount_percentage` | - Exactly one must be set<br>- Not both, not neither | ERROR: Reject invalid combination |
| `frequency` | - Required<br>- Must match fee type logic | Validate royalty=monthly, etc. |
| `minimum_cents`, `maximum_cents` | - Both optional<br>- If both set: max >= min<br>- Non-negative | ERROR if max < min |
| `calculation_basis` | - Required if percentage-based<br>- Must be logical for fee type | ERROR if missing for % fees |

**Special Rule**: Royalty fees should typically be percentage-based on gross/net sales.

### Item 7: Initial Investment

| Field | Validation Rules | Error Handling |
|-------|------------------|----------------|
| `low_cents`, `high_cents` | - At least one required<br>- If both: high >= low<br>- Non-negative<br>- Maximum: $100M | ERROR if high < low |
| `category` | - Required<br>- Standardize common names<br>- No duplicates per section | Normalize variations |
| **Total Investment** | - Sum of all categories<br>- Validate against Item 5 fees | Warning if inconsistent |

**Cross-validation**: Initial franchise fee in Item 7 must match Item 5.

### Item 19: Financial Performance Representations

| Field | Validation Rules | Error Handling |
|-------|------------------|----------------|
| `disclosure_type` | - If "None", most fields should be null<br>- If set, require supporting data | Validate data presence |
| `sample_size` | - Required if metrics provided<br>- Minimum: 5 for credibility<br>- Must be <= total outlets | Warning if < 5 |
| **Revenue Metrics** | - low <= average <= high<br>- low <= median <= high<br>- All non-negative | ERROR if out of order |
| `profit_margin_percentage` | - Range: -100% to 100%<br>- Flag if < -50% or > 50% | Review extreme values |

### Item 20: Outlet Information

#### Outlet Summary Table

| Field | Validation Rules | Error Handling |
|-------|------------------|----------------|
| **Mathematical Balance** | `count_end = count_start + opened - closed + transferred_in - transferred_out` | ERROR if doesn't balance |
| `fiscal_year` | - Range: 1900-current+1<br>- Consecutive years expected | Warning if gaps |
| **All counts** | - Non-negative<br>- Reasonable maximums (< 100,000) | Flag unusual values |

#### State Counts Table

| Field | Validation Rules | Error Handling |
|-------|------------------|----------------|
| `state_code` | - Valid US state/territory<br>- No duplicates per section | ERROR if invalid |
| **Total Validation** | Sum of all states must equal outlet summary totals | ERROR if mismatch |
| **Geographic Logic** | Adjacent states expected for chains | Flag unusual patterns |

### Item 21: Financial Statements

| Field | Validation Rules | Error Handling |
|-------|------------------|----------------|
| **Accounting Equations** | - Assets = Liabilities + Equity<br>- Revenue - COGS = Gross Profit<br>- Allow $1 rounding tolerance | ERROR if > $1 difference |
| **Component Relationships** | - Current assets <= Total assets<br>- Current liabilities <= Total liabilities<br>- Franchise revenue <= Total revenue | ERROR if violated |
| **Audit Requirements** | - If revenue > $50M, expect auditor info<br>- Audit opinion required if auditor present | Warning if missing |
| **Negative Values** | - Assets/Liabilities: Non-negative<br>- Income/Equity: Can be negative<br>- Flag if equity < -$10M | Review large losses |

## Cross-Item Validation Rules

### Consistency Checks

1. **Fee Consistency**
   - Initial franchise fee (Item 5) must appear in Item 7 initial investment
   - Royalty structure (Item 6) should align with revenue assumptions (Item 19)

2. **Outlet Validation**
   - Item 20 total outlets should be consistent with Item 19 sample sizes
   - State counts must sum to total outlet counts

3. **Financial Alignment**
   - Item 21 franchise revenue should align with Item 6 fee structures
   - Item 19 performance data should be reasonable given Item 21 financials

### Temporal Validation

1. **Document Dating**
   ```python
   # Rules
   - Issue date <= Current date + 1 year
   - Amendment date >= Issue date
   - Fiscal year end within fiscal year
   - Historical data shouldn't exceed 10 years
   ```

2. **Data Freshness**
   - Financial statements (Item 21) should be within 2 years
   - Outlet data (Item 20) should include current year or prior year
   - FPR data (Item 19) should be recent (within 3 years)

## Implementation Examples

### Basic Validation Function

```python
def validate_fdd_data(fdd_id: UUID) -> ValidationReport:
    """Comprehensive validation of FDD data"""
    
    errors = []
    warnings = []
    
    # Get all related data
    sections = get_fdd_sections(fdd_id)
    
    for section in sections:
        # Schema validation (automatic via Pydantic)
        try:
            validate_section_schema(section)
        except ValidationError as e:
            errors.append({
                'section_id': section.id,
                'type': 'SCHEMA',
                'errors': e.errors()
            })
        
        # Business rules validation
        business_errors = validate_business_rules(section)
        errors.extend(business_errors)
        
        # Quality checks
        quality_issues = run_quality_checks(section)
        warnings.extend(quality_issues)
    
    # Cross-item validation
    cross_errors = validate_cross_items(sections)
    errors.extend(cross_errors)
    
    return ValidationReport(
        fdd_id=fdd_id,
        errors=errors,
        warnings=warnings,
        validated_at=datetime.now()
    )
```

### Custom Validators

```python
class OutletValidator:
    """Specialized validation for Item 20 outlet data"""
    
    @staticmethod
    def validate_outlet_math(summary: OutletSummary) -> Optional[str]:
        """Validate outlet count mathematics"""
        calculated = (
            summary.count_start + 
            summary.opened - 
            summary.closed + 
            summary.transferred_in - 
            summary.transferred_out
        )
        
        if calculated != summary.count_end:
            return (
                f"Outlet math error: {summary.count_start} + {summary.opened} "
                f"- {summary.closed} + {summary.transferred_in} "
                f"- {summary.transferred_out} = {calculated}, "
                f"but count_end = {summary.count_end}"
            )
        return None
    
    @staticmethod
    def validate_state_totals(
        state_counts: List[StateCount],
        outlet_summary: List[OutletSummary]
    ) -> Optional[str]:
        """Validate state counts match outlet totals"""
        # Implementation as shown in pydantic_models.md
        pass
```

### Anomaly Detection

```python
class AnomalyDetector:
    """Statistical anomaly detection for quality checks"""
    
    @staticmethod
    def check_fee_outliers(fees: List[OtherFee]) -> List[Dict]:
        """Identify unusual fee structures"""
        anomalies = []
        
        # Check royalty fees
        royalty_fees = [f for f in fees if 'royalty' in f.fee_name.lower()]
        for fee in royalty_fees:
            if fee.amount_percentage and fee.amount_percentage > 15:
                anomalies.append({
                    'type': 'HIGH_ROYALTY',
                    'severity': 'WARNING',
                    'message': f'Unusually high royalty: {fee.amount_percentage}%',
                    'fee': fee
                })
        
        return anomalies
    
    @staticmethod
    def check_investment_ranges(items: List[InitialInvestment]) -> List[Dict]:
        """Identify unusual investment ranges"""
        anomalies = []
        
        for item in items:
            if item.low_cents and item.high_cents:
                ratio = item.high_cents / item.low_cents
                if ratio > 10:
                    anomalies.append({
                        'type': 'WIDE_RANGE',
                        'severity': 'INFO',
                        'message': f'Very wide range for {item.category}: {ratio:.1f}x',
                        'item': item
                    })
        
        return anomalies
```

## Validation Severity Levels

| Level | Description | Action Required |
|-------|-------------|-----------------|
| **ERROR** | Data violates core constraints | Block processing, require fix |
| **WARNING** | Unusual but possibly valid | Flag for review, allow processing |
| **INFO** | Notable patterns or outliers | Log for analysis, no action |

## Quality Metrics

### Data Completeness Score

```python
def calculate_completeness_score(fdd_id: UUID) -> float:
    """Calculate % of expected fields populated"""
    
    # Define expected fields by item
    expected = {
        5: ['fee_name', 'amount_cents', 'due_at'],
        6: ['fee_name', 'frequency', 'calculation_basis'],
        7: ['category', 'low_cents', 'high_cents'],
        # ... etc
    }
    
    total_expected = 0
    total_populated = 0
    
    # Calculate completion percentage
    # Implementation details...
    
    return (total_populated / total_expected) * 100
```

### Validation Dashboard Metrics

1. **Schema Validation Pass Rate**: % of records passing Pydantic validation
2. **Business Rule Compliance**: % of records meeting all business rules
3. **Data Quality Score**: Composite score based on completeness, accuracy, consistency
4. **Review Queue Size**: Number of records flagged for manual review
5. **Common Validation Errors**: Top 10 validation failures by frequency

## Best Practices

1. **Fail Fast**: Run schema validation before expensive operations
2. **Batch Validation**: Validate related records together for efficiency
3. **Clear Error Messages**: Include field name, expected value, actual value
4. **Validation Logging**: Track all validation attempts for auditing
5. **Progressive Enhancement**: Start with critical validations, add more over time
6. **Review Feedback Loop**: Update rules based on manual review findings

## Configuration

```yaml
# validation_config.yaml
validation:
  schema:
    enabled: true
    strict_mode: false
    
  business_rules:
    enabled: true
    outlet_math_check: true
    cross_item_validation: true
    
  quality_checks:
    enabled: true
    outlier_detection: true
    statistical_thresholds:
      royalty_fee_max: 15.0
      investment_range_ratio: 10.0
      
  severity_actions:
    ERROR: block_processing
    WARNING: flag_for_review
    INFO: log_only
```

---

**Note**: Validation rules should be regularly reviewed and updated based on:
- New FDD formats or requirements
- Patterns identified in manual reviews
- Business rule changes
- Data quality metrics