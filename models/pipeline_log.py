"""Pipeline logging models."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class PipelineLogBase(BaseModel):
    """Base model for pipeline logs."""

    prefect_run_id: Optional[UUID] = None
    task_name: Optional[str] = None
    level: LogLevel
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v):
        """Ensure message isn't too long."""
        if len(v) > 10000:
            return v[:10000] + "... (truncated)"
        return v


class PipelineLog(PipelineLogBase):
    """Pipeline log with metadata."""

    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PrefectRunBase(BaseModel):
    """Base model for Prefect run tracking."""

    flow_name: str
    deployment_name: Optional[str] = None
    state: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)


class PrefectRun(PrefectRunBase):
    """Prefect run with metadata."""

    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
