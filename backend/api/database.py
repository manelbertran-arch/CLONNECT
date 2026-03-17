import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Get DATABASE_URL and fix Railway's postgres:// to postgresql://
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    logger.info("Fixed DATABASE_URL scheme: postgres:// -> postgresql://")

# Ensure sslmode=require for Neon PostgreSQL
if DATABASE_URL and "sslmode" not in DATABASE_URL:
    separator = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{separator}sslmode=require"
    logger.info("Added sslmode=require to DATABASE_URL")

logger.info("DATABASE_URL configured: %s", bool(DATABASE_URL))

engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        # Connection pooling with keepalive and pre_ping.
        # Reduced from 10+10=20 to 3+5=8 max to allow Neon compute to scale to zero.
        # idle_in_transaction_session_timeout kills leaked transactions after 60s.
        engine = create_engine(
            DATABASE_URL,
            echo=False,
            poolclass=QueuePool,
            pool_size=5,  # 5 base connections (was 3 — too low with background scoring)
            max_overflow=7,  # 7 overflow (12 max)
            pool_timeout=10,  # Fail fast
            pool_recycle=300,  # Recycle every 5 min (shorter for Neon scale-to-zero)
            pool_pre_ping=True,  # Test connections before using them
            connect_args={
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
                # NOTE: do NOT pass idle_in_transaction_session_timeout here —
                # Neon pgbouncer rejects unsupported startup parameters.
                # Neon already sets idle_in_transaction_session_timeout=5min at DB level.
            }
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("SQLAlchemy engine created successfully with connection pooling")
    except Exception as e:
        logger.error("Failed to create SQLAlchemy engine: %s", e, exc_info=True)

Base = declarative_base()

def get_db():
    if SessionLocal is None:
        raise Exception("Database not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from contextlib import contextmanager

@contextmanager
def get_db_session():
    """Context manager for database session - for use outside FastAPI endpoints"""
    if SessionLocal is None:
        raise Exception("Database not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
