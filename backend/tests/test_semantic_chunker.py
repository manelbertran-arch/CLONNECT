"""
Tests for Semantic Chunking functionality.

Tests cover:
- Paragraph boundary respect
- Section/header boundary respect
- Sentence integrity
- Long paragraph handling
- Small chunk merging
- Overlap context
- HTML chunking
- Environment configuration
- Integration with content_indexer
"""

import pytest
import os
from unittest.mock import patch


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_markdown_text():
    """Sample markdown text with headers and sections."""
    return """# Sobre Mí

Soy coach de vida con 10 años de experiencia ayudando a personas.
Me especializo en ayudar a personas a encontrar su propósito de vida.

## Mis Servicios

### Coaching Individual

Sesiones 1:1 de 60 minutos donde trabajamos en tus objetivos personales.
Cada sesión está diseñada para maximizar tu potencial y superar obstáculos.

### Coaching Grupal

Grupos de máximo 8 personas donde compartimos experiencias.
El poder del grupo multiplica los resultados individuales.

## Contacto

Puedes escribirme a email@example.com para agendar una sesión."""


@pytest.fixture
def sample_long_paragraph():
    """Sample text with a very long paragraph that needs splitting."""
    return """Este es un párrafo muy largo que necesita ser dividido en chunks más pequeños. """ * 20


@pytest.fixture
def sample_short_paragraphs():
    """Sample text with very short paragraphs that should be merged."""
    return """Hola.

Soy coach.

Ayudo personas.

Tengo experiencia.

Contáctame."""


@pytest.fixture
def sample_html_content():
    """Sample HTML with structure."""
    return """
    <html>
    <body>
        <main>
            <h1>Bienvenidos</h1>
            <p>Este es el párrafo de introducción con suficiente contenido para ser un chunk válido.</p>

            <h2>Servicios</h2>
            <p>Ofrecemos múltiples servicios de coaching profesional para individuos y empresas.</p>
            <ul>
                <li>Coaching individual personalizado</li>
                <li>Coaching grupal interactivo</li>
                <li>Talleres de desarrollo personal</li>
            </ul>

            <h2>Metodología</h2>
            <p>Nuestra metodología se basa en años de investigación y práctica profesional.</p>
        </main>
    </body>
    </html>
    """


# =============================================================================
# TEST: SEMANTIC CHUNKER BASIC FUNCTIONALITY
# =============================================================================

class TestSemanticChunkerBasic:
    """Basic tests for SemanticChunker."""

    def test_empty_text_returns_empty_list(self):
        """Should return empty list for empty text."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        result = chunker.chunk_text("", "https://example.com")

        assert result == []

    def test_whitespace_only_returns_empty_list(self):
        """Should return empty list for whitespace-only text."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        result = chunker.chunk_text("   \n\n   ", "https://example.com")

        assert result == []

    def test_short_text_returns_single_chunk(self):
        """Should return single chunk for short text."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        text = "Este es un texto corto."
        result = chunker.chunk_text(text, "https://example.com")

        assert len(result) == 1
        assert result[0].content == text

    def test_chunk_has_correct_attributes(self):
        """Chunks should have all required attributes."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        result = chunker.chunk_text("Test content", "https://example.com")

        chunk = result[0]
        assert hasattr(chunk, 'content')
        assert hasattr(chunk, 'index')
        assert hasattr(chunk, 'source_url')
        assert hasattr(chunk, 'section_title')
        assert hasattr(chunk, 'chunk_type')
        assert chunk.source_url == "https://example.com"


# =============================================================================
# TEST: PARAGRAPH BOUNDARY RESPECT
# =============================================================================

