"""Add performance indexes for slow queries

Revision ID: 013
Revises: 012
Create Date: 2026-02-06

These indexes optimize:
- /dm/conversations (leads by creator + status + last_contact)
- /dm/leads (leads by creator)
- /knowledge (knowledge_base by creator)
- Messages lookups (by lead_id)
"""

from alembic import op


# revision identifiers
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    # Leads indexes - for /dm/conversations and /dm/leads
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_creator_id ON leads(creator_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_creator_status ON leads(creator_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_creator_last_contact ON leads(creator_id, last_contact_at DESC NULLS LAST)")

    # Messages indexes - for message counts and lookups
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_lead_id ON messages(lead_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_lead_role ON messages(lead_id, role)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_lead_created ON messages(lead_id, created_at DESC)")

    # Knowledge base index
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_creator ON knowledge_base(creator_id)")

    # Creator name index (for lookups by name)
    op.execute("CREATE INDEX IF NOT EXISTS idx_creator_name ON creators(name)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_leads_creator_id")
    op.execute("DROP INDEX IF EXISTS idx_leads_creator_status")
    op.execute("DROP INDEX IF EXISTS idx_leads_creator_last_contact")
    op.execute("DROP INDEX IF EXISTS idx_messages_lead_id")
    op.execute("DROP INDEX IF EXISTS idx_messages_lead_role")
    op.execute("DROP INDEX IF EXISTS idx_messages_lead_created")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_creator")
    op.execute("DROP INDEX IF EXISTS idx_creator_name")
