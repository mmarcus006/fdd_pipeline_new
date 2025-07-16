"""Unit tests for validation utilities."""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from utils.validation import (
    ValidationMetrics, ValidationPerformanceMonitor, ValidationQualityAnalyzer,
    ValidationRuleOptimizer, get_validation_health_check, validation_batch_processor
)
from tasks.schema_validation import (
    ValidationResult, ValidationError, ValidationSeverity, ValidationCategory
)
from utils.database import DatabaseManager


@pytest.fixture
def mock_db_manager():
    """Mock database manager for testing."""
    db = AsyncMock(spec=DatabaseManager)
    return db


@pytest.fixture
def sample_validation_result():
    """Sample validation result for testing."""
    return ValidationResult(
        entity_id=uuid4(),
        entity_type="InitialFee",
        is_valid=True,
        validated_at=datetime.utcnow(),
        validation_duration_ms=150.0
    )


@pytest.fixture
def sample_validation_error():
    """Sample validation error for testing."""
    return ValidationError(
        field_name="amount_cents",
        error_message="Amount exceeds maximum",
        severity=ValidationSeverity.ERROR,
        category=ValidationCategory.RANGE,
        actual_value=1000000000,
        expected_value="<= 500000000"
    )


class TestValidationMetrics:
    """Test validation metrics tracking."""
    
    def test_initial_metrics(self):
        """Test initial metrics state."""
        metrics = ValidationMetrics()
        
        assert metrics.total_validations == 0
        assert metrics.successful_validations == 0
        assert metrics.failed_validations == 0
        assert metrics.success_rate == 0.0
        assert metrics.avg_validation_time_ms == 0.0
        assert metrics.min_validation_time_ms == float('inf')
    
    def test_update_from_successful_result(self, sample_validation_result):
        """Test updating metrics from successful validation."""
        metrics = ValidationMetrics()
        metrics.update_from_result(sample_validation_result)
        
        assert metrics.total_validations == 1
        assert metrics.successful_validations == 1
        assert metrics.failed_validations == 0
        assert metrics.success_rate == 100.0
        assert metrics.avg_validation_time_ms == 150.0
        assert metrics.min_validation_time_ms == 150.0
        assert metrics.max_validation_time_ms == 150.0
    
    def test_update_from_failed_result(self, sample_validation_error):
        """Test updating metrics from failed validation."""
        metrics = ValidationMetrics()
        
        # Create failed result
        failed_result = ValidationResult(
            entity_id=uuid4(),
            entity_type="InitialFee",
            is_valid=False,
            validated_at=datetime.utcnow(),
            validation_duration_ms=200.0,
            errors=[sample_validation_error]
        )
        
        metrics.update_from_result(failed_result)
        
        assert metrics.total_validations == 1
        assert metrics.successful_validations == 0
        assert metrics.failed_validations == 1
        assert metrics.success_rate == 0.0
        assert metrics.error_categories["RANGE"] == 1
        assert metrics.error_fields["amount_cents"] == 1
    
    def test_update_from_bypassed_result(self):
        """Test updating metrics from bypassed validation."""
        metrics = ValidationMetrics()
        
        bypassed_result = ValidationResult(
            entity_id=uuid4(),
            entity_type="InitialFee",
            is_valid=True,
            validated_at=datetime.utcnow(),
            bypass_reason="Manual review approved"
        )
        
        metrics.update_from_result(bypassed_result)
        
        assert metrics.total_validations == 1
        assert metrics.bypassed_validations == 1
        assert metrics.successful_validations == 0
        assert metrics.failed_validations == 0


