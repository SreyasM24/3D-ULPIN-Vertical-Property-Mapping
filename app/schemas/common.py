from typing import Generic, TypeVar, Optional, Any, List
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    data: Optional[T] = None
    error: Optional[dict] = None
    meta: Optional[dict] = None


class PaginationParams(BaseModel):
    """Pagination query parameters."""
    page: int = Field(default=1, ge=1, description="Page number starting at 1")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedList(BaseModel, Generic[T]):
    """Paginated data container."""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
