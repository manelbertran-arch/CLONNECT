"""add_follower_memories

Phase 2.2: Migrate Follower Memory from JSON to PostgreSQL.
This migration creates the follower_memories table to store
follower data that was previously in data/followers/*.json files.

Revision ID: 006
Revises: 005
Create Date: 2026-01-25

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    """Create follower_memories table with all 27 fields"""
    op.create_table(
        "follower_memories",
        # Primary key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Identifiers
        sa.Column("creator_id", sa.String(100), nullable=False),
        sa.Column("follower_id", sa.String(255), nullable=False),
        # Basic info
        sa.Column("username", sa.String(255), default=""),
        sa.Column("name", sa.String(255), default=""),
        # Timestamps (ISO format strings from original JSON)
        sa.Column("first_contact", sa.String(50), default=""),
        sa.Column("last_contact", sa.String(50), default=""),
        # Interaction stats
        sa.Column("total_messages", sa.Integer, default=0),
        # Profile data (JSON arrays)
        sa.Column("interests", postgresql.JSON, default=[]),
        sa.Column("products_discussed", postgresql.JSON, default=[]),
        sa.Column("objections_raised", postgresql.JSON, default=[]),
        # Scoring
        sa.Column("purchase_intent_score", sa.Float, default=0.0),
        # Status flags
        sa.Column("is_lead", sa.Boolean, default=False),
        sa.Column("is_customer", sa.Boolean, default=False),
        sa.Column("status", sa.String(20), default="new"),
        # Preferences
        sa.Column("preferred_language", sa.String(10), default="es"),
        # Conversation history
        sa.Column("last_messages", postgresql.JSON, default=[]),
        # Link and objection control
        sa.Column("links_sent_count", sa.Integer, default=0),
        sa.Column("last_link_message_num", sa.Integer, default=0),
        sa.Column("objections_handled", postgresql.JSON, default=[]),
        sa.Column("arguments_used", postgresql.JSON, default=[]),
        # Greeting variation
        sa.Column("greeting_variant_index", sa.Integer, default=0),
        # Naturalness fields
        sa.Column("last_greeting_style", sa.String(100), default=""),
        sa.Column("last_emojis_used", postgresql.JSON, default=[]),
        sa.Column("messages_since_name_used", sa.Integer, default=0),
        # Alternative contact
        sa.Column("alternative_contact", sa.String(255), default=""),
        sa.Column("alternative_contact_type", sa.String(50), default=""),
        sa.Column("contact_requested", sa.Boolean, default=False),
        # DB timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes
    op.create_index("idx_follower_memories_creator_id", "follower_memories", ["creator_id"])
    op.create_index("idx_follower_memories_follower_id", "follower_memories", ["follower_id"])
    op.create_index(
        "idx_follower_memories_creator_follower", "follower_memories", ["creator_id", "follower_id"]
    )

    # Unique constraint (one memory per creator-follower pair)
    op.create_unique_constraint(
        "uq_follower_memory_creator_follower", "follower_memories", ["creator_id", "follower_id"]
    )


def downgrade():
    """Drop follower_memories table"""
    op.drop_constraint("uq_follower_memory_creator_follower", "follower_memories")
    op.drop_index("idx_follower_memories_creator_follower", table_name="follower_memories")
    op.drop_index("idx_follower_memories_follower_id", table_name="follower_memories")
    op.drop_index("idx_follower_memories_creator_id", table_name="follower_memories")
    op.drop_table("follower_memories")
