"""add FAMILIA to relationship_dna CHECK constraint

The Sprint 1 lead profiling changes added FAMILIA to the
RelationshipType enum but the SQL CHECK constraint on the
relationship_dna table only allows the original 6 types.
This migration drops and recreates the constraint with FAMILIA.

Revision ID: 024
Revises: 023
Create Date: 2026-02-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if the table exists first
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'relationship_dna')"
        )
    ).scalar()

    if not result:
        return  # Table doesn't exist yet, nothing to fix

    # Drop old CHECK constraint (may have different names)
    for constraint_name in [
        "chk_relationship_type_valid",
        "relationship_dna_relationship_type_check",
    ]:
        try:
            conn.execute(
                sa.text(
                    f"ALTER TABLE relationship_dna "
                    f"DROP CONSTRAINT IF EXISTS {constraint_name}"
                )
            )
        except Exception:
            pass  # Constraint doesn't exist, that's fine

    # Add new CHECK constraint with FAMILIA included
    conn.execute(
        sa.text(
            "ALTER TABLE relationship_dna "
            "ADD CONSTRAINT chk_relationship_type_valid "
            "CHECK (relationship_type IN ("
            "'FAMILIA', 'INTIMA', 'AMISTAD_CERCANA', 'AMISTAD_CASUAL', "
            "'CLIENTE', 'COLABORADOR', 'DESCONOCIDO'"
            "))"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Revert to original constraint without FAMILIA
    try:
        conn.execute(
            sa.text(
                "ALTER TABLE relationship_dna "
                "DROP CONSTRAINT IF EXISTS chk_relationship_type_valid"
            )
        )
    except Exception:
        pass

    conn.execute(
        sa.text(
            "ALTER TABLE relationship_dna "
            "ADD CONSTRAINT chk_relationship_type_valid "
            "CHECK (relationship_type IN ("
            "'INTIMA', 'AMISTAD_CERCANA', 'AMISTAD_CASUAL', "
            "'CLIENTE', 'COLABORADOR', 'DESCONOCIDO'"
            "))"
        )
    )
