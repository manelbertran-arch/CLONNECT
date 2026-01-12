"""Tests para Content Citation."""

import pytest
from datetime import datetime, timedelta
from ingestion.content_citation import (
    Citation,
    CitationContext,
    ContentType,
    ContentCitationEngine,
    extract_topics_from_query,
    format_citation_for_response,
    should_cite_content
)


class TestCitation:
    """Tests para Citation dataclass."""

    def test_create_citation(self):
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="post_123",
            source_url="https://instagram.com/p/abc/",
            title="Mi post sobre fitness",
            excerpt="En este post hablo sobre rutinas de ejercicio...",
            relevance_score=0.85
        )

        assert citation.content_type == ContentType.INSTAGRAM_POST
        assert citation.relevance_score == 0.85
        assert citation.source_id == "post_123"

    def test_to_natural_reference_casual(self):
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="contenido",
            relevance_score=0.8
        )

        ref = citation.to_natural_reference(style="casual")
        assert "post" in ref.lower()

    def test_to_natural_reference_with_recent_date(self):
        recent_date = datetime.utcnow() - timedelta(days=3)
        citation = Citation(
            content_type=ContentType.INSTAGRAM_REEL,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="contenido",
            relevance_score=0.8,
            published_date=recent_date
        )

        ref = citation.to_natural_reference(style="casual")
        assert "dias" in ref

    def test_to_natural_reference_with_old_date(self):
        old_date = datetime.utcnow() - timedelta(days=100)
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="contenido",
            relevance_score=0.8,
            published_date=old_date
        )

        ref = citation.to_natural_reference(style="casual")
        assert "tiempo" in ref

    def test_to_natural_reference_youtube(self):
        citation = Citation(
            content_type=ContentType.YOUTUBE_VIDEO,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="contenido",
            relevance_score=0.8
        )

        ref = citation.to_natural_reference(style="casual")
        assert "video" in ref.lower() or "youtube" in ref.lower()

    def test_to_natural_reference_podcast(self):
        citation = Citation(
            content_type=ContentType.PODCAST_EPISODE,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="contenido",
            relevance_score=0.8
        )

        ref = citation.to_natural_reference(style="casual")
        assert "podcast" in ref.lower()

    def test_to_natural_reference_formal(self):
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="123",
            source_url=None,
            title="Guia de nutricion",
            excerpt="contenido",
            relevance_score=0.8
        )

        ref = citation.to_natural_reference(style="formal")
        assert "Guia de nutricion" in ref

    def test_to_natural_reference_minimal(self):
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="contenido",
            relevance_score=0.8
        )

        ref = citation.to_natural_reference(style="minimal")
        assert "explique" in ref


class TestCitationContext:
    """Tests para CitationContext."""

    def test_has_relevant_content_true(self):
        citations = [
            Citation(
                content_type=ContentType.INSTAGRAM_POST,
                source_id="1",
                source_url=None,
                title=None,
                excerpt="test",
                relevance_score=0.7
            )
        ]

        context = CitationContext(query="test", citations=citations)
        assert context.has_relevant_content(min_score=0.5) == True

    def test_has_relevant_content_false(self):
        citations = [
            Citation(
                content_type=ContentType.INSTAGRAM_POST,
                source_id="1",
                source_url=None,
                title=None,
                excerpt="test",
                relevance_score=0.7
            )
        ]

        context = CitationContext(query="test", citations=citations)
        assert context.has_relevant_content(min_score=0.9) == False

    def test_get_top_citations(self):
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "a", 0.5),
            Citation(ContentType.INSTAGRAM_POST, "2", None, None, "b", 0.9),
            Citation(ContentType.INSTAGRAM_POST, "3", None, None, "c", 0.7),
        ]

        context = CitationContext(query="test", citations=citations)
        top = context.get_top_citations(2)

        assert len(top) == 2
        assert top[0].relevance_score == 0.9
        assert top[1].relevance_score == 0.7

    def test_get_top_citations_default(self):
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "a", 0.5),
            Citation(ContentType.INSTAGRAM_POST, "2", None, None, "b", 0.9),
        ]

        context = CitationContext(query="test", citations=citations, max_citations=1)
        top = context.get_top_citations()

        assert len(top) == 1
        assert top[0].relevance_score == 0.9

    def test_to_prompt_context(self):
        citations = [
            Citation(
                content_type=ContentType.INSTAGRAM_POST,
                source_id="123",
                source_url="https://instagram.com/p/abc/",
                title="Post sobre ayuno",
                excerpt="En este post explico los beneficios del ayuno intermitente...",
                relevance_score=0.85
            )
        ]

        context = CitationContext(query="ayuno", citations=citations)
        prompt = context.to_prompt_context()

        assert "CONTENIDO RELEVANTE" in prompt
        assert "Post sobre ayuno" in prompt
        assert "85%" in prompt
        assert "INSTRUCCIONES OBLIGATORIAS PARA CITAR" in prompt

    def test_empty_context(self):
        context = CitationContext(query="test", citations=[])
        assert context.has_relevant_content() == False
        assert context.to_prompt_context() == ""


class TestExtractTopicsFromQuery:
    """Tests para extract_topics_from_query."""

    def test_extracts_topics(self):
        query = "Que opinas sobre el ayuno intermitente?"
        topics = extract_topics_from_query(query)

        assert "ayuno" in topics
        assert "intermitente" in topics

    def test_removes_stopwords(self):
        query = "el la los las de del a en con por para"
        topics = extract_topics_from_query(query)

        assert len(topics) == 0

    def test_removes_short_words(self):
        query = "yo tu el a y o"
        topics = extract_topics_from_query(query)

        assert len(topics) == 0

    def test_handles_empty_query(self):
        topics = extract_topics_from_query("")
        assert topics == []

    def test_preserves_meaningful_words(self):
        query = "rutina ejercicios gimnasio"
        topics = extract_topics_from_query(query)

        assert "rutina" in topics
        assert "ejercicios" in topics
        assert "gimnasio" in topics


