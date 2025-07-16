"""
FDD Pipeline Internal API

FastAPI-based service for programmatic access to pipeline operations and data.
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from config import settings
from utils.database import DatabaseManager, get_supabase_client
from utils.logging import get_logger

# Logger setup
logger = get_logger(__name__)

# FastAPI app initialization
app = FastAPI(
    title="FDD Pipeline Internal API",
    description="Internal API for FDD document processing pipeline operations",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for requests/responses
class FlowRunRequest(BaseModel):
    limit: Optional[int] = None
    force: bool = False


class FlowRunResponse(BaseModel):
    flow_run_id: str
    status: str
    estimated_start: datetime


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    dependencies: dict


class UploadResponse(BaseModel):
    fdd_id: str
    drive_file_id: str
    status: str


# Dependencies
def verify_api_token(authorization: str = Header(None)) -> bool:
    """Verify internal API token from Authorization header."""
    if not authorization:
        return False
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return False
        
        # Check against configured token
        internal_token = os.getenv("INTERNAL_API_TOKEN")
        if not internal_token:
            logger.warning("INTERNAL_API_TOKEN not configured")
            return False
            
        return token == internal_token
    except Exception:
        return False


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check if the API service is running and can connect to dependencies."""
    dependencies = {}
    
    # Check database connection
    try:
        db = DatabaseManager()
        if db.health_check():
            dependencies["database"] = "connected"
        else:
            dependencies["database"] = "error"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        dependencies["database"] = "error"
    
    # Check Prefect connection
    try:
        # Simple check if Prefect API is reachable
        prefect_url = os.getenv("PREFECT_API_URL", "http://localhost:4200")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{prefect_url}/health",
                timeout=5.0
            )
            if response.status_code == 200:
                dependencies["prefect"] = "connected"
            else:
                dependencies["prefect"] = "error"
    except Exception:
        dependencies["prefect"] = "error"
    
    # Check Google Drive authentication
    try:
        # Check if credentials file exists
        gdrive_creds = os.getenv("GDRIVE_CREDS_JSON", "")
        if os.path.exists(gdrive_creds):
            dependencies["google_drive"] = "authenticated"
        else:
            dependencies["google_drive"] = "not_configured"
    except Exception:
        dependencies["google_drive"] = "error"
    
    # Determine overall status
    overall_status = "healthy"
    if any(status == "error" for status in dependencies.values()):
        overall_status = "degraded"
    
    response = HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        dependencies=dependencies
    )
    
    # Return 503 if degraded
    if overall_status == "degraded":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.dict()
        )
    
    return response


# Pipeline operations endpoints
@app.post("/prefect/run/{source}", response_model=FlowRunResponse)
async def trigger_scraping_flow(
    source: str,
    request: FlowRunRequest,
    authorization: str = Header(None)
):
    """Trigger a scraping flow for a specific source."""
    # Verify authorization
    if not verify_api_token(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authorization token"
        )
    
    # Validate source
    valid_sources = ["mn", "wi"]
    if source not in valid_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source. Must be one of: {valid_sources}"
        )
    
    try:
        # Import Prefect client
        from prefect import get_client
        
        # Map source to deployment name
        deployment_map = {
            "mn": "scrape-minnesota/mn-weekly",
            "wi": "scrape-wisconsin/wi-weekly"
        }
        
        deployment_name = deployment_map[source]
        
        # Create flow run via Prefect API
        async with get_client() as client:
            # Check if flow is already running
            if not request.force:
                # Query for running flows
                from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterState
                from prefect.client.schemas.objects import State
                
                filter_obj = FlowRunFilter(
                    state=FlowRunFilterState(
                        type=["RUNNING", "PENDING", "SCHEDULED"]
                    )
                )
                
                flow_runs = await client.read_flow_runs(
                    flow_run_filter=filter_obj,
                    limit=10
                )
                
                # Check if any match our deployment
                for run in flow_runs:
                    if deployment_name in str(run.deployment_id):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Flow already running: {run.id}"
                        )
            
            # Create new flow run
            deployment = await client.read_deployment_by_name(deployment_name)
            
            # Set parameters
            parameters = {}
            if request.limit:
                parameters["limit"] = request.limit
            
            # Create run
            flow_run = await client.create_flow_run_from_deployment(
                deployment_id=deployment.id,
                parameters=parameters
            )
            
            logger.info(f"Created flow run {flow_run.id} for {deployment_name}")
            
            return FlowRunResponse(
                flow_run_id=str(flow_run.id),
                status="scheduled",
                estimated_start=flow_run.expected_start_time or datetime.utcnow()
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger flow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger flow: {str(e)}"
        )


# Document management endpoints
@app.post("/file/upload", response_model=UploadResponse)
async def upload_fdd(
    document: UploadFile = File(...),
    franchise_name: str = Form(...),
    filing_state: str = Form(...),
    issue_date: str = Form(...),
    authorization: str = Header(None)
):
    """Upload a manual FDD for processing."""
    # Verify authorization
    if not verify_api_token(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authorization token"
        )
    
    # Validate file size
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    contents = await document.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE/1024/1024}MB"
        )
    
    # Validate file type
    if not document.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted"
        )
    
    # Validate state
    valid_states = ["MN", "WI"]
    if filing_state.upper() not in valid_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filing state. Must be one of: {valid_states}"
        )
    
    try:
        # Parse date
        from datetime import datetime
        issue_date_obj = datetime.strptime(issue_date, "%Y-%m-%d").date()
        
        # Generate FDD ID
        import uuid
        fdd_id = str(uuid.uuid4())
        
        # Upload to Google Drive
        from tasks.drive_operations import upload_to_drive
        
        # Create filename
        safe_franchise_name = franchise_name.replace(" ", "_").replace("/", "_")
        filename = f"{safe_franchise_name}_{issue_date}_{filing_state}.pdf"
        
        # Upload
        drive_file_id = await upload_to_drive(
            content=contents,
            filename=filename,
            folder_path=f"manual_uploads/{filing_state}"
        )
        
        # Store metadata in database
        db = DatabaseManager()
        
        # First, find or create franchisor
        franchisor_data = {
            "canonical_name": franchise_name,
            "created_at": datetime.utcnow()
        }
        
        franchisor = db.create("franchisors", franchisor_data)
        
        # Create FDD record
        fdd_data = {
            "id": fdd_id,
            "franchise_id": franchisor["id"],
            "issue_date": issue_date_obj,
            "document_type": "Initial",
            "filing_state": filing_state.upper(),
            "drive_file_id": drive_file_id,
            "drive_path": f"manual_uploads/{filing_state}/{filename}",
            "processing_status": "pending",
            "created_at": datetime.utcnow()
        }
        
        db.create("fdds", fdd_data)
        
        logger.info(f"Uploaded FDD {fdd_id} for {franchise_name}")
        
        return UploadResponse(
            fdd_id=fdd_id,
            drive_file_id=drive_file_id,
            status="queued_for_processing"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to upload FDD: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload FDD: {str(e)}"
        )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "FDD Pipeline Internal API",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/health"
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler."""
    return {
        "detail": "Resource not found"
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Custom 500 handler."""
    import uuid
    error_id = str(uuid.uuid4())
    logger.error(f"Internal error {error_id}: {exc}")
    
    return {
        "detail": "Internal server error",
        "error_id": error_id,
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)