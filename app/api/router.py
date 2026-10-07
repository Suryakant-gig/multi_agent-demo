from fastapi import APIRouter
from app.api.endpoints import upload, chat, search, chart, health

api_router = APIRouter(prefix="/api/v1")

# Mount endpoints
api_router.include_router(health.router)
api_router.include_router(upload.router)
api_router.include_router(chat.router)
api_router.include_router(search.router)
api_router.include_router(chart.router)
