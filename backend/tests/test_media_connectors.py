"""
Tests para Phase 2 Media Connectors - Transcriber, YouTube, Podcast, PDF.
"""

import pytest

# ============================================================================
# TESTS - TRANSCRIBER
# ============================================================================

class TestTranscriberDataclasses:
    """Tests para dataclasses del transcriber."""

    def test_transcript_segment_duration(self):
        """TranscriptSegment calcula duracion correctamente."""
        from ingestion.transcriber import TranscriptSegment

        segment = TranscriptSegment(
            text="Hola mundo",
            start_time=10.0,
            end_time=15.5,
            confidence=0.95
        )

        assert segment.duration == 5.5
        assert segment.text == "Hola mundo"
        assert segment.confidence == 0.95

    def test_transcript_segment_to_dict(self):
        """TranscriptSegment serializa correctamente."""
        from ingestion.transcriber import TranscriptSegment

        segment = TranscriptSegment(
            text="Test",
            start_time=0.0,
            end_time=1.0
        )

        result = segment.to_dict()
        assert result["text"] == "Test"
        assert result["start_time"] == 0.0
        assert result["end_time"] == 1.0

    def test_transcript_get_text_at_timestamp(self):
        """Transcript.get_text_at_timestamp retorna texto correcto."""
        from ingestion.transcriber import Transcript, TranscriptSegment

        transcript = Transcript(
            source_file="test.mp3",
            full_text="Hola mundo como estas",
            segments=[
                TranscriptSegment(text="Hola", start_time=0.0, end_time=1.0),
                TranscriptSegment(text="mundo", start_time=1.0, end_time=2.0),
                TranscriptSegment(text="como estas", start_time=2.0, end_time=4.0)
            ]
        )

        assert transcript.get_text_at_timestamp(0.5) == "Hola"
        assert transcript.get_text_at_timestamp(1.5) == "mundo"
        assert transcript.get_text_at_timestamp(3.0) == "como estas"
        assert transcript.get_text_at_timestamp(10.0) is None

    def test_transcript_to_dict(self):
        """Transcript serializa correctamente."""
        from ingestion.transcriber import Transcript

        transcript = Transcript(
            source_file="audio.mp3",
            full_text="Test audio",
            language="es",
            duration_seconds=120.0
        )

        result = transcript.to_dict()
        assert result["source_file"] == "audio.mp3"
        assert result["full_text"] == "Test audio"
        assert result["language"] == "es"
        assert result["duration_seconds"] == 120.0

    def test_audio_format_enum(self):
        """AudioFormat enum tiene valores correctos."""
        from ingestion.transcriber import AudioFormat

        assert AudioFormat.MP3.value == "mp3"
        assert AudioFormat.WAV.value == "wav"
        assert AudioFormat.M4A.value == "m4a"


class TestTranscriber:
    """Tests para Transcriber."""

    def test_transcriber_supported_formats(self):
        """Verifica formatos soportados."""
        from ingestion.transcriber import Transcriber

        t = Transcriber()
        assert "mp3" in t.SUPPORTED_FORMATS
        assert "wav" in t.SUPPORTED_FORMATS
        assert "mp4" in t.SUPPORTED_FORMATS
        assert "exe" not in t.SUPPORTED_FORMATS

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self):
        """Falla si archivo no existe."""
        from ingestion.transcriber import Transcriber

        t = Transcriber()
        with pytest.raises(FileNotFoundError):
            await t.transcribe_file("/nonexistent/audio.mp3")

    def test_get_extension_from_content_type(self):
        """Mapea content-type correctamente."""
        from ingestion.transcriber import Transcriber

        t = Transcriber()
        assert t._get_extension_from_content_type("audio/mpeg") == "mp3"
        assert t._get_extension_from_content_type("audio/wav") == "wav"
        assert t._get_extension_from_content_type("video/mp4") == "mp4"
        assert t._get_extension_from_content_type("text/plain") is None

    def test_get_transcriber_singleton(self):
        """get_transcriber retorna singleton."""
        from ingestion.transcriber import get_transcriber
        import ingestion.transcriber as module

        module._transcriber = None

        t1 = get_transcriber()
        t2 = get_transcriber()

        assert t1 is t2


