import os
from typing import Dict, Any, Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.utils.config import settings
from app.utils.logger import logger

Base = declarative_base()

_engine = None
_SessionLocal = None
_is_postgres = False


def normalize_db_url(url: Optional[str]) -> str:
    """
    Normalizes PostgreSQL URL for SQLAlchemy 2.x and psycopg 3.
    Converts postgresql:// to postgresql+psycopg://
    """
    if not url:
        os.makedirs(settings.DB_DIR, exist_ok=True)
        sqlite_path = os.path.join(settings.DB_DIR, "infinitygpt.db")
        return f"sqlite:///{sqlite_path}"
    
    clean_url = url.strip()
    if clean_url.startswith("postgresql://"):
        return clean_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if clean_url.startswith("postgres://"):
        return clean_url.replace("postgres://", "postgresql+psycopg://", 1)
    return clean_url


def get_engine():
    global _engine, _SessionLocal, _is_postgres
    if _engine is not None:
        return _engine

    db_url = normalize_db_url(settings.DATABASE_URL)
    is_pg = db_url.startswith("postgresql")

    try:
        if is_pg:
            _engine = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                echo=settings.DEBUG
            )
            # Verify connectivity
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            _is_postgres = True
            logger.info("Successfully connected to central PostgreSQL database via psycopg 3.")
        else:
            _engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                echo=settings.DEBUG
            )
            _is_postgres = False
            logger.info("Using SQLite database storage backend.")

    except Exception as e:
        logger.warning(f"Could not connect to configured database at {db_url.split('@')[-1] if '@' in db_url else db_url}: {e}")
        # If PostgreSQL failed, provide fallback engine to prevent server crash
        os.makedirs(settings.DB_DIR, exist_ok=True)
        fallback_url = f"sqlite:///{os.path.join(settings.DB_DIR, 'infinitygpt.db')}"
        logger.info(f"Falling back to local SQLite database at {fallback_url}")
        _engine = create_engine(
            fallback_url,
            connect_args={"check_same_thread": False},
            echo=settings.DEBUG
        )
        _is_postgres = False

    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency and context manager for database sessions.
    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> Dict[str, Any]:
    """
    Checks database health without exposing passwords or full credentials.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        is_pg = engine.url.drivername.startswith("postgresql")
        db_type = "postgresql" if is_pg else "sqlite"
        return {
            "status": "connected",
            "database": "connected",
            "type": db_type
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "degraded",
            "database": "disconnected",
            "error": str(e)
        }


def init_db() -> None:
    """
    Creates all application tables in the configured database.
    Safe and idempotent.
    """
    from app.storage import models  # Ensure all models are registered with Base
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully: all application tables created.")
