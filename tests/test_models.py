"""Unit tests for Pydantic models."""

import pytest
from datetime import datetime, date
from uuid import uuid4
from pydantic import ValidationError

from models import (
    # Core models
    Franchisor,
    FranchisorCreate,
    FranchisorUpdate,
    Address,
    FDD,
    FDDCreate,
    DocumentType,
    ProcessingStatus,
    FDDSection,
    ExtractionStatus,
    # Structured data models
    InitialFee,
    DueAt,
    OtherFee,
    FeeFrequency,
    CalculationBasis,
    InitialInvestment,
    InitialInvestmentSummary,
    FPR,
    DisclosureType,
    OutletSummary,
    OutletType,
    StateCount,
    validate_state_total,
    calculate_outlet_growth_rate,
    Financials,
    AuditOpinion,
    # Operational models
    ScrapeMetadata,
    PipelineLog,
    LogLevel,
    # Generic JSON storage
    ItemJSON,
    Item1Schema,
    Item2Schema,
    Item3Schema,
    # Composite models
    FDDExtractionProgress,
    FranchisorFDDSummary,
    # Utilities
    cents_to_dollars,
    dollars_to_cents,
    ValidationConfig,
)


class TestUtilityFunctions:
    """Test utility functions."""

    def test_cents_to_dollars(self):
        assert cents_to_dollars(100) == 1.0
        assert cents_to_dollars(150) == 1.5
        assert cents_to_dollars(None) is None
        assert cents_to_dollars(0) == 0.0

    def test_dollars_to_cents(self):
        assert dollars_to_cents(1.0) == 100
        assert dollars_to_cents(1.5) == 150
        assert dollars_to_cents(None) is None
        assert dollars_to_cents(0.0) == 0


class TestAddress:
    """Test Address model."""

    def test_valid_address(self):
        addr = Address(street="123 Main St", city="Anytown", state="CA", zip="12345")
        assert addr.street == "123 Main St"
        assert addr.state == "CA"
        assert addr.zip_code == "12345"

    def test_invalid_state(self):
        with pytest.raises(ValidationError):
            Address(
                street="123 Main St",
                city="Anytown",
                state="California",  # Should be 2-letter code
                zip="12345",
            )

    def test_invalid_zip(self):
        with pytest.raises(ValidationError):
            Address(
                street="123 Main St",
                city="Anytown",
                state="CA",
                zip="1234",  # Too short
            )


class TestFranchisor:
    """Test Franchisor models."""

    def test_franchisor_create_valid(self):
        franchisor = FranchisorCreate(
            canonical_name="McDonald's Corporation",
            website="mcdonalds.com",
            phone="1234567890",
            email="info@mcdonalds.com",
        )
        assert franchisor.canonical_name == "Mcdonald'S Corporation"  # Title case
        assert franchisor.website == "https://mcdonalds.com"  # Auto-prefix
        assert franchisor.phone == "(123) 456-7890"  # Formatted

    def test_franchisor_phone_validation(self):
        # Valid 10-digit
        f1 = FranchisorCreate(canonical_name="Test", phone="1234567890")
        assert f1.phone == "(123) 456-7890"

        # Valid 11-digit with country code
        f2 = FranchisorCreate(canonical_name="Test", phone="11234567890")
        assert f2.phone == "+1 (123) 456-7890"

        # Invalid phone
        with pytest.raises(ValidationError):
            FranchisorCreate(canonical_name="Test", phone="123")

    def test_franchisor_email_validation(self):
        # Valid email
        f1 = FranchisorCreate(canonical_name="Test", email="test@example.com")
        assert f1.email == "test@example.com"

        # Invalid email
        with pytest.raises(ValidationError):
            FranchisorCreate(canonical_name="Test", email="invalid-email")


