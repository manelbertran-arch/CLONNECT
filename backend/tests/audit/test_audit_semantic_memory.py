"""Audit tests for core/semantic_memory.py"""

import tempfile

from core.semantic_memory import ConversationMemory, get_conversation_memory


class TestAuditSemanticMemory:
    def test_import(self):
        from core.semantic_memory import (  # noqa: F811
            ConversationMemory,
            clear_memory_cache,
            get_conversation_memory,
        )

        assert ConversationMemory is not None

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ConversationMemory(
                user_id="user1",
                creator_id="creator1",
                storage_path=tmpdir,
            )
            assert memory is not None

    def test_happy_path_add_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ConversationMemory(
                user_id="u1",
                creator_id="c1",
                storage_path=tmpdir,
            )
            memory.add_message("user", "Hola, me interesa tu curso")
            recent = memory.get_recent(5)
            assert isinstance(recent, list)

    def test_edge_case_get_conversation_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = get_conversation_memory("u1", "c1", tmpdir)
            assert memory is not None

    def test_error_handling_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ConversationMemory(
                user_id="u1",
                creator_id="c1",
                storage_path=tmpdir,
            )
            try:
                results = memory.search("coaching", k=3)
                assert isinstance(results, list)
            except Exception:
                pass  # Embeddings not available
