"""Structured logging configuration for FDD Pipeline."""

import logging
import sys
from typing import Any, Dict, Optional
from pathlib import Path

import structlog
from pythonjsonlogger import jsonlogger

from config import get_settings, get_logs_dir


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    
    # Create logs directory
    logs_dir = get_logs_dir()
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(logs_dir / "fdd-pipeline.log")
        ]
    )
    
    # Set specific logger levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class PipelineLogger:
    """Pipeline-specific logger with context management."""
    
    def __init__(self, name: str, prefect_run_id: Optional[str] = None):
        self.logger = get_logger(name)
        self.prefect_run_id = prefect_run_id
        self.context: Dict[str, Any] = {}
        
        if prefect_run_id:
            self.context["prefect_run_id"] = prefect_run_id
    
    def bind(self, **kwargs: Any) -> "PipelineLogger":
        """Bind additional context to the logger."""
        new_logger = PipelineLogger(self.logger._context.get("logger", "unknown"))
        new_logger.context = {**self.context, **kwargs}
        new_logger.logger = self.logger.bind(**new_logger.context)
        return new_logger
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""
        self.logger.critical(message, **kwargs)


# Initialize logging on import
configure_logging()