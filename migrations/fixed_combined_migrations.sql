-- FDD Pipeline Complete Database Schema
-- This file combines all migrations into a single script for Supabase

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Migration 001: Initial Schema
-- ============================================================================

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
CREATE INDEX idx_fdds_issue_date ON fdds(issue_date DESC);
CREATE INDEX idx_fdds_filing_state ON fdds(filing_state);
CREATE INDEX idx_fdds_processing_status ON fdds(processing_status);
CREATE INDEX idx_fdds_superseded_by ON fdds(superseded_by_id) WHERE superseded_by_id IS NOT NULL;

-- Composite indexes for performance
CREATE INDEX idx_fdds_franchise_date ON fdds(franchise_id, issue_date DESC);

-- Scraping metadata and state tracking
CREATE TABLE scrape_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_id UUID REFERENCES fdds(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL, -- 'wisconsin', 'minnesota', etc.
    source_url TEXT NOT NULL,
    download_url TEXT,
    portal_id TEXT, -- State system's ID for the record
    registration_status TEXT,
    effective_date DATE,
    scrape_status TEXT DEFAULT 'discovered' CHECK (scrape_status IN ('discovered', 'downloaded', 'failed', 'skipped')),
    failure_reason TEXT,
    downloaded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source_name, portal_id) -- Prevent duplicate scrapes
);

-- Indexes for scrape_metadata
CREATE INDEX idx_scrape_metadata_fdd_id ON scrape_metadata(fdd_id);
CREATE INDEX idx_scrape_metadata_source ON scrape_metadata(source_name, scrape_status);
CREATE INDEX idx_scrape_metadata_portal_id ON scrape_metadata(portal_id);

-- FDD sections tracking
CREATE TABLE fdd_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_id UUID REFERENCES fdds(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL,
    item_name TEXT,
    start_page INTEGER NOT NULL,
    end_page INTEGER NOT NULL,
    drive_path TEXT, -- Path to segmented PDF in Drive
    drive_file_id TEXT, -- Drive ID for segmented PDF
    extraction_status TEXT DEFAULT 'pending' CHECK (extraction_status IN ('pending', 'processing', 'completed', 'failed', 'skipped')),
    extraction_model TEXT, -- Which LLM was used
    extraction_attempts INTEGER DEFAULT 0,
    needs_review BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    extracted_at TIMESTAMPTZ,
    UNIQUE(fdd_id, item_no)
);

-- Indexes for fdd_sections
CREATE INDEX idx_fdd_sections_fdd_id ON fdd_sections(fdd_id);
CREATE INDEX idx_fdd_sections_status ON fdd_sections(extraction_status);
CREATE INDEX idx_fdd_sections_item_no ON fdd_sections(item_no);

-- ============================================================================
-- Migration 002: Structured Data Tables
-- ============================================================================

-- Item 5: Initial Fees
CREATE TABLE item5_fees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    initial_franchise_fee DECIMAL(12, 2),
    fee_is_refundable BOOLEAN,
    fee_conditions TEXT,
    low_fee DECIMAL(12, 2),
    high_fee DECIMAL(12, 2),
    fee_variations TEXT[], -- Array of fee variation descriptions
    extracted_at TIMESTAMPTZ DEFAULT now(),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    raw_text TEXT,
    validation_status TEXT DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'needs_review', 'invalid'))
);

-- Item 6: Other Fees and Costs
CREATE TABLE item6_other_fees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fee_type TEXT NOT NULL,
    amount DECIMAL(12, 2),
    amount_min DECIMAL(12, 2),
    amount_max DECIMAL(12, 2),
    fee_frequency TEXT,
    due_date TEXT,
    remarks TEXT,
    extracted_at TIMESTAMPTZ DEFAULT now(),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    validation_status TEXT DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'needs_review', 'invalid'))
);

