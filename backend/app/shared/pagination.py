"""Shared pagination utilities."""

from pydantic import BaseModel


class PaginationParams(BaseModel):
    """Common pagination parameters."""
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse(BaseModel):
    """Standard paginated response wrapper."""
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
