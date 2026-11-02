"""
ResolveAIV2 — Structured Logging
"""

import json
import logging
import contextvars
import uuid
import time
from typing import Any, Dict

# Context variable to hold the correlation ID for the current request/task
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")

# Fields that should be masked in logs
SENSITIVE_FIELDS = {"password", "token", "access_token", "refresh_token", "jwt", "authorization", "secret", "key"}

def generate_correlation_id() -> str:
    return str(uuid.uuid4())

def mask_secrets(data: Any) -> Any:
    """Recursively mask sensitive fields in dictionaries."""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if any(sensitive in k.lower() for sensitive in SENSITIVE_FIELDS):
                masked[k] = "***REDACTED***"
            else:
                masked[k] = mask_secrets(v)
        return masked
    elif isinstance(data, list):
        return [mask_secrets(i) for i in data]
    return data

class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get()
        }
        
        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        # Extract custom fields passed via `extra={"key": "value"}`
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text", 
                          "filename", "funcName", "levelname", "levelno", 
                          "lineno", "module", "msecs", "message", "msg", 
                          "name", "pathname", "process", "processName", 
                          "relativeCreated", "stack_info", "thread", "threadName"]:
                log_obj[key] = value

        # Ensure no secrets leak in the JSON output
        safe_log_obj = mask_secrets(log_obj)
        
        return json.dumps(safe_log_obj)

def setup_logging():
    """Configure the root logger to use JSON formatting."""
    root_logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
    
    # Set default level
    root_logger.setLevel(logging.INFO)
    
    # Quiet down some chatty libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

