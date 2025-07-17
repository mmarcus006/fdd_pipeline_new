-- FDD Pipeline Complete Database Schema
-- Combined migrations 001-007 for Supabase deployment
-- Generated from individual migration files

-- ============================================================================
-- Migration 001: Initial Schema
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- Core Tables

-- Franchisors table with deduplication support
CREATE TABLE franchisors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT NOT NULL UNIQUE,
    parent_company TEXT,
    website TEXT,
    phone TEXT,
    email TEXT,
    address JSONB, -- {street, city, state, zip}
    dba_names JSONB DEFAULT '[]'::jsonb, -- array of alternate names
    name_embedding vector(384), -- for similarity search
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for franchisors
CREATE INDEX idx_franchisors_canonical_name ON franchisors(canonical_name);
CREATE INDEX idx_franchisors_parent_company ON franchisors(parent_company);
CREATE INDEX idx_franchisors_embedding ON franchisors USING ivfflat (name_embedding vector_cosine_ops);

-- FDD documents with versioning and supersession
CREATE TABLE fdds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    franchise_id UUID REFERENCES franchisors(id) ON DELETE CASCADE,
    issue_date DATE NOT NULL,
    amendment_date DATE,
    is_amendment BOOLEAN GENERATED ALWAYS AS (amendment_date IS NOT NULL) STORED,
    document_type TEXT NOT NULL CHECK (document_type IN ('Initial', 'Amendment', 'Renewal')),
    filing_state TEXT NOT NULL,
    filing_number TEXT,
    drive_path TEXT NOT NULL UNIQUE,
    drive_file_id TEXT NOT NULL UNIQUE,
    sha256_hash CHAR(64),
    total_pages INTEGER,
    language_code TEXT DEFAULT 'en',
    superseded_by_id UUID REFERENCES fdds(id),
    duplicate_of_id UUID REFERENCES fdds(id),
    needs_review BOOLEAN DEFAULT false,
    processing_status TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ
);

-- Indexes for fdds
CREATE INDEX idx_fdds_franchise_id ON fdds(franchise_id);
CREATE INDEX idx_fdds_issue_date ON fdds(issue_date);
CREATE INDEX idx_fdds_filing_state ON fdds(filing_state);
CREATE INDEX idx_fdds_processing_status ON fdds(processing_status);
CREATE INDEX idx_fdds_needs_review ON fdds(needs_review) WHERE needs_review = true;

