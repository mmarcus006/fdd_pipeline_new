# FDD Pipeline System Implementation Plan

This implementation plan converts the comprehensive system design into actionable coding tasks, building upon the extensive documentation in `/docs/01_architecture/`, `/docs/02_data_model/`, `/docs/03_implementation/`, `/docs/04_operations/`, and `/docs/05_api_reference/`.

## Implementation Tasks

- [x] 1. Core Infrastructure Setup

  - Set up project structure following `/docs/03_implementation/setup_guide.md`
  - Configure UV package management with dependencies from `TECH_STACK.md`
  - Initialize Supabase database with schema from `/docs/02_data_model/database_schema.md`
  - Set up Google Drive service account and folder structure
  - Configure environment variables and Pydantic settings validation
  - _Requirements: 1.1, 1.7, 6.6, 10.1, 10.2, 10.6_

- [x] 2. Database Schema and Models Implementation

  - [x] 2.1 Create database migration files

    - Implement PostgreSQL schema from `/docs/02_data_model/database_schema.md`
    - Create all core tables: `franchisors`, `fdds`, `fdd_sections`, `scrape_metadata`
    - Add structured data tables: `item5_initial_fees`, `item6_other_fees`, `item7_initial_investment`, `item19_fpr`, `item20_outlet_summary`, `item20_state_counts`, `item21_financials`
    - Create operational tables: `pipeline_logs`, `prefect_runs`, `fdd_item_json`
    - Add indexes, constraints, and RLS policies per schema documentation
    - _Requirements: 6.1, 6.2, 8.6_

  - [x] 2.2 Implement Pydantic models
    - Create all Pydantic models from `/docs/02_data_model/pydantic_models.md`
    - Implement core models: `Franchisor`, `FDD`, `FDDSection` with full validation
    - Create structured data models for Items 5, 6, 7, 19, 20, 21 with business rule validation
    - Add operational models: `ScrapeMetadata`, `PipelineLog` with proper enums
    - Implement validation functions and utility methods
    - Write unit tests for all model validation logic
    - _Requirements: 3.1, 3.2, 3.8, 10.4_

- [x] 3. Web Scraping Infrastructure

  - [x] 3.1 Create base scraper framework

    - Implement `BaseScraper` class with common functionality
    - Add Playwright browser management with cleanup handlers
    - Create retry logic with exponential backoff (3 attempts)
    - Implement error handling and logging infrastructure
    - Add user agent rotation and proxy support
    - Write unit tests for scraper base functionality
    - _Requirements: 1.1, 1.6, 5.2_

  - [x] 3.2 Implement Minnesota portal scraper

    - Create `MinnesotaScraper` inheriting from `BaseScraper`
    - Implement navigation to Minnesota commerce department FDD search
    - Add document discovery and metadata extraction logic
    - Create PDF download functionality with hash computation
    - Implement deduplication check against existing documents
    - Write integration tests with mock portal responses
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 3.3 Implement Wisconsin portal scraper
    - Create `WisconsinScraper` with multi-step form navigation
    - Implement active filings table parsing and franchise name extraction
    - Add detail page navigation and enhanced metadata extraction
    - Create document download with filing information capture
    - Implement search result processing and data combination
    - Write integration tests for Wisconsin-specific workflow
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 4. Document Storage and Management

  - [x] 4.1 Implement Google Drive integration

    - Create `DriveManager` class with service account authentication
    - Implement folder structure creation per `/docs/01_architecture/system_overview.md`
    - Add resumable upload functionality for large PDFs
    - Create download methods for document retrieval
    - Implement file metadata tracking and database synchronization
    - Add error handling for API rate limits and network issues
    - Write unit tests with mocked Google Drive API
    - _Requirements: 1.5, 6.7, 2.4_

  - [x] 4.2 Create database operations layer
    - Implement `DatabaseManager` with SQLAlchemy and connection pooling
    - Create CRUD operations for all entity types
    - Add batch insert functionality for performance optimization
    - Implement transaction management with rollback capabilities
    - Create query builders for common data access patterns
    - Add database health checks and connection monitoring
    - Write integration tests with test database
    - _Requirements: 6.1, 6.3, 6.4, 6.5_

