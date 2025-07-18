# FDD Pipeline Refactoring Plan - MN/WI Scraper Consolidation

## Executive Summary

This document outlines a comprehensive refactoring strategy to consolidate the Minnesota and Wisconsin web scrapers, unify database operations, and implement a modular architecture with clear separation of concerns. The plan targets a 30-40% reduction in code size while improving maintainability, testability, and extensibility.

**Target Outcomes:**
- Reduce codebase from ~30,000 to ~18,000-21,000 lines (30-40% reduction)
- Eliminate ~40% code duplication between scrapers
- Unify database operations into single abstraction layer
- Implement robust error handling and retry mechanisms
- Enable async operations with proper connection pooling

---

## 1. New Modular Architecture Design

### 1.1 Core Architecture Principles

```
┌─────────────────────────────────────────────────────────────┐
│                     Presentation Layer                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │   FastAPI   │  │   Prefect    │  │      CLI        │   │
│  │   Endpoints │  │    Flows     │  │   Interface     │   │
│  └─────────────┘  └──────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                     Business Logic Layer                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │   Scraper   │  │   Document   │  │   Extraction    │   │
│  │   Service   │  │  Processing  │  │    Service      │   │
│  └─────────────┘  └──────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Data Access Layer                         │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ Repository  │  │    Query     │  │   Connection    │   │
│  │  Pattern    │  │   Builder    │  │     Pool        │   │
│  └─────────────┘  └──────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │  Database   │  │   Storage    │  │    External     │   │
│  │  (Supabase) │  │   (S3/GCS)   │  │     APIs        │   │
│  └─────────────┘  └──────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Module Organization

```
fdd_pipeline_new/
├── core/                      # Core business logic
│   ├── scrapers/             # Scraper implementations
│   │   ├── base.py          # BaseScraper abstract class
│   │   ├── minnesota.py     # MinnesotaScraper
│   │   ├── wisconsin.py     # WisconsinScraper
│   │   └── registry.py      # Scraper registration
│   │
│   ├── processors/           # Document processing
│   │   ├── pdf.py           # PDF processing
│   │   ├── extraction.py    # Data extraction
│   │   └── validation.py    # Data validation
│   │
│   └── services/            # Business services
│       ├── scraping.py      # Scraping orchestration
│       ├── processing.py    # Processing pipeline
│       └── storage.py       # Storage operations
│
├── data/                     # Data access layer
│   ├── repositories/        # Repository pattern
│   │   ├── base.py         # BaseRepository
│   │   ├── fdd.py          # FDDRepository
│   │   ├── franchisor.py   # FranchisorRepository
│   │   └── items.py        # ItemsRepository
│   │
│   ├── models/              # Pydantic models (existing)
│   └── database.py          # Unified DB operations
│
├── infrastructure/          # Infrastructure concerns
│   ├── config/             # Configuration
│   ├── logging/            # Logging setup
│   ├── cache/              # Caching layer
│   └── monitoring/         # Health checks
│
└── interfaces/             # External interfaces
    ├── api/               # FastAPI
    ├── cli/               # CLI commands
    └── flows/             # Prefect flows
```

---

## 2. Unified Database Operations Layer

### 2.1 Repository Pattern Implementation

```python
# data/repositories/base.py
from typing import TypeVar, Generic, List, Optional, Dict, Any
from uuid import UUID
from abc import ABC, abstractmethod

T = TypeVar('T')

class BaseRepository(Generic[T], ABC):
    """Base repository with common CRUD operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[T]:
        """Get entity by ID."""
        pass
        
    @abstractmethod
    async def get_all(self, filters: Dict[str, Any] = None) -> List[T]:
        """Get all entities with optional filters."""
        pass
        
    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create new entity."""
        pass
        
    @abstractmethod
    async def update(self, id: UUID, entity: T) -> T:
        """Update existing entity."""
        pass
        
    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete entity."""
        pass
```

### 2.2 Unified Database Manager

```python
# data/database.py
class DatabaseManager:
    """Unified database operations manager."""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._engine = None
        self._session_factory = None
        self._supabase_client = None
        
    async def initialize(self):
        """Initialize database connections."""
        # Create async engine with connection pooling
        self._engine = create_async_engine(
            self.config.database_url,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        
        # Create session factory
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False
        )
        
    @asynccontextmanager
    async def transaction(self):
        """Provide transactional context."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
