-- Operational Tables for Pipeline Logging and Monitoring

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