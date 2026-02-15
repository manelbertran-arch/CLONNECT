"""
Tests for semantic memory with pgvector.

Tests the SemanticMemoryPgvector class which provides long-term
conversation memory using PostgreSQL with pgvector for semantic search.
"""

from unittest.mock import patch, MagicMock
from datetime import datetime


class TestSemanticMemoryPgvector:
    """Tests for SemanticMemoryPgvector class"""

    def setup_method(self):
        """Setup before each test"""
        # Clear the cache before each test
        from core.semantic_memory_pgvector import clear_memory_cache
        clear_memory_cache()

    def test_add_message_short_content_skipped(self):
        """Short messages (< 20 chars) should be skipped"""
        with patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', True):
            from core.semantic_memory_pgvector import SemanticMemoryPgvector

            memory = SemanticMemoryPgvector(
                creator_id="test_creator",
                follower_id="test_follower"
            )

            # Short message should return False (not saved)
            result = memory.add_message("user", "Hola")
            assert result == False

            result = memory.add_message("user", "ok")
            assert result == False

    def test_add_message_disabled_returns_false(self):
        """When disabled, add_message should return False"""
        with patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', False):
            from core.semantic_memory_pgvector import SemanticMemoryPgvector

            memory = SemanticMemoryPgvector(
                creator_id="test_creator",
                follower_id="test_follower"
            )

            result = memory.add_message("user", "This is a long message that should be stored")
            assert result == False

    def test_search_disabled_returns_empty(self):
        """When disabled, search should return empty list"""
        with patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', False):
            from core.semantic_memory_pgvector import SemanticMemoryPgvector

            memory = SemanticMemoryPgvector(
                creator_id="test_creator",
                follower_id="test_follower"
            )

            results = memory.search("test query")
            assert results == []

    def test_get_context_for_response_disabled_returns_empty(self):
        """When disabled, get_context_for_response should return empty string"""
        with patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', False):
            from core.semantic_memory_pgvector import SemanticMemoryPgvector

            memory = SemanticMemoryPgvector(
                creator_id="test_creator",
                follower_id="test_follower"
            )

            context = memory.get_context_for_response("What about my business?")
            assert context == ""

    @patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', True)
    def test_add_message_generates_embedding_and_stores(self):
        """add_message should generate embedding and store in DB"""
        mock_embedding = [0.1] * 1536  # Mock 1536-dim embedding

        with patch('core.semantic_memory_pgvector.generate_embedding', return_value=mock_embedding) as mock_gen:
            with patch('core.semantic_memory_pgvector.get_db_session') as mock_db_ctx:
                mock_db = MagicMock()
                mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
                mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

                from core.semantic_memory_pgvector import SemanticMemoryPgvector
                memory = SemanticMemoryPgvector(
                    creator_id="test_creator",
                    follower_id="test_follower"
                )

                result = memory.add_message(
                    "user",
                    "I have an online clothing store that sells vintage items"
                )

                assert result == True
                mock_gen.assert_called_once()
                mock_db.execute.assert_called_once()
                mock_db.commit.assert_called_once()

    @patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', True)
    def test_search_returns_relevant_results(self):
        """search should return matching results from DB"""
        mock_embedding = [0.1] * 1536

        # Mock DB results
        mock_row = MagicMock()
        mock_row.content = "I have an online clothing store"
        mock_row.message_role = "user"
        mock_row.similarity = 0.85
        mock_row.created_at = datetime.now()
        mock_row.msg_metadata = {"intent": "question"}

        with patch('core.semantic_memory_pgvector.generate_embedding', return_value=mock_embedding):
            with patch('core.semantic_memory_pgvector.get_db_session') as mock_db_ctx:
                mock_db = MagicMock()
                mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
                mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_db.execute.return_value = [mock_row]

                from core.semantic_memory_pgvector import SemanticMemoryPgvector
                memory = SemanticMemoryPgvector(
                    creator_id="test_creator",
                    follower_id="test_follower"
                )

                results = memory.search("tell me about your business")

                assert len(results) == 1
                assert results[0]["content"] == "I have an online clothing store"
                assert results[0]["role"] == "user"
                assert results[0]["similarity"] == 0.85

    @patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', True)
    def test_get_context_for_response_formats_correctly(self):
        """get_context_for_response should format context string correctly"""
        mock_embedding = [0.1] * 1536

        mock_row = MagicMock()
        mock_row.content = "I sell vintage clothing online"
        mock_row.message_role = "user"
        mock_row.similarity = 0.85
        mock_row.created_at = datetime.now()
        mock_row.msg_metadata = {}

        with patch('core.semantic_memory_pgvector.generate_embedding', return_value=mock_embedding):
            with patch('core.semantic_memory_pgvector.get_db_session') as mock_db_ctx:
                mock_db = MagicMock()
                mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
                mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_db.execute.return_value = [mock_row]

                from core.semantic_memory_pgvector import SemanticMemoryPgvector
                memory = SemanticMemoryPgvector(
                    creator_id="test_creator",
                    follower_id="test_follower"
                )

                context = memory.get_context_for_response("What do you sell?")

                assert "CONTEXTO HISTORICO RELEVANTE:" in context
                assert "Usuario dijo:" in context
                assert "vintage clothing" in context

    @patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', True)
    def test_get_context_excludes_recent_messages(self):
        """get_context_for_response should exclude messages already in recent_messages"""
        mock_embedding = [0.1] * 1536

        mock_row = MagicMock()
        mock_row.content = "I sell vintage clothing online"
        mock_row.message_role = "user"
        mock_row.similarity = 0.85
        mock_row.created_at = datetime.now()
        mock_row.msg_metadata = {}

        with patch('core.semantic_memory_pgvector.generate_embedding', return_value=mock_embedding):
            with patch('core.semantic_memory_pgvector.get_db_session') as mock_db_ctx:
                mock_db = MagicMock()
                mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
                mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_db.execute.return_value = [mock_row]

                from core.semantic_memory_pgvector import SemanticMemoryPgvector
                memory = SemanticMemoryPgvector(
                    creator_id="test_creator",
                    follower_id="test_follower"
                )

                # Include the same message in recent_messages
                recent = [{"content": "I sell vintage clothing online"}]
                context = memory.get_context_for_response(
                    "What do you sell?",
                    recent_messages=recent
                )

                # Should return empty since all results are in recent
                assert context == ""


