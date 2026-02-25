"""
Common database utilities — session factory and constants.
"""

import logging
import os

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)
pg_pool = None  # Not using asyncpg, using SQLAlchemy instead


def get_session():
    if not DATABASE_URL:
        return None
    try:
        from api.database import SessionLocal
        if SessionLocal is None:
            logger.error("SessionLocal not initialized")
            return None
        return SessionLocal()
    except Exception as e:
        logger.error("Failed to create database session: %s", e)
        return None
