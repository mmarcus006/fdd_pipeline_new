# FDD Pipeline - Project Documentation

## Overview
This is an automated Franchise Disclosure Document (FDD) processing pipeline that scrapes, downloads, processes, and extracts structured data from FDD documents filed with state franchise portals.

## Key Features
- **Web Scraping**: Automated scraping of FDD documents from state portals (Minnesota CARDS, Wisconsin DFI)
- **Document Processing**: PDF processing using MinerU for layout analysis and section detection
- **Data Extraction**: LLM-powered extraction of structured data from specific FDD items (5, 6, 7, 19, 20, 21)
- **Database Storage**: Structured storage in Supabase with full data lineage tracking
- **Google Drive Integration**: Automatic document storage and organization in Google Drive
- **Workflow Orchestration**: Prefect-based workflow management with retry logic and monitoring

## Architecture (Current Implementation)

### Core Components

1. **Web Scrapers** (`tasks/`):
   - `BaseScraper`: Abstract base class with common scraping functionality (Playwright browser automation)
   - `MinnesotaScraper`: Scrapes Minnesota CARDS portal
   - `WisconsinScraper`: Scrapes Wisconsin DFI portal
   - `web_scraping.py`: Factory pattern for scraper instantiation

2. **Document Processing** (`tasks/` & `src/`):
   - `mineru_processing.py`: Task wrapper for MinerU Web API
   - `src/MinerU/mineru_web_api.py`: MinerU Web API client with browser authentication
   - `document_segmentation.py`: FDD section detection and boundary extraction
   - `src/processing/enhanced_fdd_section_detector_claude_v2.py`: Advanced section detection using Claude
   - `pdf_extractor.py`: Basic PDF text extraction utilities

3. **Data Extraction** (`tasks/`):
   - `llm_extraction.py`: Multi-model LLM framework with routing and fallback
   - Supports Gemini, OpenAI, and Ollama models
   - Item-specific extraction for FDD sections
   - `utils/multimodal_processor.py`: Handles image and table extraction

4. **Data Models** (`models/`):
   - Pydantic models for all database entities
   - Item-specific response models (Item5Fees, Item6OtherFees, etc.)
   - Composite models for complex data structures
   - JSON storage models for flexible item data

5. **Workflows** (`flows/`):
   - `base_state_flow.py`: Generic state scraping flow (unified implementation)
   - `state_configs.py`: State-specific configurations
   - `process_single_pdf.py`: Single PDF processing flow
   - `complete_pipeline.py`: End-to-end orchestration flow

6. **API Layer** (`src/api/`):
   - `main.py`: FastAPI application with REST endpoints
   - `run.py`: Uvicorn server runner
   - Endpoints for document processing and data retrieval

## Database Schema

### Core Tables
- **franchisors**: Canonical franchise entities with deduplication
- **fdds**: FDD documents with versioning and supersession tracking
- **fdd_sections**: Document sections after segmentation
- **scrape_metadata**: Web scraping audit trail

### Extracted Data Tables
- **item5_fees**: Initial franchise fees
- **item6_other_fees**: Other fees and costs
- **item7_investment**: Estimated initial investment
- **item19_fpr**: Financial performance representations
- **item20_outlets**: Outlet and franchisee information
- **item21_financials**: Financial statements

## Common Tasks

### 1. Run Complete Pipeline
```bash
# Run for all configured states
python main.py run-all

# Run for specific state (now uses unified base flow)
python main.py scrape --state minnesota
python main.py scrape --state wisconsin

# With options
python main.py scrape --state all --limit 10 --test-mode
```

### 2. Process Single PDF
```bash
python main.py process-pdf --path /path/to/fdd.pdf
```

### 3. Check Pipeline Health
```bash
python main.py health-check
```

### 4. Deploy Workflows to Prefect
```bash
python main.py orchestrate --deploy --schedule
```

### 5. Run Tests
```bash
# Unit tests
pytest tests/ -m unit

# Integration tests  
pytest tests/ -m integration

# All tests
pytest tests/
```

### 6. Database Migrations
```sql
-- Apply migrations in order
psql -d your_database -f migrations/001_initial_schema.sql
psql -d your_database -f migrations/002_structured_data_tables.sql
-- etc...
```

## Configuration