# ============================================================================
# TESTS - YOUTUBE CONNECTOR
# ============================================================================

class TestYouTubeDataclasses:
    """Tests para dataclasses de YouTube."""

    def test_youtube_video_url_property(self):
        """YouTubeVideo genera URL correctamente."""
        from ingestion.youtube_connector import YouTubeVideo

        video = YouTubeVideo(
            video_id="dQw4w9WgXcQ",
            title="Test Video",
            description="Test description",
            channel_id="UC123",
            channel_name="Test Channel",
            published_at="2024-01-01",
            duration_seconds=180
        )

        assert video.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_youtube_video_to_dict(self):
        """YouTubeVideo serializa correctamente."""
        from ingestion.youtube_connector import YouTubeVideo

        video = YouTubeVideo(
            video_id="abc123",
            title="Mi Video",
            description="Descripcion",
            channel_id="channel_id",
            channel_name="Mi Canal",
            published_at="2024-06-15",
            duration_seconds=600,
            view_count=1000,
            like_count=50
        )

        result = video.to_dict()
        assert result["video_id"] == "abc123"
        assert result["title"] == "Mi Video"
        assert result["view_count"] == 1000
        assert "url" in result

    def test_youtube_transcript_to_dict(self):
        """YouTubeTranscript serializa correctamente."""
        from ingestion.youtube_connector import YouTubeTranscript

        transcript = YouTubeTranscript(
            video_id="abc123",
            video_title="Test Video",
            full_text="Este es el texto completo",
            segments=[{"text": "Este", "start": 0, "duration": 1}],
            language="es",
            is_auto_generated=True,
            source="youtube_captions"
        )

        result = transcript.to_dict()
        assert result["video_id"] == "abc123"
        assert result["full_text"] == "Este es el texto completo"
        assert result["is_auto_generated"] is True


class TestYouTubeConnector:
    """Tests para YouTubeConnector."""

    def test_extract_video_id_standard_url(self):
        """Extrae video ID de URL estandar."""
        from ingestion.youtube_connector import YouTubeConnector

        assert YouTubeConnector.extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ) == "dQw4w9WgXcQ"

    def test_extract_video_id_short_url(self):
        """Extrae video ID de URL corta."""
        from ingestion.youtube_connector import YouTubeConnector

        assert YouTubeConnector.extract_video_id(
            "https://youtu.be/dQw4w9WgXcQ"
        ) == "dQw4w9WgXcQ"

    def test_extract_video_id_embed_url(self):
        """Extrae video ID de URL embed."""
        from ingestion.youtube_connector import YouTubeConnector

        assert YouTubeConnector.extract_video_id(
            "https://www.youtube.com/embed/dQw4w9WgXcQ"
        ) == "dQw4w9WgXcQ"

    def test_extract_video_id_raw(self):
        """Extrae video ID cuando se pasa solo el ID."""
        from ingestion.youtube_connector import YouTubeConnector

        assert YouTubeConnector.extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_extract_video_id_invalid(self):
        """Retorna None para URL invalida."""
        from ingestion.youtube_connector import YouTubeConnector

        assert YouTubeConnector.extract_video_id("not-a-valid-url") is None
        assert YouTubeConnector.extract_video_id("") is None

    @pytest.mark.asyncio
    async def test_get_channel_videos_requires_id_or_url(self):
        """Falla sin channel_id ni channel_url."""
        try:
            pass
        except ImportError:
            pytest.skip("yt-dlp not installed")

        from ingestion.youtube_connector import YouTubeConnector

        connector = YouTubeConnector()
        with pytest.raises(ValueError, match="Se requiere"):
            await connector.get_channel_videos()

    def test_get_youtube_connector_singleton(self):
        """get_youtube_connector retorna singleton."""
        from ingestion.youtube_connector import get_youtube_connector
        import ingestion.youtube_connector as module

        module._connector = None

        c1 = get_youtube_connector()
        c2 = get_youtube_connector()

        assert c1 is c2


