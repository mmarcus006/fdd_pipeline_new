# FDD Pipeline System Requirements

## Introduction

The FDD Pipeline is an automated document intelligence system that transforms unstructured Franchise Disclosure Documents (FDDs) into structured, queryable data. This system combines web scraping, AI-powered document analysis, and cloud storage to create a comprehensive franchise intelligence platform.

The system serves franchise analysts, data engineers, researchers, and developers who need reliable access to structured franchise disclosure information. By automating the acquisition, processing, and validation of FDD documents from state regulatory portals, the system eliminates manual data entry and ensures consistent, high-quality franchise intelligence.

This requirements document is based on the comprehensive documentation in the `/docs` folder, including architecture designs, data models, implementation guides, operations procedures, and API specifications.

## Requirements

### Requirement 1: Automated Document Acquisition

**User Story:** As a franchise analyst, I want the system to automatically discover and download new FDD documents from state regulatory portals, so that I have access to the latest franchise disclosure information without manual intervention.

#### Acceptance Criteria

1. WHEN the system runs its scheduled scraping workflow THEN it SHALL successfully connect to Minnesota and Wisconsin franchise portals
2. WHEN new FDD documents are discovered on state portals THEN the system SHALL extract filing metadata including franchise name, filing date, document type, and filing number
3. WHEN a document is downloaded THEN the system SHALL compute and store a SHA256 hash for deduplication purposes
4. WHEN duplicate documents are detected via hash comparison THEN the system SHALL skip processing and mark as duplicate
5. WHEN documents are successfully downloaded THEN they SHALL be uploaded to Google Drive with organized folder structure `/fdds/{source}/{franchise_slug}/{year}/`
6. WHEN scraping encounters errors THEN the system SHALL retry up to 3 times with exponential backoff
7. WHEN scraping completes THEN metadata SHALL be stored in the `scrape_metadata` table with Prefect run tracking

### Requirement 2: Intelligent Document Processing

**User Story:** As a data engineer, I want the system to automatically segment FDD documents into their constituent sections and extract structured data, so that franchise information is available in a queryable format.

#### Acceptance Criteria

1. WHEN a new FDD document is registered THEN the system SHALL send it to MinerU API for layout analysis
2. WHEN MinerU processing completes THEN the system SHALL identify all 25 FDD sections (Intro + Items 1-23 + Appendix) based on layout JSON
3. WHEN sections are identified THEN the system SHALL split the original PDF into individual section PDFs with accurate page ranges
4. WHEN section PDFs are created THEN they SHALL be uploaded to Google Drive at `/processed/{franchise_id}/{year}/section_{item_no:02d}.pdf`
5. WHEN section records are created THEN they SHALL be stored in `fdd_sections` table with extraction status "pending"
6. WHEN LLM extraction begins THEN the system SHALL select appropriate model based on section complexity (Ollama for simple tables, Gemini Pro for complex text, OpenAI GPT-4 for fallback)
7. WHEN extraction fails THEN the system SHALL attempt fallback models in order: Primary → Secondary → OpenAI GPT-4
8. WHEN structured data is extracted THEN it SHALL be validated against Pydantic schemas before storage

### Requirement 3: Multi-Tier Data Validation

**User Story:** As a data quality manager, I want the system to validate all extracted data through multiple validation tiers, so that only high-quality, consistent data is stored in the database.

#### Acceptance Criteria

1. WHEN data is extracted from any section THEN it SHALL pass Pydantic schema validation for data types, formats, and basic constraints
2. WHEN Item 5 (Initial Fees) data is processed THEN fee amounts SHALL be non-negative and less than $10M, and refund conditions SHALL be present if refundable is true
3. WHEN Item 6 (Other Fees) data is processed THEN exactly one of amount_cents OR amount_percentage SHALL be set, and maximum_cents SHALL be >= minimum_cents if both specified
4. WHEN Item 7 (Initial Investment) data is processed THEN high_cents SHALL be >= low_cents, and total investment SHALL be cross-validated against Item 5 fees
5. WHEN Item 19 (FPR) data is processed THEN revenue metrics SHALL satisfy low <= average <= high and low <= median <= high relationships
6. WHEN Item 20 (Outlet) data is processed THEN outlet math SHALL balance: count_end = count_start + opened - closed + transferred_in - transferred_out
7. WHEN Item 21 (Financials) data is processed THEN accounting equations SHALL balance: Assets = Liabilities + Equity (within $1 tolerance)
8. WHEN validation errors occur THEN records SHALL be flagged for manual review with detailed error descriptions
9. WHEN data quality scores are calculated THEN completeness percentage SHALL be computed based on populated vs expected fields

### Requirement 4: Franchise Entity Management

**User Story:** As a franchise researcher, I want the system to intelligently match and deduplicate franchise entities across different documents and states, so that I can track franchise information consistently over time.

#### Acceptance Criteria

1. WHEN a new FDD is processed THEN the system SHALL attempt exact name matching against existing franchisors in the database
2. WHEN exact name match fails THEN the system SHALL generate semantic embeddings using sentence-transformers and perform similarity search
3. WHEN embedding similarity exceeds 0.94 THEN the system SHALL automatically link to existing franchisor
4. WHEN embedding similarity is between 0.85-0.94 THEN the system SHALL flag for human review with candidate matches
5. WHEN no suitable match is found THEN the system SHALL create a new franchisor record with canonical name normalization
6. WHEN franchise names are processed THEN they SHALL be normalized (strip whitespace, title case) and stored with 384-dimension embedding vectors
7. WHEN amendments are processed THEN they SHALL supersede previous FDD versions and maintain document lineage

### Requirement 5: Workflow Orchestration and Monitoring

