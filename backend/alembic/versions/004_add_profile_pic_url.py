"""add_profile_pic_url

Add profile_pic_url column to leads table for Instagram profile pictures.

Revision ID: 004
Revises: 003
Create Date: 2026-01-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    """Add profile_pic_url column to leads table"""
    op.add_column('leads', sa.Column('profile_pic_url', sa.String(500)))


def downgrade():
    """Remove profile_pic_url column from leads table"""
    op.drop_column('leads', 'profile_pic_url')
