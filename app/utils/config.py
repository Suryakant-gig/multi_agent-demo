import logging
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "InfinityGPT"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database configuration
    DATABASE_URL: Optional[str] = None

    # Storage settings
    UPLOAD_DIR: str = "./data/uploads"
    DB_DIR: str = "./data/dbs"
    CONVERSATIONS_DIR: str = "./data/conversations"
    MAX_UPLOAD_SIZE_MB: int = 100
    CHUNK_SIZE_ROWS: int = 10000
    
    # LLM Settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_API_KEY: Optional[str] = None

    # Research & Web Search Settings
    WEB_SEARCH_PROVIDER: str = "tavily"
    TAVILY_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None
    BRAVE_API_KEY: Optional[str] = None
    MAX_WEB_RESULTS: int = 5
    MAX_RESEARCH_SOURCES: int = 5
    MAX_FETCH_CHARS: int = 50000
    FETCH_TIMEOUT_SECONDS: int = 15

    # Document / PDF Settings
    PDF_CHUNK_SIZE_CHARS: int = 1200
    PDF_CHUNK_OVERLAP_CHARS: int = 200
    
    # Retrieval defaults
    DEFAULT_TOP_K: int = 5
    MAX_SEARCH_RESULTS: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )



settings = Settings()