-- Item 7: Estimated Initial Investment
CREATE TABLE item7_investment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    expense_type TEXT NOT NULL,
    low_amount DECIMAL(12, 2),
    high_amount DECIMAL(12, 2),
    method_of_payment TEXT,
    when_due TEXT,
    to_whom_paid TEXT,
    remarks TEXT,
    extracted_at TIMESTAMPTZ DEFAULT now(),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    validation_status TEXT DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'needs_review', 'invalid'))
);

-- Item 19: Financial Performance Representations
CREATE TABLE item19_fpr (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    has_fpr BOOLEAN NOT NULL,
    revenue_data JSONB, -- Flexible structure for various revenue representations
    expense_data JSONB,
    profit_data JSONB,
    unit_count INTEGER,
    time_period TEXT,
    geographic_scope TEXT,
    data_notes TEXT,
    substantiation_available BOOLEAN,
    extracted_at TIMESTAMPTZ DEFAULT now(),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    raw_text TEXT,
    validation_status TEXT DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'needs_review', 'invalid'))
);

-- Item 20: Outlets and Franchise Information
CREATE TABLE item20_outlets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    state_code TEXT NOT NULL,
    franchise_owned INTEGER DEFAULT 0,
    company_owned INTEGER DEFAULT 0,
    total_outlets INTEGER GENERATED ALWAYS AS (franchise_owned + company_owned) STORED,
    transfers INTEGER DEFAULT 0,
    terminations INTEGER DEFAULT 0,
    non_renewals INTEGER DEFAULT 0,
    reacquired INTEGER DEFAULT 0,
    ceased_operations INTEGER DEFAULT 0,
    extracted_at TIMESTAMPTZ DEFAULT now(),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    validation_status TEXT DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'needs_review', 'invalid'))
);

-- Item 21: Financial Statements
CREATE TABLE item21_financials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    statement_type TEXT NOT NULL CHECK (statement_type IN ('audited', 'unaudited', 'reviewed')),
    fiscal_year_end DATE,
    total_revenue DECIMAL(15, 2),
    net_income DECIMAL(15, 2),
    total_assets DECIMAL(15, 2),
    total_liabilities DECIMAL(15, 2),
    stockholders_equity DECIMAL(15, 2),
    audit_firm TEXT,
    opinion_type TEXT,
    extracted_at TIMESTAMPTZ DEFAULT now(),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    raw_text TEXT,
    validation_status TEXT DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'needs_review', 'invalid'))
);

-- Generic JSON storage for flexibility
CREATE TABLE item_json (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL,
    extracted_data JSONB NOT NULL,
    extraction_model TEXT,
    extraction_prompt_version TEXT,
    extracted_at TIMESTAMPTZ DEFAULT now(),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    validation_status TEXT DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'needs_review', 'invalid'))
);

-- Indexes for all structured tables
CREATE INDEX idx_item5_fees_section ON item5_fees(fdd_section_id);
CREATE INDEX idx_item6_other_fees_section ON item6_other_fees(fdd_section_id);
CREATE INDEX idx_item7_investment_section ON item7_investment(fdd_section_id);
CREATE INDEX idx_item19_fpr_section ON item19_fpr(fdd_section_id);
CREATE INDEX idx_item20_outlets_section ON item20_outlets(fdd_section_id);
CREATE INDEX idx_item20_outlets_year_state ON item20_outlets(year, state_code);
CREATE INDEX idx_item21_financials_section ON item21_financials(fdd_section_id);
CREATE INDEX idx_item_json_section ON item_json(fdd_section_id);
CREATE INDEX idx_item_json_item_no ON item_json(item_no);

-- ============================================================================
-- Migration 003: Operational Tables
-- ============================================================================

-- Pipeline logs for monitoring and debugging
CREATE TABLE pipeline_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL, -- Prefect run ID
    task_name TEXT NOT NULL,
    fdd_id UUID REFERENCES fdds(id),
    level TEXT NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT NOT NULL,
    context JSONB, -- Additional structured data
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for pipeline_logs
CREATE INDEX idx_pipeline_logs_run_id ON pipeline_logs(run_id);
CREATE INDEX idx_pipeline_logs_fdd_id ON pipeline_logs(fdd_id);
CREATE INDEX idx_pipeline_logs_level ON pipeline_logs(level);
CREATE INDEX idx_pipeline_logs_created ON pipeline_logs(created_at DESC);

