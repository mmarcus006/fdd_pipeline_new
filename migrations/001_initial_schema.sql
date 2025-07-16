-- FDD Pipeline Initial Database Schema
-- Based on docs/02_data_model/database_schema.md

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