class TestFormatCitationForResponse:
    """Tests para format_citation_for_response."""

    def test_basic_format(self):
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="Mi experiencia con el ayuno",
            relevance_score=0.8
        )

        formatted = format_citation_for_response(citation)
        assert len(formatted) > 0

    def test_with_excerpt(self):
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="Mi experiencia con el ayuno intermitente ha sido increible",
            relevance_score=0.8
        )

        formatted = format_citation_for_response(citation, include_excerpt=True)
        assert "ayuno" in formatted.lower()
        assert "donde" in formatted

    def test_long_excerpt_truncated(self):
        citation = Citation(
            content_type=ContentType.INSTAGRAM_POST,
            source_id="123",
            source_url=None,
            title=None,
            excerpt="A" * 200,
            relevance_score=0.8
        )

        formatted = format_citation_for_response(citation, include_excerpt=True)
        assert "..." in formatted


class TestShouldCiteContent:
    """Tests para should_cite_content."""

    def test_should_cite_with_question(self):
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "test", 0.8)
        ]
        context = CitationContext(query="Que opinas del ayuno?", citations=citations)

        assert should_cite_content("Que opinas del ayuno?", context) == True

    def test_should_cite_with_knowledge_indicator(self):
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "test", 0.8)
        ]
        context = CitationContext(query="explicame sobre nutricion", citations=citations)

        assert should_cite_content("explicame sobre nutricion", context) == True

    def test_should_not_cite_low_relevance(self):
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "test", 0.3)
        ]
        context = CitationContext(query="test?", citations=citations)

        assert should_cite_content("test?", context, min_relevance=0.6) == False

    def test_should_not_cite_empty(self):
        context = CitationContext(query="test", citations=[])
        assert should_cite_content("test", context) == False

    def test_should_not_cite_no_knowledge_query(self):
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "test", 0.8)
        ]
        context = CitationContext(query="hola buenos dias", citations=citations)

        assert should_cite_content("hola buenos dias", context) == False


class TestContentCitationEngine:
    """Tests para ContentCitationEngine."""

    def test_create_engine(self):
        engine = ContentCitationEngine()
        assert engine.vector_store is None
        assert engine.embeddings_model is None

    def test_create_engine_with_params(self):
        mock_store = object()
        mock_model = object()
        engine = ContentCitationEngine(vector_store=mock_store, embeddings_model=mock_model)

        assert engine.vector_store is mock_store
        assert engine.embeddings_model is mock_model

    def test_map_source_type_instagram(self):
        engine = ContentCitationEngine()

        assert engine._map_source_type('instagram_post') == ContentType.INSTAGRAM_POST
        assert engine._map_source_type('instagram_reel') == ContentType.INSTAGRAM_REEL

    def test_map_source_type_youtube(self):
        engine = ContentCitationEngine()

        assert engine._map_source_type('youtube') == ContentType.YOUTUBE_VIDEO
        assert engine._map_source_type('youtube_video') == ContentType.YOUTUBE_VIDEO

    def test_map_source_type_podcast(self):
        engine = ContentCitationEngine()

        assert engine._map_source_type('podcast') == ContentType.PODCAST_EPISODE
        assert engine._map_source_type('podcast_episode') == ContentType.PODCAST_EPISODE

    def test_map_source_type_pdf(self):
        engine = ContentCitationEngine()

        assert engine._map_source_type('pdf') == ContentType.PDF_EBOOK
        assert engine._map_source_type('ebook') == ContentType.PDF_EBOOK

    def test_map_source_type_unknown(self):
        engine = ContentCitationEngine()

        assert engine._map_source_type('unknown') == ContentType.INSTAGRAM_POST

    def test_create_citation_from_chunk(self):
        engine = ContentCitationEngine()

        chunk = {
            'source_type': 'instagram_reel',
            'source_id': 'reel_123',
            'source_url': 'https://instagram.com/reel/abc/',
            'title': 'Mi reel de fitness',
            'content': 'Contenido del reel sobre ejercicios...',
            'platform': 'instagram'
        }

        citation = engine.create_citation_from_chunk(chunk, relevance_score=0.75)

        assert citation.content_type == ContentType.INSTAGRAM_REEL
        assert citation.source_id == 'reel_123'
        assert citation.relevance_score == 0.75
        assert citation.platform == 'instagram'

    def test_create_citation_from_minimal_chunk(self):
        engine = ContentCitationEngine()

        chunk = {
            'content': 'Solo contenido'
        }

        citation = engine.create_citation_from_chunk(chunk)

        assert citation.content_type == ContentType.INSTAGRAM_POST
        assert citation.relevance_score == 0.5
        assert citation.excerpt == 'Solo contenido'


class TestContentType:
    """Tests para ContentType enum."""

    def test_all_types_exist(self):
        assert ContentType.INSTAGRAM_POST.value == "instagram_post"
        assert ContentType.INSTAGRAM_REEL.value == "instagram_reel"
        assert ContentType.YOUTUBE_VIDEO.value == "youtube_video"
        assert ContentType.PODCAST_EPISODE.value == "podcast_episode"
        assert ContentType.PDF_EBOOK.value == "pdf_ebook"
        assert ContentType.FAQ.value == "faq"
