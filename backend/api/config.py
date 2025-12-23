"""
Centralized configuration for Clonnect API
"""
import os
import logging
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


class Settings:
    """Application settings"""

    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    USE_DB: bool = bool(DATABASE_URL)
    # If False (default), raise exception when DB expected but fails
    # If True, allow fallback to JSON files with warning
    ENABLE_JSON_FALLBACK: bool = os.getenv("ENABLE_JSON_FALLBACK", "false").lower() == "true"
    APP_NAME: str = "Clonnect API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"
    DEFAULT_CREATOR_ID: str = os.getenv("DEFAULT_CREATOR_ID", "manel")
    CORS_ORIGINS: list = ["*"]
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    API_PREFIX: str = ""
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    INSTAGRAM_VERIFY_TOKEN: str = os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")

    def __init__(self):
        self.DATABASE_URL = os.getenv("DATABASE_URL", "")
        self.USE_DB = bool(self.DATABASE_URL)
        self.ENABLE_JSON_FALLBACK = os.getenv("ENABLE_JSON_FALLBACK", "false").lower() == "true"


def handle_db_fallback(operation: str, error: Exception, fallback_func=None):
    """
    Handle database operation failure with optional JSON fallback.

    Args:
        operation: Description of the failed operation
        error: The exception that occurred
        fallback_func: Optional callable for JSON fallback (only used if ENABLE_JSON_FALLBACK=true)

    Returns:
        Result from fallback_func if enabled, otherwise raises exception
    """
    settings = get_settings()

    if settings.ENABLE_JSON_FALLBACK and fallback_func:
        logger.warning(f"[DB FALLBACK] {operation} failed, using JSON fallback: {error}")
        return fallback_func()
    else:
        logger.error(f"[DB ERROR] {operation} failed: {error}")
        raise RuntimeError(f"Database operation failed: {operation}. Error: {error}")

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
