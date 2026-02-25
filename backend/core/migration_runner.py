"""
Atomic migration runner for database schema changes.

Provides idempotent ALTER TABLE operations that can be run safely
on startup without risking partial migrations.
"""
import logging
from sqlalchemy import text
from api.database import SessionLocal

logger = logging.getLogger(__name__)


def run_migrations():
    """Run all pending idempotent migrations.

    Each migration uses IF NOT EXISTS / IF EXISTS to be safely re-runnable.
    Wrapped in individual transactions so a failure in one doesn't block others.
    """
    migrations = [
        _add_column_if_not_exists("leads", "lead_score", "FLOAT DEFAULT 0"),
        _add_column_if_not_exists("leads", "lead_stage", "VARCHAR(50) DEFAULT 'new'"),
        _add_column_if_not_exists("leads", "last_interaction_at", "TIMESTAMP WITH TIME ZONE"),
        _add_column_if_not_exists("leads", "tags", "JSONB DEFAULT '[]'"),
        _add_column_if_not_exists("messages", "intent", "VARCHAR(100)"),
        _add_column_if_not_exists("messages", "sentiment", "FLOAT"),
        _add_column_if_not_exists("messages", "metadata_json", "JSONB DEFAULT '{}'"),
        _add_column_if_not_exists("creators", "is_paused", "BOOLEAN DEFAULT FALSE"),
        _add_column_if_not_exists("creators", "pause_reason", "TEXT"),
    ]

    with SessionLocal() as session:
        applied = 0
        for migration_sql in migrations:
            try:
                session.execute(text(migration_sql))
                session.commit()
                applied += 1
            except Exception as e:
                session.rollback()
                logger.warning(f"Migration skipped (may already exist): {e}")

        logger.info(f"Migration runner: {applied}/{len(migrations)} migrations applied")


def _add_column_if_not_exists(table: str, column: str, definition: str) -> str:
    """Generate idempotent ALTER TABLE ADD COLUMN statement."""
    return f"""
    DO $$ BEGIN
        ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition};
    EXCEPTION WHEN duplicate_column THEN
        NULL;
    END $$;
    """
