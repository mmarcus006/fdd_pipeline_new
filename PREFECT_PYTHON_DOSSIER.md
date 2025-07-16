---
title: "Prefect Python — Implementation Cheat-Sheet"
sections:
  - Overview               # one-sentence description
  - Installation           # pip/uv command, system reqs, env vars
  - Quick Start            # ≤ 30-line runnable snippet
  - Core API Map           # table [class|func|endpoint → purpose] + version notes
  - Extended Recipes       # ≥ 3 sourced snippets, each with source URL comment
  - Best Practices         # bullets: perf, security, testing
  - Troubleshooting FAQ    # top 5 errors + fixes (from GitHub Issues/StackO)
  - Edge Cases & Pitfalls  # nuanced behaviours, gotchas
  - Version Matrix         # chart of breaking changes by version
  - Further Reading        # official docs, blog posts, videos, communities
metadata:
  lib: Prefect Python
  latest_version: 3.1.15
  generated: 2025-01-16T00:00:00Z
  mcp_sources: [websearch, task]
---

# Prefect Python — Implementation Cheat-Sheet

## Overview
Prefect is a modern workflow orchestration framework for Python that enables building, scheduling, and monitoring data pipelines with native Python code, offering dynamic workflows without rigid DAG constraints.

## Installation

```bash
# Using pip
pip install prefect

# Using UV (recommended)
uv pip install prefect

# With optional dependencies
pip install "prefect[dev]"  # Development tools
pip install "prefect[docker]"  # Docker support
pip install "prefect[kubernetes]"  # K8s support
```

**System Requirements:**
- Python 3.9+
- SQLite (included) or PostgreSQL for production
- 2GB+ RAM recommended

**Key Environment Variables:**
```bash
PREFECT_API_URL=http://localhost:4200/api  # Prefect server URL
PREFECT_LOGGING_LEVEL=INFO                  # Log level (DEBUG|INFO|WARNING|ERROR)
PREFECT_LOGGING_COLORS=true                 # Colored logs
PREFECT_HOME=~/.prefect                     # Configuration directory
```

## Quick Start

```python
from prefect import flow, task
import httpx

@task(retries=2, retry_delay_seconds=60, log_prints=True)
def fetch_weather(city: str) -> dict:
    """Fetch weather data with automatic retries."""
    url = f"https://wttr.in/{city}?format=j1"
    response = httpx.get(url)
    response.raise_for_status()
    temp = response.json()["current_condition"][0]["temp_C"]
    print(f"Current temperature in {city}: {temp}°C")
    return {"city": city, "temp": temp}

@flow(name="Weather Pipeline")
def weather_flow(cities: list[str] = ["London", "Paris", "Tokyo"]):
    """Process weather data for multiple cities."""
    results = []
    for city in cities:
        result = fetch_weather(city)
        results.append(result)
    return results

if __name__ == "__main__":
    # Run locally
    weather_flow()
```

## Core API Map

| Component | Purpose | Version Notes |
|-----------|---------|---------------|
| `@flow` | Defines a workflow container | v3: No automatic failure on task errors |
| `@task` | Defines a unit of work with retries/caching | v3: `submit()` is always synchronous |
| `Flow.serve()` | Creates a deployment for scheduled/triggered runs | v3: Replaces `flow.register()` |
| `flow.deploy()` | Deploy to work pools (Docker/K8s/Cloud) | v3: Enhanced infrastructure options |
| `Task.submit()` | Submit task for concurrent execution | v3: Always returns synchronously |
| `Task.map()` | Map task over iterable inputs | v3: Improved performance |
| `get_run_logger()` | Access Prefect's logger within tasks/flows | Consistent across versions |
| `State` | Represents execution state | v3: New state behavior model |
| `Block` | Secure storage for configurations | v2+: Replaces contexts |
| `work_pool` | Infrastructure abstraction layer | v3: Replaces agents |
| `Variable` | Key-value storage for dynamic config | v3: Enhanced UI integration |
| `Artifact` | Store/visualize task outputs | v3: JSON artifact support |

