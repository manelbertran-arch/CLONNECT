"""add_user_profiles

Phase 2.3: Migrate User Profiles from JSON to PostgreSQL.
This migration creates the user_profiles table to store
lead behavior and preferences for personalization.

Note: Different from unified_profiles which stores identity (email, name).
This table stores behavior data (interests, preferences, objections).

Revision ID: 007
Revises: 004
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    """Create user_profiles table"""
    op.create_table(
        'user_profiles',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Identifiers
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),

        # Preferences (language, response_style, communication_tone)
        sa.Column('preferences', postgresql.JSON, default={}),

        # Interests with weights (topic -> weight)
        sa.Column('interests', postgresql.JSON, default={}),

        # Objections raised (list of {type, context, timestamp})
        sa.Column('objections', postgresql.JSON, default=[]),

        # Products of interest (list of {id, name, first_interest, interest_count})
        sa.Column('interested_products', postgresql.JSON, default=[]),

        # Content scores for personalized ranking (content_id -> score)
        sa.Column('content_scores', postgresql.JSON, default={}),

        # Interaction stats
        sa.Column('interaction_count', sa.Integer, default=0),
        sa.Column('last_interaction', sa.DateTime(timezone=True)),

        # DB timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes
    op.create_index('idx_user_profiles_creator_id', 'user_profiles', ['creator_id'])
    op.create_index('idx_user_profiles_user_id', 'user_profiles', ['user_id'])
    op.create_index('idx_user_profiles_creator_user', 'user_profiles', ['creator_id', 'user_id'])

    # Unique constraint (one profile per creator-user pair)
    op.create_unique_constraint(
        'uq_user_profile_creator_user',
        'user_profiles',
        ['creator_id', 'user_id']
    )


def downgrade():
    """Drop user_profiles table"""
    op.drop_constraint('uq_user_profile_creator_user', 'user_profiles')
    op.drop_index('idx_user_profiles_creator_user', table_name='user_profiles')
    op.drop_index('idx_user_profiles_user_id', table_name='user_profiles')
    op.drop_index('idx_user_profiles_creator_id', table_name='user_profiles')
    op.drop_table('user_profiles')
