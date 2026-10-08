from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    status_code: int
    details: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    database: str = "connected"
    active_sessions: int = 0
    storage_ready: bool = True