class TestFDD:
    """Test FDD models."""

    def test_fdd_create_valid(self):
        fdd = FDDCreate(
            franchise_id=uuid4(),
            issue_date=date(2023, 1, 1),
            document_type=DocumentType.INITIAL,
            filing_state="CA",
            drive_path="/fdds/test.pdf",
            drive_file_id="abc123",
        )
        assert fdd.document_type == DocumentType.INITIAL
        assert fdd.filing_state == "CA"

    def test_amendment_validation(self):
        # Amendment must have amendment_date
        with pytest.raises(ValidationError):
            FDDCreate(
                franchise_id=uuid4(),
                issue_date=date(2023, 1, 1),
                document_type=DocumentType.AMENDMENT,  # Missing amendment_date
                filing_state="CA",
                drive_path="/fdds/test.pdf",
                drive_file_id="abc123",
            )

        # Valid amendment
        fdd = FDDCreate(
            franchise_id=uuid4(),
            issue_date=date(2023, 1, 1),
            amendment_date=date(2023, 6, 1),
            document_type=DocumentType.AMENDMENT,
            filing_state="CA",
            drive_path="/fdds/test.pdf",
            drive_file_id="abc123",
        )
        assert fdd.amendment_date == date(2023, 6, 1)

    def test_drive_path_validation(self):
        with pytest.raises(ValidationError):
            FDDCreate(
                franchise_id=uuid4(),
                issue_date=date(2023, 1, 1),
                document_type=DocumentType.INITIAL,
                filing_state="CA",
                drive_path="fdds/test.pdf",  # Must start with /
                drive_file_id="abc123",
            )


class TestFDDSection:
    """Test FDD Section models."""

    def test_section_valid(self):
        section = FDDSection(
            id=uuid4(),
            fdd_id=uuid4(),
            item_no=5,
            start_page=10,
            end_page=15,
            created_at=datetime.now(),
        )
        assert section.item_no == 5
        assert section.extraction_status == ExtractionStatus.PENDING

    def test_page_range_validation(self):
        with pytest.raises(ValidationError):
            FDDSection(
                id=uuid4(),
                fdd_id=uuid4(),
                item_no=5,
                start_page=15,
                end_page=10,  # end < start
                created_at=datetime.now(),
            )

    def test_item_no_bounds(self):
        # Valid range
        section = FDDSection(
            id=uuid4(),
            fdd_id=uuid4(),
            item_no=0,
            start_page=1,
            end_page=5,
            created_at=datetime.now(),
        )
        assert section.item_no == 0

        # Invalid - too high
        with pytest.raises(ValidationError):
            FDDSection(
                id=uuid4(),
                fdd_id=uuid4(),
                item_no=25,  # Max is 24
                start_page=1,
                end_page=5,
                created_at=datetime.now(),
            )


class TestInitialFee:
    """Test Initial Fee models."""

    def test_initial_fee_valid(self):
        fee = InitialFee(
            section_id=uuid4(),
            fee_name="Initial Franchise Fee",
            amount_cents=5000000,  # $50,000
            refundable=False,
            due_at=DueAt.SIGNING,
        )
        assert fee.amount_dollars == 50000.0
        assert fee.due_at == DueAt.SIGNING

    def test_amount_validation(self):
        # Valid amount
        fee = InitialFee(section_id=uuid4(), fee_name="Test Fee", amount_cents=100000)
        assert fee.amount_cents == 100000

        # Negative amount should fail
        with pytest.raises(ValidationError):
            InitialFee(section_id=uuid4(), fee_name="Test Fee", amount_cents=-1000)

        # Excessive amount should fail
        with pytest.raises(ValidationError):
            InitialFee(
                section_id=uuid4(),
                fee_name="Test Fee",
                amount_cents=ValidationConfig.MAX_FEE_AMOUNT + 1,
            )


class TestOtherFee:
    """Test Other Fee models."""

    def test_other_fee_with_cents(self):
        fee = OtherFee(
            section_id=uuid4(),
            fee_name="Royalty Fee",
            amount_cents=500,
            frequency=FeeFrequency.MONTHLY,
            calculation_basis=CalculationBasis.FIXED,
        )
        assert fee.amount_cents == 500
        assert fee.amount_percentage is None

    def test_other_fee_with_percentage(self):
        fee = OtherFee(
            section_id=uuid4(),
            fee_name="Royalty Fee",
            amount_percentage=5.0,
            frequency=FeeFrequency.MONTHLY,
            calculation_basis=CalculationBasis.GROSS_SALES,
        )
        assert fee.amount_percentage == 5.0
        assert fee.amount_cents is None

    def test_amount_validation(self):
        # Must have either cents or percentage, not both
        with pytest.raises(ValidationError):
            OtherFee(
                section_id=uuid4(),
                fee_name="Test Fee",
                amount_cents=500,
                amount_percentage=5.0,  # Can't have both
                frequency=FeeFrequency.MONTHLY,
            )

        # Must have at least one
        with pytest.raises(ValidationError):
            OtherFee(
                section_id=uuid4(), fee_name="Test Fee", frequency=FeeFrequency.MONTHLY
            )

    def test_min_max_validation(self):
        # Valid min/max
        fee = OtherFee(
            section_id=uuid4(),
            fee_name="Test Fee",
            amount_percentage=5.0,
            frequency=FeeFrequency.MONTHLY,
            minimum_cents=10000,
            maximum_cents=50000,
        )
        assert fee.minimum_cents == 10000

        # Invalid - max < min
        with pytest.raises(ValidationError):
            OtherFee(
                section_id=uuid4(),
                fee_name="Test Fee",
                amount_percentage=5.0,
                frequency=FeeFrequency.MONTHLY,
                minimum_cents=50000,
                maximum_cents=10000,  # max < min
            )