```

### 2.3 Query Builder Enhancement

```python
# data/query_builder.py
class AsyncQueryBuilder:
    """Async query builder with fluent interface."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.query = None
        
    def select(self, model: Type[T]) -> 'AsyncQueryBuilder':
        self.query = select(model)
        return self
        
    def filter(self, *conditions) -> 'AsyncQueryBuilder':
        self.query = self.query.filter(*conditions)
        return self
        
    def join(self, target, *conditions) -> 'AsyncQueryBuilder':
        self.query = self.query.join(target, *conditions)
        return self
        
    async def first(self) -> Optional[T]:
        result = await self.session.execute(self.query)
        return result.scalars().first()
        
    async def all(self) -> List[T]:
        result = await self.session.execute(self.query)
        return result.scalars().all()
```

---

## 3. Scraper Consolidation Strategy

### 3.1 Base Scraper Architecture

```python
# core/scrapers/base.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import asyncio
from playwright.async_api import Browser, Page

class BaseScraper(ABC):
    """Abstract base scraper with common functionality."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.session_manager = SessionManager(config)
        self.retry_policy = RetryPolicy(config.retry_settings)
        
    async def initialize(self):
        """Initialize browser and session."""
        self.browser = await self._create_browser()
        self.page = await self.browser.new_page()
        await self._setup_page()
        
    async def _create_browser(self) -> Browser:
        """Create browser with standard configuration."""
        return await playwright.chromium.launch(
            headless=self.config.headless,
            args=self.config.browser_args
        )
        
    async def _setup_page(self):
        """Configure page with headers and settings."""
        await self.page.set_extra_http_headers(self.config.headers)
        await self.page.set_viewport_size(self.config.viewport)
        
    @abstractmethod
    async def discover_documents(self) -> List[DocumentMetadata]:
        """Discover available documents."""
        pass
        
    @abstractmethod
    async def extract_document_metadata(self, url: str) -> DocumentMetadata:
        """Extract metadata for specific document."""
        pass
        
    async def download_document(self, url: str, destination: Path) -> bool:
        """Download document with retry logic."""
        return await self.retry_policy.execute(
            self._download_with_session,
            url, destination
        )
```

### 3.2 State-Specific Implementations

```python
# core/scrapers/minnesota.py
class MinnesotaScraper(BaseScraper):
    """Minnesota-specific scraper implementation."""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config or MinnesotaScraperConfig())
        
    async def discover_documents(self) -> List[DocumentMetadata]:
        """Implement Minnesota's Load More pagination."""
        documents = []
        
        await self.navigate_to_search()
        
        while True:
            # Extract current page documents
            page_docs = await self._extract_page_documents()
            documents.extend(page_docs)
            
            # Check for Load More button
            if not await self._click_load_more():
                break
                
            # Wait for new content
            await self._wait_for_content_update()
            
        return documents

# core/scrapers/wisconsin.py  
class WisconsinScraper(BaseScraper):
    """Wisconsin-specific scraper implementation."""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config or WisconsinScraperConfig())
        
    async def discover_documents(self) -> List[DocumentMetadata]:
        """Implement Wisconsin's table-based discovery."""
        # Get franchise list
        franchises = await self._extract_franchise_table()
        
        documents = []
        for franchise in franchises:
            # Search for each franchise
            doc = await self._search_franchise(franchise)
            if doc:
                documents.append(doc)
                
        return documents
