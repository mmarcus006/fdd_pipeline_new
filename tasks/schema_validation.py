"""Schema validation layer for FDD Pipeline.

This module implements the first tier of the three-tier validation system,
providing automatic Pydantic validation with custom business rules,
error collection, and validation result tracking.
"""

import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Union, Type, Tuple, Callable
from uuid import UUID, uuid4
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel, ValidationError, Field
import asyncio
from contextlib import asynccontextmanager

from models import (
    InitialFee,
    OtherFee,
    InitialInvestment,
    FPR,
    OutletSummary,
    StateCount,
    Financials,
    FDD,
    FDDSection,
    Franchisor,
    ValidationConfig,
)
from utils.database import DatabaseManager
from utils.logging import get_logger

logger = get_logger(__name__)


class ValidationSeverity(str, Enum):
    """Validation error severity levels."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationCategory(str, Enum):
    """Categories of validation errors."""

    SCHEMA = "SCHEMA"
    BUSINESS_RULE = "BUSINESS_RULE"
    CROSS_FIELD = "CROSS_FIELD"
    RANGE = "RANGE"
    FORMAT = "FORMAT"
    REFERENCE = "REFERENCE"


@dataclass
class ValidationError:
    """Individual validation error details."""

    field_name: str
    error_message: str
    severity: ValidationSeverity
    category: ValidationCategory
    actual_value: Any = None
    expected_value: Any = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validation operation."""

    entity_id: UUID
    entity_type: str
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    info: List[ValidationError] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.utcnow)
    validation_duration_ms: Optional[float] = None
    bypass_reason: Optional[str] = None


@dataclass
class ValidationReport:
    """Comprehensive validation report for multiple entities."""

    report_id: UUID = field(default_factory=uuid4)
    fdd_id: Optional[UUID] = None
    results: List[ValidationResult] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    total_duration_ms: Optional[float] = None


class ValidationBypass:
    """Manages validation bypass for manual review cases."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._bypass_cache: Dict[str, bool] = {}

    async def is_bypassed(
        self, entity_id: UUID, entity_type: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if validation is bypassed for an entity."""
        cache_key = f"{entity_type}:{entity_id}"

        if cache_key in self._bypass_cache:
            return self._bypass_cache[cache_key], "Cached bypass"

        # Check database for bypass record
        query = """
        SELECT bypass_reason, created_at 
        FROM validation_bypasses 
        WHERE entity_id = $1 AND entity_type = $2 AND active = true
        """

        try:
            result = await self.db.fetch_one(query, entity_id, entity_type)
            if result:
                self._bypass_cache[cache_key] = True
                return True, result["bypass_reason"]
            else:
                self._bypass_cache[cache_key] = False
                return False, None
        except Exception as e:
            logger.error(f"Error checking validation bypass: {e}")
            return False, None

    async def set_bypass(
        self,
        entity_id: UUID,
        entity_type: str,
        reason: str,
        user_id: Optional[str] = None,
    ):
        """Set validation bypass for an entity."""
        query = """
        INSERT INTO validation_bypasses (entity_id, entity_type, bypass_reason, created_by, active)
        VALUES ($1, $2, $3, $4, true)
        ON CONFLICT (entity_id, entity_type) 
        DO UPDATE SET bypass_reason = $3, created_by = $4, updated_at = NOW(), active = true
        """

        await self.db.execute(query, entity_id, entity_type, reason, user_id)

        # Update cache
        cache_key = f"{entity_type}:{entity_id}"
        self._bypass_cache[cache_key] = True

        logger.info(
            f"Validation bypass set for {entity_type}:{entity_id}",
            extra={
                "entity_id": str(entity_id),
                "entity_type": entity_type,
                "reason": reason,
                "user_id": user_id,
            },
        )