- [x] 5. Document Processing Pipeline

  - [x] 5.1 Implement MinerU integration

    - Create `MinerUClient` with API authentication and rate limiting
    - Implement document upload and processing status polling
    - Add layout JSON parsing and section identification logic
    - Create section boundary detection with fuzzy matching
    - Implement error handling for API failures and timeouts
    - Add fallback to PyPDF2 for simple text extraction
    - Write unit tests with mocked MinerU API responses
    - _Requirements: 2.1, 2.2, 9.5_

  - [x] 5.2 Create document segmentation system
    - Implement PDF splitting functionality using PyPDF2
    - Create section PDF generation with accurate page ranges
    - Add section metadata creation and database storage
    - Implement Google Drive upload for segmented documents
    - Create section validation and quality checks
    - Add progress tracking and status updates
    - Write integration tests with sample FDD documents
    - _Requirements: 2.3, 2.4, 2.5_

- [ ] 6. LLM Extraction Engine


  - [x] 6.1 Create multi-model LLM framework

    - Implement `LLMExtractor` base class with model selection logic
    - Create adapters for Gemini Pro, Ollama, and OpenAI APIs
    - Add model routing based on section complexity per `technology_decisions.md`
    - Implement fallback chain: Primary → Secondary → OpenAI GPT-4
    - Create token usage tracking and cost monitoring
    - Add async processing with connection pooling
    - Write unit tests for model selection and fallback logic
    - _Requirements: 2.6, 2.7, 9.6_

  - [x] 6.2 Implement prompt template system

    - Create YAML prompt templates for each FDD section (Items 0-24)
    - Implement Jinja2 template rendering with variable injection
    - Add section-specific extraction instructions and examples
    - Create generic templates for fallback scenarios
    - Implement prompt versioning and A/B testing capability
    - Add template validation and error handling
    - Write tests for template rendering and variable substitution
    - _Requirements: 2.8_

  - [x] 6.3 Create structured data extraction

    - Implement Instructor integration for structured LLM outputs
    - Create extraction functions for each high-value section (5, 6, 7, 19, 20, 21)
    - Add retry logic for validation failures with model fallback
    - Implement extraction result caching to avoid reprocessing
    - Create extraction progress tracking and status updates
    - Add extraction quality scoring and confidence metrics
    - Write integration tests with real FDD section samples
    - _Requirements: 2.8, 3.1_
-

- [-] 7. Data Validation System

  - [-] 7.1 Implement schema validation layer

    - Create automatic Pydantic validation for all extracted data

    - Implement custom validators for business-specific rules
    - Add validation error collection and detailed reporting
    - Create validation result storage and tracking
    - Implement validation bypass for manual review cases
    - Add validation performance monitoring and optimization
    - Write comprehensive unit tests for all validation rules
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ] 7.2 Create business rules validation

    - Implement cross-field validation for Items 5, 6, 7 fee consistency
    - Add outlet math validation for Item 20 (count balancing)
    - Create financial equation validation for Item 21 (accounting balance)
    - Implement temporal validation for dates and fiscal years
    - Add statistical outlier detection for unusual values
    - Create validation severity levels (ERROR/WARNING/INFO)
    - Write integration tests for complex business rule scenarios
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ] 7.3 Implement quality control system
    - Create data completeness scoring algorithm
    - Implement quality metrics calculation and tracking
    - Add manual review queue management
    - Create quality dashboard with key metrics
    - Implement quality trend analysis and alerting
    - Add quality improvement feedback loop
    - Write tests for quality scoring and metrics calculation
    - _Requirements: 3.8, 3.9_

- [-] 8. Franchise Entity Management

  - [x] 8.1 Implement franchise matching system

    - Create exact name matching against existing franchisors
    - Implement semantic embedding generation using sentence-transformers
    - Add similarity search with configurable thresholds (0.85, 0.94)
    - Create automatic linking for high-confidence matches
    - Implement manual review queue for medium-confidence matches
    - Add new franchisor creation with name normalization
    - Write unit tests for matching algorithms and thresholds
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [-] 8.2 Create document lineage tracking

    - Implement amendment processing and document supersession
    - Add document version tracking and history maintenance
    - Create duplicate detection and linking
    - Implement document status management (active/superseded/duplicate)
    - Add lineage query capabilities for document history
    - Create audit trail for all document changes
    - Write integration tests for complex lineage scenarios
    - _Requirements: 4.7_



