# FDD Pipeline Refactoring - Step-by-Step To-Do List

## Overview
This document provides a detailed, actionable to-do list for executing the refactoring plan, including deletion of unnecessary scripts and tests.

## Phase 1: Create Base State Flow (High Priority)

### 1.1 Create Base Flow Infrastructure
- [ ] Create `flows/base_state_flow.py`
  - [ ] Define abstract `scrape_state_portal` task
  - [ ] Define abstract `process_state_documents` task
  - [ ] Define abstract `download_state_documents` task
  - [ ] Implement generic `scrape_state_flow` with state parameter
  - [ ] Add metrics collection task

### 1.2 Extract Common Logic
- [ ] Analyze `flows/scrape_minnesota.py` and `flows/scrape_wisconsin.py`
- [ ] Identify all common code blocks (90%+ similarity)
- [ ] Extract common functions:
  - [ ] Document processing logic
  - [ ] Franchisor/FDD record creation
  - [ ] Duplicate checking logic
  - [ ] Google Drive upload logic
  - [ ] Metrics collection logic

### 1.3 Create State Configuration
- [ ] Create `flows/state_configs.py`
- [ ] Define `StateConfig` dataclass:
  ```python
  @dataclass
  class StateConfig:
      state_code: str
      state_name: str
      scraper_class: Type[BaseScraper]
      folder_name: str
      portal_name: str
  ```
- [ ] Create configurations for MN and WI

### 1.4 Update Existing Flows
- [ ] Modify `flows/scrape_minnesota.py` to use base flow
- [ ] Modify `flows/scrape_wisconsin.py` to use base flow
- [ ] Add deprecation warnings to old implementations
- [ ] Test both flows still work correctly

## Phase 2: Consolidate Utilities (Medium Priority)

### 2.1 Create Document Download Module
- [ ] Create `tasks/document_download.py`
- [ ] Move `download_minnesota_documents` function (generic version)
- [ ] Extract common download logic:
  - [ ] Document hash computation
  - [ ] Duplicate checking
  - [ ] Google Drive upload
  - [ ] Progress tracking

### 2.2 Create Document Metadata Module
- [ ] Create `tasks/document_metadata.py`
- [ ] Move metadata processing functions
- [ ] Create unified metadata creation logic
- [ ] Add metadata validation

### 2.3 Move Shared Functions
- [ ] From state scrapers to base scraper:
  - [ ] `download_and_save_document`
  - [ ] `process_all_with_downloads`
  - [ ] `export_to_csv`
- [ ] Update scraper imports

### 2.4 Update Imports
- [ ] Find all imports of moved functions
- [ ] Update import paths
- [ ] Test all imports resolve correctly

## Phase 3: Clean Up Files (Low Priority)

### 3.1 Delete Unnecessary Test Files
- [ ] Delete `tests/test_minnesota_flow_simple.py`
- [ ] Delete `tests/test_minnesota_flow_integration.py` (empty)
- [ ] Delete `tests/test_schema_validation.py` (keep enhanced version)

### 3.2 Delete Duplicate/Demo Files
- [ ] Delete any remaining demo scripts in `scripts/`
- [ ] Remove temporary test data files
- [ ] Clean up any backup files (*.bak, *.old)

### 3.3 Archive Old Files
- [ ] Create `archive/` directory
- [ ] Move old migration files (keep only combined)
- [ ] Move any deprecated utilities

### 3.4 Clean Up Imports
- [ ] Run import analysis tool
- [ ] Remove all unused imports
- [ ] Sort imports using isort

## Phase 4: Test Consolidation (Medium Priority)

### 4.1 Create Test Base Classes
- [ ] Create `tests/test_state_flow_base.py`
- [ ] Define `BaseStateFlowTest` class
- [ ] Move common test fixtures
- [ ] Create parameterized test methods

### 4.2 Consolidate State Tests
- [ ] Create `tests/test_state_flows.py`
- [ ] Use pytest.mark.parametrize for states
- [ ] Merge logic from:
  - [ ] `test_minnesota_flow.py`
  - [ ] `test_wisconsin_flow.py`
- [ ] Delete original test files after verification

### 4.3 Create Test Utilities
- [ ] Create `tests/fixtures/` directory
- [ ] Create `tests/fixtures/sample_documents.py`
- [ ] Create `tests/fixtures/mock_responses.py`
- [ ] Create `tests/utils/test_helpers.py`

### 4.4 Update Test Imports
- [ ] Update all test files to use new fixtures
- [ ] Ensure all tests still pass

## Phase 5: Database & Documentation (Medium Priority)

### 5.1 Enhance Database Operations
- [ ] Add to `utils/database.py`:
  ```python
  class FDDDatabaseOperations:
      async def create_fdd_with_franchisor(...)
      async def update_scrape_status(...)
      async def check_duplicate_document(...)
      async def get_pending_fdds(...)
  ```
- [ ] Update flows to use new operations

### 5.2 Add Deprecation System
- [ ] Add deprecation warnings to old flows
- [ ] Create migration guide document
- [ ] Set deprecation timeline (e.g., 30 days)

### 5.3 Update Documentation
- [ ] Update `CLAUDE.md` with new structure
- [ ] Add docstrings to all new modules
- [ ] Update deployment documentation
- [ ] Create state addition guide

### 5.4 Update Deployment
- [ ] Update Prefect deployment scripts
- [ ] Update CI/CD pipelines
- [ ] Test deployments with new structure

## Phase 6: Final Cleanup & Validation

### 6.1 Remove Deprecated Code
- [ ] After transition period, remove old flows
- [ ] Remove old test files
- [ ] Clean up any temporary migration code

### 6.2 Performance Validation
- [ ] Run performance benchmarks
- [ ] Compare before/after metrics
- [ ] Ensure no performance regression

### 6.3 Final Testing
- [ ] Run full test suite
- [ ] Test both state scrapers end-to-end
- [ ] Verify database operations
- [ ] Check file downloads

## Checklist Summary

### Files to Create:
1. `flows/base_state_flow.py`
2. `flows/state_configs.py`
3. `tasks/document_download.py`
4. `tasks/document_metadata.py`
5. `tests/test_state_flow_base.py`
6. `tests/test_state_flows.py`
7. `tests/fixtures/` (directory)
8. `archive/` (directory)

### Files to Delete:
1. `tests/test_minnesota_flow_simple.py`
2. `tests/test_minnesota_flow_integration.py`
3. `tests/test_schema_validation.py`
4. Old individual state test files (after consolidation)
5. Any remaining .DS_Store files
6. Demo/example scripts not in documentation

### Files to Modify:
1. `flows/scrape_minnesota.py` (refactor to use base)
2. `flows/scrape_wisconsin.py` (refactor to use base)
3. `utils/database.py` (add high-level operations)
4. `CLAUDE.md` (update with new structure)
5. `.gitignore` (ensure covers all temp files)

## Success Metrics
- [ ] Code reduction: ~800 lines removed
- [ ] Test suite passes 100%
- [ ] Both state scrapers functional
- [ ] No performance regression
- [ ] Documentation updated
- [ ] Deployment scripts working

## Timeline Estimate
- Phase 1: 2-3 days
- Phase 2: 1-2 days
- Phase 3: 0.5 days
- Phase 4: 1-2 days
- Phase 5: 1 day
- Phase 6: 0.5 days

**Total: 6-9 days**