class SchemaValidator:
    """Main schema validation engine."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.bypass = ValidationBypass(db_manager)
        self._validation_stats = {
            "total_validations": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "bypassed_validations": 0,
        }
        self._validation_cache: Dict[str, ValidationResult] = {}
        self._cache_max_size = 1000
        self._performance_metrics = {
            "avg_validation_time": 0.0,
            "total_validation_time": 0.0,
            "slowest_validation": 0.0,
            "fastest_validation": float("inf"),
        }

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get current validation statistics."""
        stats = self._validation_stats.copy()
        if stats["total_validations"] > 0:
            stats["success_rate"] = (
                stats["successful_validations"] / stats["total_validations"]
            ) * 100
        else:
            stats["success_rate"] = 0.0

        stats.update(self._performance_metrics)
        return stats

    def clear_cache(self):
        """Clear validation cache."""
        self._validation_cache.clear()
        logger.info("Validation cache cleared")

    async def validate_model(
        self,
        data: Dict[str, Any],
        model_class: Type[BaseModel],
        entity_id: Optional[UUID] = None,
        allow_bypass: bool = True,
    ) -> ValidationResult:
        """Validate data against a Pydantic model."""
        start_time = datetime.utcnow()
        entity_type = model_class.__name__

        # Generate entity ID if not provided
        if entity_id is None:
            entity_id = uuid4()

        # Check for validation bypass
        if allow_bypass:
            is_bypassed, bypass_reason = await self.bypass.is_bypassed(
                entity_id, entity_type
            )
            if is_bypassed:
                self._validation_stats["bypassed_validations"] += 1
                return ValidationResult(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    is_valid=True,
                    bypass_reason=bypass_reason,
                    validation_duration_ms=0,
                )

        result = ValidationResult(
            entity_id=entity_id, entity_type=entity_type, is_valid=True
        )

        try:
            # Attempt Pydantic validation
            validated_model = model_class.model_validate(data)

            # Run custom business validators
            custom_errors = await self._run_custom_validators(
                validated_model, entity_id
            )

            # Categorize errors by severity
            for error in custom_errors:
                if error.severity == ValidationSeverity.ERROR:
                    result.errors.append(error)
                    result.is_valid = False
                elif error.severity == ValidationSeverity.WARNING:
                    result.warnings.append(error)
                else:
                    result.info.append(error)

            if result.is_valid:
                self._validation_stats["successful_validations"] += 1
            else:
                self._validation_stats["failed_validations"] += 1

        except ValidationError as e:
            # Convert Pydantic validation errors
            result.is_valid = False
            for pydantic_error in e.errors():
                validation_error = ValidationError(
                    field_name=".".join(str(loc) for loc in pydantic_error["loc"]),
                    error_message=pydantic_error["msg"],
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SCHEMA,
                    actual_value=pydantic_error.get("input"),
                    context={"pydantic_type": pydantic_error["type"]},
                )
                result.errors.append(validation_error)

            self._validation_stats["failed_validations"] += 1

        except Exception as e:
            # Unexpected validation error
            logger.error(f"Unexpected validation error for {entity_type}: {e}")
            result.is_valid = False
            result.errors.append(
                ValidationError(
                    field_name="__validation__",
                    error_message=f"Unexpected validation error: {str(e)}",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SCHEMA,
                )
            )
            self._validation_stats["failed_validations"] += 1

        # Calculate duration and update performance metrics
        end_time = datetime.utcnow()
        result.validation_duration_ms = (end_time - start_time).total_seconds() * 1000

        # Update performance metrics
        if result.validation_duration_ms is not None:
            self._performance_metrics[
                "total_validation_time"
            ] += result.validation_duration_ms
            self._performance_metrics["slowest_validation"] = max(
                self._performance_metrics["slowest_validation"],
                result.validation_duration_ms,
            )
            self._performance_metrics["fastest_validation"] = min(
                self._performance_metrics["fastest_validation"],
                result.validation_duration_ms,
            )

            # Update average
            total_validations = self._validation_stats["total_validations"] + 1
            self._performance_metrics["avg_validation_time"] = (
                self._performance_metrics["total_validation_time"] / total_validations
            )

        self._validation_stats["total_validations"] += 1

        # Store validation result
        await self._store_validation_result(result)

        return result

    async def _run_custom_validators(
        self, model: BaseModel, entity_id: UUID
    ) -> List[ValidationError]:
        """Run custom business validators for specific model types."""
        errors = []

        # Route to specific validators based on model type
        if isinstance(model, InitialFee):
            errors.extend(await self._validate_initial_fee(model))
        elif isinstance(model, OtherFee):
            errors.extend(await self._validate_other_fee(model))
        elif isinstance(model, InitialInvestment):
            errors.extend(await self._validate_initial_investment(model))
        elif isinstance(model, FPR):
            errors.extend(await self._validate_fpr(model))
        elif isinstance(model, OutletSummary):
            errors.extend(await self._validate_outlet_summary(model))
        elif isinstance(model, Financials):
            errors.extend(await self._validate_financials(model))

        return errors

    async def _validate_initial_fee(self, fee: InitialFee) -> List[ValidationError]:
        """Custom validation for Initial Fee (Item 5)."""
        errors = []

        # Validate refund conditions
        if fee.refundable and not fee.refund_conditions:
            errors.append(
                ValidationError(
                    field_name="refund_conditions",
                    error_message="Refund conditions should be specified when fee is refundable",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.BUSINESS_RULE,
                    context={"fee_name": fee.fee_name},
                )
            )

        # Validate reasonable amounts
        if fee.amount_cents > ValidationConfig.MAX_FEE_AMOUNT:
            errors.append(
                ValidationError(
                    field_name="amount_cents",
                    error_message=f"Fee amount exceeds reasonable maximum of ${ValidationConfig.MAX_FEE_AMOUNT/100:,.2f}",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.RANGE,
                    actual_value=fee.amount_cents,
                    expected_value=f"<= {ValidationConfig.MAX_FEE_AMOUNT}",
                )
            )

        # Flag unusually high fees for review
        if fee.amount_cents > 1_000_000_00:  # $1M
            errors.append(
                ValidationError(
                    field_name="amount_cents",
                    error_message=f"Unusually high initial fee: ${fee.amount_cents/100:,.2f}",
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.RANGE,
                    actual_value=fee.amount_cents,
                    context={"fee_name": fee.fee_name},
                )
            )

        return errors

    async def _validate_other_fee(self, fee: OtherFee) -> List[ValidationError]:
        """Custom validation for Other Fee (Item 6)."""
        errors = []

        # Validate percentage-based fees have calculation basis
        if fee.amount_percentage is not None and not fee.calculation_basis:
            errors.append(
                ValidationError(
                    field_name="calculation_basis",
                    error_message="Calculation basis required for percentage-based fees",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.BUSINESS_RULE,
                    context={
                        "fee_name": fee.fee_name,
                        "percentage": fee.amount_percentage,
                    },
                )
            )

        # Flag unusually high royalty percentages
        if (
            fee.amount_percentage is not None
            and fee.amount_percentage > ValidationConfig.MAX_ROYALTY_PERCENTAGE
            and "royalty" in fee.fee_name.lower()
        ):
            errors.append(
                ValidationError(
                    field_name="amount_percentage",
                    error_message=f"Unusually high royalty percentage: {fee.amount_percentage}%",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.RANGE,
                    actual_value=fee.amount_percentage,
                    expected_value=f"<= {ValidationConfig.MAX_ROYALTY_PERCENTAGE}%",
                    context={"fee_name": fee.fee_name},
                )
            )

        return errors

    async def _validate_initial_investment(
        self, investment: InitialInvestment
    ) -> List[ValidationError]:
        """Custom validation for Initial Investment (Item 7)."""
        errors = []

        # Validate investment ranges
        if investment.low_cents and investment.high_cents:
            if investment.high_cents < investment.low_cents:
                errors.append(
                    ValidationError(
                        field_name="high_cents",
                        error_message="High investment amount must be >= low amount",
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.RANGE,
                        actual_value=investment.high_cents,
                        expected_value=f">= {investment.low_cents}",
                        context={"category": investment.category},
                    )
                )

            # Flag very wide ranges
            ratio = investment.high_cents / investment.low_cents
            if ratio > 10:
                errors.append(
                    ValidationError(
                        field_name="investment_range",
                        error_message=f"Very wide investment range: {ratio:.1f}x difference",
                        severity=ValidationSeverity.INFO,
                        category=ValidationCategory.RANGE,
                        context={
                            "category": investment.category,
                            "low": investment.low_cents,
                            "high": investment.high_cents,
                            "ratio": ratio,
                        },
                    )
                )

        return errors

    async def _validate_fpr(self, fpr: FPR) -> List[ValidationError]:
        """Custom validation for Financial Performance Representation (Item 19)."""
        errors = []

        # Validate sample size
        if (
            fpr.sample_size is not None
            and fpr.sample_size < ValidationConfig.MIN_SAMPLE_SIZE_FOR_FPR
        ):
            errors.append(
                ValidationError(
                    field_name="sample_size",
                    error_message=f"Sample size below recommended minimum of {ValidationConfig.MIN_SAMPLE_SIZE_FOR_FPR}",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.BUSINESS_RULE,
                    actual_value=fpr.sample_size,
                    expected_value=f">= {ValidationConfig.MIN_SAMPLE_SIZE_FOR_FPR}",
                )
            )

        # Validate revenue metric ordering
        if (
            fpr.revenue_low_cents
            and fpr.revenue_average_cents
            and fpr.revenue_high_cents
        ):
            if not (
                fpr.revenue_low_cents
                <= fpr.revenue_average_cents
                <= fpr.revenue_high_cents
            ):
                errors.append(
                    ValidationError(
                        field_name="revenue_metrics",
                        error_message="Revenue metrics must follow order: low <= average <= high",
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.BUSINESS_RULE,
                        context={
                            "low": fpr.revenue_low_cents,
                            "average": fpr.revenue_average_cents,
                            "high": fpr.revenue_high_cents,
                        },
                    )
                )

        if (
            fpr.revenue_low_cents
            and fpr.revenue_median_cents
            and fpr.revenue_high_cents
        ):
            if not (
                fpr.revenue_low_cents
                <= fpr.revenue_median_cents
                <= fpr.revenue_high_cents
            ):
                errors.append(
                    ValidationError(
                        field_name="revenue_metrics",
                        error_message="Revenue metrics must follow order: low <= median <= high",
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.BUSINESS_RULE,
                        context={
                            "low": fpr.revenue_low_cents,
                            "median": fpr.revenue_median_cents,
                            "high": fpr.revenue_high_cents,
                        },
                    )
                )

        # Validate statistical consistency
        if (
            fpr.revenue_low_cents
            and fpr.revenue_high_cents
            and fpr.revenue_average_cents
            and fpr.revenue_median_cents
        ):

            # Check if average and median are reasonably close (within 50% of range)
            revenue_range = fpr.revenue_high_cents - fpr.revenue_low_cents
            avg_median_diff = abs(fpr.revenue_average_cents - fpr.revenue_median_cents)

            if revenue_range > 0 and avg_median_diff > (revenue_range * 0.5):
                errors.append(
                    ValidationError(
                        field_name="revenue_metrics",
                        error_message="Large difference between average and median suggests skewed data",
                        severity=ValidationSeverity.INFO,
                        category=ValidationCategory.BUSINESS_RULE,
                        context={
                            "average": fpr.revenue_average_cents,
                            "median": fpr.revenue_median_cents,
                            "difference": avg_median_diff,
                            "range": revenue_range,
                        },
                    )
                )

        # Validate disclosure period
        if hasattr(fpr, "disclosure_period") and fpr.disclosure_period:
            if fpr.disclosure_period > ValidationConfig.MAX_YEARS_HISTORICAL_DATA:
                errors.append(
                    ValidationError(
                        field_name="disclosure_period",
                        error_message=f"Disclosure period exceeds maximum of {ValidationConfig.MAX_YEARS_HISTORICAL_DATA} years",
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.RANGE,
                        actual_value=fpr.disclosure_period,
                        expected_value=f"<= {ValidationConfig.MAX_YEARS_HISTORICAL_DATA}",
                    )
                )

        return errors

    async def _validate_outlet_summary(
        self, outlet: OutletSummary
    ) -> List[ValidationError]:
        """Custom validation for Outlet Summary (Item 20)."""
        errors = []

        # Validate outlet mathematics
        calculated_end = (
            outlet.count_start
            + outlet.opened
            - outlet.closed
            + outlet.transferred_in
            - outlet.transferred_out
        )

        if calculated_end != outlet.count_end:
            errors.append(
                ValidationError(
                    field_name="outlet_math",
                    error_message=(
                        f"Outlet math error: {outlet.count_start} + {outlet.opened} "
                        f"- {outlet.closed} + {outlet.transferred_in} "
                        f"- {outlet.transferred_out} = {calculated_end}, "
                        f"but count_end = {outlet.count_end}"
                    ),
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.BUSINESS_RULE,
                    actual_value=outlet.count_end,
                    expected_value=calculated_end,
                    context={"fiscal_year": outlet.fiscal_year},
                )
            )

        return errors

    async def _validate_financials(
        self, financials: Financials
    ) -> List[ValidationError]:
        """Custom validation for Financial Statements (Item 21)."""
        errors = []

        # Validate accounting equation: Assets = Liabilities + Equity
        if (
            financials.total_assets_cents is not None
            and financials.total_liabilities_cents is not None
            and financials.total_equity_cents is not None
        ):

            calculated_total = (
                financials.total_liabilities_cents + financials.total_equity_cents
            )
            difference = abs(financials.total_assets_cents - calculated_total)

            # Allow $1 tolerance for rounding
            if difference > 100:  # $1.00 in cents
                errors.append(
                    ValidationError(
                        field_name="accounting_equation",
                        error_message=(
                            f"Accounting equation imbalance: Assets ({financials.total_assets_cents/100:,.2f}) "
                            f"!= Liabilities + Equity ({calculated_total/100:,.2f}), "
                            f"difference: ${difference/100:,.2f}"
                        ),
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.BUSINESS_RULE,
                        actual_value=financials.total_assets_cents,
                        expected_value=calculated_total,
                        context={"difference_cents": difference},
                    )
                )

        # Flag large negative equity
        if (
            financials.total_equity_cents is not None
            and financials.total_equity_cents
            < ValidationConfig.FLAG_NEGATIVE_EQUITY_THRESHOLD
        ):
            errors.append(
                ValidationError(
                    field_name="total_equity_cents",
                    error_message=f"Large negative equity: ${financials.total_equity_cents/100:,.2f}",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.RANGE,
                    actual_value=financials.total_equity_cents,
                    context={"fiscal_year": financials.fiscal_year},
                )
            )

        return errors

    async def _store_validation_result(self, result: ValidationResult):
        """Store validation result in database for tracking."""
        try:
            # Store main validation result
            query = """
            INSERT INTO validation_results (
                id, entity_id, entity_type, is_valid, validated_at, 
                validation_duration_ms, bypass_reason, error_count, warning_count, info_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """

            await self.db.execute(
                query,
                uuid4(),
                result.entity_id,
                result.entity_type,
                result.is_valid,
                result.validated_at,
                result.validation_duration_ms,
                result.bypass_reason,
                len(result.errors),
                len(result.warnings),
                len(result.info),
            )

            # Store individual validation errors
            if result.errors or result.warnings or result.info:
                all_errors = result.errors + result.warnings + result.info
                error_query = """
                INSERT INTO validation_errors (
                    id, entity_id, field_name, error_message, severity, 
                    category, actual_value, expected_value, context
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """

                for error in all_errors:
                    await self.db.execute(
                        error_query,
                        uuid4(),
                        result.entity_id,
                        error.field_name,
                        error.error_message,
                        error.severity.value,
                        error.category.value,
                        (
                            str(error.actual_value)
                            if error.actual_value is not None
                            else None
                        ),
                        (
                            str(error.expected_value)
                            if error.expected_value is not None
                            else None
                        ),
                        error.context,
                    )

        except Exception as e:
            logger.error(f"Failed to store validation result: {e}")

    async def validate_batch(
        self,
        batch_data: List[Dict[str, Any]],
        model_classes: List[Type[BaseModel]],
        entity_ids: Optional[List[UUID]] = None,
        allow_bypass: bool = True,
        max_concurrent: int = 10,
    ) -> List[ValidationResult]:
        """Validate multiple entities concurrently."""
        if len(batch_data) != len(model_classes):
            raise ValueError("batch_data and model_classes must have same length")

        if entity_ids and len(entity_ids) != len(batch_data):
            raise ValueError("entity_ids must match batch_data length if provided")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def validate_single(index: int) -> ValidationResult:
            async with semaphore:
                return await self.validate_model(
                    batch_data[index],
                    model_classes[index],
                    entity_ids[index] if entity_ids else None,
                    allow_bypass,
                )

        # Execute all validations concurrently
        tasks = [validate_single(i) for i in range(len(batch_data))]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch validation error at index {i}: {result}")
                # Create error result
                error_result = ValidationResult(
                    entity_id=entity_ids[i] if entity_ids else uuid4(),
                    entity_type=model_classes[i].__name__,
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field_name="__batch_validation__",
                            error_message=f"Batch validation failed: {str(result)}",
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.SCHEMA,
                        )
                    ],
                )
                final_results.append(error_result)
            else:
                final_results.append(result)

        return final_results

    async def validate_cross_field_consistency(
        self, fdd_id: UUID, extracted_data: Dict[str, Any]
    ) -> List[ValidationError]:
        """Validate cross-field consistency across FDD sections."""
        errors = []

        try:
            # Get Item 5 (Initial Fees) and Item 7 (Investment) data for consistency check
            item5_data = extracted_data.get("item5_fees", [])
            item7_data = extracted_data.get("item7_investment", [])

            if item5_data and item7_data:
                # Check if initial franchise fees are consistent between Item 5 and Item 7
                item5_franchise_fees = [
                    fee
                    for fee in item5_data
                    if "franchise fee" in fee.get("fee_name", "").lower()
                ]

                item7_franchise_fees = [
                    inv
                    for inv in item7_data
                    if "franchise fee" in inv.get("category", "").lower()
                ]

                if item5_franchise_fees and item7_franchise_fees:
                    item5_amount = item5_franchise_fees[0].get("amount_cents", 0)
                    item7_low = item7_franchise_fees[0].get("low_cents", 0)
                    item7_high = item7_franchise_fees[0].get("high_cents", 0)

                    # Check if Item 5 amount falls within Item 7 range
                    if not (item7_low <= item5_amount <= item7_high):
                        errors.append(
                            ValidationError(
                                field_name="franchise_fee_consistency",
                                error_message=(
                                    f"Item 5 franchise fee (${item5_amount/100:,.2f}) "
                                    f"not within Item 7 range (${item7_low/100:,.2f} - ${item7_high/100:,.2f})"
                                ),
                                severity=ValidationSeverity.WARNING,
                                category=ValidationCategory.CROSS_FIELD,
                                context={
                                    "fdd_id": str(fdd_id),
                                    "item5_amount": item5_amount,
                                    "item7_low": item7_low,
                                    "item7_high": item7_high,
                                },
                            )
                        )

            # Check Item 20 outlet consistency across years
            item20_data = extracted_data.get("item20_outlets", [])
            if len(item20_data) > 1:
                # Sort by fiscal year
                sorted_outlets = sorted(
                    item20_data, key=lambda x: x.get("fiscal_year", 0)
                )

                for i in range(1, len(sorted_outlets)):
                    prev_year = sorted_outlets[i - 1]
                    curr_year = sorted_outlets[i]

                    # Check if previous year's count_end matches current year's count_start
                    if (
                        prev_year.get("count_end") != curr_year.get("count_start")
                        and curr_year.get("fiscal_year")
                        == prev_year.get("fiscal_year") + 1
                    ):
                        errors.append(
                            ValidationError(
                                field_name="outlet_year_consistency",
                                error_message=(
                                    f"Outlet count inconsistency: FY{prev_year.get('fiscal_year')} "
                                    f"end count ({prev_year.get('count_end')}) != "
                                    f"FY{curr_year.get('fiscal_year')} start count ({curr_year.get('count_start')})"
                                ),
                                severity=ValidationSeverity.WARNING,
                                category=ValidationCategory.CROSS_FIELD,
                                context={
                                    "fdd_id": str(fdd_id),
                                    "prev_year": prev_year.get("fiscal_year"),
                                    "curr_year": curr_year.get("fiscal_year"),
                                },
                            )
                        )

        except Exception as e:
            logger.error(f"Cross-field validation error for FDD {fdd_id}: {e}")
            errors.append(
                ValidationError(
                    field_name="cross_field_validation",
                    error_message=f"Cross-field validation failed: {str(e)}",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.CROSS_FIELD,
                    context={"fdd_id": str(fdd_id)},
                )
            )

        return errors

    async def validate_data_completeness(
        self,
        data: Dict[str, Any],
        model_class: Type[BaseModel],
        required_fields: Optional[List[str]] = None,
    ) -> List[ValidationError]:
        """Validate data completeness and quality."""
        errors = []

        try:
            # Get model fields
            model_fields = model_class.model_fields

            # Check for missing critical fields
            if required_fields:
                for field_name in required_fields:
                    if field_name not in data or data[field_name] is None:
                        errors.append(
                            ValidationError(
                                field_name=field_name,
                                error_message=f"Critical field '{field_name}' is missing or null",
                                severity=ValidationSeverity.ERROR,
                                category=ValidationCategory.SCHEMA,
                                context={"model_type": model_class.__name__},
                            )
                        )

            # Check data quality indicators
            total_fields = len(model_fields)
            populated_fields = sum(
                1 for key, value in data.items() if value is not None and value != ""
            )

            completeness_ratio = (
                populated_fields / total_fields if total_fields > 0 else 0
            )

            if completeness_ratio < 0.5:  # Less than 50% complete
                errors.append(
                    ValidationError(
                        field_name="data_completeness",
                        error_message=f"Low data completeness: {completeness_ratio:.1%} of fields populated",
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.BUSINESS_RULE,
                        actual_value=completeness_ratio,
                        expected_value=">= 0.5",
                        context={
                            "total_fields": total_fields,
                            "populated_fields": populated_fields,
                            "model_type": model_class.__name__,
                        },
                    )
                )

        except Exception as e:
            logger.error(f"Data completeness validation error: {e}")
            errors.append(
                ValidationError(
                    field_name="completeness_validation",
                    error_message=f"Completeness validation failed: {str(e)}",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SCHEMA,
                )
            )

        return errors

    async def validate_temporal_consistency(
        self, data_by_year: Dict[int, Dict[str, Any]]
    ) -> List[ValidationError]:
        """Validate temporal consistency across multiple years of data."""
        errors = []

        try:
            years = sorted(data_by_year.keys())

            for i in range(1, len(years)):
                prev_year = years[i - 1]
                curr_year = years[i]

                prev_data = data_by_year[prev_year]
                curr_data = data_by_year[curr_year]

                # Check for unrealistic year-over-year changes
                numeric_fields = [
                    "count_end",
                    "total_revenue_cents",
                    "total_assets_cents",
                ]

                for field in numeric_fields:
                    if field in prev_data and field in curr_data:
                        prev_value = prev_data[field]
                        curr_value = curr_data[field]

                        if prev_value and curr_value and prev_value > 0:
                            change_ratio = abs(curr_value - prev_value) / prev_value

                            # Flag changes > 500% as potentially erroneous
                            if change_ratio > 5.0:
                                errors.append(
                                    ValidationError(
                                        field_name=f"{field}_temporal_consistency",
                                        error_message=(
                                            f"Extreme year-over-year change in {field}: "
                                            f"{change_ratio:.1%} from {prev_year} to {curr_year}"
                                        ),
                                        severity=ValidationSeverity.WARNING,
                                        category=ValidationCategory.BUSINESS_RULE,
                                        context={
                                            "prev_year": prev_year,
                                            "curr_year": curr_year,
                                            "prev_value": prev_value,
                                            "curr_value": curr_value,
                                            "change_ratio": change_ratio,
                                        },
                                    )
                                )

        except Exception as e:
            logger.error(f"Temporal consistency validation error: {e}")
            errors.append(
                ValidationError(
                    field_name="temporal_validation",
                    error_message=f"Temporal validation failed: {str(e)}",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.BUSINESS_RULE,
                )
            )

        return errors

    def clear_validation_cache(self):
        """Clear the validation cache."""
        self._validation_cache.clear()
        logger.info("Validation cache cleared")

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get current validation statistics."""
        return {
            **self._validation_stats,
            "success_rate": (
                self._validation_stats["successful_validations"]
                / max(self._validation_stats["total_validations"], 1)
            )
            * 100,
            "cache_size": len(self._validation_cache),
            "cache_hit_rate": 0.0,  # Could implement cache hit tracking
        }


class ValidationReportGenerator:
    """Generates comprehensive validation reports."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def generate_fdd_report(self, fdd_id: UUID) -> ValidationReport:
        """Generate validation report for an entire FDD."""
        start_time = datetime.utcnow()

        report = ValidationReport(fdd_id=fdd_id)

        # Get all sections for this FDD
        sections_query = """
        SELECT id, item_no, extraction_status 
        FROM fdd_sections 
        WHERE fdd_id = $1 
        ORDER BY item_no
        """

        sections = await self.db.fetch_all(sections_query, fdd_id)

        # Get validation results for each section
        for section in sections:
            results_query = """
            SELECT * FROM validation_results 
            WHERE entity_id = $1 
            ORDER BY validated_at DESC 
            LIMIT 1
            """

            result_row = await self.db.fetch_one(results_query, section["id"])
            if result_row:
                # Get associated errors
                errors_query = """
                SELECT * FROM validation_errors 
                WHERE entity_id = $1 
                ORDER BY severity, field_name
                """

                error_rows = await self.db.fetch_all(errors_query, section["id"])

                # Convert to ValidationResult
                validation_result = self._convert_db_to_validation_result(
                    result_row, error_rows
                )
                report.results.append(validation_result)

        # Generate summary
        report.summary = self._generate_summary(report.results)

        # Calculate total duration
        end_time = datetime.utcnow()
        report.total_duration_ms = (end_time - start_time).total_seconds() * 1000

        return report

    def _convert_db_to_validation_result(
        self, result_row: Dict, error_rows: List[Dict]
    ) -> ValidationResult:
        """Convert database rows to ValidationResult object."""
        result = ValidationResult(
            entity_id=result_row["entity_id"],
            entity_type=result_row["entity_type"],
            is_valid=result_row["is_valid"],
            validated_at=result_row["validated_at"],
            validation_duration_ms=result_row["validation_duration_ms"],
            bypass_reason=result_row["bypass_reason"],
        )

        # Convert errors
        for error_row in error_rows:
            validation_error = ValidationError(
                field_name=error_row["field_name"],
                error_message=error_row["error_message"],
                severity=ValidationSeverity(error_row["severity"]),
                category=ValidationCategory(error_row["category"]),
                actual_value=error_row["actual_value"],
                expected_value=error_row["expected_value"],
                context=error_row["context"] or {},
            )

            if validation_error.severity == ValidationSeverity.ERROR:
                result.errors.append(validation_error)
            elif validation_error.severity == ValidationSeverity.WARNING:
                result.warnings.append(validation_error)
            else:
                result.info.append(validation_error)

        return result

    def _generate_summary(self, results: List[ValidationResult]) -> Dict[str, int]:
        """Generate summary statistics for validation results."""
        summary = {
            "total_entities": len(results),
            "valid_entities": sum(1 for r in results if r.is_valid),
            "invalid_entities": sum(1 for r in results if not r.is_valid),
            "bypassed_entities": sum(1 for r in results if r.bypass_reason),
            "total_errors": sum(len(r.errors) for r in results),
            "total_warnings": sum(len(r.warnings) for r in results),
            "total_info": sum(len(r.info) for r in results),
        }

        summary["validation_success_rate"] = (
            summary["valid_entities"] / max(summary["total_entities"], 1)
        ) * 100

        return summary


