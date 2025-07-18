-- Row Level Security Policies and Additional Indexes
-- Based on docs/02_data_model/database_schema.md

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