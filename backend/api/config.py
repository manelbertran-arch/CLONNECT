"""
Centralized configuration for Clonnect API
"""
import os
from typing import Optional
from functools import lru_cache

class Settings:
    """Application settings"""
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    USE_DB: bool = bool(DATABASE_URL)
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

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