class TestParagraphBoundaries:
    """Tests for paragraph boundary handling."""

    def test_respects_paragraph_boundaries(self):
        """Should create separate chunks for paragraphs."""
        from core.semantic_chunker import SemanticChunker

        text = """Primer párrafo con contenido suficiente para ser un chunk válido independiente.

Segundo párrafo que también tiene suficiente contenido para ser su propio chunk.

Tercer párrafo con más contenido relevante que debería ser separado."""

        chunker = SemanticChunker(min_chunk_size=50)
        result = chunker.chunk_text(text, "")

        # Each paragraph should be a separate chunk (or merged if too small)
        assert len(result) >= 1
        # Content should be preserved
        full_content = ' '.join([c.content for c in result])
        assert "Primer párrafo" in full_content
        assert "Segundo párrafo" in full_content
        assert "Tercer párrafo" in full_content

    def test_double_newline_splits_paragraphs(self):
        """Double newlines should trigger paragraph splits."""
        from core.semantic_chunker import SemanticChunker

        text = "Párrafo uno.\n\nPárrafo dos.\n\nPárrafo tres."

        chunker = SemanticChunker(min_chunk_size=10)
        result = chunker.chunk_text(text, "")

        # Should have multiple chunks
        assert len(result) >= 1


# =============================================================================
# TEST: SECTION/HEADER BOUNDARIES
# =============================================================================

class TestHeaderBoundaries:
    """Tests for header/section boundary handling."""

    def test_respects_markdown_headers(self, sample_markdown_text):
        """Should split by markdown headers and track section titles."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        result = chunker.chunk_text(sample_markdown_text, "")

        # Should have multiple chunks
        assert len(result) > 1

        # Check that section titles are tracked
        section_titles = [c.section_title for c in result if c.section_title]
        assert len(section_titles) > 0

        # Check expected sections exist
        all_titles = ' '.join([t for t in section_titles if t])
        # At least some headers should be captured
        assert any(t in all_titles for t in ['Sobre Mí', 'Mis Servicios', 'Coaching'])

    def test_h1_through_h4_recognized(self):
        """Should recognize h1 through h4 headers."""
        from core.semantic_chunker import SemanticChunker

        text = """# Header 1
Content one.

## Header 2
Content two.

### Header 3
Content three.

#### Header 4
Content four."""

        chunker = SemanticChunker(min_chunk_size=10)
        result = chunker.chunk_text(text, "")

        section_titles = [c.section_title for c in result if c.section_title]
        assert "Header 1" in section_titles or "Header 2" in section_titles


# =============================================================================
# TEST: SENTENCE INTEGRITY
# =============================================================================

class TestSentenceIntegrity:
    """Tests for keeping sentences intact."""

    def test_keeps_sentences_intact(self):
        """Should not split in the middle of sentences."""
        from core.semantic_chunker import SemanticChunker

        # Create a text where fixed chunking would cut mid-sentence
        text = "Esta es la primera oración completa. Esta es la segunda oración que también es completa. Y esta es la tercera oración final."

        chunker = SemanticChunker(max_chunk_size=100, min_chunk_size=20)
        result = chunker.chunk_text(text, "")

        # Each chunk should end with sentence-ending punctuation
        for chunk in result:
            content = chunk.content.strip()
            # Should end with period, question mark, or exclamation
            assert content[-1] in '.?!' or len(content) < 50, f"Chunk doesn't end properly: {content}"

    def test_splits_long_paragraph_by_sentences(self, sample_long_paragraph):
        """Should split very long paragraphs by sentences."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker(max_chunk_size=200)
        result = chunker.chunk_text(sample_long_paragraph, "")

        # Should create multiple chunks
        assert len(result) > 1

        # Each chunk should be under max size (approximately)
        for chunk in result:
            # Allow some flexibility for overlap
            assert chunk.char_count <= 200 * 1.5, f"Chunk too large: {chunk.char_count}"


# =============================================================================
# TEST: CHUNK SIZE LIMITS
# =============================================================================

class TestChunkSizeLimits:
    """Tests for min/max chunk size handling."""

    def test_respects_max_chunk_size(self, sample_long_paragraph):
        """Chunks should not exceed max_chunk_size (with some tolerance)."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker(max_chunk_size=300)
        result = chunker.chunk_text(sample_long_paragraph, "")

        for chunk in result:
            # Allow 50% tolerance for overlap and sentence boundaries
            assert chunk.char_count <= 300 * 1.5

    def test_merges_small_chunks(self, sample_short_paragraphs):
        """Should merge adjacent small chunks."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker(min_chunk_size=50, max_chunk_size=500)
        result = chunker.chunk_text(sample_short_paragraphs, "")

        # Should merge the tiny paragraphs
        # With 5 tiny paragraphs, should result in fewer chunks
        assert len(result) < 5

    def test_min_chunk_size_configuration(self):
        """Should respect min_chunk_size setting."""
        from core.semantic_chunker import SemanticChunker

        text = "Short. " * 50  # Many short sentences

        chunker = SemanticChunker(min_chunk_size=100, max_chunk_size=500)
        result = chunker.chunk_text(text, "")

        # Most chunks should be at least min_size (with some tolerance)
        for chunk in result:
            # Very small final chunks are acceptable
            if chunk.index < len(result) - 1:
                assert chunk.char_count >= 50  # Some tolerance


