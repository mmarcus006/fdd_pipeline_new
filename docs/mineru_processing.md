# MinerU PDF Processing Documentation

## Overview

The FDD Pipeline now uses MinerU's Web API exclusively for PDF processing. This provides superior layout analysis and text extraction compared to local processing methods. All PDFs are processed through MinerU's cloud service, with results automatically stored in Google Drive.

## Architecture Changes

### Previous Architecture (Removed)
- Local MinerU installation with magic-pdf library
- Complex document_processing.py with 1000+ lines
- Multiple processing modes (API vs local)
- Manual layout analysis and section detection

### New Architecture
- Single MinerU Web API implementation
- Streamlined mineru_processing.py (~400 lines)
- Automatic Google Drive storage with UUID-based organization
- Consistent processing across all environments

## File Organization

### UUID-Based Tracking
Every FDD document is assigned a UUID at download time. This UUID is used throughout the pipeline:

1. **PDF Filename**: `{fdd_uuid}_{franchise_name}_{date}.pdf`
2. **Google Drive Folder**: `/{fdd_uuid}/`
3. **MinerU Output Files**: 
   - `/{fdd_uuid}/{franchise_name}_mineru.md`
   - `/{fdd_uuid}/{franchise_name}_layout.json`

### Google Drive Structure
```
Root Folder (1df-zMpAYkfM0EhDTeqH36RpmwKfmYApj)
├── {fdd_uuid_1}/
│   ├── {franchise_name}_mineru.md
│   └── {franchise_name}_layout.json
├── {fdd_uuid_2}/
│   ├── {franchise_name}_mineru.md
│   └── {franchise_name}_layout.json
└── ...
```

## Authentication

MinerU requires GitHub authentication. The auth state is saved locally:

1. First run: Browser opens for GitHub login
2. Auth saved to: `{project_root}/mineru_auth.json`
3. Subsequent runs: Uses saved authentication

## API Integration

### Key Functions

#### `process_document_with_mineru()`
Main processing function that:
1. Submits PDF to MinerU API
2. Polls for completion
3. Downloads results (markdown and JSON)
4. Stores results in Google Drive
5. Returns processing metadata

#### `MinerUProcessor` Class
- Handles authentication
- Manages API requests
- Integrates with Google Drive
- Provides retry logic

### Usage Example

```python
from tasks.mineru_processing import process_document_with_mineru
from uuid import uuid4

# Process a PDF
results = await process_document_with_mineru(
    pdf_url="https://example.com/fdd.pdf",
    fdd_id=uuid4(),
    franchise_name="Example Franchise",
    timeout_seconds=300
)

# Results include:
# - task_id: MinerU processing task ID
# - mineru_results: URLs for markdown and JSON
# - drive_files: Google Drive file IDs and paths
# - fdd_uuid: The UUID used for tracking
# - processed_at: Timestamp
```

## Configuration

Add to your environment:
```bash
# Google Drive folder for MinerU outputs
GDRIVE_FOLDER_ID=1df-zMpAYkfM0EhDTeqH36RpmwKfmYApj

# MinerU auth file location (auto-created)
MINERU_AUTH_FILE=mineru_auth.json
```

## Migration Notes

### Removed Components
- `tasks/document_processing.py` - Replaced by `mineru_processing.py`
- `src/MinerU/` directory - Cleaned up experimental code
- Local MinerU configurations - No longer needed

### Updated Components
- `flows/process_single_pdf.py` - Uses new MinerU processor
- Import statements - Now use `models.document_models`
- Section detection - Simplified placeholder implementation

### Backward Compatibility
For components that depend on old classes:
- `DocumentLayout`, `SectionBoundary`, `LayoutElement` → Moved to `models.document_models.py`
- `process_document_layout` → Replaced by `process_document_with_mineru`

## Benefits

1. **Simplicity**: Single implementation path
2. **Reliability**: Cloud-based processing with retry logic
3. **Traceability**: UUID-based file tracking
4. **Storage**: Automatic Google Drive organization
5. **Maintenance**: 70% less code to maintain

## Troubleshooting

### Authentication Issues
- Delete `mineru_auth.json` and re-authenticate
- Ensure GitHub account has access to MinerU

### Processing Failures
- Check MinerU task status in logs
- Verify PDF URL is accessible
- Review Google Drive permissions

### Storage Issues
- Confirm Google Drive service account permissions
- Check folder ID configuration
- Verify available storage quota