### Environment Variables
```bash
# Database
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key

# LLM APIs
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key  # Optional, for fallback
OLLAMA_BASE_URL=http://localhost:11434  # For local models

# Google Drive
GDRIVE_CREDS_JSON=gdrive_cred.json  # Path to service account JSON
GDRIVE_FOLDER_ID=root_folder_id

# MinerU Web API
MINERU_AUTH_FILE=mineru_auth.json  # Browser auth storage

# Section Detection
USE_ENHANCED_SECTION_DETECTION=true
ENHANCED_DETECTION_CONFIDENCE_THRESHOLD=0.7
ENHANCED_DETECTION_MIN_FUZZY_SCORE=80

# Application Settings
DEBUG=false
LOG_LEVEL=INFO
MAX_CONCURRENT_EXTRACTIONS=5
```

### Key Settings (config.py)
- Retry attempts: 3 (configurable per task)
- Request timeout: 30 seconds
- Document processing timeout: 5 minutes
- LLM extraction timeout: 60 seconds per section
- MinerU processing timeout: 300 seconds
- Enhanced section detection: Enabled by default
- Concurrent extractions: 5 (prevents rate limiting)

## Refactoring Status (Completed)

### Major Changes Implemented
1. **State Scraping Flows Consolidated**:
   - Created `flows/base_state_flow.py` with generic state scraping logic
   - Created `flows/state_configs.py` for state-specific configurations
   - Reduced ~1,200 lines to ~400 lines (67% reduction)
   - Original flows now use base flow with deprecation warnings

2. **Files Cleaned Up**:
   - Deleted 3 duplicate test files
   - Archived individual migration files (kept combined versions)
   - Removed all .DS_Store files
   - Updated .gitignore to prevent future accumulation

### Adding New States
To add a new state (e.g., California):
1. Create scraper class: `tasks/california_scraper.py` extending `BaseScraper`
2. Add configuration to `flows/state_configs.py`:
   ```python
   CALIFORNIA_CONFIG = StateConfig(
       state_code="CA",
       state_name="California",
       scraper_class=CaliforniaScraper,
       folder_name="California FDDs",
       portal_name="CA DBO"
   )
   ```
3. Update `STATE_CONFIGS` dictionary in `state_configs.py`
4. That's it! The state is now available in CLI and flows

## Performance Considerations

### Scraping
- Implements exponential backoff with jitter
- Respects rate limits with configurable delays
- Browser resource pooling for efficiency

### Document Processing
- Streaming downloads for large PDFs
- Chunk-based processing for memory efficiency
- Parallel section extraction when possible

### LLM Extraction
- Model routing based on section complexity
- Token usage tracking and cost optimization
- Fallback chains for reliability

## Monitoring & Logging
- Structured logging with correlation IDs
- Prefect flow run tracking
- Database audit trails for all operations
- Extraction metrics and model performance tracking

## Security Notes
- All API keys stored as environment variables
- Database connections use service keys (RLS bypassed)
- Document hashes for deduplication and integrity
- No sensitive data logged

## Troubleshooting

### Common Issues

1. **MinerU Authentication Failed**
   - Delete `mineru_auth.json` and re-authenticate
   - Ensure Playwright browsers are installed: `playwright install chromium`
   - Check if MinerU Web API is accessible

2. **Database Connection Issues**
   - Verify Supabase URL and service key
   - Check if tables exist: `python main.py health-check`
   - Run migrations if needed

3. **Scraping Failures**
   - State portals may change their structure
   - Check browser automation with `DEBUG=true`
   - Verify network connectivity to state portals

4. **LLM Extraction Errors**
   - Ensure API keys are valid
   - Check rate limits for your API tier
   - For Ollama, ensure models are pulled: `ollama pull llama3`

5. **Google Drive Upload Issues**
   - Verify service account credentials
   - Check folder permissions
   - Ensure quota hasn't been exceeded

### Debug Mode

Enable detailed logging:
```bash
DEBUG=true LOG_LEVEL=DEBUG python main.py scrape --state minnesota
```

## Future Enhancements
1. Add more state portals (CA, NY, IL)
2. Implement incremental scraping (only new documents)
3. Add data validation and quality scoring
4. Enhance API layer with authentication
5. Implement automated testing for scrapers
6. Add document change detection and diff tracking
7. Create admin dashboard for monitoring
8. Add webhook notifications for pipeline events