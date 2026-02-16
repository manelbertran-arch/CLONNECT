"""Add unified_leads table and unified_lead_id FK on leads

Revision ID: 018
Revises: 017
Create Date: 2026-02-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Create unified_leads table if not exists
    result = conn.execute(
        sa.text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'unified_leads'"
        )
    ).fetchone()

    if not result:
        op.create_table(
            "unified_leads",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
            sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
            sa.Column("display_name", sa.String(255)),
            sa.Column("email", sa.String(255)),
            sa.Column("phone", sa.String(50)),
            sa.Column("profile_pic_url", sa.Text),
            sa.Column("unified_score", sa.Float, server_default="0"),
            sa.Column("status", sa.String(50), server_default="nuevo"),
            sa.Column("first_contact_at", sa.DateTime(timezone=True)),
            sa.Column("last_contact_at", sa.DateTime(timezone=True)),
            sa.Column("merge_history", sa.JSON, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("idx_unified_creator", "unified_leads", ["creator_id"])
        op.create_index("idx_unified_email", "unified_leads", ["creator_id", "email"])
        op.create_index("idx_unified_phone", "unified_leads", ["creator_id", "phone"])

    # Add unified_lead_id column to leads if not exists
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'leads' AND column_name = 'unified_lead_id'"
        )
    ).fetchone()
    if not result:
        op.add_column(
            "leads",
            sa.Column("unified_lead_id", UUID(as_uuid=True), sa.ForeignKey("unified_leads.id"), nullable=True),
        )
        op.create_index("idx_lead_unified", "leads", ["unified_lead_id"])


def downgrade():
    op.drop_index("idx_lead_unified", table_name="leads")
    op.drop_column("leads", "unified_lead_id")
    op.drop_table("unified_leads")