# ============================================================================
# TESTS - PODCAST CONNECTOR
# ============================================================================

class TestPodcastDataclasses:
    """Tests para dataclasses de Podcast."""

    def test_podcast_show_id_generated(self):
        """PodcastShow genera ID unico."""
        from ingestion.podcast_connector import PodcastShow

        show = PodcastShow(
            feed_url="https://feed.example.com/podcast.rss",
            title="Mi Podcast"
        )

        assert show.show_id is not None
        assert len(show.show_id) == 12

    def test_podcast_show_to_dict(self):
        """PodcastShow serializa correctamente."""
        from ingestion.podcast_connector import PodcastShow

        show = PodcastShow(
            feed_url="https://feed.example.com/rss",
            title="Test Podcast",
            description="Un podcast de prueba",
            author="Test Author",
            episode_count=10
        )

        result = show.to_dict()
        assert result["title"] == "Test Podcast"
        assert result["author"] == "Test Author"
        assert result["episode_count"] == 10
        assert "show_id" in result

    def test_podcast_episode_url_property(self):
        """PodcastEpisode.url retorna audio_url."""
        from ingestion.podcast_connector import PodcastEpisode

        episode = PodcastEpisode(
            episode_id="ep1",
            title="Episodio 1",
            description="Primer episodio",
            audio_url="https://example.com/episode1.mp3",
            published_at="2024-01-01"
        )

        assert episode.url == "https://example.com/episode1.mp3"

    def test_podcast_episode_to_dict(self):
        """PodcastEpisode serializa correctamente."""
        from ingestion.podcast_connector import PodcastEpisode

        episode = PodcastEpisode(
            episode_id="ep1",
            title="Test Episode",
            description="Description",
            audio_url="https://example.com/audio.mp3",
            published_at="2024-01-15",
            duration_seconds=3600,
            episode_number=5,
            season_number=2
        )

        result = episode.to_dict()
        assert result["episode_id"] == "ep1"
        assert result["duration_seconds"] == 3600
        assert result["episode_number"] == 5
        assert result["season_number"] == 2


class TestPodcastConnector:
    """Tests para PodcastConnector."""

    def test_duration_to_seconds_hhmmss(self):
        """Convierte HH:MM:SS correctamente."""
        from ingestion.podcast_connector import PodcastConnector

        connector = PodcastConnector()
        assert connector._duration_to_seconds("01:30:00") == 5400
        assert connector._duration_to_seconds("00:30:00") == 1800
        assert connector._duration_to_seconds("01:00:15") == 3615

    def test_duration_to_seconds_mmss(self):
        """Convierte MM:SS correctamente."""
        from ingestion.podcast_connector import PodcastConnector

        connector = PodcastConnector()
        assert connector._duration_to_seconds("30:00") == 1800
        assert connector._duration_to_seconds("05:30") == 330

    def test_duration_to_seconds_raw_seconds(self):
        """Convierte segundos directos."""
        from ingestion.podcast_connector import PodcastConnector

        connector = PodcastConnector()
        assert connector._duration_to_seconds("3600") == 3600
        assert connector._duration_to_seconds("120") == 120

    def test_duration_to_seconds_invalid(self):
        """Retorna 0 para formato invalido."""
        from ingestion.podcast_connector import PodcastConnector

        connector = PodcastConnector()
        assert connector._duration_to_seconds("invalid") == 0
        assert connector._duration_to_seconds("") == 0

    def test_get_audio_extension(self):
        """Detecta extension de audio."""
        from ingestion.podcast_connector import PodcastConnector

        connector = PodcastConnector()
        assert connector._get_audio_extension("https://example.com/audio.mp3") == "mp3"
        assert connector._get_audio_extension("https://example.com/audio.m4a") == "m4a"
        assert connector._get_audio_extension("https://example.com/audio.ogg") == "ogg"
        assert connector._get_audio_extension("https://example.com/audio") == "mp3"  # default

    def test_get_podcast_connector_singleton(self):
        """get_podcast_connector retorna singleton."""
        from ingestion.podcast_connector import get_podcast_connector
        import ingestion.podcast_connector as module

        module._connector = None

        c1 = get_podcast_connector()
        c2 = get_podcast_connector()

        assert c1 is c2