**User Story:** As a system administrator, I want comprehensive workflow orchestration and monitoring capabilities, so that I can ensure reliable pipeline operation and quickly identify issues.

#### Acceptance Criteria

1. WHEN the system is deployed THEN Prefect workflows SHALL be configured for weekly scraping of each state portal
2. WHEN workflows execute THEN all tasks SHALL have retry logic with 3 attempts and exponential backoff
3. WHEN pipeline failures occur THEN email alerts SHALL be sent to configured recipients with error details
4. WHEN processing completes THEN metrics SHALL be tracked including documents/day, success rates, LLM token usage, and processing times
5. WHEN extraction accuracy falls below 95% THEN alerts SHALL be triggered for investigation
6. WHEN API response times exceed 2 seconds THEN performance alerts SHALL be generated
7. WHEN system resources exceed 80% utilization THEN capacity alerts SHALL be sent
8. WHEN workflows run THEN structured logs SHALL be written to `pipeline_logs` table with context and run IDs

### Requirement 6: Data Storage and Retrieval

**User Story:** As an application developer, I want reliable data storage with efficient retrieval capabilities, so that I can build analytics and reporting applications on top of the FDD data.

#### Acceptance Criteria

1. WHEN structured data is validated THEN high-value sections (Items 5, 6, 7, 19, 20, 21) SHALL be stored in normalized PostgreSQL tables
2. WHEN other sections are processed THEN they SHALL be stored as validated JSON in the `fdd_item_json` table
3. WHEN database writes occur THEN they SHALL use connection pooling and batch inserts where possible for performance
4. WHEN queries are executed THEN appropriate indexes SHALL exist on foreign keys, status fields, and common filter combinations
5. WHEN data is accessed THEN row-level security policies SHALL enforce appropriate access controls
6. WHEN documents are stored THEN Google Drive SHALL maintain organized folder structure with unlimited capacity
7. WHEN database maintenance runs THEN old logs SHALL be archived (>90 days) and vacuum operations SHALL optimize performance

### Requirement 7: API Access Layer

**User Story:** As a client application developer, I want well-documented APIs to access FDD data, so that I can integrate franchise intelligence into external systems.

#### Acceptance Criteria

1. WHEN internal APIs are deployed THEN FastAPI SHALL provide automatic OpenAPI documentation with Pydantic model integration
2. WHEN public APIs are accessed THEN Supabase Edge Functions SHALL handle authentication and rate limiting
3. WHEN API requests are made THEN responses SHALL include appropriate HTTP status codes and error messages
4. WHEN data is requested THEN APIs SHALL support filtering, pagination, and sorting capabilities
5. WHEN API documentation is generated THEN it SHALL include field descriptions, examples, and usage patterns
6. WHEN API performance is measured THEN response times SHALL be under 2 seconds for standard queries
7. WHEN API errors occur THEN they SHALL be logged with request context for debugging

### Requirement 8: Security and Compliance

**User Story:** As a compliance officer, I want the system to implement appropriate security measures and maintain audit trails, so that franchise data is protected and regulatory requirements are met.

#### Acceptance Criteria

1. WHEN external communications occur THEN all connections SHALL use HTTPS/TLS encryption
2. WHEN service accounts are configured THEN they SHALL have minimal required permissions for their specific functions
3. WHEN API keys are managed THEN they SHALL be stored in environment variables and never committed to code
4. WHEN data operations occur THEN complete audit trails SHALL be maintained in the database
5. WHEN PII is encountered THEN it SHALL NOT be extracted or stored in the system
6. WHEN data retention policies apply THEN documents SHALL be archived after 7 years per compliance requirements
7. WHEN security breaches are detected THEN all credentials SHALL be rotated immediately
8. WHEN access is requested THEN row-level security SHALL enforce appropriate data access controls

### Requirement 9: System Scalability and Performance

**User Story:** As a system architect, I want the system to handle increasing document volumes efficiently, so that processing capabilities can scale with business growth.

#### Acceptance Criteria

1. WHEN document volume increases THEN multiple Prefect agents SHALL process work in parallel
2. WHEN LLM calls are made THEN async operations with connection pooling SHALL optimize throughput
3. WHEN database load increases THEN Supabase SHALL auto-scale to handle increased usage
4. WHEN processing targets are set THEN the system SHALL handle 100+ FDDs per day with <10 minute end-to-end latency
5. WHEN bottlenecks are identified THEN MinerU API calls SHALL be queued and rate-limited appropriately
6. WHEN costs are monitored THEN local models SHALL be used for simple tasks to optimize LLM expenses
7. WHEN storage grows THEN Google Drive SHALL provide unlimited capacity without performance degradation

### Requirement 10: Development and Deployment

**User Story:** As a software developer, I want standardized development practices and deployment procedures, so that I can contribute effectively to the system and deploy changes safely.

#### Acceptance Criteria

1. WHEN code is written THEN it SHALL follow Python 3.11+ standards with type hints and Google-style docstrings
2. WHEN dependencies are managed THEN UV package manager SHALL handle virtual environments and installations
3. WHEN code quality is checked THEN pre-commit hooks SHALL run Black formatting, mypy type checking, and pytest tests
4. WHEN tests are written THEN they SHALL achieve adequate coverage for unit and integration scenarios
5. WHEN deployments occur THEN they SHALL follow the documented procedures in `docs/04_operations/deployment.md`
6. WHEN configuration is managed THEN Pydantic Settings SHALL handle environment variables with validation
7. WHEN documentation is updated THEN it SHALL maintain consistency with the comprehensive `/docs` folder structure
8. WHEN branches are managed THEN the strategy SHALL follow main/develop/feature/* pattern with required code reviews