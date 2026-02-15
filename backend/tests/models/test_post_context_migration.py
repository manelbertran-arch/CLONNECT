"""Tests for PostContext SQL migration.

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import os



class TestPostContextMigration:
    """Test suite for post_contexts table migration."""

    def test_migration_file_exists(self):
        """Should have migration SQL file."""
        migration_path = "migrations/post_contexts.sql"
        assert os.path.exists(migration_path), f"Migration file not found: {migration_path}"

    def test_migration_has_required_columns(self):
        """Should define all required columns."""
        migration_path = "migrations/post_contexts.sql"
        with open(migration_path, "r") as f:
            sql = f.read().lower()

        # Required columns
        assert "creator_id" in sql
        assert "active_promotion" in sql
        assert "promotion_deadline" in sql
        assert "promotion_urgency" in sql
        assert "recent_topics" in sql
        assert "recent_products" in sql
        assert "availability_hint" in sql
        assert "context_instructions" in sql
        assert "posts_analyzed" in sql
        assert "analyzed_at" in sql
        assert "expires_at" in sql
        assert "source_posts" in sql

    def test_migration_has_unique_constraint(self):
        """Should have unique constraint on creator_id."""
        migration_path = "migrations/post_contexts.sql"
        with open(migration_path, "r") as f:
            sql = f.read().lower()

        assert "unique" in sql
        assert "creator_id" in sql

    def test_migration_has_indexes(self):
        """Should have performance indexes."""
        migration_path = "migrations/post_contexts.sql"
        with open(migration_path, "r") as f:
            sql = f.read().lower()

        assert "create index" in sql
        assert "idx_post_contexts" in sql
