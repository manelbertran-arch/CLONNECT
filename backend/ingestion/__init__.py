# -*- coding: utf-8 -*-
"""
Ingestion Module - Magic Slice Pipeline.
Fase 1 del desarrollo de Clonnect.

Este modulo contiene todos los componentes para:
- Indexar contenido del creador (Content Indexer)
- Scrapear Instagram (Instagram Scraper)
- Analizar tono/voz del creador (Tone Analyzer)
- Citar contenido en respuestas (Content Citation)
- Generar respuestas mejoradas (Response Engine v2)
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
    should_cite_content
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

    # Response Engine v2
    'FollowerContext',
    'ConversationContext',
    'ResponseEngineV2',
    'create_conversation_context',
    'enhance_response_with_magic_slice',
    'build_magic_slice_prompt',
]