```

### 3.3 Shared Utilities

```python
# core/scrapers/utils.py
class ScraperUtils:
    """Shared scraper utilities."""
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Remove invalid filename characters."""
        return re.sub(r'[\\/*?:"<>|]', "", name)
        
    @staticmethod
    async def extract_table_data(page: Page, selector: str) -> List[Dict[str, Any]]:
        """Extract data from HTML table."""
        # Common table extraction logic
        
    @staticmethod
    async def wait_for_content_update(page: Page, selector: str, timeout: int = 10000):
        """Wait for dynamic content to update."""
        # Common wait logic
```

---

## 4. Error Handling and Retry Logic

### 4.1 Structured Exception Hierarchy

```python
# core/exceptions.py
class FDDPipelineError(Exception):
    """Base exception for all pipeline errors."""
    pass

class ScrapingError(FDDPipelineError):
    """Base scraping error."""
    pass

class NetworkError(ScrapingError):
    """Network-related errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code

class RateLimitError(NetworkError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: Optional[int] = None):
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after

class ExtractionError(FDDPipelineError):
    """Data extraction errors."""
    pass

class ValidationError(FDDPipelineError):
    """Data validation errors."""
    pass
```

### 4.2 Retry Policy Implementation

```python
# core/retry.py
from typing import TypeVar, Callable, Optional, List, Type
import asyncio
from functools import wraps

T = TypeVar('T')

class RetryPolicy:
    """Configurable retry policy with exponential backoff."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        retryable_exceptions: Optional[List[Type[Exception]]] = None
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions or [
            NetworkError,
            asyncio.TimeoutError,
            ConnectionError
        ]
        
    async def execute(
        self,
        func: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """Execute function with retry logic."""
        last_exception = None
        
        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if not self._is_retryable(e):
                    raise
                    
                last_exception = e
                if attempt < self.max_attempts - 1:
                    delay = self._calculate_delay(attempt)
                    await asyncio.sleep(delay)
                    
        raise last_exception
        
    def _is_retryable(self, exception: Exception) -> bool:
        """Check if exception is retryable."""
        return any(
            isinstance(exception, exc_type)
            for exc_type in self.retryable_exceptions
        )
        
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)
```

### 4.3 Circuit Breaker Pattern

```python
# core/circuit_breaker.py
class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function through circuit breaker."""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError()
                
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
```

---

## 5. Connection Pooling and Async Operations

### 5.1 Async Connection Pool Manager

```python
# infrastructure/connection_pool.py
class AsyncConnectionPool:
    """Manages async database connections with pooling."""
    
    def __init__(self, config: PoolConfig):
        self.config = config
        self.pool = None
        self._semaphore = asyncio.Semaphore(config.max_connections)
        
    async def initialize(self):
        """Initialize connection pool."""
        self.pool = await asyncpg.create_pool(
            self.config.database_url,
            min_size=self.config.min_size,
            max_size=self.config.max_size,
            max_queries=self.config.max_queries,
            max_inactive_connection_lifetime=self.config.max_lifetime,
            command_timeout=self.config.command_timeout,
            server_settings={
                'application_name': 'fdd_pipeline',
                'jit': 'off'
            }
        )
        
    async def acquire(self) -> AsyncConnection:
        """Acquire connection from pool."""
        async with self._semaphore:
            return await self.pool.acquire()
            
    async def release(self, connection: AsyncConnection):
        """Release connection back to pool."""
        await self.pool.release(connection)
        
    @asynccontextmanager
    async def connection(self):
        """Context manager for connections."""
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)
```

### 5.2 Async Task Orchestration

```python
# core/orchestration.py
class AsyncTaskOrchestrator:
    """Orchestrates async task execution with concurrency control."""
    
    def __init__(self, max_concurrent_tasks: int = 10):
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self.tasks = []
        
    async def submit(self, coro: Coroutine) -> asyncio.Task:
        """Submit coroutine for execution."""
        async with self.semaphore:
            task = asyncio.create_task(coro)
            self.tasks.append(task)
            return task
            
    async def gather_results(self) -> List[Any]:
        """Gather all task results."""
        return await asyncio.gather(*self.tasks, return_exceptions=True)
        
    async def process_batch(
        self,
        items: List[Any],
        processor: Callable[[Any], Coroutine],
        batch_size: int = 10
    ) -> List[Any]:
        """Process items in batches."""
        results = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_tasks = [
                self.submit(processor(item))
                for item in batch
            ]
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)
            
        return results
