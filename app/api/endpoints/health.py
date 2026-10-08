from fastapi import APIRouter
from app.schemas.common import HealthResponse
from app.utils.config import settings
from app.state.session_manager import session_manager
from app.storage.database import check_connection

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Health check endpoint returning system status, database connectivity, and session metrics.
    """
    db_health = check_connection()
    db_status = db_health.get("database", "disconnected")
    overall_status = "ok" if db_status == "connected" else "degraded"

    active_count = len(session_manager._sessions)
    return HealthResponse(
        status=overall_status,
        version=settings.APP_VERSION,
        database=db_status,
        active_sessions=active_count,
        storage_ready=db_status == "connected"
    )
