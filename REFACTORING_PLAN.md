# FDD Pipeline - Refactoring Plan

## Code Duplication Removal Strategy

### 1. Consolidate State Scraping Flows (~800 lines of duplicate code)

**Problem**: `flows/scrape_minnesota.py` and `flows/scrape_wisconsin.py` are 95% identical.

**Solution**: Create a generic state scraping flow:

```python
# flows/base_state_flow.py
@flow(name="scrape-state-portal")
async def scrape_state_flow(
    state: str,
    scraper_class: Type[BaseScraper],
    download_documents: bool = True,
    max_documents: Optional[int] = None
) -> dict:
    """Generic state scraping flow."""
    # Common implementation for all states
```

**Benefits**:
- Removes ~400 lines of duplicate code per state
- Makes adding new states trivial (just add a new scraper class)
- Centralizes maintenance and bug fixes

### 2. Unify Document Processing Functions

**Problem**: Document download and processing logic is duplicated in both state flows.

**Solution**: Move common functions to shared modules:

```python
# tasks/document_download.py
async def download_documents(
    metadata_list: List[ScrapeMetadata],
    scraper: BaseScraper,
    state_name: str,
    prefect_run_id: UUID
) -> List[str]:
    """Generic document download function."""
    # Single implementation for all states
```

### 3. Clean Up Unnecessary Files

**Files to Remove**:
- All `.DS_Store` files (25 instances)
- `mn_pagination_results.json` (test data)
- `examples/database_operations_demo.py` (demo script)
- Duplicate test files with similar functionality

### 4. Consolidate Database Operations

**Problem**: Database operations are scattered across flows and tasks.

**Solution**: Enhance `utils/database.py` with high-level operations:

```python
# utils/database.py
class FDDDatabaseOperations:
    """High-level database operations for FDD pipeline."""
    
    async def create_fdd_with_franchisor(self, ...):
    async def update_scrape_status(self, ...):
    async def check_duplicate_document(self, ...):
```

### 5. Simplify Import Structure

**Problem**: Deep import paths and circular dependencies.

**Solution**: 
- Create `__all__` exports in `__init__.py` files
- Use relative imports within packages
- Create top-level imports for commonly used classes

## Implementation Steps

### Phase 1: Create Base Flow (High Priority)
1. Create `flows/base_state_flow.py`
2. Extract common logic from Minnesota and Wisconsin flows
3. Create state-specific configuration classes
4. Update existing flows to use base flow

### Phase 2: Consolidate Utilities (Medium Priority)
1. Create `tasks/document_download.py`
2. Create `tasks/document_metadata.py` 
3. Move shared functions from state scrapers
4. Update imports across the project

### Phase 3: Clean Up Files (Low Priority)
1. Remove all `.DS_Store` files
2. Remove test/demo files from main codebase
3. Archive old migration files if needed
4. Clean up unused imports

### Phase 4: Documentation Update
1. Update CLAUDE.md with new structure
2. Add docstrings to new base classes
3. Create migration guide for existing deployments

## Expected Outcomes

### Code Reduction
- **Before**: ~1,200 lines (both state flows)
- **After**: ~400 lines (base flow + configurations)
- **Savings**: ~800 lines (67% reduction)

### Maintenance Benefits
- Single point of updates for flow logic
- Easier debugging (one flow to trace)
- Consistent behavior across states
- Simpler testing (test base flow once)

### Extensibility
- Adding new state: ~50 lines (just scraper class)
- Previously: ~600 lines (entire flow copy)

## Backwards Compatibility

### Breaking Changes
- Import paths will change
- Flow deployment names may change

### Migration Path
1. Keep old flows temporarily with deprecation warnings
2. Update Prefect deployments to use new flows
3. Update any scripts referencing old flows
4. Remove old flows after transition period

## Testing Strategy

### Unit Tests
- Test base flow with mock scrapers
- Test each scraper independently
- Test shared utilities

### Integration Tests
- Test full pipeline with each state
- Verify database operations
- Check file downloads

### Performance Tests
- Ensure refactoring doesn't impact performance
- Monitor memory usage
- Check for any new bottlenecks