class TestValidationPerformanceMonitor:
    """Test validation performance monitoring."""
    
    def test_record_validation(self, mock_db_manager, sample_validation_result):
        """Test recording validation results."""
        monitor = ValidationPerformanceMonitor(mock_db_manager)
        
        monitor.record_validation(sample_validation_result)
        
        assert monitor.metrics.total_validations == 1
        assert monitor.metrics.successful_validations == 1
        assert len(monitor._validation_times) == 1
        assert monitor._validation_times[0] == 150.0
    
    def test_performance_summary(self, mock_db_manager):
        """Test performance summary generation."""
        monitor = ValidationPerformanceMonitor(mock_db_manager)
        
        # Record multiple validations
        for i in range(5):
            result = ValidationResult(
                entity_id=uuid4(),
                entity_type="InitialFee",
                is_valid=True,
                validated_at=datetime.utcnow(),
                validation_duration_ms=100.0 + i * 10
            )
            monitor.record_validation(result)
        
        summary = monitor.get_performance_summary()
        
        assert summary["total_validations"] == 5
        assert summary["success_rate"] == 100.0
        assert summary["avg_validation_time_ms"] == 120.0
        assert "performance_percentiles" in summary
        assert "hourly_distribution" in summary
    
    @pytest.mark.asyncio
    async def test_generate_performance_report(self, mock_db_manager):
        """Test generating detailed performance report."""
        # Mock database responses
        mock_db_manager.fetch_all.side_effect = [
            # Trends query
            [{
                "hour": datetime.utcnow(),
                "total_validations": 10,
                "successful_validations": 9,
                "avg_duration": 150.0
            }],
            # Common errors query
            [{
                "category": "SCHEMA",
                "field_name": "amount_cents",
                "error_message": "Invalid amount",
                "frequency": 5
            }]
        ]
        
        monitor = ValidationPerformanceMonitor(mock_db_manager)
        report = await monitor.generate_performance_report()
        
        assert "hourly_trends" in report
        assert "common_errors" in report
        assert len(report["hourly_trends"]) == 1
        assert len(report["common_errors"]) == 1
    
    @pytest.mark.asyncio
    async def test_performance_report_database_error(self, mock_db_manager):
        """Test handling database errors in performance report."""
        mock_db_manager.fetch_all.side_effect = Exception("Database error")
        
        monitor = ValidationPerformanceMonitor(mock_db_manager)
        report = await monitor.generate_performance_report()
        
        assert "database_insights_error" in report
        assert "Database error" in report["database_insights_error"]


class TestValidationQualityAnalyzer:
    """Test validation quality analysis."""
    
    @pytest.mark.asyncio
    async def test_analyze_validation_quality(self, mock_db_manager):
        """Test validation quality analysis."""
        # Mock database responses
        mock_db_manager.fetch_all.side_effect = [
            # Stats query
            [{
                "entity_type": "InitialFee",
                "total_validations": 100,
                "successful_validations": 95,
                "bypassed_validations": 2,
                "avg_errors": 0.1,
                "avg_warnings": 0.3,
                "avg_duration": 150.0
            }],
            # Error patterns query
            [{
                "category": "SCHEMA",
                "field_name": "amount_cents",
                "entity_type": "InitialFee",
                "frequency": 10,
                "affected_entities": 8
            }]
        ]
        
        analyzer = ValidationQualityAnalyzer(mock_db_manager)
        analysis = await analyzer.analyze_validation_quality(days=7)
        
        assert analysis["analysis_period_days"] == 7
        assert len(analysis["entity_quality_scores"]) == 1
        assert analysis["overall_quality_score"] == 95.0
        assert len(analysis["error_patterns"]) == 1
        assert len(analysis["recommendations"]) >= 0
    
    def test_calculate_entity_quality_score(self, mock_db_manager):
        """Test entity quality score calculation."""
        analyzer = ValidationQualityAnalyzer(mock_db_manager)
        
        stats = {
            "total_validations": 100,
            "successful_validations": 90,
            "bypassed_validations": 5,
            "avg_errors": 0.2,
            "avg_warnings": 0.1,
            "avg_duration": 500.0
        }
        
        score = analyzer._calculate_entity_quality_score(stats)
        
        # Should be 90% base score with some penalties
        assert 80 <= score <= 90
    
    def test_classify_error_severity(self, mock_db_manager):
        """Test error severity classification."""
        analyzer = ValidationQualityAnalyzer(mock_db_manager)
        
        # High severity
        high_pattern = {"frequency": 150, "affected_entities": 60}
        assert analyzer._classify_error_severity(high_pattern) == "HIGH"
        
        # Medium severity
        medium_pattern = {"frequency": 30, "affected_entities": 15}
        assert analyzer._classify_error_severity(medium_pattern) == "MEDIUM"
        
        # Low severity
        low_pattern = {"frequency": 5, "affected_entities": 3}
        assert analyzer._classify_error_severity(low_pattern) == "LOW"
    
    def test_generate_quality_recommendations(self, mock_db_manager):
        """Test quality improvement recommendations."""
        analyzer = ValidationQualityAnalyzer(mock_db_manager)
        
        entity_scores = [
            {
                "entity_type": "InitialFee",
                "quality_score": 60.0,
                "bypass_rate": 25.0,
                "avg_errors": 3.0
            }
        ]
        
        error_patterns = [
            {
                "category": "SCHEMA",
                "field_name": "amount_cents",
                "entity_type": "InitialFee",
                "frequency": 200,
                "affected_entities": 80,
                "severity": "HIGH"
            }
        ]
        
        recommendations = analyzer._generate_quality_recommendations(entity_scores, error_patterns)
        
        assert len(recommendations) >= 2  # Should have bypass and error recommendations
        assert any(rec["type"] == "HIGH_BYPASS_RATE" for rec in recommendations)
        assert any(rec["type"] == "HIGH_ERROR_RATE" for rec in recommendations)
        assert any(rec["type"] == "FREQUENT_ERROR" for rec in recommendations)


