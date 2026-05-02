from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str
    uptime_seconds: float
    dependencies: dict[str, str] = {}


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    trace_id: Optional[str] = None


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool


class EventMessage(BaseModel):
    source: str
    detail_type: str
    detail: dict[str, Any]
    timestamp: datetime