# Enhanced convenience functions for common validation operations
async def validate_extracted_data(
    data: Dict[str, Any],
    model_class: Type[BaseModel],
    db_manager: DatabaseManager,
    entity_id: Optional[UUID] = None,
    include_completeness_check: bool = True,
) -> ValidationResult:
    """Convenience function to validate extracted data with optional completeness check."""
    validator = SchemaValidator(db_manager)

    # Perform standard validation
    result = await validator.validate_model(data, model_class, entity_id)

    # Add completeness validation if requested
    if include_completeness_check and result.is_valid:
        completeness_errors = await validator.validate_data_completeness(
            data, model_class
        )
        result.warnings.extend(
            [e for e in completeness_errors if e.severity == ValidationSeverity.WARNING]
        )
        result.info.extend(
            [e for e in completeness_errors if e.severity == ValidationSeverity.INFO]
        )

    return result


async def validate_fdd_sections(
    fdd_id: UUID,
    db_manager: DatabaseManager,
    include_cross_field_validation: bool = True,
) -> ValidationReport:
    """Convenience function to validate all sections of an FDD with cross-field validation."""
    report_generator = ValidationReportGenerator(db_manager)
    report = await report_generator.generate_fdd_report(fdd_id)

    # Add cross-field validation if requested
    if include_cross_field_validation:
        try:
            # Get extracted data for cross-field validation
            # This would typically come from the database
            extracted_data = {}  # Placeholder - would fetch from DB

            validator = SchemaValidator(db_manager)
            cross_field_errors = await validator.validate_cross_field_consistency(
                fdd_id, extracted_data
            )

            if cross_field_errors:
                # Add cross-field validation result to report
                cross_field_result = ValidationResult(
                    entity_id=fdd_id,
                    entity_type="FDD_CrossField",
                    is_valid=not any(
                        e.severity == ValidationSeverity.ERROR
                        for e in cross_field_errors
                    ),
                    errors=[
                        e
                        for e in cross_field_errors
                        if e.severity == ValidationSeverity.ERROR
                    ],
                    warnings=[
                        e
                        for e in cross_field_errors
                        if e.severity == ValidationSeverity.WARNING
                    ],
                    info=[
                        e
                        for e in cross_field_errors
                        if e.severity == ValidationSeverity.INFO
                    ],
                )
                report.results.append(cross_field_result)

                # Update summary
                report.summary = report_generator._generate_summary(report.results)

        except Exception as e:
            logger.error(f"Cross-field validation failed for FDD {fdd_id}: {e}")

    return report