class TestValidationRuleOptimizer:
    """Test validation rule optimization."""
    
    @pytest.mark.asyncio
    async def test_suggest_rule_optimizations(self, mock_db_manager):
        """Test rule optimization suggestions."""
        # Mock database responses
        mock_db_manager.fetch_all.side_effect = [
            # Performance query
            [{
                "entity_type": "InitialFee",
                "avg_duration": 800.0,
                "total_validations": 100,
                "slow_validations": 30
            }],
            # False positive query
            [{
                "field_name": "amount_cents",
                "category": "RANGE",
                "error_count": 50,
                "bypassed_count": 20
            }]
        ]
        
        optimizer = ValidationRuleOptimizer(mock_db_manager)
        optimizations = await optimizer.suggest_rule_optimizations()
        
        assert "performance_optimizations" in optimizations
        assert "rule_adjustments" in optimizations
        assert "threshold_recommendations" in optimizations
        
        # Should have performance optimization for slow validation
        assert len(optimizations["performance_optimizations"]) == 1
        assert optimizations["performance_optimizations"][0]["entity_type"] == "InitialFee"
        
        # Should have rule adjustment for high bypass rate
        assert len(optimizations["rule_adjustments"]) == 1
        assert optimizations["rule_adjustments"][0]["field_name"] == "amount_cents"


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @pytest.mark.asyncio
    async def test_get_validation_health_check(self, mock_db_manager):
        """Test validation health check."""
        # Mock database responses
        mock_db_manager.fetch_one.return_value = {
            "total_recent": 50,
            "successful_recent": 48,
            "avg_duration_recent": 120.0
        }
        
        # Mock quality analysis
        with patch('utils.validation.ValidationQualityAnalyzer') as mock_analyzer:
            mock_analyzer.return_value.analyze_validation_quality.return_value = {
                "overall_quality_score": 85.0,
                "recommendations": [
                    {"priority": "HIGH"},
                    {"priority": "MEDIUM"},
                    {"priority": "HIGH"}
                ]
            }
            
            health_check = await get_validation_health_check(mock_db_manager)
            
            assert health_check["status"] in ["HEALTHY", "WARNING", "DEGRADED"]
            assert health_check["recent_activity"]["total_validations_last_hour"] == 50
            assert health_check["recent_activity"]["success_rate_last_hour"] == 96.0
            assert health_check["overall_quality_score"] == 85.0
            assert health_check["high_priority_issues"] == 2
    
    @pytest.mark.asyncio
    async def test_validation_batch_processor(self, mock_db_manager):
        """Test batch validation processor."""
        # Mock validator and monitor
        with patch('utils.validation.SchemaValidator') as mock_validator, \
             patch('utils.validation.ValidationPerformanceMonitor') as mock_monitor:
            
            mock_result = ValidationResult(
                entity_id=uuid4(),
                entity_type="InitialFee",
                is_valid=True,
                validated_at=datetime.utcnow()
            )
            
            mock_validator.return_value.validate_model.return_value = mock_result
            mock_monitor.return_value.get_performance_summary.return_value = {"test": "summary"}
            
            async with validation_batch_processor(mock_db_manager, batch_size=10) as process_batch:
                batch_items = [
                    {
                        "data": {"test": "data"},
                        "model_class": "TestModel",
                        "entity_id": uuid4()
                    }
                ]
                
                results = await process_batch(batch_items)
                
                assert len(results) == 1
                assert results[0] == mock_result


