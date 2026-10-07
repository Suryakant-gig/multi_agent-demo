import logging
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "AI Data Agent Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Storage settings
    UPLOAD_DIR: str = "./data/uploads"
    DB_DIR: str = "./data/dbs"
    MAX_UPLOAD_SIZE_MB: int = 100
    CHUNK_SIZE_ROWS: int = 10000
    
    # LLM Settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_API_KEY: Optional[str] = None
    
    # Retrieval defaults
    DEFAULT_TOP_K: int = 5
    MAX_SEARCH_RESULTS: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
