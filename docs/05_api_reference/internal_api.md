# Internal API Reference

## Overview

The FDD Pipeline Internal API is a FastAPI-based service that provides programmatic access to pipeline operations and data. It runs locally alongside the Prefect deployment and is intended for internal tooling and automation.

## Base Configuration

```python
# Base URL (local deployment)
http://localhost:8000

# Authentication
Bearer token in Authorization header (for protected endpoints)
```

## Endpoints

### Health Check

#### `GET /health`

Check if the API service is running and can connect to dependencies.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-20T10:30:00Z",
  "dependencies": {
    "database": "connected",
    "prefect": "connected",
    "google_drive": "authenticated"
  }
}
```

**Status Codes:**
- `200`: All systems operational
- `503`: One or more dependencies unavailable

---

### Pipeline Operations

#### `POST /prefect/run/{source}`

Trigger a scraping flow for a specific source.

**Parameters:**
- `source` (path): Source identifier (`mn` or `wi`)

**Request Body (optional):**
```json
{
  "limit": 10,
  "force": false
}
```

**Response:**
```json
{
  "flow_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "scheduled",
  "estimated_start": "2024-01-20T10:35:00Z"
}
```

**Status Codes:**
- `201`: Flow run created
- `400`: Invalid source
- `409`: Flow already running

---

### Document Management

#### `POST /file/upload`

Upload a manual FDD for processing.

**Request:**
- Content-Type: `multipart/form-data`
- File field: `document`

**Form Data:**
```
document: (binary)
franchise_name: "Example Franchise"
filing_state: "MN"
issue_date: "2024-01-15"
```

**Response:**
```json
{
  "fdd_id": "550e8400-e29b-41d4-a716-446655440000",
  "drive_file_id": "1a2b3c4d5e6f",
  "status": "queued_for_processing"
}
```

**Status Codes:**
- `201`: Upload successful
- `400`: Invalid file or metadata
- `413`: File too large (>50MB)

---

## Error Responses

All endpoints may return these error formats:

### Validation Error (400)
```json
{
  "detail": [
    {
      "loc": ["body", "franchise_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Not Found (404)
```json
{
  "detail": "Resource not found"
}
```

### Internal Server Error (500)
```json
{
  "detail": "Internal server error",
  "error_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-20T10:30:00Z"
}
```

## Authentication

Currently, the internal API uses basic token authentication for administrative endpoints:

```python
headers = {
    "Authorization": "Bearer your-internal-api-token"
}
```

Tokens are configured in the `.env` file:
```
INTERNAL_API_TOKEN=your-secure-token-here
```

## Rate Limiting

- Default: 100 requests per minute per IP
- Upload endpoint: 10 requests per minute
- No rate limiting for health checks

## Example Usage

### Python Client

```python
import httpx

# Initialize client
client = httpx.Client(
    base_url="http://localhost:8000",
    headers={"Authorization": "Bearer your-token"}
)

# Trigger a scrape
response = client.post("/prefect/run/mn", json={"limit": 5})
flow_run = response.json()

# Upload FDD
with open("fdd.pdf", "rb") as f:
    files = {"document": f}
    data = {
        "franchise_name": "Test Franchise",
        "filing_state": "MN",
        "issue_date": "2024-01-15"
    }
    response = client.post("/file/upload", files=files, data=data)
```

### cURL Examples

```bash
# Health check
curl http://localhost:8000/health

# Trigger scrape with auth
curl -X POST http://localhost:8000/prefect/run/wi \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}'

# Upload FDD
curl -X POST http://localhost:8000/file/upload \
  -H "Authorization: Bearer your-token" \
  -F "document=@fdd.pdf" \
  -F "franchise_name=Test Franchise" \
  -F "filing_state=MN" \
  -F "issue_date=2024-01-15"
```

## Development

### Running the API

```bash
# Development mode with auto-reload
uvicorn src.api.main:app --reload --port 8000

# Production mode
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Documentation

When running, interactive API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

For public-facing API access, see [Edge Functions Documentation](edge_functions.md).