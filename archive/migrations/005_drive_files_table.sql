-- Drive Files Metadata Table
-- Tracks Google Drive file metadata and synchronization

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