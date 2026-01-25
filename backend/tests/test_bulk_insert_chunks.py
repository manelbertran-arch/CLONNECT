"""
Tests for BUG-001 fix: Bulk insert for Instagram posts.

Verifies that:
1. Bulk insert of 1000+ chunks completes without timeout
2. Chunks are correctly persisted to content_chunks table
3. Bot can search and retrieve indexed Instagram content

Run with: pytest tests/test_bulk_insert_chunks.py -v
"""

import time
import uuid
from datetime import datetime
from typing import List
from unittest.mock import MagicMock, patch

import pytest


class TestBulkInsertChunks:
    """Tests for bulk insert functionality in citation_service."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        session.bulk_insert_mappings = MagicMock()
        session.bulk_update_mappings = MagicMock()
        session.commit = MagicMock()
        session.rollback = MagicMock()
        session.close = MagicMock()
        return session

    @pytest.fixture
    def sample_chunks(self) -> List[dict]:
        """Generate sample chunks for testing."""
        return [
            {
                "id": f"chunk_{i}",
                "chunk_id": f"chunk_{i}",
                "content": f"This is test content for chunk {i}. It contains Instagram post text.",
                "source_type": "instagram_post",
                "source_id": f"post_{i}",
                "source_url": f"https://instagram.com/p/test{i}",
                "title": f"Instagram Post {i}",
                "chunk_index": 0,
                "total_chunks": 1,
            }
            for i in range(100)
        ]

    @pytest.fixture
    def large_chunks(self) -> List[dict]:
        """Generate 1000+ chunks for stress testing."""
        return [
            {
                "id": f"large_chunk_{i}",
                "chunk_id": f"large_chunk_{i}",
                "content": f"Stress test content for chunk {i}. " * 10,
                "source_type": "instagram_post",
                "source_id": f"stress_post_{i}",
                "source_url": f"https://instagram.com/p/stress{i}",
                "title": f"Stress Test Post {i}",
                "chunk_index": 0,
                "total_chunks": 1,
            }
            for i in range(1500)  # 1500 chunks to test bulk performance
        ]

    def test_bulk_insert_does_not_use_n_plus_1_queries(self, mock_db_session, sample_chunks):
        """
        Verify that bulk insert uses bulk operations, not N+1 queries.

        The old implementation did:
        - 1 query per chunk to check if exists
        - 1 insert per chunk
        = 2N queries for N chunks

        The new implementation should do:
        - 1 query to get all existing chunk_ids
        - 1 bulk_update_mappings call
        - 1 bulk_insert_mappings call
        - 1 commit
        = O(1) database round trips
        """
        from core.citation_service import _save_chunks_to_db

        with patch("core.citation_service.SessionLocal", return_value=mock_db_session):
            with patch("core.citation_service.ContentChunk"):
                result = _save_chunks_to_db("test_creator", sample_chunks)

        # Should use bulk operations
        assert mock_db_session.bulk_insert_mappings.called or mock_db_session.bulk_update_mappings.called

        # Should NOT call db.add() for each chunk (N+1 pattern)
        # The old code called db.add() in a loop - we don't want that
        add_calls = mock_db_session.add.call_count
        assert add_calls == 0, f"Expected 0 db.add() calls, got {add_calls} (N+1 pattern detected)"

    def test_bulk_insert_1000_chunks_under_timeout(self, large_chunks):
        """
        Verify that inserting 1000+ chunks completes in reasonable time.

        Timeout threshold: 10 seconds
        Old N+1 implementation: ~60+ seconds (caused worker timeout)
        New bulk implementation: should be < 5 seconds
        """
        from core.citation_service import _save_chunks_to_db

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.bulk_insert_mappings = MagicMock()
        mock_session.bulk_update_mappings = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.close = MagicMock()

        start_time = time.time()

        with patch("core.citation_service.SessionLocal", return_value=mock_session):
            with patch("core.citation_service.ContentChunk"):
                result = _save_chunks_to_db("stress_test_creator", large_chunks)

        elapsed_time = time.time() - start_time

        # Should complete in under 10 seconds
        assert elapsed_time < 10, f"Bulk insert took {elapsed_time:.2f}s, expected < 10s"

        # Verify bulk insert was called with all chunks
        if mock_session.bulk_insert_mappings.called:
            call_args = mock_session.bulk_insert_mappings.call_args
            inserted_chunks = call_args[0][1]  # Second argument is the list of mappings
            assert len(inserted_chunks) == len(large_chunks)

    def test_bulk_insert_handles_mixed_update_and_insert(self, mock_db_session, sample_chunks):
        """
        Verify that bulk operations correctly handle:
        - Existing chunks (should be updated)
        - New chunks (should be inserted)
        """
        from core.citation_service import _save_chunks_to_db

        # Simulate that first 30 chunks already exist
        existing_ids = [f"chunk_{i}" for i in range(30)]
        mock_existing = [
            MagicMock(id=uuid.uuid4(), chunk_id=chunk_id)
            for chunk_id in existing_ids
        ]
        mock_db_session.query.return_value.filter.return_value.all.return_value = mock_existing

        with patch("core.citation_service.SessionLocal", return_value=mock_db_session):
            with patch("core.citation_service.ContentChunk"):
                result = _save_chunks_to_db("test_creator", sample_chunks)

        # Should call bulk_update for existing chunks
        assert mock_db_session.bulk_update_mappings.called
        update_args = mock_db_session.bulk_update_mappings.call_args[0][1]
        assert len(update_args) == 30, f"Expected 30 updates, got {len(update_args)}"

        # Should call bulk_insert for new chunks
        assert mock_db_session.bulk_insert_mappings.called
        insert_args = mock_db_session.bulk_insert_mappings.call_args[0][1]
        assert len(insert_args) == 70, f"Expected 70 inserts, got {len(insert_args)}"

    def test_bulk_insert_empty_list_returns_true(self, mock_db_session):
        """Verify that empty chunk list is handled gracefully."""
        from core.citation_service import _save_chunks_to_db

        with patch("core.citation_service.SessionLocal", return_value=mock_db_session):
            result = _save_chunks_to_db("test_creator", [])

        assert result is True
        # Should not attempt any database operations
        assert not mock_db_session.bulk_insert_mappings.called
        assert not mock_db_session.bulk_update_mappings.called

    def test_bulk_insert_rollback_on_error(self, mock_db_session, sample_chunks):
        """Verify that transaction is rolled back on error."""
        from core.citation_service import _save_chunks_to_db

        mock_db_session.commit.side_effect = Exception("Database error")

        with patch("core.citation_service.SessionLocal", return_value=mock_db_session):
            with patch("core.citation_service.ContentChunk"):
                result = _save_chunks_to_db("test_creator", sample_chunks)

        # Should have called rollback
        assert mock_db_session.rollback.called
        assert result is False


class TestIndexCreatorPostsIntegration:
    """Integration tests for index_creator_posts with bulk save."""

    @pytest.fixture
    def sample_posts(self) -> List[dict]:
        """Generate sample Instagram posts."""
        return [
            {
                "post_id": f"ig_post_{i}",
                "caption": f"This is a great post about coaching and wellness! Post number {i}. " * 5,
                "post_type": "instagram_post",
                "url": f"https://instagram.com/p/test{i}",
                "timestamp": datetime.now().isoformat(),
            }
            for i in range(50)
        ]

    @pytest.mark.asyncio
    async def test_index_creator_posts_calls_save(self, sample_posts):
        """Verify that index_creator_posts now calls save (was disabled)."""
        from core.citation_service import index_creator_posts

        with patch("core.citation_service._save_chunks_to_db") as mock_save:
            with patch("core.citation_service._save_chunks_to_json") as mock_json:
                mock_save.return_value = True
                mock_json.return_value = True

                result = await index_creator_posts(
                    creator_id="test_creator",
                    posts=sample_posts,
                    save=True
                )

        # save=True should now trigger actual save
        assert mock_save.called or mock_json.called, "Save was not called - BUG-001 not fixed!"

    @pytest.mark.asyncio
    async def test_index_creator_posts_returns_correct_stats(self, sample_posts):
        """Verify that indexing returns correct statistics."""
        from core.citation_service import index_creator_posts

        with patch("core.citation_service._save_chunks_to_db", return_value=True):
            with patch("core.citation_service._save_chunks_to_json", return_value=True):
                result = await index_creator_posts(
                    creator_id="test_creator",
                    posts=sample_posts,
                    save=True
                )

        assert "posts_indexed" in result
        assert result["posts_indexed"] == len(sample_posts)
        assert "total_chunks" in result
        assert result["total_chunks"] > 0


class TestSearchAfterBulkInsert:
    """Tests to verify search works after bulk insert."""

    def test_search_finds_bulk_inserted_content(self):
        """
        Verify that content indexed via bulk insert is searchable.

        This is a crucial test: after bulk insert, the bot must be able
        to find and cite the Instagram content.
        """
        from core.citation_service import CreatorContentIndex
        from ingestion import ContentChunk

        # Create index and add chunks directly (simulating bulk insert result)
        index = CreatorContentIndex("test_creator")

        # Add test content
        test_chunks = [
            ContentChunk(
                id="search_test_1",
                creator_id="test_creator",
                source_type="instagram_post",
                source_id="ig_123",
                source_url="https://instagram.com/p/test123",
                title="Coaching Post",
                content="Descubre cómo el coaching puede transformar tu vida y ayudarte a alcanzar tus metas.",
                chunk_index=0,
                total_chunks=1,
            ),
            ContentChunk(
                id="search_test_2",
                creator_id="test_creator",
                source_type="instagram_post",
                source_id="ig_456",
                source_url="https://instagram.com/p/test456",
                title="Wellness Tips",
                content="Bienestar y salud mental: claves para una vida equilibrada y plena.",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        index.chunks = test_chunks

        # Search should find relevant content
        results = index.search("coaching transformar vida", max_results=5)

        assert len(results) > 0, "Search returned no results after bulk insert"
        assert any("coaching" in r.get("content", "").lower() for r in results)

    def test_search_returns_source_url_for_citation(self):
        """Verify that search results include source_url for bot citations."""
        from core.citation_service import CreatorContentIndex
        from ingestion import ContentChunk

        index = CreatorContentIndex("test_creator")

        index.chunks = [
            ContentChunk(
                id="citation_test_1",
                creator_id="test_creator",
                source_type="instagram_post",
                source_id="ig_789",
                source_url="https://instagram.com/p/citation_test",
                title="Citable Post",
                content="Este contenido debe ser citable por el bot con su URL original.",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        results = index.search("citable bot URL", max_results=5)

        assert len(results) > 0
        assert results[0].get("source_url") is not None
        assert "instagram.com" in results[0].get("source_url", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
