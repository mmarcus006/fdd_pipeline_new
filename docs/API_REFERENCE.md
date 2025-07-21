# API Reference

## Overview

The FDD Pipeline provides a REST API built with FastAPI for programmatic access to document processing and data retrieval functionality. The API is designed for internal use and integration with other systems.

## Base URL

```
http://localhost:8000
```

## Authentication

The API uses Bearer token authentication for protected endpoints. Include the token in the Authorization header:

```http
Authorization: Bearer {INTERNAL_API_TOKEN}
```

The token is configured via the `INTERNAL_API_TOKEN` environment variable.

## Endpoints

### Root Endpoint

Get basic API information.

```http
GET /
```

**Response:**
```json
{
  "name": "FDD Pipeline API",
  "version": "0.1.0",
  "description": "API for FDD document processing and management"
}
```

### Health Check

Check if the API and its dependencies are healthy.

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "dependencies": {
    "database": "connected",
    "prefect": "connected",
    "google_drive": "connected"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Status Codes:**
- `200 OK`: All dependencies healthy
- `503 Service Unavailable`: One or more dependencies degraded

### Trigger Prefect Flow

Trigger a state scraping flow via Prefect.

```http
POST /prefect/run/{source}
```

**Authentication Required:** Yes

**Path Parameters:**
- `source`: State code (`mn` or `wi`)

**Response:**
```json
{
  "flow_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "state": "PENDING",
  "message": "Flow run created for minnesota"
}
```

**Status Codes:**
- `200 OK`: Flow triggered successfully
- `401 Unauthorized`: Invalid or missing token
- `400 Bad Request`: Invalid source parameter
- `500 Internal Server Error`: Prefect unavailable

### Upload FDD File

Manually upload an FDD PDF file.

```http
POST /file/upload
```

**Authentication Required:** Yes

**Request:** Multipart form data
- `file`: PDF file (required)
- `franchisor_name`: String (required)
- `state_code`: Two-letter state code (required)
- `filing_year`: Integer (optional, defaults to current year)

**Response:**
```json
{
  "fdd_id": "550e8400-e29b-41d4-a716-446655440000",
  "franchisor_id": "660e8400-e29b-41d4-a716-446655440001",
  "google_drive_id": "1ABC...XYZ",
  "message": "FDD uploaded successfully"
}
```

**Status Codes:**
- `200 OK`: Upload successful
- `401 Unauthorized`: Invalid or missing token
- `400 Bad Request`: Invalid file or parameters
- `500 Internal Server Error`: Processing error


## Not Yet Implemented Endpoints

The following endpoints are planned but not yet implemented:

- `GET /franchises/search` - Search franchises
- `GET /franchises/{id}` - Get franchise details
- `GET /fdds/{id}/data` - Retrieve extracted FDD data
- `POST /process-pdf` - Submit PDF for processing
- `GET /task/{id}` - Check processing task status
- `GET /metrics/extractions` - Get extraction metrics




## Error Responses

Error responses use standard HTTP status codes:

**401 Unauthorized:**
```json
{
  "detail": "Invalid token"
}
```

**404 Not Found:**
```json
{
  "detail": "Not Found",
  "path": "/invalid/path"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error",
  "error_id": "550e8400-e29b-41d4-a716-446655440000"
}
```


## Rate Limiting

Rate limiting is not currently implemented but is planned for future versions.


## CORS Configuration

The API allows CORS requests from:
- `http://localhost:*` (any localhost port)

For production deployments, update the CORS configuration in `src/api/main.py`.

## OpenAPI Documentation

Interactive API documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

## SDK Support

No SDK is currently available. Use standard HTTP clients with Bearer token authentication.

## Best Practices

1. **Always include authentication** token for protected endpoints
2. **Handle 503 responses** from health check gracefully
3. **Validate file uploads** before sending to avoid errors
4. **Monitor Prefect flows** separately after triggering

## Versioning

The API is currently at version 0.1.0 and does not use URL versioning. Breaking changes will be communicated in advance.
```

## Changelog

### v0.1.0 (Current)
- Initial API release with basic functionality
- Health check endpoint
- Prefect flow triggering
- Manual FDD file upload
- Bearer token authentication