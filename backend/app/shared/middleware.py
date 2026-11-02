"""
ResolveAIV2 — Middleware

CORS configuration and global exception handling.
"""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict
import asyncio

import uuid

from app.config import settings
from app.shared.exceptions import ResolveAIException
from app.core.logging import correlation_id_var, generate_correlation_id

logger = logging.getLogger(__name__)


# In-memory rate limiter state
_RATE_LIMIT_CACHE: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_LOCK: asyncio.Lock | None = None
MAX_REQUESTS_PER_MINUTE = 100

def _get_rate_limit_lock() -> asyncio.Lock:
    global _RATE_LIMIT_LOCK
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _RATE_LIMIT_LOCK is None or getattr(_RATE_LIMIT_LOCK, "_loop", None) not in (None, loop):
        _RATE_LIMIT_LOCK = asyncio.Lock()
    return _RATE_LIMIT_LOCK

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate or extract correlation ID
        corr_id = request.headers.get("X-Correlation-ID", generate_correlation_id())
        
        # Set in context
        token = correlation_id_var.set(corr_id)
        
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = corr_id
            return response
        finally:
            correlation_id_var.reset(token)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

class RateLimitingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/docs"):
            client_ip = request.client.host if request.client else "127.0.0.1"
            now = time.time()
            
            lock = _get_rate_limit_lock()
            async with lock:
                # Cleanup old requests
                _RATE_LIMIT_CACHE[client_ip] = [req_time for req_time in _RATE_LIMIT_CACHE[client_ip] if now - req_time < 60]
                
                if len(_RATE_LIMIT_CACHE[client_ip]) >= MAX_REQUESTS_PER_MINUTE:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please try again later."},
                    )
                
                _RATE_LIMIT_CACHE[client_ip].append(now)
                
        return await call_next(request)

def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application."""
    
    # Security Headers
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Rate Limiting
    app.add_middleware(RateLimitingMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(ResolveAIException)
    async def resolveai_exception_handler(request: Request, exc: ResolveAIException):
        from app.shared.exceptions import AuthenticationError, ConflictError, ForbiddenError, NotFoundError, ValidationError
        status_code = 400
        if isinstance(exc, AuthenticationError):
            status_code = 401
            error_code = "AUTH_ERROR"
        elif isinstance(exc, ForbiddenError):
            status_code = 403
            error_code = "FORBIDDEN"
        elif isinstance(exc, NotFoundError):
            status_code = 404
            error_code = "NOT_FOUND"
        elif isinstance(exc, ConflictError):
            status_code = 409
            error_code = "CONFLICT"
        elif isinstance(exc, ValidationError):
            status_code = 422
            error_code = "VALIDATION_ERROR"
        else:
            error_code = "BAD_REQUEST"
            
        logger.warning("Client error", extra={"status_code": status_code, "error_code": error_code, "detail": exc.message})
            
        return JSONResponse(
            status_code=status_code,
            content={
                "error_code": error_code,
                "detail": exc.message,
                "correlation_id": correlation_id_var.get()
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled server exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "detail": f"{type(exc).__name__}: {str(exc)}" if settings.debug else "An unexpected error occurred.",
                "correlation_id": correlation_id_var.get()
            },
        )
        
    from fastapi.exceptions import RequestValidationError
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "VALIDATION_ERROR",
                "detail": str(exc.errors()),
                "correlation_id": correlation_id_var.get()
            },
        )
        
    from fastapi import HTTPException
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        error_code = "HTTP_ERROR"
        if exc.status_code == 401: error_code = "AUTH_ERROR"
        elif exc.status_code == 403: error_code = "FORBIDDEN"
        elif exc.status_code == 404: error_code = "NOT_FOUND"
        elif exc.status_code == 429: error_code = "RATE_LIMITED"
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": error_code,
                "detail": exc.detail,
                "correlation_id": correlation_id_var.get()
            },
            headers=exc.headers
        )

    # Correlation ID (Add last so it runs first)
    app.add_middleware(CorrelationIdMiddleware)
