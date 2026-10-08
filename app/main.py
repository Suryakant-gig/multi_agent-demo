import os
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.utils.config import settings
from app.utils.logger import logger
from app.utils.exceptions import AppException
from contextlib import asynccontextmanager
from app.storage.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database initialization deferred on startup: {e}")
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    description="""
    InfinityGPT — Unified AI-powered Tabular Data Analysis, Research Agent, and Document Intelligence Platform.
    
    ### Capabilities:
    * **Single-Origin Frontend:** InfinityGPT ChatGPT-style UI served directly at http://localhost:8000/
    * **PostgreSQL Central Persistence:** Conversations, messages, file metadata, document chunks, research bibliographies, citations, and tool audits.
    * **Tabular Ingestion & Analytics:** Streamed CSV/Excel processing, categorical group aggregations, schema profiling, and secure SQL queries.
    * **Research Agent:** Query planning, multi-query web search, candidate ranking, fetch, evidence synthesis, and citations.
    * **Document Intelligence:** Page-level PDF extraction, semantic chunking, and verifiable page citations.
    * **Visualization:** Declarative charts with Base64 previews and dynamic multi-turn context tracking.
    """,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Restrict CORS to known local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.warning(f"Handled application exception on {request.url.path}: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "detail": exc.message,
            "status_code": exc.status_code,
            "details": exc.details
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Only return JSON error if requesting API or not an asset
    logger.warning(f"HTTP exception on {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": str(exc.detail),
            "detail": str(exc.detail),
            "status_code": exc.status_code,
            "details": {}
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Request validation failure on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Input request validation error",
            "status_code": 422,
            "details": {"validation_errors": exc.errors()}
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "An unexpected internal server error occurred.",
            "status_code": 500,
            "details": {"message": str(exc)}
        }
    )

# Include API Router BEFORE static files mount
app.include_router(api_router)

# Mount Frontend at root '/' to serve index.html, app.js, index.css from single origin
if os.path.exists("frontend"):
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse("frontend/index.html")

    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
