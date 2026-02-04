"""Tests for RelationshipDNA SQL migration.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""

import os


class TestRelationshipDNAMigration:
    """Test suite for RelationshipDNA migration file."""

    def test_migration_file_exists(self):
        """Migration SQL file should exist."""
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "migrations", "relationship_dna.sql"
        )
        assert os.path.exists(migration_path), f"Migration file not found at {migration_path}"

    def test_migration_contains_create_table(self):
        """Migration should contain CREATE TABLE statement."""
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "migrations", "relationship_dna.sql"
        )
        with open(migration_path, "r") as f:
            content = f.read()

        assert "CREATE TABLE" in content.upper()
        assert "relationship_dna" in content.lower()

    def test_migration_contains_required_columns(self):
        """Migration should contain all required columns."""
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "migrations", "relationship_dna.sql"
        )
        with open(migration_path, "r") as f:
            content = f.read().lower()

        required_columns = [
            "creator_id",
            "follower_id",
            "relationship_type",
            "trust_score",
            "depth_level",
            "vocabulary_uses",
            "vocabulary_avoids",
            "emojis",
            "bot_instructions",
            "golden_examples",
            "total_messages_analyzed",
            "version",
        ]

        for col in required_columns:
            assert col in content, f"Required column '{col}' not found in migration"

    def test_migration_contains_unique_constraint(self):
        """Migration should have unique constraint on creator_id + follower_id."""
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "migrations", "relationship_dna.sql"
        )
        with open(migration_path, "r") as f:
            content = f.read().lower()

        assert "unique" in content
        assert "creator_id" in content
        assert "follower_id" in content

    def test_migration_contains_indexes(self):
        """Migration should create indexes for performance."""
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "migrations", "relationship_dna.sql"
        )
        with open(migration_path, "r") as f:
            content = f.read().lower()

        assert "create index" in content
        assert "idx_relationship_dna" in content