```

### 5.3 Async HTTP Client with Connection Pooling

```python
# infrastructure/http_client.py
class AsyncHTTPClient:
    """Async HTTP client with connection pooling."""
    
    def __init__(self, config: HTTPClientConfig):
        self.config = config
        self.session = None
        
    async def initialize(self):
        """Initialize HTTP session with connection pool."""
        connector = aiohttp.TCPConnector(
            limit=self.config.pool_size,
            limit_per_host=self.config.limit_per_host,
            ttl_dns_cache=self.config.dns_cache_ttl
        )
        
        timeout = aiohttp.ClientTimeout(
            total=self.config.total_timeout,
            connect=self.config.connect_timeout,
            sock_read=self.config.read_timeout
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.config.default_headers
        )
        
    async def download_file(
        self,
        url: str,
        destination: Path,
        chunk_size: int = 8192
    ) -> bool:
        """Download file with streaming."""
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                
                with open(destination, 'wb') as file:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        file.write(chunk)
                        
                return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
```

---

## 6. Testing Framework and Validation

### 6.1 Test Structure

```
tests/
├── unit/                    # Unit tests
│   ├── core/
│   │   ├── test_scrapers.py
│   │   ├── test_processors.py
│   │   └── test_services.py
│   ├── data/
│   │   ├── test_repositories.py
│   │   └── test_models.py
│   └── infrastructure/
│       └── test_connection_pool.py
│
├── integration/             # Integration tests
│   ├── test_scraping_flow.py
│   ├── test_database_operations.py
│   └── test_end_to_end.py
│
├── fixtures/               # Test fixtures
│   ├── scrapers.py
│   ├── documents.py
│   └── database.py
│
└── conftest.py            # Pytest configuration
```

### 6.2 Testing Utilities

```python
# tests/fixtures/scrapers.py
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
async def mock_browser():
    """Mock Playwright browser."""
    browser = AsyncMock()
    page = AsyncMock()
    
    # Configure mock responses
    page.content.return_value = "<html>...</html>"
    page.query_selector_all.return_value = []
    
    browser.new_page.return_value = page
    
    yield browser
    
@pytest.fixture
def scraper_config():
    """Test scraper configuration."""
    return ScraperConfig(
        headless=True,
        timeout=5000,
        retry_attempts=2
    )

# tests/unit/core/test_scrapers.py
class TestBaseScraper:
    """Test base scraper functionality."""
    
    async def test_initialize(self, mock_browser, scraper_config):
        """Test scraper initialization."""
        scraper = MockScraper(scraper_config)
        scraper._create_browser = AsyncMock(return_value=mock_browser)
        
        await scraper.initialize()
        
        assert scraper.browser is not None
        assert scraper.page is not None
        mock_browser.new_page.assert_called_once()
        
    async def test_retry_on_network_error(self, scraper):
        """Test retry logic on network errors."""
        scraper._download_with_session = AsyncMock(
            side_effect=[NetworkError("Timeout"), True]
        )
        
        result = await scraper.download_document("http://test.com", Path("test.pdf"))
        
        assert result is True
        assert scraper._download_with_session.call_count == 2