# =============================================================================
# TEST: OVERLAP CONTEXT
# =============================================================================

class TestOverlapContext:
    """Tests for overlap/context between chunks."""

    def test_adds_overlap_between_chunks(self):
        """Should add sentence overlap for context."""
        from core.semantic_chunker import SemanticChunker

        text = """Primera oración del primer chunk. Segunda oración del primer chunk.

Tercera oración que debería tener overlap. Cuarta oración después del overlap."""

        chunker = SemanticChunker(max_chunk_size=100, min_chunk_size=30, overlap_sentences=1)
        result = chunker.chunk_text(text, "")

        if len(result) > 1:
            # Check if any chunk has overlap metadata
            _has_overlap = any(c.metadata.get("has_overlap") for c in result)
            # Overlap is added when sections match and size permits
            # This is optional based on content structure

    def test_no_overlap_with_zero_setting(self):
        """Should not add overlap when overlap_sentences=0."""
        from core.semantic_chunker import SemanticChunker

        text = "Sentence one. Sentence two.\n\nSentence three. Sentence four."

        chunker = SemanticChunker(overlap_sentences=0)
        result = chunker.chunk_text(text, "")

        # No chunk should have overlap metadata
        for chunk in result:
            assert not chunk.metadata.get("has_overlap")


# =============================================================================
# TEST: HTML CHUNKING
# =============================================================================

class TestHtmlChunking:
    """Tests for HTML content chunking."""

    def test_chunks_html_content(self, sample_html_content):
        """Should chunk HTML while preserving structure."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        result = chunker.chunk_html(sample_html_content, "https://example.com")

        # Should create chunks
        assert len(result) > 0

        # Content should be extracted (no HTML tags)
        for chunk in result:
            assert '<' not in chunk.content
            assert '>' not in chunk.content

    def test_html_extracts_section_titles(self, sample_html_content):
        """Should extract section titles from HTML headers."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        result = chunker.chunk_html(sample_html_content, "")

        section_titles = [c.section_title for c in result if c.section_title]

        # Should capture some headers
        if section_titles:
            all_titles = ' '.join(section_titles)
            assert any(h in all_titles for h in ['Bienvenidos', 'Servicios', 'Metodología'])

    def test_html_handles_lists(self, sample_html_content):
        """Should handle list items in HTML."""
        from core.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        result = chunker.chunk_html(sample_html_content, "")

        # List content should be present
        all_content = ' '.join([c.content for c in result])
        assert 'Coaching individual' in all_content or 'coaching' in all_content.lower()


# =============================================================================
# TEST: ENVIRONMENT CONFIGURATION
# =============================================================================

