"""Audit tests for core/semantic_chunker.py"""

from core.semantic_chunker import SemanticChunk, SemanticChunker, get_semantic_chunker


class TestAuditSemanticChunker:
    def test_import(self):
        from core.semantic_chunker import (  # noqa: F811
            SemanticChunk,
            SemanticChunker,
            chunk_content,
        )

        assert SemanticChunker is not None

    def test_init(self):
        chunker = SemanticChunker()
        assert chunker is not None

    def test_happy_path_chunk_text(self):
        chunker = get_semantic_chunker()
        chunks = chunker.chunk_text("This is a test. Another sentence here. And a third one.")
        assert chunks is not None
        assert len(chunks) >= 1

    def test_edge_case_empty_text(self):
        chunker = SemanticChunker()
        chunks = chunker.chunk_text("")
        assert isinstance(chunks, list)

    def test_error_handling_chunk_to_dict(self):
        chunker = SemanticChunker()
        chunks = chunker.chunk_text("Hello world")
        if chunks:
            d = chunks[0].to_dict()
            assert isinstance(d, dict)