```

### 6.3 Validation Framework

```python
# core/validation.py
class ValidationFramework:
    """Comprehensive validation framework."""
    
    def __init__(self):
        self.validators = {}
        
    def register_validator(
        self,
        model_type: Type[BaseModel],
        validator: Callable[[BaseModel], ValidationResult]
    ):
        """Register validator for model type."""
        self.validators[model_type] = validator
        
    async def validate(
        self,
        data: BaseModel,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Validate data using registered validators."""
        validator = self.validators.get(type(data))
        if not validator:
            return ValidationResult(valid=True)
            
        return await validator(data, context)

# Example validator
async def validate_fdd_document(
    doc: FDDDocument,
    context: Dict[str, Any]
) -> ValidationResult:
    """Validate FDD document."""
    errors = []
    warnings = []
    
    # Check required fields
    if not doc.franchisor_name:
        errors.append("Franchisor name is required")
        
    # Check business rules
    if doc.initial_fee_cents and doc.initial_fee_cents > 10_000_000:
        warnings.append("Initial fee exceeds typical range")
        
    # Cross-reference validations
    if context.get('check_duplicates'):
        if await check_duplicate_filing(doc):
            warnings.append("Possible duplicate filing detected")
            
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Create new directory structure
- [ ] Implement base classes (BaseScraper, BaseRepository)
- [ ] Set up async database manager with connection pooling
- [ ] Create shared utilities module
- [ ] Implement retry policy and circuit breaker

### Phase 2: Core Refactoring (Week 2)
- [ ] Refactor Minnesota scraper to inherit from BaseScraper
- [ ] Refactor Wisconsin scraper to inherit from BaseScraper
- [ ] Consolidate database operations into repositories
- [ ] Implement unified error handling
- [ ] Create async task orchestrator

### Phase 3: Testing & Validation (Week 3)
- [ ] Set up comprehensive test framework
- [ ] Write unit tests for all new components
- [ ] Create integration tests for scrapers
- [ ] Implement validation framework
- [ ] Performance benchmarking

### Phase 4: Migration & Cleanup (Week 4)
- [ ] Migrate existing flows to new architecture
- [ ] Update API endpoints
- [ ] Remove deprecated code
- [ ] Update documentation
- [ ] Deploy and monitor

---

## 8. Measurable Goals and Success Metrics

### Code Reduction Targets
- **Total Lines**: 30,068 → 18,000-21,000 (30-40% reduction)
- **Files**: 87 → 50-60 files
- **Scraper Code**: ~776 lines → ~400 lines (48% reduction)
- **Database Operations**: 1,276 lines → ~600 lines (53% reduction)
- **Test Files**: 22 → 12-15 files (consolidated)

### Performance Improvements
- **Scraping Speed**: 20% faster through async operations
- **Memory Usage**: 30% reduction through connection pooling
- **Error Recovery**: 90% automatic recovery rate
- **Test Execution**: 40% faster through parallel execution

### Quality Metrics
- **Code Coverage**: Maintain >80%
- **Cyclomatic Complexity**: <10 per function
- **Coupling**: Reduce inter-module dependencies by 50%
- **Documentation**: 100% public API documentation

### Maintenance Benefits
- **Bug Fix Time**: 50% reduction
- **Feature Addition**: 40% faster
- **Onboarding Time**: 30% reduction for new developers
- **Code Review Time**: 25% reduction

---

## 9. Risk Mitigation

### Technical Risks
1. **Breaking Changes**
   - Mitigation: Comprehensive test coverage before refactoring
   - Parallel run of old and new systems during transition

2. **Performance Regression**
   - Mitigation: Benchmark before and after each phase
   - Load testing with production-like data

3. **Data Loss**
   - Mitigation: Database backups before migration
   - Rollback procedures documented

### Process Risks
1. **Timeline Slippage**
   - Mitigation: Phased approach with clear milestones
   - Weekly progress reviews

2. **Scope Creep**
   - Mitigation: Strict adherence to defined goals
   - Change requests through formal process

---

## 10. Next Steps

1. **Review and Approval**: Get stakeholder buy-in on the plan
2. **Environment Setup**: Create development branch for refactoring
3. **Team Allocation**: Assign developers to specific phases
4. **Kickoff Meeting**: Align team on approach and timeline
5. **Begin Phase 1**: Start with foundation components

---

*Document Version: 1.0*  
*Created: January 2025*  
*Target Completion: February 2025*
