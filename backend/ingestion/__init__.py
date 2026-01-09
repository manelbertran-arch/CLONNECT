# -*- coding: utf-8 -*-
"""
Ingestion Module - Magic Slice Pipeline.
Fases 1 y 2 del desarrollo de Clonnect.

Este modulo contiene todos los componentes para:
- Indexar contenido del creador (Content Indexer)
- Scrapear Instagram (Instagram Scraper)
- Analizar tono/voz del creador (Tone Analyzer)
- Citar contenido en respuestas (Content Citation)
- Generar respuestas mejoradas (Response Engine v2)

Fase 2 - Media Connectors:
- Transcribir audio/video (Transcriber - Whisper)
- Importar videos de YouTube (YouTube Connector)
- Importar episodios de podcast (Podcast Connector)
- Extraer texto de PDFs (PDF Extractor)
"""

# Content Indexer
from .content_indexer import (
    ContentChunk,
    split_text,
    generate_chunk_id,
    create_chunks_from_content
)

# Instagram Scraper
from .instagram_scraper import (
    InstagramPost,
    ManualJSONScraper,
    MetaGraphAPIScraper,
    InstaloaderScraper,
    get_instagram_scraper,
    InstagramScraperError
)

# Tone Analyzer
from .tone_analyzer import (
    ToneProfile,
    ToneAnalyzer,
    quick_analyze_text
)

# Content Citation
from .content_citation import (
    ContentType,
    Citation,
    CitationContext,
    ContentCitationEngine,
    extract_topics_from_query,
    format_citation_for_response,
    should_cite_content,
    normalize_text
)

# Response Engine v2
from .response_engine_v2 import (
    FollowerContext,
    ConversationContext,
    ResponseEngineV2,
    create_conversation_context,
    enhance_response_with_magic_slice,
    build_magic_slice_prompt
)

# Phase 2 - Transcriber
from .transcriber import (
    AudioFormat,
    TranscriptSegment,
    Transcript,
    Transcriber,
    get_transcriber
)

# Phase 2 - YouTube Connector
from .youtube_connector import (
    YouTubeVideo,
    YouTubeTranscript,
    YouTubeConnector,
    get_youtube_connector
)

# Phase 2 - Podcast Connector
from .podcast_connector import (
    PodcastShow,
    PodcastEpisode,
    PodcastTranscript,
    PodcastConnector,
    get_podcast_connector
)

# Phase 2 - PDF Extractor
from .pdf_extractor import (
    PDFPage,
    PDFDocument,
    PDFExtractor,
    get_pdf_extractor
)

# Phase 3 - Deterministic Ingestion Pipeline (Anti-hallucination)
from .deterministic_scraper import (
    ScrapedPage,
    DeterministicScraper,
    get_deterministic_scraper
)

from .structured_extractor import (
    ExtractedProduct,
    ExtractedTestimonial,
    ExtractedFAQ,
    ExtractedContent,
    StructuredExtractor,
    get_structured_extractor
)

from .content_store import (
    ContentStore,
    get_content_store,
    generate_doc_id
)

from .pipeline import (
    IngestionResult,
    IngestionPipeline,
    get_ingestion_pipeline,
    ingest_website
)

__all__ = [
    # Content Indexer
    'ContentChunk',
    'split_text',
    'generate_chunk_id',
    'create_chunks_from_content',

    # Instagram Scraper
    'InstagramPost',
    'ManualJSONScraper',
    'MetaGraphAPIScraper',
    'InstaloaderScraper',
    'get_instagram_scraper',
    'InstagramScraperError',

    # Tone Analyzer
    'ToneProfile',
    'ToneAnalyzer',
    'quick_analyze_text',

    # Content Citation
    'ContentType',
    'Citation',
    'CitationContext',
    'ContentCitationEngine',
    'extract_topics_from_query',
    'format_citation_for_response',
    'should_cite_content',
    'normalize_text',

    # Response Engine v2
    'FollowerContext',
    'ConversationContext',
    'ResponseEngineV2',
    'create_conversation_context',
    'enhance_response_with_magic_slice',
    'build_magic_slice_prompt',

    # Phase 2 - Transcriber
    'AudioFormat',
    'TranscriptSegment',
    'Transcript',
    'Transcriber',
    'get_transcriber',

    # Phase 2 - YouTube Connector
    'YouTubeVideo',
    'YouTubeTranscript',
    'YouTubeConnector',
    'get_youtube_connector',

    # Phase 2 - Podcast Connector
    'PodcastShow',
    'PodcastEpisode',
    'PodcastTranscript',
    'PodcastConnector',
    'get_podcast_connector',

    # Phase 2 - PDF Extractor
    'PDFPage',
    'PDFDocument',
    'PDFExtractor',
    'get_pdf_extractor',

    # Phase 3 - Deterministic Ingestion Pipeline
    'ScrapedPage',
    'DeterministicScraper',
    'get_deterministic_scraper',
    'ExtractedProduct',
    'ExtractedTestimonial',
    'ExtractedFAQ',
    'ExtractedContent',
    'StructuredExtractor',
    'get_structured_extractor',
    'ContentStore',
    'get_content_store',
    'generate_doc_id',
    'IngestionResult',
    'IngestionPipeline',
    'get_ingestion_pipeline',
    'ingest_website',
]