class TestInitialInvestment:
    """Test Initial Investment models."""

    def test_initial_investment_valid(self):
        investment = InitialInvestment(
            section_id=uuid4(),
            category="Equipment",
            low_cents=10000000,  # $100k
            high_cents=50000000,  # $500k
            when_due="Before Opening",
            to_whom="Equipment Suppliers",
        )
        assert investment.category == "Equipment"
        assert investment.low_cents == 10000000

    def test_range_validation(self):
        # Valid range
        investment = InitialInvestment(
            section_id=uuid4(), category="Test", low_cents=10000, high_cents=20000
        )
        assert investment.high_cents == 20000

        # Invalid - high < low
        with pytest.raises(ValidationError):
            InitialInvestment(
                section_id=uuid4(), category="Test", low_cents=20000, high_cents=10000
            )

        # Must have at least one value
        with pytest.raises(ValidationError):
            InitialInvestment(section_id=uuid4(), category="Test")

    def test_category_standardization(self):
        investment = InitialInvestment(
            section_id=uuid4(), category="REAL ESTATE", low_cents=100000
        )
        assert investment.category == "Real Estate"


class TestOutletSummary:
    """Test Outlet Summary models."""

    def test_outlet_summary_valid(self):
        summary = OutletSummary(
            section_id=uuid4(),
            fiscal_year=2023,
            outlet_type=OutletType.FRANCHISED,
            count_start=100,
            opened=10,
            closed=5,
            transferred_in=2,
            transferred_out=3,
            count_end=104,  # 100 + 10 - 5 + 2 - 3
        )
        assert summary.count_end == 104

    def test_outlet_math_validation(self):
        # Valid math
        summary = OutletSummary(
            section_id=uuid4(),
            fiscal_year=2023,
            outlet_type=OutletType.FRANCHISED,
            count_start=100,
            opened=10,
            closed=5,
            count_end=105,  # 100 + 10 - 5
        )
        assert summary.count_end == 105

        # Invalid math
        with pytest.raises(ValidationError):
            OutletSummary(
                section_id=uuid4(),
                fiscal_year=2023,
                outlet_type=OutletType.FRANCHISED,
                count_start=100,
                opened=10,
                closed=5,
                count_end=110,  # Wrong calculation
            )

    def test_future_year_validation(self):
        current_year = datetime.now().year

        # Future year should fail
        with pytest.raises(ValidationError):
            OutletSummary(
                section_id=uuid4(),
                fiscal_year=current_year + 2,
                outlet_type=OutletType.FRANCHISED,
                count_start=100,
                count_end=100,
            )


class TestStateCount:
    """Test State Count models."""

    def test_state_count_valid(self):
        state = StateCount(
            section_id=uuid4(),
            state_code="CA",
            franchised_count=50,
            company_owned_count=10,
        )
        assert state.total_count == 60

    def test_state_code_validation(self):
        # Valid state
        state = StateCount(section_id=uuid4(), state_code="TX", franchised_count=25)
        assert state.state_code == "TX"

        # Invalid state code
        with pytest.raises(ValidationError):
            StateCount(
                section_id=uuid4(), state_code="XX", franchised_count=25  # Invalid
            )