-- Prefect run tracking
CREATE TABLE prefect_runs (
    id UUID PRIMARY KEY,
    flow_name TEXT NOT NULL,
    flow_run_name TEXT,
    state TEXT NOT NULL,
    state_name TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    parameters JSONB,
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for prefect_runs
CREATE INDEX idx_prefect_runs_flow_name ON prefect_runs(flow_name);
CREATE INDEX idx_prefect_runs_state ON prefect_runs(state);
CREATE INDEX idx_prefect_runs_started ON prefect_runs(started_at DESC);

-- Create useful views
-- View for latest FDD per franchise
CREATE VIEW latest_fdds AS
SELECT DISTINCT ON (f.id)
    f.id as franchise_id,
    f.canonical_name,
    fdd.id as fdd_id,
    fdd.issue_date,
    fdd.filing_state,
    fdd.processing_status
FROM franchisors f
JOIN fdds fdd ON f.id = fdd.franchise_id
WHERE fdd.superseded_by_id IS NULL
ORDER BY f.id, fdd.issue_date DESC;

-- View for extraction progress
CREATE VIEW extraction_status AS
SELECT 
    fdd.id as fdd_id,
    fdd.franchise_id,
    f.canonical_name,
    COUNT(DISTINCT s.id) as total_sections,
    COUNT(DISTINCT s.id) FILTER (WHERE s.extraction_status = 'completed') as completed_sections,
    COUNT(DISTINCT s.id) FILTER (WHERE s.extraction_status = 'failed') as failed_sections,
    ROUND(100.0 * COUNT(DISTINCT s.id) FILTER (WHERE s.extraction_status = 'completed') / NULLIF(COUNT(DISTINCT s.id), 0), 2) as completion_percentage
FROM fdds fdd
JOIN franchisors f ON fdd.franchise_id = f.id
LEFT JOIN fdd_sections s ON fdd.id = s.fdd_id
GROUP BY fdd.id, fdd.franchise_id, f.canonical_name;

-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at
CREATE TRIGGER update_franchisors_updated_at BEFORE UPDATE ON franchisors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- Migration 004: RLS Policies and Indexes
-- ============================================================================

-- Enable Row Level Security
ALTER TABLE franchisors ENABLE ROW LEVEL SECURITY;
ALTER TABLE fdds ENABLE ROW LEVEL SECURITY;
ALTER TABLE fdd_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE item5_fees ENABLE ROW LEVEL SECURITY;
ALTER TABLE item6_other_fees ENABLE ROW LEVEL SECURITY;
ALTER TABLE item7_investment ENABLE ROW LEVEL SECURITY;
ALTER TABLE item19_fpr ENABLE ROW LEVEL SECURITY;
ALTER TABLE item20_outlets ENABLE ROW LEVEL SECURITY;
ALTER TABLE item21_financials ENABLE ROW LEVEL SECURITY;
ALTER TABLE item_json ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE prefect_runs ENABLE ROW LEVEL SECURITY;

-- Create policies for service role (full access)
CREATE POLICY "Service role has full access to franchisors" ON franchisors
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to fdds" ON fdds
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to fdd_sections" ON fdd_sections
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to scrape_metadata" ON scrape_metadata
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to item5_fees" ON item5_fees
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to item6_other_fees" ON item6_other_fees
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to item7_investment" ON item7_investment
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to item19_fpr" ON item19_fpr
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to item20_outlets" ON item20_outlets
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to item21_financials" ON item21_financials
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to item_json" ON item_json
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to pipeline_logs" ON pipeline_logs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to prefect_runs" ON prefect_runs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Create policies for authenticated users (read-only for now)
CREATE POLICY "Authenticated users can read franchisors" ON franchisors
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read fdds" ON fdds
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read fdd_sections" ON fdd_sections
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read item5_fees" ON item5_fees
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read item6_other_fees" ON item6_other_fees
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read item7_investment" ON item7_investment
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read item19_fpr" ON item19_fpr
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read item20_outlets" ON item20_outlets
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read item21_financials" ON item21_financials
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read item_json" ON item_json
    FOR SELECT TO authenticated USING (true);

-- Additional performance indexes
CREATE INDEX idx_fdds_created_at ON fdds(created_at DESC);
CREATE INDEX idx_fdd_sections_created_at ON fdd_sections(created_at DESC);
CREATE INDEX idx_scrape_metadata_created_at ON scrape_metadata(created_at DESC);

-- Composite indexes for common queries
CREATE INDEX idx_fdds_franchise_status ON fdds(franchise_id, processing_status);
CREATE INDEX idx_sections_fdd_status ON fdd_sections(fdd_id, extraction_status);

-- Indexes for JSON fields (using GIN for better performance)
CREATE INDEX idx_item19_revenue_data ON item19_fpr USING GIN (revenue_data);
CREATE INDEX idx_item19_expense_data ON item19_fpr USING GIN (expense_data);
CREATE INDEX idx_item_json_data ON item_json USING GIN (extracted_data);

-- Partial indexes for common filters
CREATE INDEX idx_fdds_needs_review ON fdds(id) WHERE needs_review = true;
CREATE INDEX idx_sections_needs_review ON fdd_sections(id) WHERE needs_review = true;
CREATE INDEX idx_fdds_processing ON fdds(id) WHERE processing_status = 'processing';
CREATE INDEX idx_sections_pending ON fdd_sections(id) WHERE extraction_status = 'pending';

-- ============================================================================
-- Migration 005: Drive Files Table
-- ============================================================================

-- Google Drive file tracking
CREATE TABLE drive_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    parent_folder_id TEXT,
    size_bytes BIGINT,
    md5_checksum TEXT,
    web_view_link TEXT,
    download_link TEXT,
    -- Relations to our entities
    fdd_id UUID REFERENCES fdds(id) ON DELETE SET NULL,
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE SET NULL,
    -- Metadata
    created_time TIMESTAMPTZ,
    modified_time TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ DEFAULT now(),
    sync_status TEXT DEFAULT 'active' CHECK (sync_status IN ('active', 'deleted', 'error')),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for drive_files
CREATE INDEX idx_drive_files_file_id ON drive_files(file_id);
CREATE INDEX idx_drive_files_fdd_id ON drive_files(fdd_id);
CREATE INDEX idx_drive_files_section_id ON drive_files(fdd_section_id);
CREATE INDEX idx_drive_files_parent ON drive_files(parent_folder_id);
CREATE INDEX idx_drive_files_sync_status ON drive_files(sync_status);

-- Enable RLS
ALTER TABLE drive_files ENABLE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY "Service role has full access to drive_files" ON drive_files
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read drive_files" ON drive_files
    FOR SELECT TO authenticated USING (true);

-- Function to sync drive file metadata
CREATE OR REPLACE FUNCTION sync_drive_file(
    p_file_id TEXT,
    p_file_name TEXT,
    p_mime_type TEXT,
    p_parent_folder_id TEXT,
    p_size_bytes BIGINT,
    p_md5_checksum TEXT,
    p_web_view_link TEXT,
    p_download_link TEXT,
    p_created_time TIMESTAMPTZ,
    p_modified_time TIMESTAMPTZ
)
RETURNS UUID AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO drive_files (
        file_id, file_name, mime_type, parent_folder_id,
        size_bytes, md5_checksum, web_view_link, download_link,
        created_time, modified_time, last_synced_at
    ) VALUES (
        p_file_id, p_file_name, p_mime_type, p_parent_folder_id,
        p_size_bytes, p_md5_checksum, p_web_view_link, p_download_link,
        p_created_time, p_modified_time, now()
    )
    ON CONFLICT (file_id) DO UPDATE SET
        file_name = EXCLUDED.file_name,
        mime_type = EXCLUDED.mime_type,
        parent_folder_id = EXCLUDED.parent_folder_id,
        size_bytes = EXCLUDED.size_bytes,
        md5_checksum = EXCLUDED.md5_checksum,
        web_view_link = EXCLUDED.web_view_link,
        download_link = EXCLUDED.download_link,
        modified_time = EXCLUDED.modified_time,
        last_synced_at = now()
    RETURNING id INTO v_id;
    
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION sync_drive_file TO authenticated;
GRANT EXECUTE ON FUNCTION sync_drive_file TO service_role;

-- ============================================================================
-- Migration 006: Vector Similarity Functions
-- ============================================================================

-- Function to find similar franchises by name
CREATE OR REPLACE FUNCTION find_similar_franchises(
    query_text TEXT,
    query_embedding vector(384),
    similarity_threshold FLOAT DEFAULT 0.8,
    max_results INTEGER DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    canonical_name TEXT,
    similarity_score FLOAT,
    parent_company TEXT,
    dba_names JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        f.id,
        f.canonical_name,
        1 - (f.name_embedding <=> query_embedding) as similarity_score,
        f.parent_company,
        f.dba_names
    FROM franchisors f
    WHERE f.name_embedding IS NOT NULL
        AND 1 - (f.name_embedding <=> query_embedding) >= similarity_threshold
    ORDER BY f.name_embedding <=> query_embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Function to deduplicate franchises
CREATE OR REPLACE FUNCTION deduplicate_franchise(
    source_franchise_id UUID,
    target_franchise_id UUID
)
RETURNS BOOLEAN AS $$
BEGIN
    -- Update all FDDs to point to target franchise
    UPDATE fdds 
    SET franchise_id = target_franchise_id
    WHERE franchise_id = source_franchise_id;
    
    -- Copy any unique DBA names to target
    UPDATE franchisors
    SET dba_names = (
        SELECT jsonb_agg(DISTINCT value)
        FROM (
            SELECT jsonb_array_elements(f1.dba_names) AS value
            FROM franchisors f1
            WHERE f1.id IN (source_franchise_id, target_franchise_id)
        ) t
    )
    WHERE id = target_franchise_id;
    
    -- Delete the source franchise
    DELETE FROM franchisors WHERE id = source_franchise_id;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Check if vector index exists before creating
DO $$ 
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes 
    WHERE tablename = 'franchisors' 
    AND indexname = 'idx_franchisors_embedding'
  ) THEN
    CREATE INDEX idx_franchisors_embedding ON franchisors 
    USING ivfflat (name_embedding vector_cosine_ops)
    WITH (lists = 100);
  END IF;
END $$;

-- Helper function to update franchise embeddings (FIXED: renamed parameter to avoid conflict)
CREATE OR REPLACE FUNCTION update_franchise_embedding(
  p_franchise_id uuid,
  new_embedding vector(384)
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE franchisors 
  SET name_embedding = new_embedding,
      updated_at = now()
  WHERE id = p_franchise_id;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION update_franchise_embedding TO authenticated;
GRANT EXECUTE ON FUNCTION update_franchise_embedding TO service_role;

-- ============================================================================
-- Migration 007: Validation Tracking Tables
-- ============================================================================

-- Validation results tracking
CREATE TABLE validation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL,
    validation_type TEXT NOT NULL, -- 'schema', 'business_logic', 'cross_reference'
    validation_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    message TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Validation errors for detailed tracking
CREATE TABLE validation_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    validation_result_id UUID REFERENCES validation_results(id) ON DELETE CASCADE,
    field_path TEXT NOT NULL, -- JSON path to the field with error
    expected_value TEXT,
    actual_value TEXT,
    error_code TEXT,
    error_message TEXT,
    suggested_fix TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Validation bypasses for manual overrides
CREATE TABLE validation_bypasses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fdd_section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    validation_type TEXT NOT NULL,
    validation_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    bypassed_by TEXT NOT NULL, -- User who bypassed
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(fdd_section_id, validation_type, validation_name)
);

-- Indexes for validation tables
CREATE INDEX idx_validation_results_section ON validation_results(fdd_section_id);
CREATE INDEX idx_validation_results_passed ON validation_results(passed);
CREATE INDEX idx_validation_results_severity ON validation_results(severity);
CREATE INDEX idx_validation_errors_result ON validation_errors(validation_result_id);
CREATE INDEX idx_validation_bypasses_section ON validation_bypasses(fdd_section_id);
CREATE INDEX idx_validation_bypasses_expires ON validation_bypasses(expires_at);

-- Enable RLS
ALTER TABLE validation_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_bypasses ENABLE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY "Service role has full access to validation_results" ON validation_results
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to validation_errors" ON validation_errors
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role has full access to validation_bypasses" ON validation_bypasses
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read validation_results" ON validation_results
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read validation_errors" ON validation_errors
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read validation_bypasses" ON validation_bypasses
    FOR SELECT TO authenticated USING (true);

-- Function to get validation summary
CREATE OR REPLACE FUNCTION get_validation_summary(p_fdd_id UUID)
RETURNS TABLE (
    total_validations INTEGER,
    passed_validations INTEGER,
    failed_validations INTEGER,
    error_count INTEGER,
    warning_count INTEGER,
    info_count INTEGER,
    sections_validated INTEGER,
    sections_with_errors INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT vr.id)::INTEGER as total_validations,
        COUNT(DISTINCT vr.id) FILTER (WHERE vr.passed = true)::INTEGER as passed_validations,
        COUNT(DISTINCT vr.id) FILTER (WHERE vr.passed = false)::INTEGER as failed_validations,
        COUNT(DISTINCT vr.id) FILTER (WHERE vr.severity = 'error')::INTEGER as error_count,
        COUNT(DISTINCT vr.id) FILTER (WHERE vr.severity = 'warning')::INTEGER as warning_count,
        COUNT(DISTINCT vr.id) FILTER (WHERE vr.severity = 'info')::INTEGER as info_count,
        COUNT(DISTINCT s.id)::INTEGER as sections_validated,
        COUNT(DISTINCT s.id) FILTER (WHERE EXISTS (
            SELECT 1 FROM validation_results vr2 
            WHERE vr2.fdd_section_id = s.id AND vr2.passed = false AND vr2.severity = 'error'
        ))::INTEGER as sections_with_errors
    FROM fdd_sections s
    LEFT JOIN validation_results vr ON s.id = vr.fdd_section_id
    WHERE s.fdd_id = p_fdd_id;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION get_validation_summary TO authenticated;
GRANT EXECUTE ON FUNCTION get_validation_summary TO service_role;

-- Create trigger to auto-update FDD sections based on validation results
CREATE OR REPLACE FUNCTION update_section_validation_status()
RETURNS TRIGGER AS $$
BEGIN
    -- Update the section's validation status based on validation results
    UPDATE fdd_sections
    SET validation_status = CASE
        WHEN EXISTS (
            SELECT 1 FROM validation_results 
            WHERE fdd_section_id = NEW.fdd_section_id 
            AND passed = false 
            AND severity = 'error'
        ) THEN 'invalid'
        WHEN EXISTS (
            SELECT 1 FROM validation_results 
            WHERE fdd_section_id = NEW.fdd_section_id 
            AND passed = false 
            AND severity = 'warning'
        ) THEN 'needs_review'
        ELSE 'validated'
    END
    WHERE id = NEW.fdd_section_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_section_validation
AFTER INSERT OR UPDATE ON validation_results
FOR EACH ROW
EXECUTE FUNCTION update_section_validation_status();

-- Final grants for all functions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;