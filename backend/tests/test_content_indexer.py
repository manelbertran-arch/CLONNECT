"""Tests para Content Indexer."""

import pytest
from ingestion.content_indexer import (
    split_text,
    generate_chunk_id,
    create_chunks_from_content,
    ContentChunk
)


class TestSplitText:
    """Tests para la funcion split_text."""

    def test_empty_text(self):
        assert split_text("") == []

    def test_none_text(self):
        assert split_text(None) == []

    def test_short_text(self):
        text = "Este es un texto corto."
        result = split_text(text, chunk_size=500)
        assert len(result) == 1
        assert result[0] == text

    def test_long_text_splits(self):
        text = "Primera oracion. " * 100  # Texto largo
        result = split_text(text, chunk_size=100, overlap=20)
        assert len(result) > 1

    def test_respects_sentence_boundaries(self):
        text = "Primera oracion completa. Segunda oracion que sigue. Tercera oracion final."
        result = split_text(text, chunk_size=40, overlap=10)
        # Deberia intentar cortar despues de puntos
        assert len(result) >= 1

    def test_overlap_works(self):
        text = "ABCDEFGHIJ" * 20  # 200 caracteres
        result = split_text(text, chunk_size=50, overlap=10)
        # Con overlap, el contenido se solapa entre chunks
        assert len(result) > 1

    def test_exact_chunk_size(self):
        text = "A" * 500
        result = split_text(text, chunk_size=500)
        assert len(result) == 1

    def test_just_over_chunk_size(self):
        text = "A" * 501
        result = split_text(text, chunk_size=500, overlap=50)
        assert len(result) == 2


class TestCreateChunks:
    """Tests para create_chunks_from_content."""

    def test_creates_chunks(self):
        chunks = create_chunks_from_content(
            creator_id="creator_123",
            source_type="instagram_post",
            source_id="post_456",
            content="Este es el contenido del post. " * 50,
            title="Mi post",
            source_url="https://instagram.com/p/abc123"
        )

        assert len(chunks) > 0
        assert all(isinstance(c, ContentChunk) for c in chunks)
        assert all(c.creator_id == "creator_123" for c in chunks)
        assert all(c.source_type == "instagram_post" for c in chunks)

    def test_chunk_ids_unique(self):
        chunks = create_chunks_from_content(
            creator_id="creator_123",
            source_type="instagram_post",
            source_id="post_456",
            content="Contenido largo. " * 100
        )

        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))  # Todos unicos

    def test_chunk_indices_sequential(self):
        chunks = create_chunks_from_content(
            creator_id="creator_123",
            source_type="instagram_post",
            source_id="post_456",
            content="Contenido largo. " * 100
        )

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)

    def test_metadata_preserved(self):
        metadata = {"likes": 100, "comments": 50}
        chunks = create_chunks_from_content(
            creator_id="creator_123",
            source_type="instagram_post",
            source_id="post_456",
            content="Contenido corto.",
            metadata=metadata
        )

        assert len(chunks) == 1
        assert chunks[0].metadata == metadata

    def test_empty_content(self):
        chunks = create_chunks_from_content(
            creator_id="creator_123",
            source_type="instagram_post",
            source_id="post_456",
            content=""
        )

        assert len(chunks) == 0


class TestGenerateChunkId:
    """Tests para generate_chunk_id."""

    def test_deterministic(self):
        id1 = generate_chunk_id("c1", "post", "p1", 0)
        id2 = generate_chunk_id("c1", "post", "p1", 0)
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = generate_chunk_id("c1", "post", "p1", 0)
        id2 = generate_chunk_id("c1", "post", "p1", 1)
        id3 = generate_chunk_id("c2", "post", "p1", 0)
        assert id1 != id2
        assert id2 != id3
        assert id1 != id3

    def test_id_length(self):
        id1 = generate_chunk_id("c1", "post", "p1", 0)
        assert len(id1) == 16

    def test_id_is_hex(self):
        id1 = generate_chunk_id("c1", "post", "p1", 0)
        # Should be valid hex
        int(id1, 16)