class TestFinancials:
    """Test Financial models."""

    def test_financials_valid(self):
        financials = Financials(
            section_id=uuid4(),
            fiscal_year=2023,
            total_revenue_cents=100000000,  # $1M
            cost_of_goods_cents=60000000,  # $600k
            gross_profit_cents=40000000,  # $400k
            total_assets_cents=200000000,  # $2M
            total_liabilities_cents=120000000,  # $1.2M
            total_equity_cents=80000000,  # $800k
            created_at=datetime.now(),
        )
        assert financials.total_revenue_cents == 100000000

    def test_gross_profit_validation(self):
        # Valid calculation
        financials = Financials(
            section_id=uuid4(),
            total_revenue_cents=100000000,
            cost_of_goods_cents=60000000,
            gross_profit_cents=40000000,  # 100M - 60M = 40M
            created_at=datetime.now(),
        )
        assert financials.gross_profit_cents == 40000000

        # Invalid calculation
        with pytest.raises(ValidationError):
            Financials(
                section_id=uuid4(),
                total_revenue_cents=100000000,
                cost_of_goods_cents=60000000,
                gross_profit_cents=50000000,  # Wrong: should be 40M
                created_at=datetime.now(),
            )

    def test_balance_sheet_validation(self):
        # Valid balance sheet
        financials = Financials(
            section_id=uuid4(),
            total_assets_cents=200000000,
            total_liabilities_cents=120000000,
            total_equity_cents=80000000,  # 200M - 120M = 80M
            created_at=datetime.now(),
        )
        assert financials.total_equity_cents == 80000000

        # Invalid balance sheet
        with pytest.raises(ValidationError):
            Financials(
                section_id=uuid4(),
                total_assets_cents=200000000,
                total_liabilities_cents=120000000,
                total_equity_cents=90000000,  # Wrong: should be 80M
                created_at=datetime.now(),
            )

    def test_franchise_revenue_validation(self):
        # Franchise revenue can't exceed total revenue
        with pytest.raises(ValidationError):
            Financials(
                section_id=uuid4(),
                total_revenue_cents=100000000,
                franchise_revenue_cents=150000000,  # Exceeds total
                created_at=datetime.now(),
            )


class TestScrapeMetadata:
    """Test Scrape Metadata models."""

    def test_scrape_metadata_valid(self):
        metadata = ScrapeMetadata(
            id=uuid4(),
            fdd_id=uuid4(),
            source_name="MN",
            source_url="https://example.com/fdd",
            scraped_at=datetime.now(),
        )
        assert metadata.source_name == "MN"

    def test_source_validation(self):
        # Valid source
        metadata = ScrapeMetadata(
            id=uuid4(),
            fdd_id=uuid4(),
            source_name="WI",
            source_url="https://example.com",
            scraped_at=datetime.now(),
        )
        assert metadata.source_name == "WI"

        # Invalid source
        with pytest.raises(ValidationError):
            ScrapeMetadata(
                id=uuid4(),
                fdd_id=uuid4(),
                source_name="INVALID",
                source_url="https://example.com",
                scraped_at=datetime.now(),
            )

    def test_url_validation(self):
        # Valid URL
        metadata = ScrapeMetadata(
            id=uuid4(),
            fdd_id=uuid4(),
            source_name="MN",
            source_url="https://example.com",
            scraped_at=datetime.now(),
        )
        assert metadata.source_url == "https://example.com"

        # Invalid URL
        with pytest.raises(ValidationError):
            ScrapeMetadata(
                id=uuid4(),
                fdd_id=uuid4(),
                source_name="MN",
                source_url="not-a-url",
                scraped_at=datetime.now(),
            )


class TestPipelineLog:
    """Test Pipeline Log models."""

    def test_pipeline_log_valid(self):
        log = PipelineLog(
            id=uuid4(),
            level=LogLevel.INFO,
            message="Test message",
            created_at=datetime.now(),
        )
        assert log.level == LogLevel.INFO
        assert log.message == "Test message"

    def test_message_truncation(self):
        long_message = "x" * 15000  # Longer than 10k limit
        log = PipelineLog(
            id=uuid4(),
            level=LogLevel.INFO,
            message=long_message,
            created_at=datetime.now(),
        )
        assert len(log.message) <= 10020  # 10000 + "... (truncated)" with some buffer
        assert log.message.endswith("... (truncated)")


