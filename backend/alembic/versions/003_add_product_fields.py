"""add_product_fields

Add product_type, short_description, and payment_link to products table.

Revision ID: 003
Revises: 002
Create Date: 2026-01-16

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Add new product fields"""
    # Add product_type column
    op.add_column('products', sa.Column('product_type', sa.String(50), server_default='otro'))

    # Add short_description column
    op.add_column('products', sa.Column('short_description', sa.String(300)))

    # Add payment_link column
    op.add_column('products', sa.Column('payment_link', sa.String(500), server_default=''))

    # Ensure currency can hold longer codes
    op.alter_column('products', 'currency', type_=sa.String(10))


def downgrade():
    """Remove new product fields"""
    op.drop_column('products', 'product_type')
    op.drop_column('products', 'short_description')
    op.drop_column('products', 'payment_link')
    op.alter_column('products', 'currency', type_=sa.String(3))