# ============================================================================
# TESTS - PDF EXTRACTOR
# ============================================================================

class TestPDFDataclasses:
    """Tests para dataclasses de PDF."""

    def test_pdf_page_char_count(self):
        """PDFPage calcula char_count automaticamente."""
        from ingestion.pdf_extractor import PDFPage

        page = PDFPage(page_number=1, text="Hello world")

        assert page.char_count == 11

    def test_pdf_page_to_dict(self):
        """PDFPage serializa correctamente."""
        from ingestion.pdf_extractor import PDFPage

        page = PDFPage(page_number=5, text="Test content")

        result = page.to_dict()
        assert result["page_number"] == 5
        assert result["text"] == "Test content"
        assert result["char_count"] == 12

    def test_pdf_document_id_generated(self):
        """PDFDocument genera document_id."""
        from ingestion.pdf_extractor import PDFDocument

        doc = PDFDocument(
            source="/path/to/document.pdf",
            title="Test Document",
            full_text="Content here"
        )

        assert doc.document_id is not None
        assert len(doc.document_id) == 12

    def test_pdf_document_word_count(self):
        """PDFDocument calcula word_count."""
        from ingestion.pdf_extractor import PDFDocument

        doc = PDFDocument(
            source="test.pdf",
            title="Test",
            full_text="uno dos tres cuatro cinco"
        )

        assert doc.word_count == 5

    def test_pdf_document_char_count(self):
        """PDFDocument calcula char_count."""
        from ingestion.pdf_extractor import PDFDocument

        doc = PDFDocument(
            source="test.pdf",
            title="Test",
            full_text="Hello"
        )

        assert doc.char_count == 5

    def test_pdf_document_get_text_by_pages(self):
        """PDFDocument.get_text_by_pages funciona correctamente."""
        from ingestion.pdf_extractor import PDFDocument, PDFPage

        doc = PDFDocument(
            source="test.pdf",
            title="Test",
            full_text="Page1 Page2 Page3",
            pages=[
                PDFPage(page_number=1, text="Page1"),
                PDFPage(page_number=2, text="Page2"),
                PDFPage(page_number=3, text="Page3")
            ],
            page_count=3
        )

        assert doc.get_text_by_pages(1, 1) == "Page1"
        assert doc.get_text_by_pages(2, 3) == "Page2\n\nPage3"
        assert doc.get_text_by_pages(1) == "Page1\n\nPage2\n\nPage3"