class TestFPR:
    """Test FPR (Financial Performance Representations) models."""

    def test_fpr_valid(self):
        fpr = FPR(
            section_id=uuid4(),
            disclosure_type=DisclosureType.HISTORICAL,
            methodology="Based on actual results",
            sample_size=50,
            time_period="2022",
            average_revenue_cents=100000000,  # $1M
            median_revenue_cents=90000000,  # $900k
            low_revenue_cents=50000000,  # $500k
            high_revenue_cents=200000000,  # $2M
            profit_margin_percentage=15.0,
            created_at=datetime.now(),
        )
        assert fpr.disclosure_type == DisclosureType.HISTORICAL
        assert fpr.average_revenue_cents == 100000000

    def test_fpr_revenue_range_validation(self):
        # Valid range - average between low and high
        fpr = FPR(
            section_id=uuid4(),
            low_revenue_cents=50000000,
            high_revenue_cents=200000000,
            average_revenue_cents=100000000,  # Between 50M and 200M
            created_at=datetime.now(),
        )
        assert fpr.average_revenue_cents == 100000000

        # Invalid - average outside range
        with pytest.raises(ValidationError):
            FPR(
                section_id=uuid4(),
                low_revenue_cents=50000000,
                high_revenue_cents=200000000,
                average_revenue_cents=250000000,  # Above high
                created_at=datetime.now(),
            )

        # Invalid - median outside range
        with pytest.raises(ValidationError):
            FPR(
                section_id=uuid4(),
                low_revenue_cents=50000000,
                high_revenue_cents=200000000,
                median_revenue_cents=30000000,  # Below low
                created_at=datetime.now(),
            )

    def test_fpr_profit_margin_validation(self):
        # Valid profit margin
        fpr = FPR(
            section_id=uuid4(), profit_margin_percentage=25.0, created_at=datetime.now()
        )
        assert fpr.profit_margin_percentage == 25.0

        # Extreme values should not raise errors but may be flagged
        fpr_negative = FPR(
            section_id=uuid4(),
            profit_margin_percentage=-75.0,  # Very negative
            created_at=datetime.now(),
        )
        assert fpr_negative.profit_margin_percentage == -75.0

        fpr_high = FPR(
            section_id=uuid4(),
            profit_margin_percentage=75.0,  # Very high
            created_at=datetime.now(),
        )
        assert fpr_high.profit_margin_percentage == 75.0


