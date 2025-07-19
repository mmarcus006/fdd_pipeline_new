# API Reference

## Overview

The FDD Pipeline provides a REST API built with FastAPI for programmatic access to document processing and data retrieval functionality. The API is designed for internal use and integration with other systems.

## Base URL

```
http://localhost:8000
```

## Authentication

Currently, the API does not require authentication as it's designed for internal use. Authentication will be added in future versions.

## Endpoints

### Health Check

Check if the API is running and healthy.

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0"
}
```

### Process PDF

Submit a PDF for processing through the complete pipeline.

```http
POST /process-pdf
```

**Request Body:**
```json
{
  "pdf_url": "https://example.com/path/to/fdd.pdf",
  "franchise_name": "Example Franchise LLC",  // Optional
  "metadata": {
    "source": "manual_upload",
    "filing_date": "2024-01-15"
  }
}
```

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "PDF processing started",
  "estimated_time_seconds": 300
}
```

### Get Task Status

Check the status of a processing task.

```http
GET /task/{task_id}
```

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",  // pending, processing, completed, failed
  "progress": 100,
  "result": {
    "fdd_id": "660e8400-e29b-41d4-a716-446655440001",
    "franchise_name": "Example Franchise LLC",
    "sections_processed": 23,
    "extraction_complete": true
  },
  "error": null,
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:35:00Z"
}
```

### Search Franchises

Search for franchises in the database.

```http
GET /franchises/search?q={query}&limit={limit}&offset={offset}
```

**Query Parameters:**
- `q` (required): Search query
- `limit` (optional): Number of results (default: 20, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "total": 150,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "canonical_name": "Example Franchise LLC",
      "parent_company": "Example Corp",
      "website": "https://example.com",
      "latest_fdd": {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "issue_date": "2024-01-01",
        "filing_state": "MN"
      }
    }
  ],
  "limit": 20,
  "offset": 0
}
```

### Get Franchise Details

Get detailed information about a specific franchise.

```http
GET /franchises/{franchise_id}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "canonical_name": "Example Franchise LLC",
  "parent_company": "Example Corp",
  "website": "https://example.com",
  "phone": "+1-555-123-4567",
  "email": "franchise@example.com",
  "address": {
    "street": "123 Main St",
    "city": "Minneapolis",
    "state": "MN",
    "zip": "55401"
  },
  "dba_names": ["Example Franchise", "EF"],
  "fdds": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "issue_date": "2024-01-01",
      "document_type": "Initial",
      "filing_state": "MN",
      "processing_status": "completed"
    }
  ],
  "created_at": "2023-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### Get FDD Data

Retrieve extracted data from a specific FDD.

```http
GET /fdds/{fdd_id}/data
```

**Query Parameters:**
- `items` (optional): Comma-separated list of items to include (e.g., "5,6,7,19,20,21")

**Response:**
```json
{
  "fdd_id": "660e8400-e29b-41d4-a716-446655440001",
  "franchise_name": "Example Franchise LLC",
  "issue_date": "2024-01-01",
  "data": {
    "item5": {
      "initial_franchise_fee": {
        "amount_cents": 4500000,
        "refundable": false,
        "due_at": "Signing"
      }
    },
    "item6": {
      "royalty_fee": {
        "amount_percentage": 6.0,
        "frequency": "Monthly",
        "calculation_basis": "Gross Sales"
      },
      "marketing_fee": {
        "amount_percentage": 2.0,
        "frequency": "Monthly",
        "calculation_basis": "Gross Sales"
      }
    },
    "item7": {
      "total_investment": {
        "low_cents": 15000000,
        "high_cents": 35000000
      },
      "categories": [
        {
          "category": "Real Estate",
          "low_cents": 5000000,
          "high_cents": 15000000
        }
      ]
    }
  }
}
```

### Trigger State Scraping

Manually trigger scraping for a specific state portal.

```http
POST /scrape/{state}
```

**Path Parameters:**
- `state`: State code (minnesota, wisconsin)

**Request Body:**
```json
{
  "limit": 10,  // Optional: limit number of documents
  "download": true  // Optional: whether to download PDFs
}
```

**Response:**
```json
{
  "task_id": "770e8400-e29b-41d4-a716-446655440000",
  "state": "minnesota",
  "status": "started",
  "message": "Scraping task initiated"
}
```

### Get Extraction Metrics

Retrieve metrics about extraction performance.

```http
GET /metrics/extractions
```

**Query Parameters:**
- `start_date` (optional): ISO date string
- `end_date` (optional): ISO date string
- `model` (optional): Filter by LLM model

**Response:**
```json
{
  "total_extractions": 1250,
  "success_rate": 0.96,
  "average_time_seconds": 45.2,
  "by_model": {
    "gemini-pro": {
      "count": 800,
      "success_rate": 0.98,
      "average_time": 35.5
    },
    "gpt-4": {
      "count": 350,
      "success_rate": 0.95,
      "average_time": 58.3
    },
    "ollama:llama3": {
      "count": 100,
      "success_rate": 0.88,
      "average_time": 42.1
    }
  },
  "by_item": {
    "5": {"count": 208, "success_rate": 0.99},
    "6": {"count": 208, "success_rate": 0.97},
    "7": {"count": 208, "success_rate": 0.96},
    "19": {"count": 208, "success_rate": 0.94},
    "20": {"count": 208, "success_rate": 0.95},
    "21": {"count": 208, "success_rate": 0.93}
  }
}
```

## Error Responses

All endpoints return consistent error responses:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "pdf_url",
      "reason": "Invalid URL format"
    }
  },
  "request_id": "req_123456789"
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Invalid request parameters |
| `NOT_FOUND` | Resource not found |
| `PROCESSING_ERROR` | Error during processing |
| `RATE_LIMIT` | Too many requests |
| `INTERNAL_ERROR` | Internal server error |

## Rate Limiting

The API implements rate limiting to prevent abuse:

- **Default limit**: 100 requests per minute per IP
- **Burst limit**: 10 concurrent requests
- **Headers returned**:
  - `X-RateLimit-Limit`: Request limit
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Reset timestamp

## WebSocket Support (Future)

WebSocket support for real-time updates is planned for future versions:

```
ws://localhost:8000/ws/task/{task_id}
```

## OpenAPI Documentation

Interactive API documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

## SDK Support

Python SDK example:

```python
from fdd_pipeline_sdk import FDDClient

client = FDDClient(base_url="http://localhost:8000")

# Process a PDF
task = client.process_pdf(
    pdf_url="https://example.com/fdd.pdf",
    franchise_name="Example Franchise"
)

# Check status
status = client.get_task_status(task.id)

# Search franchises
results = client.search_franchises("pizza", limit=10)

# Get FDD data
data = client.get_fdd_data(fdd_id, items=[5, 6, 7])
```

## Best Practices

1. **Use pagination** for search endpoints to avoid large responses
2. **Poll task status** with exponential backoff for long-running operations
3. **Handle rate limits** gracefully with retry logic
4. **Cache responses** when appropriate to reduce API calls
5. **Use specific item filters** when retrieving FDD data to minimize payload size

## Versioning

The API uses URL versioning. The current version is v1 (implicit). Future versions will use:

```
http://localhost:8000/v2/franchises/search
```

## Changelog

### v1.0.0 (Current)
- Initial API release
- Basic CRUD operations
- PDF processing endpoints
- Search functionality
- Metrics endpoints