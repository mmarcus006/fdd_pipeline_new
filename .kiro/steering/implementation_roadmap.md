---
inclusion: always
---

# Implementation Patterns & Development Guidelines

## Architecture Patterns

### Prefect Flow Design
- **State-specific flows**: One flow per state scraper (`scrape_minnesota.py`, `scrape_wisconsin.py`)
- **Processing pipelines**: Separate flows for document processing, extraction, validation
- **Error handling**: Use Prefect's retry decorators with exponential backoff
- **Task composition**: Break complex operations into reusable tasks

### Database Operations
- **Connection management**: Use connection pooling via SQLAlchemy
- **Transaction boundaries**: Wrap related operations in database transactions
- **Error handling**: Implement graceful degradation and rollback mechanisms
- **CRUD patterns**: Use repository pattern for consistent data access

### LLM Integration Strategy
- **Model selection**: Route by complexity (Ollama → Gemini Pro → OpenAI GPT-4)
- **Fallback chain**: Always implement secondary model fallback
- **Structured outputs**: Use Instructor with Pydantic for type-safe extraction
- **Rate limiting**: Implement intelligent queuing and backoff

### Document Processing Pipeline
- **MinerU integration**: Prefer local processing, fallback to API
- **Section detection**: Use layout analysis for accurate segmentation
- **Quality validation**: Multi-tier validation (schema → business rules → quality checks)
- **Deduplication**: Fuzzy matching on franchise name and document metadata

## Code Style & Conventions

### File Organization
- **Models**: One Pydantic model per file in `models/`
- **Tasks**: Reusable Prefect tasks in `tasks/`
- **Flows**: Complete workflows in `flows/`
- **Utilities**: Helper functions in `utils/`

### Naming Conventions
- **Python files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions/variables**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Prefect flows**: `{action}_{target}` (e.g., `scrape_minnesota`)

### Error Handling Patterns
```python
# Use structured logging with context
logger.info("Processing document", extra={"franchise_id": fid, "document_type": "fdd"})

# Implement retry with exponential backoff
@task(retries=3, retry_delay_seconds=[1, 4, 10])
def extract_section(document_path: str) -> SectionData:
    pass

# Use Pydantic for validation
try:
    validated_data = FranchiseModel.model_validate(raw_data)
except ValidationError as e:
    logger.error("Validation failed", extra={"errors": e.errors()})
```

### Configuration Management
- **Environment variables**: Use Pydantic Settings for type-safe config
- **Secrets**: Never commit credentials, use `.env` files
- **Defaults**: Provide sensible defaults in `config.py`
- **Validation**: Validate configuration on startup

## Development Workflow

### Testing Requirements
- **Unit tests**: Required for all utility functions and models
- **Integration tests**: Required for database operations and external APIs
- **Mock external services**: Use pytest fixtures for consistent test data
- **Coverage target**: Maintain >80% test coverage

### Code Quality Gates
- **Pre-commit hooks**: black, mypy, pytest must pass
- **Type hints**: Required for all function parameters and returns
- **Docstrings**: Google-style docstrings for all public functions
- **Import organization**: Standard library → Third-party → Local imports

### Performance Considerations
- **Batch processing**: Process documents in configurable batch sizes
- **Connection pooling**: Reuse database connections
- **Async operations**: Use async/await for I/O-bound operations
- **Memory management**: Stream large files, avoid loading entire documents

## Critical Implementation Notes

### MinerU Integration
- **Local setup**: Requires CUDA for GPU acceleration
- **Fallback strategy**: API mode when local processing fails
- **Output format**: Expect structured JSON with section boundaries
- **Error handling**: Graceful degradation to text-based extraction

### Database Schema Adherence
- **Foreign keys**: Always maintain referential integrity
- **Timestamps**: Use UTC timestamps with timezone awareness
- **Soft deletes**: Use `deleted_at` fields instead of hard deletes
- **Indexing**: Index frequently queried fields (franchise_name, state, year)

### LLM Prompt Engineering
- **YAML templates**: Store all prompts in `prompts/*.yaml`
- **Few-shot examples**: Include 2-3 examples per prompt
- **Variable injection**: Use Jinja2 templating for dynamic content
- **Output validation**: Always validate LLM outputs against Pydantic schemas

### Security & Privacy
- **API keys**: Store in environment variables, never in code
- **Data sanitization**: Sanitize all user inputs and file paths
- **Access control**: Implement proper authentication for internal APIs
- **Audit logging**: Log all data modifications with user context