## Extended Recipes

### Recipe 1: Concurrent Task Execution with Error Handling
```python
# Source: https://docs.prefect.io/v3/develop/task-runners
from prefect import flow, task
from prefect.futures import as_completed
import asyncio

@task
def process_item(item: int) -> int:
    if item == 5:
        raise ValueError(f"Failed processing {item}")
    return item * 2

@flow
def concurrent_processing():
    # Submit tasks concurrently
    futures = [process_item.submit(i) for i in range(10)]
    
    # Process results as they complete
    results = []
    for future in as_completed(futures):
        try:
            result = future.result()
            results.append(result)
        except Exception as e:
            print(f"Task failed: {e}")
    
    return results
```

### Recipe 2: Database Operations with Blocks
```python
# Source: https://github.com/PrefectHQ/prefect-recipes/database-blocks
from prefect import flow, task
from prefect_sqlalchemy import SqlAlchemyConnector

@task
def extract_data(block_name: str, query: str) -> list:
    with SqlAlchemyConnector.load(block_name) as conn:
        result = conn.fetch_all(query)
        return result

@flow
def etl_pipeline():
    # Load from source database
    source_data = extract_data(
        "source-db",
        "SELECT * FROM orders WHERE created_at > '2024-01-01'"
    )
    
    # Transform and load to destination
    transformed = transform_data(source_data)
    load_data("dest-db", transformed)
```

### Recipe 3: Event-Driven Workflows with Automations
```python
# Source: https://docs.prefect.io/v3/automate/events/automations-triggers
from prefect import flow, task
from prefect.events import emit_event

@task
def monitor_metrics(threshold: float = 0.9):
    """Monitor system metrics and emit events."""
    cpu_usage = get_cpu_usage()  # Your monitoring logic
    
    if cpu_usage > threshold:
        emit_event(
            event="high-cpu-usage",
            resource={"prefect.resource.id": "system-monitor"},
            attributes={"cpu_usage": cpu_usage}
        )

@flow
def monitoring_flow():
    monitor_metrics()
    
# Automation trigger configuration (via UI or API):
# When: event "high-cpu-usage" occurs
# Then: run scale_resources flow with parameters
```

## Best Practices

**Performance:**
- Use `task.submit()` for concurrent execution instead of sequential calls
- Implement task caching with `cache_key_fn` for expensive operations
- Leverage work pools for distributed execution
- Use `.map()` for parallel processing of collections
- Enable `persist_result=True` only when needed (storage overhead)

**Security:**
- Store sensitive data in Blocks, never hardcode credentials
- Use Prefect Cloud's RBAC for team environments
- Implement service accounts for production deployments
- Rotate API keys regularly via Variables
- Use environment-specific configurations

**Testing:**
- Test flows with `flow.test()` context manager
- Mock external dependencies in tasks
- Use `prefect.testing.utilities` for test fixtures
- Validate flow parameters with Pydantic models
- Test failure scenarios with `raise_on_failure=False`

**Monitoring:**
- Enable `log_prints=True` on tasks for visibility
- Use Artifacts to persist important outputs
- Set up Automations for failure notifications
- Monitor work queue health metrics
- Implement custom metrics with events

## Troubleshooting FAQ

### 1. ImportError: No module named 'prefect'
**Fix:** Ensure correct virtual environment activation and installation:
```bash
python -m pip install prefect
python -m prefect version  # Verify installation
```

### 2. Connection Error to Prefect Server
**Fix:** Check server status and API URL configuration:
```bash
prefect server start  # Start local server
export PREFECT_API_URL=http://localhost:4200/api
prefect config view  # Verify settings
```

### 3. Task Failures Don't Fail Flow (v3 behavior)
**Fix:** Explicitly handle task states in flow logic:
```python
@flow
def my_flow():
    future = my_task.submit()
    if future.state.is_failed():
        raise ValueError("Critical task failed")
    return future.result()
```

