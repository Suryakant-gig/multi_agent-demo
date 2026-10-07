from fastapi import APIRouter
from app.schemas.common import HealthResponse
from app.utils.config import settings
from app.state.session_manager import session_manager

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Health check endpoint returning system status and session metrics.
    """
    active_count = len(session_manager._sessions)
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        active_sessions=active_count,
        storage_ready=True
    )
