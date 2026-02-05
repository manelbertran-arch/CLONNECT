"""
Shared utilities for admin routers.

Common imports, constants, and helper functions used across admin modules.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Only enable if ENABLE_DEMO_RESET is set (default true for testing)
DEMO_RESET_ENABLED = os.getenv("ENABLE_DEMO_RESET", "true").lower() == "true"

# Whitelist of allowed table names for SQL operations (SQL injection prevention)
ALLOWED_TABLES = frozenset(
    {
        "messages",
        "lead_activities",
        "lead_tasks",
        "leads",
        "products",
        "nurturing_sequences",
        "knowledge_base",
        "email_ask_tracking",
        "platform_identities",
        "user_creators",
        "rag_documents",
        "sync_queue",
        "sync_state",
        "creators",
        "users",
        "unified_profiles",
        "tone_profiles",
        "booking_links",
        "calendar_bookings",
        "content_embeddings",
        "relationship_dna",
        "post_contexts",
    }
)

# Whitelist of allowed FK column names
ALLOWED_FK_COLUMNS = frozenset(
    {
        "lead_id",
        "creator_id",
        "user_id",
    }
)


def validate_table_name(table: str) -> str:
    """Validate table name against whitelist to prevent SQL injection."""
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Table '{table}' not in allowed tables whitelist")
    return table


def validate_fk_column(column: str) -> str:
    """Validate FK column name against whitelist to prevent SQL injection."""
    if column not in ALLOWED_FK_COLUMNS:
        raise ValueError(f"Column '{column}' not in allowed FK columns whitelist")
    return column
