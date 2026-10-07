from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.api.router import api_router
from app.utils.config import settings
from app.utils.logger import logger
from app.utils.exceptions import AppException

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    Production-ready AI-powered Excel & CSV Data Analysis, Search, and Visualization Agent Platform.
    
    ### Capabilities:
    * **Ingestion:** Streamed/chunked Excel and CSV ingestion into indexed queryable SQLite storage.
    * **Agent Intelligence:** Dual-mode agent orchestrator (Gemini LLM reasoning + deterministic semantic pipeline fallback).
    * **Data Retrieval:** Ranked Top-K candidate search with verifiable row-level citations.
    * **Analytics & Tools:** Categorical group aggregations, schema profiling, and secure read-only SQL queries.
    * **Visualization:** Multi-chart generation (Bar, Line, Pie, Scatter, Histogram, Time-Series) with Base64 images and declarative JSON specs.
    * **Conversational Context:** Multi-turn session tracking with automatic coreference resolution ("Make a chart for that").
    """,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.exceptions import HTTPException as StarletteHTTPException

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

# Include Router
app.include_router(api_router)

# Root endpoint
@app.get("/", tags=["Root"])
def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