- [-] 9. Workflow Orchestration

  - [ ] 9.1 Create Minnesota scraping flow


    - Create `flows/scrape_minnesota.py` with weekly scheduling
    - Implement Minnesota scraping workflow with error handling
    - Add scraping result processing and database updates
    - Create scraping performance monitoring and alerting
    - Implement scraping failure recovery and retry logic
    - Add scraping metrics collection and reporting
    - Write integration tests for complete scraping workflows
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 9.2 Implement Wisconsin scraping flow

    - Create Wisconsin scraping workflow with weekly scheduling
    - Implement Wisconsin scraping workflow with error handling
    - Add scraping result processing and database updates
    - Create scraping performance monitoring and alerting
    - Implement scraping failure recovery and retry logic
    - Add scraping metrics collection and reporting
    - Write integration tests for complete scraping workflows
    - _Requirements: 5.1, 5.2, 5.3, 5.4_


  - [ ] 9.3 Create document processing workflows

    - Implement end-to-end document processing pipeline
    - Add parallel section processing with task mapping
    - Create processing status tracking and updates
    - Implement processing failure handling and recovery
    - Add processing performance optimization
    - Create processing metrics and monitoring
    - Write integration tests for complete processing pipeline
    - _Requirements: 5.5, 5.6, 5.7, 5.8_


- [ ] 10. API Layer Implementation


  - [x] 10.1 Create internal FastAPI services

    - Implement FastAPI application with automatic OpenAPI documentation
    - Create CRUD endpoints for all major entities
    - Add query endpoints with filtering, pagination, and sorting
    - Implement data export endpoints for analytics
    - Add API authentication and authorization
    - Create API performance monitoring and rate limiting
    - Write API integration tests with test client
    - _Requirements: 7.1, 7.4, 7.6_

  - [ ] 10.2 Implement Supabase Edge Functions

    - Create public API endpoints using Supabase Edge Functions
    - Implement authentication and row-level security
    - Add rate limiting and request validation
    - Create API documentation and usage examples
    - Implement API monitoring and error tracking
    - Add API versioning and backward compatibility

    - Write edge function tests and deployment scripts

    - _Requirements: 7.2, 7.3, 7.5, 7.7_

- [ ] 11. Security and Compliance


  - [ ] 11.1 Implement security measures


    - Configure HTTPS/TLS for all external communications
    - Implement service account security with minimal permissions
    - Add API key management and rotation procedures
    - Create audit trail logging for all data operations
    - Implement data access controls and RLS policies
    - Add security monitoring and breach detection
    - Write security tests and penetration testing procedures
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.8_

  - [ ] 11.2 Create compliance framework

    - Implement PII detection and exclusion mechanisms
    - Add data retention policies and archival procedures
    - Create compliance reporting and audit capabilities
    - Implement data deletion and right-to-be-forgotten support

    - Add compliance monitoring and alerting
    - Create compliance documentation and procedures
    - Write compliance tests and validation procedures
    - _Requirements: 8.5, 8.6, 8.7_

- [ ] 12. Monitoring and Operations


  - [ ] 12.1 Implement comprehensive monitoring


    - Create structured logging with context preservation
    - Implement metrics collection for all system components
    - Add performance monitoring and alerting
    - Create operational dashboards and visualizations
    - Implement health checks and system status monitoring
    - Add capacity planning and resource utilization tracking
    - Write monitoring tests and alert validation
    - _Requirements: 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [ ] 12.2 Create operational procedures

    - Implement deployment procedures per `/docs/04_operations/deployment.md`
    - Create backup and disaster recovery procedures
    - Add maintenance and update procedures
    - Implement troubleshooting guides and runbooks
    - Create operational documentation and training materials
    - Add operational testing and validation procedures
    - Write operational automation scripts and tools
    - _Requirements: 10.5, 10.7_

- [ ] 13. Testing and Quality Assurance


  - [x] 13.1 Create comprehensive test suite

    - Implement unit tests for all components with >90% coverage
    - Create integration tests for end-to-end workflows
    - Add performance tests for scalability validation
    - Implement load tests for high-volume scenarios
    - Create regression tests for critical functionality
    - Add test data management and fixture creation
    - Write test automation and CI/CD integration

    - _Requirements: 10.4_

  - [ ] 13.2 Implement quality assurance processes

    - Create code review procedures and checklists
    - Implement automated code quality checks (Black, mypy, flake8)
    - Add pre-commit hooks for code quality enforcement
    - Create documentation review and update procedures
    - Implement quality metrics tracking and reporting
    - Add quality improvement processes and feedback loops
    - Write quality assurance documentation and training
    - _Requirements: 10.3, 10.8_
