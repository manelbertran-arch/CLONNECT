"""Fix personality_docs id DEFAULT: uuid_generate_v4() -> gen_random_uuid().

Revision ID: 034
Revises: 033
Create Date: 2026-02-23

Problem: Migration 033 created personality_docs with
  DEFAULT uuid_generate_v4() which requires the uuid-ossp extension.
  Neon does not have uuid-ossp enabled, so the column DEFAULT is broken.

Solution: Switch to gen_random_uuid() which is built-in in PostgreSQL 13+
  and available on Neon without any extension. The INSERT paths in
  extractor.py and maintenance.py already supply the UUID from Python, so
  the server-side DEFAULT is only a safety net.
"""

from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE personality_docs ALTER COLUMN id SET DEFAULT gen_random_uuid()"
    )


def downgrade():
    op.execute(
        "ALTER TABLE personality_docs ALTER COLUMN id SET DEFAULT gen_random_uuid()"
    )