async def validate_batch_data(
    batch_data: List[Dict[str, Any]],
    model_classes: List[Type[BaseModel]],
    db_manager: DatabaseManager,
    entity_ids: Optional[List[UUID]] = None,
    max_concurrent: int = 10,
) -> List[ValidationResult]:
    """Convenience function for batch validation."""
    validator = SchemaValidator(db_manager)
    return await validator.validate_batch(
        batch_data, model_classes, entity_ids, max_concurrent=max_concurrent
    )


@asynccontextmanager
async def validation_performance_monitor(operation_name: str = "validation"):
    """Context manager for monitoring validation performance."""
    start_time = datetime.utcnow()

    try:
        yield
    finally:
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds() * 1000

        logger.info(
            f"{operation_name} performance",
            extra={
                "operation": operation_name,
                "duration_ms": duration,
                "timestamp": end_time.isoformat(),
            },
        )


class ValidationRuleRegistry:
    """Registry for custom validation rules that can be dynamically added."""

    def __init__(self):
        self._custom_rules: Dict[str, List[Callable]] = {}

    def register_rule(self, model_name: str, rule_func: Callable):
        """Register a custom validation rule for a model."""
        if model_name not in self._custom_rules:
            self._custom_rules[model_name] = []
        self._custom_rules[model_name].append(rule_func)
        logger.info(f"Registered custom validation rule for {model_name}")

    def get_rules(self, model_name: str) -> List[Callable]:
        """Get custom validation rules for a model."""
        return self._custom_rules.get(model_name, [])

    def clear_rules(self, model_name: Optional[str] = None):
        """Clear validation rules for a specific model or all models."""
        if model_name:
            self._custom_rules.pop(model_name, None)
            logger.info(f"Cleared custom validation rules for {model_name}")
        else:
            self._custom_rules.clear()
            logger.info("Cleared all custom validation rules")


# Global validation rule registry
validation_rule_registry = ValidationRuleRegistry()
