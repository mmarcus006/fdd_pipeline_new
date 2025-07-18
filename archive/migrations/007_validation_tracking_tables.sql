-- Migration 007: Validation Tracking Tables
-- Creates tables for storing validation results, errors, and bypass records

-- Validation results table
CREATE TABLE IF NOT EXISTS validation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    is_valid BOOLEAN NOT NULL,
    validated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    validation_duration_ms NUMERIC(10,2),
    bypass_reason TEXT,
    error_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    info_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Validation errors table
CREATE TABLE IF NOT EXISTS validation_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    error_message TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('ERROR', 'WARNING', 'INFO')),
    category VARCHAR(50) NOT NULL CHECK (category IN ('SCHEMA', 'BUSINESS_RULE', 'CROSS_FIELD', 'RANGE', 'FORMAT', 'REFERENCE')),
    actual_value TEXT,
    expected_value TEXT,
    context JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Validation bypasses table
CREATE TABLE IF NOT EXISTS validation_bypasses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    bypass_reason TEXT NOT NULL,
    created_by VARCHAR(255),
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure only one active bypass per entity
    UNIQUE(entity_id, entity_type)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_validation_results_entity ON validation_results(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_validation_results_validated_at ON validation_results(validated_at);
CREATE INDEX IF NOT EXISTS idx_validation_results_is_valid ON validation_results(is_valid);

CREATE INDEX IF NOT EXISTS idx_validation_errors_entity ON validation_errors(entity_id);
CREATE INDEX IF NOT EXISTS idx_validation_errors_severity ON validation_errors(severity);
CREATE INDEX IF NOT EXISTS idx_validation_errors_category ON validation_errors(category);

CREATE INDEX IF NOT EXISTS idx_validation_bypasses_entity ON validation_bypasses(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_validation_bypasses_active ON validation_bypasses(active);

-- Triggers for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_validation_results_updated_at 
    BEFORE UPDATE ON validation_results 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_validation_bypasses_updated_at 
    BEFORE UPDATE ON validation_bypasses 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE validation_results IS 'Stores results of schema validation operations';
COMMENT ON TABLE validation_errors IS 'Stores individual validation errors with details';
COMMENT ON TABLE validation_bypasses IS 'Manages validation bypasses for manual review cases';

COMMENT ON COLUMN validation_results.entity_id IS 'ID of the entity being validated (section, FDD, etc.)';
COMMENT ON COLUMN validation_results.entity_type IS 'Type of entity (InitialFee, OtherFee, etc.)';
COMMENT ON COLUMN validation_results.validation_duration_ms IS 'Time taken for validation in milliseconds';

COMMENT ON COLUMN validation_errors.severity IS 'ERROR blocks processing, WARNING flags for review, INFO is informational';
COMMENT ON COLUMN validation_errors.category IS 'Category of validation error for reporting and analysis';
COMMENT ON COLUMN validation_errors.context IS 'Additional context data as JSON';

COMMENT ON COLUMN validation_bypasses.bypass_reason IS 'Reason for bypassing validation (manual review, etc.)';
COMMENT ON COLUMN validation_bypasses.created_by IS 'User who created the bypass';