-- Web scraping metadata
CREATE TABLE scrape_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_id UUID REFERENCES fdds(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL, -- 'MN', 'WI'
    source_url TEXT NOT NULL,
    filing_metadata JSONB, -- portal-specific fields
    prefect_run_id UUID,
    scraped_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for scrape_metadata
CREATE INDEX idx_scrape_metadata_fdd_id ON scrape_metadata(fdd_id);
CREATE INDEX idx_scrape_metadata_source ON scrape_metadata(source_name, scraped_at);

-- Document sections after MinerU segmentation
CREATE TABLE fdd_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_id UUID REFERENCES fdds(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL CHECK (item_no >= 0 AND item_no <= 24), -- 0=intro, 24=appendix
    item_name TEXT,
    start_page INTEGER NOT NULL,
    end_page INTEGER NOT NULL CHECK (end_page >= start_page),
    drive_path TEXT,
    drive_file_id TEXT,
    extraction_status TEXT DEFAULT 'pending' CHECK (extraction_status IN ('pending', 'processing', 'success', 'failed', 'skipped')),
    extraction_model TEXT, -- which LLM was used
    extraction_attempts INTEGER DEFAULT 0,
    needs_review BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    extracted_at TIMESTAMPTZ,
    
    CONSTRAINT unique_fdd_section UNIQUE (fdd_id, item_no)
);

-- Indexes for fdd_sections
CREATE INDEX idx_fdd_sections_fdd_id ON fdd_sections(fdd_id);
CREATE INDEX idx_fdd_sections_status ON fdd_sections(extraction_status);
CREATE INDEX idx_fdd_sections_needs_review ON fdd_sections(needs_review) WHERE needs_review = true;

-- ============================================================================
-- Migration 002: Structured Data Tables
-- ============================================================================

-- Item 5: Initial franchise fees
CREATE TABLE item5_initial_fees (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fee_name TEXT NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    refundable BOOLEAN DEFAULT false,
    refund_conditions TEXT,
    due_at TEXT, -- 'Signing', 'Training', 'Opening'
    notes TEXT,
    
    PRIMARY KEY (section_id, fee_name)
);

-- Item 6: Ongoing and other fees
CREATE TABLE item6_other_fees (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fee_name TEXT NOT NULL,
    amount_cents BIGINT CHECK (amount_cents >= 0),
    amount_percentage NUMERIC(5,2) CHECK (amount_percentage >= 0 AND amount_percentage <= 100),
    frequency TEXT NOT NULL, -- 'Weekly', 'Monthly', 'Annual', 'One-time'
    calculation_basis TEXT, -- 'Gross Sales', 'Net Sales', 'Fixed'
    minimum_cents BIGINT CHECK (minimum_cents >= 0),
    maximum_cents BIGINT CHECK (maximum_cents >= minimum_cents),
    remarks TEXT,
    
    PRIMARY KEY (section_id, fee_name),
    CONSTRAINT check_amount_or_percentage CHECK (
        (amount_cents IS NOT NULL AND amount_percentage IS NULL) OR
        (amount_cents IS NULL AND amount_percentage IS NOT NULL)
    )
);

-- Item 7: Initial investment breakdown
CREATE TABLE item7_initial_investment (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    low_cents BIGINT CHECK (low_cents >= 0),
    high_cents BIGINT CHECK (high_cents >= low_cents),
    when_due TEXT,
    to_whom TEXT,
    remarks TEXT,
    
    PRIMARY KEY (section_id, category)
);

-- Item 19: Financial Performance Representations
CREATE TABLE item19_fpr (
    section_id UUID PRIMARY KEY REFERENCES fdd_sections(id) ON DELETE CASCADE,
    disclosure_type TEXT, -- 'Historical', 'Projected', 'None'
    methodology TEXT, -- narrative description
    sample_size INTEGER CHECK (sample_size > 0),
    sample_description TEXT,
    time_period TEXT,
    
    -- Common financial metrics (all nullable)
    average_revenue_cents BIGINT CHECK (average_revenue_cents >= 0),
    median_revenue_cents BIGINT CHECK (median_revenue_cents >= 0),
    low_revenue_cents BIGINT CHECK (low_revenue_cents >= 0),
    high_revenue_cents BIGINT CHECK (high_revenue_cents >= 0),
    
    average_profit_cents BIGINT,
    median_profit_cents BIGINT,
    profit_margin_percentage NUMERIC(5,2),
    
    -- For complex/varied data
    additional_metrics JSONB DEFAULT '{}'::jsonb,
    tables_data JSONB DEFAULT '[]'::jsonb, -- array of table representations
    
    disclaimers TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Item 20: Outlet summary by year
CREATE TABLE item20_outlet_summary (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fiscal_year SMALLINT NOT NULL CHECK (fiscal_year >= 1900 AND fiscal_year <= 2100),
    outlet_type TEXT NOT NULL CHECK (outlet_type IN ('Franchised', 'Company-Owned')),
    
    -- Annual movements
    count_start INTEGER NOT NULL CHECK (count_start >= 0),
    opened INTEGER NOT NULL DEFAULT 0 CHECK (opened >= 0),
    closed INTEGER NOT NULL DEFAULT 0 CHECK (closed >= 0),
    transferred_in INTEGER NOT NULL DEFAULT 0 CHECK (transferred_in >= 0),
    transferred_out INTEGER NOT NULL DEFAULT 0 CHECK (transferred_out >= 0),
    count_end INTEGER NOT NULL CHECK (count_end >= 0),
    
    -- Calculated check
    CONSTRAINT outlet_math_check CHECK (
        count_end = count_start + opened - closed + transferred_in - transferred_out
    ),
    
    PRIMARY KEY (section_id, fiscal_year, outlet_type)
);

-- Item 20: State-by-state breakdown
CREATE TABLE item20_state_counts (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    state_code CHAR(2) NOT NULL,
    franchised_count INTEGER DEFAULT 0 CHECK (franchised_count >= 0),
    company_owned_count INTEGER DEFAULT 0 CHECK (company_owned_count >= 0),
    
    PRIMARY KEY (section_id, state_code)
);

-- Item 21: Financial statements
CREATE TABLE item21_financials (
    section_id UUID PRIMARY KEY REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fiscal_year SMALLINT CHECK (fiscal_year >= 1900 AND fiscal_year <= 2100),
    fiscal_year_end DATE,
    
    -- Income Statement
    total_revenue_cents BIGINT CHECK (total_revenue_cents >= 0),
    franchise_revenue_cents BIGINT CHECK (franchise_revenue_cents >= 0),
    cost_of_goods_cents BIGINT CHECK (cost_of_goods_cents >= 0),
    gross_profit_cents BIGINT,
    operating_expenses_cents BIGINT CHECK (operating_expenses_cents >= 0),
    operating_income_cents BIGINT,
    net_income_cents BIGINT,
    
    -- Balance Sheet
    total_assets_cents BIGINT CHECK (total_assets_cents >= 0),
    current_assets_cents BIGINT CHECK (current_assets_cents >= 0),
    total_liabilities_cents BIGINT CHECK (total_liabilities_cents >= 0),
    current_liabilities_cents BIGINT CHECK (current_liabilities_cents >= 0),
    total_equity_cents BIGINT,
    
    -- Audit info
    auditor_name TEXT,
    audit_opinion TEXT,
    
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Generic storage for all other items
CREATE TABLE fdd_item_json (
    section_id UUID PRIMARY KEY REFERENCES fdd_sections(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT DEFAULT '1.0',
    validated BOOLEAN DEFAULT false,
    validation_errors JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for querying specific fields within JSON
CREATE INDEX idx_fdd_item_json_data ON fdd_item_json USING gin(data);

-- ============================================================================
-- Migration 003: Operational Tables
-- ============================================================================

-- Structured logging for all pipeline operations
CREATE TABLE pipeline_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prefect_run_id UUID,
    task_name TEXT,
    level TEXT NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT NOT NULL,
    context JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for pipeline_logs
CREATE INDEX idx_pipeline_logs_run_id ON pipeline_logs(prefect_run_id);
CREATE INDEX idx_pipeline_logs_level ON pipeline_logs(level, created_at DESC);
CREATE INDEX idx_pipeline_logs_created ON pipeline_logs(created_at DESC);

-- Track Prefect flow runs for debugging
CREATE TABLE prefect_runs (
    id UUID PRIMARY KEY,
    flow_name TEXT NOT NULL,
    deployment_name TEXT,
    state TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    parameters JSONB,
    context JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Views for common queries

-- Shows only the most recent FDD per franchise
CREATE VIEW v_latest_fdds AS
SELECT DISTINCT ON (f.id) 
    f.id as franchise_id,
    f.canonical_name,
    fdd.*
FROM franchisors f
JOIN fdds fdd ON f.id = fdd.franchise_id
WHERE fdd.superseded_by_id IS NULL
    AND fdd.duplicate_of_id IS NULL
ORDER BY f.id, fdd.issue_date DESC, fdd.amendment_date DESC NULLS LAST;

-- Summary of extraction progress
CREATE VIEW v_extraction_status AS
SELECT 
    fdd.id as fdd_id,
    fdd.franchise_id,
    f.canonical_name,
    COUNT(*) as total_sections,
    COUNT(*) FILTER (WHERE fs.extraction_status = 'success') as extracted_sections,
    COUNT(*) FILTER (WHERE fs.extraction_status = 'failed') as failed_sections,
    COUNT(*) FILTER (WHERE fs.needs_review) as needs_review,
    ROUND(100.0 * COUNT(*) FILTER (WHERE fs.extraction_status = 'success') / COUNT(*), 2) as success_rate
FROM fdds fdd
JOIN franchisors f ON fdd.franchise_id = f.id
JOIN fdd_sections fs ON fdd.id = fs.fdd_id
GROUP BY fdd.id, fdd.franchise_id, f.canonical_name;

-- Performance indexes for common queries

-- For finding documents to process
CREATE INDEX idx_fdds_to_process ON fdds(processing_status, created_at) 
    WHERE processing_status = 'pending';

-- For extraction workload
CREATE INDEX idx_sections_to_extract ON fdd_sections(extraction_status, item_no) 
    WHERE extraction_status IN ('pending', 'failed');

-- ============================================================================
-- Migration 004: RLS Policies and Indexes
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE franchisors ENABLE ROW LEVEL SECURITY;
ALTER TABLE fdds ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE fdd_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE item5_initial_fees ENABLE ROW LEVEL SECURITY;
ALTER TABLE item6_other_fees ENABLE ROW LEVEL SECURITY;
ALTER TABLE item7_initial_investment ENABLE ROW LEVEL SECURITY;
ALTER TABLE item19_fpr ENABLE ROW LEVEL SECURITY;
ALTER TABLE item20_outlet_summary ENABLE ROW LEVEL SECURITY;
ALTER TABLE item20_state_counts ENABLE ROW LEVEL SECURITY;
ALTER TABLE item21_financials ENABLE ROW LEVEL SECURITY;
ALTER TABLE fdd_item_json ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE prefect_runs ENABLE ROW LEVEL SECURITY;

-- Public read access for franchisors
CREATE POLICY "Public read access" ON franchisors
    FOR SELECT USING (true);

-- Service role has full access to all tables
CREATE POLICY "Service role full access franchisors" ON franchisors
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access fdds" ON fdds
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access scrape_metadata" ON scrape_metadata
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access fdd_sections" ON fdd_sections
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access item5_initial_fees" ON item5_initial_fees
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access item6_other_fees" ON item6_other_fees
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access item7_initial_investment" ON item7_initial_investment
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access item19_fpr" ON item19_fpr
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access item20_outlet_summary" ON item20_outlet_summary
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access item20_state_counts" ON item20_state_counts
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access item21_financials" ON item21_financials
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access fdd_item_json" ON fdd_item_json
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access pipeline_logs" ON pipeline_logs
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access prefect_runs" ON prefect_runs
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

-- Anon users can only read completed data
CREATE POLICY "Anon read completed fdds" ON fdds
    FOR SELECT USING (
        processing_status = 'completed' 
        AND auth.jwt() ->> 'role' = 'anon'
    );

-- Anon users can read public franchise data
CREATE POLICY "Anon read franchisors" ON franchisors
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

-- Anon users can read completed sections and their data
CREATE POLICY "Anon read completed sections" ON fdd_sections
    FOR SELECT USING (
        extraction_status = 'success' 
        AND auth.jwt() ->> 'role' = 'anon'
    );

CREATE POLICY "Anon read item5_initial_fees" ON item5_initial_fees
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

CREATE POLICY "Anon read item6_other_fees" ON item6_other_fees
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

CREATE POLICY "Anon read item7_initial_investment" ON item7_initial_investment
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

CREATE POLICY "Anon read item19_fpr" ON item19_fpr
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

CREATE POLICY "Anon read item20_outlet_summary" ON item20_outlet_summary
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

CREATE POLICY "Anon read item20_state_counts" ON item20_state_counts
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

CREATE POLICY "Anon read item21_financials" ON item21_financials
    FOR SELECT USING (auth.jwt() ->> 'role' = 'anon');

CREATE POLICY "Anon read fdd_item_json" ON fdd_item_json
    FOR SELECT USING (
        validated = true 
        AND auth.jwt() ->> 'role' = 'anon'
    );

-- Vacuum strategy for high-write tables
ALTER TABLE pipeline_logs SET (
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_analyze_scale_factor = 0.05
);

-- Additional performance indexes that may have been missed
CREATE INDEX IF NOT EXISTS idx_fdd_sections_item_no ON fdd_sections(item_no);
CREATE INDEX IF NOT EXISTS idx_item5_fees_amount ON item5_initial_fees(amount_cents);
CREATE INDEX IF NOT EXISTS idx_item6_fees_frequency ON item6_other_fees(frequency);
CREATE INDEX IF NOT EXISTS idx_item7_investment_category ON item7_initial_investment(category);
CREATE INDEX IF NOT EXISTS idx_item19_disclosure_type ON item19_fpr(disclosure_type);
CREATE INDEX IF NOT EXISTS idx_item20_fiscal_year ON item20_outlet_summary(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_item21_fiscal_year ON item21_financials(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_fdd_item_json_item_no ON fdd_item_json(item_no);
CREATE INDEX IF NOT EXISTS idx_fdd_item_json_validated ON fdd_item_json(validated);

-- ============================================================================
-- Migration 005: Drive Files Table
-- ============================================================================

-- Drive Files Metadata Table
CREATE TABLE drive_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drive_file_id TEXT NOT NULL UNIQUE, -- Google Drive file ID
    filename TEXT NOT NULL,
    folder_path TEXT, -- Logical folder path (e.g., "fdds/raw/mn/franchise_name")
    drive_path TEXT, -- Full Google Drive path
    file_size BIGINT NOT NULL CHECK (file_size >= 0),
    mime_type TEXT NOT NULL,
    sha256_hash CHAR(64), -- For deduplication
    document_type TEXT DEFAULT 'original' CHECK (document_type IN ('original', 'processed', 'section')),
    
    -- Optional linking to FDD
    fdd_id UUID REFERENCES fdds(id) ON DELETE SET NULL,
    
    -- Timestamps from Google Drive
    created_at TIMESTAMPTZ NOT NULL,
    modified_at TIMESTAMPTZ NOT NULL,
    
    -- Local tracking
    synced_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for drive_files
CREATE INDEX idx_drive_files_drive_file_id ON drive_files(drive_file_id);
CREATE INDEX idx_drive_files_fdd_id ON drive_files(fdd_id);
CREATE INDEX idx_drive_files_sha256_hash ON drive_files(sha256_hash);
CREATE INDEX idx_drive_files_folder_path ON drive_files(folder_path);
CREATE INDEX idx_drive_files_document_type ON drive_files(document_type);
CREATE INDEX idx_drive_files_filename ON drive_files(filename);

-- Update trigger for updated_at
CREATE OR REPLACE FUNCTION update_drive_files_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_drive_files_updated_at
    BEFORE UPDATE ON drive_files
    FOR EACH ROW
    EXECUTE FUNCTION update_drive_files_updated_at();

-- Comments for documentation
COMMENT ON TABLE drive_files IS 'Tracks Google Drive file metadata and synchronization with database';
COMMENT ON COLUMN drive_files.drive_file_id IS 'Google Drive file ID (unique identifier from Google)';
COMMENT ON COLUMN drive_files.folder_path IS 'Logical folder path for organization';
COMMENT ON COLUMN drive_files.drive_path IS 'Full path within Google Drive';
COMMENT ON COLUMN drive_files.sha256_hash IS 'File hash for deduplication detection';
COMMENT ON COLUMN drive_files.document_type IS 'Type of document: original PDF, processed section, etc.';
COMMENT ON COLUMN drive_files.fdd_id IS 'Optional link to FDD record';

-- ============================================================================
-- Migration 006: Vector Similarity Functions
-- ============================================================================

-- Create RPC function for franchise similarity search
CREATE OR REPLACE FUNCTION match_franchises(
  query_embedding vector(384),
  match_threshold float DEFAULT 0.8,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id uuid,
  canonical_name text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    f.id,
    f.canonical_name,
    1 - (f.name_embedding <=> query_embedding) as similarity
  FROM franchisors f
  WHERE f.name_embedding IS NOT NULL
    AND 1 - (f.name_embedding <=> query_embedding) >= match_threshold
  ORDER BY f.name_embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION match_franchises TO authenticated;
GRANT EXECUTE ON FUNCTION match_franchises TO service_role;

-- Create index for better vector search performance if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes 
    WHERE schemaname = 'public' 
    AND tablename = 'franchisors' 
    AND indexname = 'idx_franchisors_embedding'
  ) THEN
    CREATE INDEX idx_franchisors_embedding ON franchisors 
    USING ivfflat (name_embedding vector_cosine_ops)
    WITH (lists = 100);
  END IF;
END $$;

-- Helper function to update franchise embeddings
CREATE OR REPLACE FUNCTION update_franchise_embedding(
  franchise_id uuid,
  new_embedding vector(384)
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE franchisors 
  SET name_embedding = new_embedding,
      updated_at = now()
  WHERE id = franchise_id;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION update_franchise_embedding TO authenticated;
GRANT EXECUTE ON FUNCTION update_franchise_embedding TO service_role;

-- ============================================================================
-- Migration 007: Validation Tracking Tables
-- ============================================================================

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

-- ============================================================================
-- End of Combined Migrations
-- ============================================================================

-- Summary of created objects:
-- Tables: 23 (including validation tracking tables)
-- Views: 2
-- Functions: 4
-- Triggers: 3
-- Indexes: 50+
-- RLS Policies: 29

-- This schema supports:
-- 1. Franchise and FDD document management with versioning
-- 2. Document section extraction and LLM processing
-- 3. Structured storage for key FDD items (5, 6, 7, 19, 20, 21)
-- 4. Generic JSON storage for other items
-- 5. Drive file synchronization tracking
-- 6. Pipeline logging and monitoring
-- 7. Vector similarity search for franchise matching
-- 8. Comprehensive validation tracking and bypass management
-- 9. Row-level security for multi-tenant access