class TestItemJSON:
    """Test ItemJSON models."""

    def test_item_json_valid(self):
        item_json = ItemJSON(
            section_id=uuid4(),
            item_no=1,
            data={"franchisor_info": {"name": "Test Franchise"}},
            schema_version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert item_json.item_no == 1
        assert item_json.validated == False

    def test_item_json_empty_data_validation(self):
        # Empty data should fail
        with pytest.raises(ValidationError):
            ItemJSON(
                section_id=uuid4(),
                item_no=1,
                data={},  # Empty data
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

    def test_item_no_bounds(self):
        # Valid range
        item_json = ItemJSON(
            section_id=uuid4(),
            item_no=24,  # Max value
            data={"test": "data"},
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert item_json.item_no == 24

        # Invalid - too high
        with pytest.raises(ValidationError):
            ItemJSON(
                section_id=uuid4(),
                item_no=25,  # Above max
                data={"test": "data"},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )


class TestItemSchemas:
    """Test item-specific schema models."""

    def test_item1_schema(self):
        schema = Item1Schema(
            franchisor_info={"name": "Test Corp", "address": "123 Main St"},
            parent_companies=[{"name": "Parent Corp", "relationship": "Parent"}],
            predecessors=[{"name": "Old Corp", "year": "2020"}],
            affiliates=[{"name": "Sister Corp", "relationship": "Affiliate"}],
        )
        assert schema.franchisor_info["name"] == "Test Corp"
        assert len(schema.parent_companies) == 1

    def test_item2_schema(self):
        schema = Item2Schema(
            executives=[
                {"name": "John Doe", "position": "CEO", "experience": "10 years"},
                {"name": "Jane Smith", "position": "COO", "experience": "8 years"},
            ]
        )
        assert len(schema.executives) == 2
        assert schema.executives[0]["name"] == "John Doe"

    def test_item3_schema(self):
        schema = Item3Schema(
            cases=[
                {
                    "case_name": "Smith v. Franchise Corp",
                    "court": "Superior Court",
                    "date": "2023-01-15",
                    "status": "Settled",
                    "description": "Contract dispute",
                }
            ]
        )
        assert len(schema.cases) == 1
        assert schema.cases[0]["status"] == "Settled"


class TestCompositeModels:
    """Test composite models and views."""

    def test_fdd_extraction_progress(self):
        progress = FDDExtractionProgress(
            fdd_id=uuid4(),
            franchise_id=uuid4(),
            canonical_name="Test Franchise",
            total_sections=25,
            extracted_sections=20,
            failed_sections=2,
            needs_review=3,
            success_rate=80.0,
        )
        assert progress.is_complete == False  # 20/25 not complete
        assert progress.has_failures == True  # 2 failed sections

    def test_fdd_extraction_progress_complete(self):
        progress = FDDExtractionProgress(
            fdd_id=uuid4(),
            franchise_id=uuid4(),
            canonical_name="Test Franchise",
            total_sections=25,
            extracted_sections=25,
            failed_sections=0,
            needs_review=0,
            success_rate=100.0,
        )
        assert progress.is_complete == True
        assert progress.has_failures == False

    def test_franchisor_fdd_summary(self):
        franchisor = Franchisor(
            id=uuid4(),
            canonical_name="Test Franchise",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        summary = FranchisorFDDSummary(
            franchisor=franchisor,
            total_fdds=5,
            states_filed=["CA", "TX", "NY"],
            years_available=[2020, 2021, 2022, 2023],
        )
        assert summary.filing_history_years == 4  # 2023 - 2020 + 1
        assert len(summary.states_filed) == 3


class TestValidateStateTotal:
    """Test state total validation function."""

    def test_validate_state_total_valid(self):
        section_id = uuid4()

        state_counts = [
            StateCount(
                section_id=section_id,
                state_code="CA",
                franchised_count=50,
                company_owned_count=10,
            ),
            StateCount(
                section_id=section_id,
                state_code="TX",
                franchised_count=30,
                company_owned_count=5,
            ),
        ]

        outlet_summaries = [
            OutletSummary(
                section_id=section_id,
                fiscal_year=2023,
                outlet_type=OutletType.FRANCHISED,
                count_start=75,
                opened=5,
                count_end=80,
            ),
            OutletSummary(
                section_id=section_id,
                fiscal_year=2023,
                outlet_type=OutletType.COMPANY_OWNED,
                count_start=10,
                opened=5,
                count_end=15,
            ),
        ]

        # State totals: 80 franchised, 15 company-owned
        # Outlet totals: 80 franchised, 15 company-owned
        assert validate_state_total(state_counts, outlet_summaries) == True

    def test_validate_state_total_invalid(self):
        section_id = uuid4()

        state_counts = [
            StateCount(
                section_id=section_id,
                state_code="CA",
                franchised_count=50,
                company_owned_count=10,
            )
        ]

        outlet_summaries = [
            OutletSummary(
                section_id=section_id,
                fiscal_year=2023,
                outlet_type=OutletType.FRANCHISED,
                count_start=40,
                opened=5,
                count_end=45,  # Doesn't match state count of 50
            )
        ]

        assert validate_state_total(state_counts, outlet_summaries) == False

    def test_calculate_outlet_growth_rate(self):
        section_id = uuid4()

        # Test with growth (valid outlet math)
        summaries = [
            OutletSummary(
                section_id=section_id,
                fiscal_year=2022,
                outlet_type=OutletType.FRANCHISED,
                count_start=100,
                opened=0,
                closed=0,
                count_end=100,
            ),
            OutletSummary(
                section_id=section_id,
                fiscal_year=2023,
                outlet_type=OutletType.FRANCHISED,
                count_start=100,
                opened=10,  # 10 new outlets
                closed=0,
                count_end=110,  # 10% growth
            ),
        ]

        growth_rate = calculate_outlet_growth_rate(summaries)
        assert growth_rate == 10.0

        # Test with decline (valid outlet math)
        summaries_decline = [
            OutletSummary(
                section_id=section_id,
                fiscal_year=2022,
                outlet_type=OutletType.FRANCHISED,
                count_start=100,
                opened=0,
                closed=0,
                count_end=100,
            ),
            OutletSummary(
                section_id=section_id,
                fiscal_year=2023,
                outlet_type=OutletType.FRANCHISED,
                count_start=100,
                opened=0,
                closed=10,  # 10 closed outlets
                count_end=90,  # -10% decline
            ),
        ]

        growth_rate_decline = calculate_outlet_growth_rate(summaries_decline)
        assert growth_rate_decline == -10.0

        # Test with insufficient data
        single_summary = [summaries[0]]
        assert calculate_outlet_growth_rate(single_summary) is None

        # Test with zero previous year count
        summaries_zero = [
            OutletSummary(
                section_id=section_id,
                fiscal_year=2022,
                outlet_type=OutletType.FRANCHISED,
                count_start=0,
                opened=0,
                closed=0,
                count_end=0,
            ),
            OutletSummary(
                section_id=section_id,
                fiscal_year=2023,
                outlet_type=OutletType.FRANCHISED,
                count_start=0,
                opened=10,
                closed=0,
                count_end=10,
            ),
        ]

        assert calculate_outlet_growth_rate(summaries_zero) is None
