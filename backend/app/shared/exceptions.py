"""
ResolveAIV2 — Custom Exceptions

Structured exceptions for consistent error handling across the application.
"""

from fastapi import HTTPException, status


class ResolveAIException(Exception):
    """Base exception for all ResolveAI errors."""
    def __init__(self, message: str = "An error occurred"):
        self.message = message
        super().__init__(self.message)


class NotFoundError(ResolveAIException):
    """Resource not found."""
    def __init__(self, resource: str = "Resource", resource_id: int | str | None = None):
        detail = f"{resource} not found" + (f" (id={resource_id})" if resource_id else "")
        super().__init__(detail)


class ForbiddenError(ResolveAIException):
    """Access denied."""
    def __init__(self, message: str = "You do not have permission to access this resource"):
        super().__init__(message)


class ConflictError(ResolveAIException):
    """Resource conflict (e.g., duplicate email)."""
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message)


class ValidationError(ResolveAIException):
    """Business logic validation error."""
    def __init__(self, message: str = "Validation error"):
        super().__init__(message)


class AuthenticationError(ResolveAIException):
    """Authentication failed."""
    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message)


def raise_not_found(resource: str = "Resource", resource_id: int | str | None = None):
    detail = f"{resource} not found" + (f" (id={resource_id})" if resource_id else "")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def raise_forbidden(message: str = "You do not have permission to access this resource"):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def raise_unauthorized(message: str = "Invalid credentials"):
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_conflict(message: str = "Resource already exists"):
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def raise_bad_request(message: str = "Bad request"):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