class TestPDFExtractor:
    """Tests para PDFExtractor."""

    def test_extractor_supported_extensions(self):
        """Verifica extensiones soportadas."""
        from ingestion.pdf_extractor import PDFExtractor

        e = PDFExtractor()
        assert ".pdf" in e.SUPPORTED_EXTENSIONS
        assert ".txt" not in e.SUPPORTED_EXTENSIONS

    @pytest.mark.asyncio
    async def test_extract_file_not_found(self):
        """Retorna None si archivo no existe."""
        from ingestion.pdf_extractor import PDFExtractor

        e = PDFExtractor()
        result = await e.extract_file("/nonexistent/document.pdf")

        assert result is None

    def test_clean_text(self):
        """Limpia texto correctamente."""
        from ingestion.pdf_extractor import PDFExtractor

        e = PDFExtractor()

        # Multiples espacios
        assert "  " not in e._clean_text("Hello   world")

        # Multiples newlines
        cleaned = e._clean_text("Hello\n\n\n\nworld")
        assert "\n\n\n" not in cleaned

    def test_parse_pdf_date_valid(self):
        """Parsea fecha PDF correctamente."""
        from ingestion.pdf_extractor import PDFExtractor

        e = PDFExtractor()

        result = e._parse_pdf_date("D:20240115120000")
        assert result is not None
        assert "2024-01-15" in result

    def test_parse_pdf_date_invalid(self):
        """Retorna None para fecha invalida."""
        from ingestion.pdf_extractor import PDFExtractor

        e = PDFExtractor()

        assert e._parse_pdf_date("invalid") is None
        assert e._parse_pdf_date("") is None

    def test_chunk_document(self):
        """chunk_document divide correctamente."""
        from ingestion.pdf_extractor import PDFExtractor, PDFDocument

        e = PDFExtractor()
        doc = PDFDocument(
            source="test.pdf",
            title="Test",
            full_text=" ".join(["word"] * 100),  # 100 palabras
            page_count=5
        )

        chunks = e.chunk_document(doc, chunk_size=30, overlap=5)

        assert len(chunks) > 1
        assert all("chunk_id" in c for c in chunks)
        assert all("content" in c for c in chunks)
        assert chunks[0]["word_count"] == 30

    def test_chunk_document_empty(self):
        """chunk_document maneja documento vacio."""
        from ingestion.pdf_extractor import PDFExtractor, PDFDocument

        e = PDFExtractor()
        doc = PDFDocument(
            source="empty.pdf",
            title="Empty",
            full_text=""
        )

        chunks = e.chunk_document(doc)
        assert chunks == []

    def test_get_pdf_extractor_singleton(self):
        """get_pdf_extractor retorna singleton."""
        from ingestion.pdf_extractor import get_pdf_extractor
        import ingestion.pdf_extractor as module

        module._extractor = None

        e1 = get_pdf_extractor()
        e2 = get_pdf_extractor()

        assert e1 is e2


# ============================================================================
# TESTS - MODULE IMPORTS
# ============================================================================

class TestModuleImports:
    """Tests para verificar que los imports funcionan."""

    def test_import_from_ingestion_transcriber(self):
        """Verifica imports del transcriber."""
        from ingestion import (
            AudioFormat,
            TranscriptSegment,
            Transcript,
            Transcriber,
            get_transcriber
        )

        assert AudioFormat is not None
        assert TranscriptSegment is not None
        assert Transcript is not None
        assert Transcriber is not None
        assert get_transcriber is not None

    def test_import_from_ingestion_youtube(self):
        """Verifica imports de YouTube."""
        from ingestion import (
            YouTubeVideo,
            YouTubeTranscript,
            YouTubeConnector,
            get_youtube_connector
        )

        assert YouTubeVideo is not None
        assert YouTubeTranscript is not None
        assert YouTubeConnector is not None
        assert get_youtube_connector is not None

    def test_import_from_ingestion_podcast(self):
        """Verifica imports de Podcast."""
        from ingestion import (
            PodcastShow,
            PodcastEpisode,
            PodcastTranscript,
            PodcastConnector,
            get_podcast_connector
        )

        assert PodcastShow is not None
        assert PodcastEpisode is not None
        assert PodcastTranscript is not None
        assert PodcastConnector is not None
        assert get_podcast_connector is not None

    def test_import_from_ingestion_pdf(self):
        """Verifica imports de PDF."""
        from ingestion import (
            PDFPage,
            PDFDocument,
            PDFExtractor,
            get_pdf_extractor
        )

        assert PDFPage is not None
        assert PDFDocument is not None
        assert PDFExtractor is not None
        assert get_pdf_extractor is not None