class TestSemanticMemoryFactory:
    """Tests for factory function"""

    def setup_method(self):
        """Setup before each test"""
        from core.semantic_memory_pgvector import clear_memory_cache
        clear_memory_cache()

    def test_get_semantic_memory_returns_same_instance(self):
        """get_semantic_memory should return same instance for same creator+follower"""
        from core.semantic_memory_pgvector import get_semantic_memory

        mem1 = get_semantic_memory("creator1", "follower1")
        mem2 = get_semantic_memory("creator1", "follower1")

        assert mem1 is mem2

    def test_get_semantic_memory_returns_different_instances(self):
        """get_semantic_memory should return different instances for different followers"""
        from core.semantic_memory_pgvector import get_semantic_memory

        mem1 = get_semantic_memory("creator1", "follower1")
        mem2 = get_semantic_memory("creator1", "follower2")

        assert mem1 is not mem2

    def test_clear_memory_cache_clears_instances(self):
        """clear_memory_cache should clear all cached instances"""
        from core.semantic_memory_pgvector import get_semantic_memory, clear_memory_cache

        mem1 = get_semantic_memory("creator1", "follower1")
        clear_memory_cache()
        mem2 = get_semantic_memory("creator1", "follower1")

        # After clearing, should be a new instance
        assert mem1 is not mem2


class TestGetMemoryStats:
    """Tests for get_memory_stats function"""

    def test_stats_disabled_returns_disabled_flag(self):
        """get_memory_stats should return enabled=False when disabled"""
        with patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', False):
            from core.semantic_memory_pgvector import get_memory_stats

            stats = get_memory_stats()
            assert stats == {"enabled": False}

    @patch('core.semantic_memory_pgvector.ENABLE_SEMANTIC_MEMORY_PGVECTOR', True)
    def test_stats_returns_counts(self):
        """get_memory_stats should return embedding counts"""
        mock_row = MagicMock()
        mock_row.total = 100
        mock_row.followers = 10

        with patch('core.semantic_memory_pgvector.get_db_session') as mock_db_ctx:
            mock_db = MagicMock()
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = mock_row
            mock_db.execute.return_value = mock_result

            from core.semantic_memory_pgvector import get_memory_stats

            stats = get_memory_stats(creator_id="test_creator")

            assert stats["enabled"] == True
            assert stats["total_embeddings"] == 100
            assert stats["followers"] == 10