### 4. Worker Not Picking Up Flow Runs
**Fix:** Ensure worker is subscribed to correct work pool:
```bash
prefect worker start --pool default-pool --type process
# Or check worker status
prefect work-pool ls
```

### 5. Pydantic Validation Errors After Upgrade
**Fix:** Update to Pydantic v2 syntax:
```python
# Old (Pydantic v1)
class MyModel(BaseModel):
    class Config:
        extra = "forbid"

# New (Pydantic v2)
class MyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

## Edge Cases & Pitfalls

**State Behavior Changes (v3):**
- Task failures don't automatically fail flows unless they affect return values
- Use `raise_on_failure=True` or explicit state checks for v2-like behavior

**Async Execution Gotchas:**
- `task.submit()` is synchronous in v3 (unlike v2's async behavior)
- Mix async/sync carefully - Prefect handles both but consistency helps
- Async flows run tasks concurrently by default

**Dynamic Flow Construction:**
- Flows are Python functions - leverage loops, conditionals freely
- Avoid creating tasks inside loops unless using `.submit()` or `.map()`
- Task decorators are evaluated at import time, not runtime

**Resource Management:**
- Results persist by default in v3 - manage storage carefully
- Large data in parameters can impact performance
- Use Blocks for data references rather than passing large objects

**Deployment Nuances:**
- Work pools require compatible infrastructure
- Schedules use UTC by default - specify timezone explicitly
- Flow parameters must be JSON-serializable

## Version Matrix

| Version | Released | Breaking Changes | Migration Impact |
|---------|----------|------------------|------------------|
| 3.0.0 | Sept 2024 | • Task failures don't fail flows<br>• `submit()` always synchronous<br>• Agents → Workers<br>• `schedule` → `schedules`<br>• Pydantic 2.0 | High - State behavior & API changes |
| 2.14.x | 2023 | • Blocks replace Contexts<br>• New deployment model<br>• Artifacts introduced | Medium - Configuration changes |
| 2.0.0 | July 2022 | • Complete rewrite from v1<br>• Dynamic DAGs<br>• Native async | High - Full rewrite needed |
| 1.x | Legacy | • Rigid DAG structure<br>• Different API | N/A - EOL |

**Compatibility Notes:**
- v3 clients only work with v3 servers
- v2 → v3 requires code review for state handling
- Database migration required for self-hosted servers

## Further Reading

**Official Resources:**
- [Prefect Documentation](https://docs.prefect.io/) - Comprehensive guides
- [API Reference](https://docs.prefect.io/api-ref/) - Detailed API documentation
- [Prefect Recipes](https://github.com/PrefectHQ/prefect-recipes) - Production patterns
- [Prefect Cloud](https://app.prefect.cloud/) - Managed orchestration platform

**Community & Learning:**
- [Prefect Community Slack](https://prefect.io/slack) - Active community support
- [Prefect Discourse](https://discourse.prefect.io/) - Technical discussions
- [YouTube - Prefect](https://youtube.com/@PrefectIO) - Video tutorials
- [GitHub Discussions](https://github.com/PrefectHQ/prefect/discussions) - Feature requests & Q&A

**Integration Libraries:**
- [prefect-aws](https://pypi.org/project/prefect-aws/) - AWS services
- [prefect-dbt](https://pypi.org/project/prefect-dbt/) - dbt integration
- [prefect-sqlalchemy](https://pypi.org/project/prefect-sqlalchemy/) - Database blocks
- [prefect-kubernetes](https://pypi.org/project/prefect-kubernetes/) - K8s workflows

**Blog Posts & Tutorials:**
- [Prefect vs Airflow](https://www.prefect.io/guide/blog/prefect-vs-airflow/) - Comparison guide
- [Event-Driven Workflows](https://www.prefect.io/guide/blog/event-driven-workflows/) - Patterns guide
- [DataOps with Prefect](https://docs.prefect.io/latest/guides/dataops/) - Best practices