class TestValidationUtilsIntegration:
    """Integration tests for validation utilities."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_flow(self, mock_db_manager):
        """Test complete monitoring workflow."""
        monitor = ValidationPerformanceMonitor(mock_db_manager)
        
        # Simulate multiple validation results
        results = []
        for i in range(10):
            result = ValidationResult(
                entity_id=uuid4(),
                entity_type="InitialFee",
                is_valid=i % 8 != 0,  # 80% success rate
                validated_at=datetime.utcnow(),
                validation_duration_ms=100.0 + i * 5
            )
            
            if not result.is_valid:
                result.errors = [ValidationError(
                    field_name=f"field_{i}",
                    error_message=f"Error {i}",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SCHEMA
                )]
            
            monitor.record_validation(result)
            results.append(result)
        
        # Check final metrics
        stats = monitor.get_validation_stats()
        assert stats["total_validations"] == 10
        assert stats["successful_validations"] == 8
        assert stats["failed_validations"] == 2
        assert stats["success_rate"] == 80.0
        
        # Check performance summary
        summary = monitor.get_performance_summary()
        assert summary["total_validations"] == 10
        assert summary["success_rate"] == 80.0
        assert "performance_percentiles" in summary
    
    @pytest.mark.asyncio
    async def test_quality_analysis_with_recommendations(self, mock_db_manager):
        """Test quality analysis with realistic data."""
        # Mock realistic database responses
        mock_db_manager.fetch_all.side_effect = [
            # Stats for multiple entity types
            [
                {
                    "entity_type": "InitialFee",
                    "total_validations": 200,
                    "successful_validations": 180,
                    "bypassed_validations": 10,
                    "avg_errors": 0.5,
                    "avg_warnings": 1.2,
                    "avg_duration": 200.0
                },
                {
                    "entity_type": "OtherFee",
                    "total_validations": 150,
                    "successful_validations": 120,
                    "bypassed_validations": 20,
                    "avg_errors": 1.8,
                    "avg_warnings": 0.8,
                    "avg_duration": 300.0
                }
            ],
            # Error patterns
            [
                {
                    "category": "BUSINESS_RULE",
                    "field_name": "calculation_basis",
                    "entity_type": "OtherFee",
                    "frequency": 80,
                    "affected_entities": 40
                },
                {
                    "category": "RANGE",
                    "field_name": "amount_cents",
                    "entity_type": "InitialFee",
                    "frequency": 25,
                    "affected_entities": 20
                }
            ]
        ]
        
        analyzer = ValidationQualityAnalyzer(mock_db_manager)
        analysis = await analyzer.analyze_validation_quality(days=30)
        
        # Should have analysis for both entity types
        assert len(analysis["entity_quality_scores"]) == 2
        
        # Overall quality should be weighted average
        assert 70 <= analysis["overall_quality_score"] <= 85
        
        # Should have error patterns
        assert len(analysis["error_patterns"]) == 2
        
        # Should generate recommendations for low-quality entities
        recommendations = analysis["recommendations"]
        assert len(recommendations) > 0
        
        # Should recommend addressing high bypass rate for OtherFee
        bypass_recommendations = [r for r in recommendations if r["type"] == "HIGH_BYPASS_RATE"]
        assert len(bypass_recommendations) > 0
        assert any(r["entity_type"] == "OtherFee" for r in bypass_recommendations)


if __name__ == "__main__":
    pytest.main([__file__])