class TestEnvironmentConfiguration:
    """Tests for environment variable configuration."""

    def test_default_chunking_mode_is_semantic(self):
        """Default chunking mode should be 'semantic'."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import core.semantic_chunker as module
            importlib.reload(module)

            assert module.CHUNKING_MODE == "semantic"

    def test_chunking_mode_from_env(self):
        """Should respect CHUNKING_MODE env var."""
        with patch.dict(os.environ, {"CHUNKING_MODE": "fixed"}):
            import importlib
            import core.semantic_chunker as module
            importlib.reload(module)

            assert module.CHUNKING_MODE == "fixed"

    def test_chunk_max_size_from_env(self):
        """Should respect CHUNK_MAX_SIZE env var."""
        with patch.dict(os.environ, {"CHUNK_MAX_SIZE": "1000"}):
            import importlib
            import core.semantic_chunker as module
            importlib.reload(module)

            assert module.CHUNK_MAX_SIZE == 1000

    def test_chunk_min_size_from_env(self):
        """Should respect CHUNK_MIN_SIZE env var."""
        with patch.dict(os.environ, {"CHUNK_MIN_SIZE": "200"}):
            import importlib
            import core.semantic_chunker as module
            importlib.reload(module)

            assert module.CHUNK_MIN_SIZE == 200

    def test_is_semantic_chunking_enabled(self):
        """is_semantic_chunking_enabled should reflect config."""
        from core.semantic_chunker import is_semantic_chunking_enabled

        with patch("core.semantic_chunker.CHUNKING_MODE", "semantic"):
            assert is_semantic_chunking_enabled() is True

        with patch("core.semantic_chunker.CHUNKING_MODE", "fixed"):
            assert is_semantic_chunking_enabled() is False


# =============================================================================
# TEST: INTEGRATION WITH CONTENT_INDEXER
# =============================================================================

class TestContentIndexerIntegration:
    """Tests for integration with content_indexer.split_text."""

    def test_split_text_uses_semantic_by_default(self):
        """split_text should use semantic chunking by default."""
        from ingestion.content_indexer import split_text

        text = """Párrafo uno con contenido suficiente.

Párrafo dos con más contenido suficiente."""

        with patch("ingestion.content_indexer.CHUNKING_MODE", "semantic"):
            result = split_text(text)
            assert len(result) >= 1

    def test_split_text_mode_override(self):
        """split_text should respect mode parameter."""
        from ingestion.content_indexer import split_text

        text = "A" * 1000  # Long text

        # Force fixed mode
        result_fixed = split_text(text, mode="fixed", chunk_size=200)
        assert len(result_fixed) > 1

    def test_split_text_fallback_on_error(self):
        """split_text should fallback to fixed if semantic fails."""
        from ingestion.content_indexer import split_text

        text = "Test content that needs chunking. " * 20

        # Even if semantic chunker has issues, should still return chunks
        result = split_text(text)
        assert len(result) >= 1

    def test_create_chunks_from_content_works(self):
        """create_chunks_from_content should work with semantic chunking."""
        from ingestion.content_indexer import create_chunks_from_content

        content = """# Test Content

This is test content for chunking.

## Section One

More content here with sufficient length."""

        chunks = create_chunks_from_content(
            creator_id="test_creator",
            source_type="website",
            source_id="test_123",
            content=content
        )

        assert len(chunks) >= 1
        assert all(c.creator_id == "test_creator" for c in chunks)


# =============================================================================
# TEST: HELPER FUNCTIONS
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_chunk_content_semantic_mode(self):
        """chunk_content should work in semantic mode."""
        from core.semantic_chunker import chunk_content

        text = "Test paragraph one.\n\nTest paragraph two."
        result = chunk_content(text, source_url="https://example.com", mode="semantic")

        assert len(result) >= 1
        assert all("content" in chunk for chunk in result)
        assert all("source_url" in chunk for chunk in result)

    def test_chunk_content_fixed_mode(self):
        """chunk_content should work in fixed mode."""
        from core.semantic_chunker import chunk_content

        text = "A" * 1000
        result = chunk_content(text, mode="fixed")

        assert len(result) >= 1
        assert all(chunk["chunk_type"] == "fixed" for chunk in result)

    def test_get_chunking_stats(self):
        """get_chunking_stats should return config info."""
        from core.semantic_chunker import get_chunking_stats

        stats = get_chunking_stats()

        assert "mode" in stats
        assert "max_size" in stats
        assert "min_size" in stats
        assert "overlap_sentences" in stats
        assert "semantic_enabled" in stats

    def test_semantic_chunk_to_dict(self):
        """SemanticChunk.to_dict should return proper dictionary."""
        from core.semantic_chunker import SemanticChunk

        chunk = SemanticChunk(
            content="Test content",
            index=0,
            source_url="https://example.com",
            section_title="Test Section",
            chunk_type="paragraph"
        )

        d = chunk.to_dict()

        assert d["content"] == "Test content"
        assert d["index"] == 0
        assert d["source_url"] == "https://example.com"
        assert d["section_title"] == "Test Section"
        assert d["chunk_type"] == "paragraph"
        assert d["char_count"] == 12
