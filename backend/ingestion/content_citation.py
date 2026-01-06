"""
Content Citation - Permite al bot citar contenido especifico del creador.
Fase 1 - Magic Slice

Este modulo habilita el WOW #4: "Sabe tanto como el creador"
"""

import logging
import re
import unicodedata
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Normaliza texto removiendo acentos y caracteres especiales.
    Útil para matching de búsqueda.
    """
    # Normalizar unicode (descomponer caracteres acentuados)
    normalized = unicodedata.normalize('NFD', text)
    # Remover marcas diacríticas (acentos)
    without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return without_accents.lower()


class ContentType(Enum):
    """Tipos de contenido que se pueden citar."""
    INSTAGRAM_POST = "instagram_post"
    INSTAGRAM_REEL = "instagram_reel"
    YOUTUBE_VIDEO = "youtube_video"
    PODCAST_EPISODE = "podcast_episode"
    PDF_EBOOK = "pdf_ebook"
    FAQ = "faq"


@dataclass
class Citation:
    """
    Representa una cita de contenido del creador.
    """
    content_type: ContentType
    source_id: str
    source_url: Optional[str]
    title: Optional[str]
    excerpt: str  # Fragmento relevante del contenido
    relevance_score: float  # 0-1, que tan relevante es para la query
    published_date: Optional[datetime] = None

    # Metadata adicional
    likes_count: Optional[int] = None
    platform: str = "instagram"

    def to_natural_reference(self, style: str = "casual") -> str:
        """
        Genera una referencia natural para usar en conversacion.

        Args:
            style: 'casual', 'formal', 'minimal'

        Returns:
            String con referencia natural
        """
        if style == "minimal":
            return self._minimal_reference()
        elif style == "formal":
            return self._formal_reference()
        else:
            return self._casual_reference()

    def _casual_reference(self) -> str:
        """Referencia casual para conversacion."""
        type_refs = {
            ContentType.INSTAGRAM_POST: [
                "en un post que hice",
                "lo explique en un post",
                "en uno de mis posts",
                "hable de esto en Instagram"
            ],
            ContentType.INSTAGRAM_REEL: [
                "en un reel que subi",
                "lo mostre en un reel",
                "hice un reel sobre esto"
            ],
            ContentType.YOUTUBE_VIDEO: [
                "en un video de mi canal",
                "lo explico en YouTube",
                "tengo un video donde hablo de esto"
            ],
            ContentType.PODCAST_EPISODE: [
                "en un episodio del podcast",
                "lo comente en el podcast",
                "hable de esto en el podcast"
            ],
            ContentType.PDF_EBOOK: [
                "en mi guia",
                "lo explico en el ebook",
                "esta en mi material"
            ],
            ContentType.FAQ: [
                "como suelo explicar",
                "es algo que me preguntan mucho"
            ]
        }

        refs = type_refs.get(self.content_type, ["en mi contenido"])

        # Anadir contexto temporal si hay fecha
        if self.published_date:
            days_ago = (datetime.utcnow() - self.published_date).days
            if days_ago < 7:
                time_ref = "hace unos dias"
            elif days_ago < 30:
                time_ref = "hace unas semanas"
            elif days_ago < 90:
                time_ref = "hace unos meses"
            else:
                time_ref = "hace tiempo"

            return f"{refs[0]} {time_ref}"

        return refs[0]

    def _formal_reference(self) -> str:
        """Referencia formal."""
        if self.title:
            return f'en mi contenido "{self.title}"'
        return f"en mi contenido de {self.platform}"

    def _minimal_reference(self) -> str:
        """Referencia minima."""
        return "como explique antes"


@dataclass
class CitationContext:
    """
    Contexto completo para inyectar en el prompt del LLM.
    """
    query: str  # Pregunta original del seguidor
    citations: List[Citation] = field(default_factory=list)
    max_citations: int = 3

    def has_relevant_content(self, min_score: float = 0.5) -> bool:
        """Verifica si hay contenido relevante."""
        return any(c.relevance_score >= min_score for c in self.citations)

    def get_top_citations(self, n: Optional[int] = None) -> List[Citation]:
        """Obtiene las N citas mas relevantes."""
        n = n or self.max_citations
        sorted_citations = sorted(
            self.citations,
            key=lambda c: c.relevance_score,
            reverse=True
        )
        return sorted_citations[:n]

    def to_prompt_context(self) -> str:
        """
        Genera contexto para inyectar en el prompt del LLM.
        """
        if not self.citations:
            return ""

        top_citations = self.get_top_citations()

        lines = [
            "CONTENIDO RELEVANTE DEL CREADOR QUE PUEDES REFERENCIAR:",
            ""
        ]

        for i, citation in enumerate(top_citations, 1):
            lines.append(f"[{i}] {citation.content_type.value.upper()}")
            if citation.title:
                lines.append(f"    Titulo: {citation.title}")
            lines.append(f"    Contenido: {citation.excerpt[:300]}...")
            if citation.source_url:
                lines.append(f"    URL: {citation.source_url}")
            lines.append(f"    Relevancia: {citation.relevance_score:.0%}")
            lines.append("")

        lines.extend([
            "",
            "⚠️ INSTRUCCIONES OBLIGATORIAS PARA CITAR (MUY IMPORTANTE):",
            "- DEBES hacer referencia EXPLÍCITA a este contenido en tu respuesta",
            "- USA frases como:",
            "  * 'Como comenté en un post...'",
            "  * 'Justo hablé de esto en mi último video...'",
            "  * 'En un contenido que publiqué expliqué que...'",
            "  * 'Lo expliqué en detalle en un post...'",
            "  * 'Precisamente toqué este tema y...'",
            "- Parafrasea con tu estilo, NO copies textualmente",
            "- La referencia hace tu respuesta más AUTÉNTICA y personal",
            "",
            "EJEMPLO DE CITA CORRECTA:",
            "Usuario: ¿Qué opinas de meter todo en una operación?",
            "Tú: Justo hablé de esto en un post: la gestión de riesgo es CLAVE. Nunca metas más del 2% por operación 👍",
            "",
            "EJEMPLO INCORRECTO (sin citar):",
            "Tú: La gestión de riesgo es importante, no metas todo..."
        ])

        return "\n".join(lines)


class ContentCitationEngine:
    """
    Motor de citacion de contenido.
    Busca contenido relevante y genera citas para el bot.
    """

    def __init__(self, vector_store=None, embeddings_model=None):
        """
        Args:
            vector_store: FAISS o similar para busqueda semantica
            embeddings_model: Modelo para generar embeddings
        """
        self.vector_store = vector_store
        self.embeddings_model = embeddings_model

    async def find_relevant_content(
        self,
        creator_id: str,
        query: str,
        content_types: Optional[List[ContentType]] = None,
        max_results: int = 5,
        min_relevance: float = 0.3
    ) -> CitationContext:
        """
        Busca contenido relevante para una query.

        Args:
            creator_id: ID del creador
            query: Pregunta/mensaje del seguidor
            content_types: Filtrar por tipos de contenido
            max_results: Maximo de resultados
            min_relevance: Score minimo de relevancia

        Returns:
            CitationContext con citas encontradas
        """
        citations = []

        try:
            # Buscar en vector store si esta disponible
            if self.vector_store:
                results = await self._search_vector_store(
                    creator_id, query, max_results
                )
                citations.extend(results)

            # Filtrar por tipo si se especifica
            if content_types:
                citations = [
                    c for c in citations
                    if c.content_type in content_types
                ]

            # Filtrar por relevancia minima
            citations = [
                c for c in citations
                if c.relevance_score >= min_relevance
            ]

            logger.info(
                f"Found {len(citations)} relevant citations for query: {query[:50]}..."
            )

        except Exception as e:
            logger.error(f"Error finding relevant content: {e}")

        return CitationContext(
            query=query,
            citations=citations,
            max_citations=max_results
        )

    async def _search_vector_store(
        self,
        creator_id: str,
        query: str,
        k: int
    ) -> List[Citation]:
        """Busca en el vector store."""
        # Esta implementacion depende del vector store especifico
        # Por ahora, retornamos lista vacia - se conectara con FAISS existente

        if not self.vector_store:
            return []

        try:
            # Generar embedding de la query
            if self.embeddings_model:
                query_embedding = self.embeddings_model.encode(query)
            else:
                # Fallback: intentar usar modelo default
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer('all-MiniLM-L6-v2')
                query_embedding = model.encode(query)

            # Buscar en vector store
            # La interfaz exacta depende de como este implementado en el proyecto
            results = self.vector_store.search(
                query_embedding,
                k=k,
                filter={"creator_id": creator_id}
            )

            citations = []
            for result in results:
                citation = Citation(
                    content_type=self._map_source_type(result.get('source_type')),
                    source_id=result.get('source_id', ''),
                    source_url=result.get('source_url'),
                    title=result.get('title'),
                    excerpt=result.get('content', '')[:500],
                    relevance_score=result.get('score', 0.5),
                    published_date=result.get('published_date')
                )
                citations.append(citation)

            return citations

        except Exception as e:
            logger.error(f"Vector store search error: {e}")
            return []

    def _map_source_type(self, source_type: str) -> ContentType:
        """Mapea string a ContentType."""
        mapping = {
            'instagram_post': ContentType.INSTAGRAM_POST,
            'instagram_reel': ContentType.INSTAGRAM_REEL,
            'youtube': ContentType.YOUTUBE_VIDEO,
            'youtube_video': ContentType.YOUTUBE_VIDEO,
            'podcast': ContentType.PODCAST_EPISODE,
            'podcast_episode': ContentType.PODCAST_EPISODE,
            'pdf': ContentType.PDF_EBOOK,
            'ebook': ContentType.PDF_EBOOK,
            'faq': ContentType.FAQ
        }
        return mapping.get(source_type, ContentType.INSTAGRAM_POST)

    def create_citation_from_chunk(
        self,
        chunk: Dict,
        relevance_score: float = 0.5
    ) -> Citation:
        """
        Crea una Citation desde un ContentChunk.

        Args:
            chunk: Dict con datos del chunk (del Content Indexer)
            relevance_score: Score de relevancia

        Returns:
            Citation object
        """
        return Citation(
            content_type=self._map_source_type(chunk.get('source_type', 'instagram_post')),
            source_id=chunk.get('source_id', ''),
            source_url=chunk.get('source_url'),
            title=chunk.get('title'),
            excerpt=chunk.get('content', ''),
            relevance_score=relevance_score,
            published_date=chunk.get('created_at'),
            platform=chunk.get('platform', 'instagram')
        )


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

def extract_topics_from_query(query: str) -> List[str]:
    """
    Extrae temas/keywords de una query para mejorar busqueda.

    Args:
        query: Pregunta del seguidor

    Returns:
        Lista de temas/keywords (normalizados sin acentos)
    """
    # Remover palabras comunes en espanol (sin acentos para matching)
    stopwords = {
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'de', 'del', 'al', 'a', 'en', 'con', 'por', 'para',
        'que', 'cual', 'como',
        'me', 'te', 'se', 'nos', 'mi', 'tu', 'su',
        'es', 'son', 'esta', 'estan', 'ser', 'estar',
        'hola', 'hey', 'buenas', 'buenos',
        'quiero', 'quisiera', 'puedo', 'puedes',
        'saber', 'conocer', 'preguntar',
        'sobre', 'acerca', 'respecto',
        'y', 'o', 'pero', 'si', 'no', 'mas', 'muy',
        'tienes', 'tiene', 'hay', 'info', 'informacion'
    }

    # Sinónimos comunes (inglés -> español)
    synonyms = {
        'challenge': ['reto', 'desafio', 'challenge'],
        'reto': ['challenge', 'desafio'],
        'coaching': ['acompanamiento', 'coach', 'coaching'],
        'coach': ['coaching', 'acompanamiento'],
        'taller': ['workshop', 'talleres'],
        'workshop': ['taller', 'talleres'],
        'respiracion': ['respira', 'respirar', 'breathwork'],
        'breathwork': ['respiracion', 'respira'],
    }

    # Normalizar (quitar acentos) y tokenizar
    query_normalized = normalize_text(query)
    words = re.findall(r'\b\w+\b', query_normalized)

    # Filtrar stopwords y palabras muy cortas (pero permitir números como "11")
    topics = []
    for w in words:
        if w in stopwords:
            continue
        if len(w) < 2:
            continue
        # Permitir números de 2+ dígitos
        if w.isdigit() and len(w) >= 2:
            topics.append(w)
        elif len(w) > 2:
            topics.append(w)
            # Añadir sinónimos si existen
            if w in synonyms:
                topics.extend(synonyms[w])

    return list(set(topics))  # Eliminar duplicados


def format_citation_for_response(
    citation: Citation,
    include_excerpt: bool = False
) -> str:
    """
    Formatea una cita para incluir en la respuesta.

    Args:
        citation: Citation a formatear
        include_excerpt: Si incluir parte del contenido

    Returns:
        String formateado
    """
    ref = citation.to_natural_reference(style="casual")

    if include_excerpt and citation.excerpt:
        # Truncar excerpt a algo razonable
        short_excerpt = citation.excerpt[:150]
        if len(citation.excerpt) > 150:
            short_excerpt += "..."
        return f"{ref}, donde {short_excerpt}"

    return ref


def should_cite_content(
    query: str,
    citation_context: CitationContext,
    min_relevance: float = 0.6
) -> bool:
    """
    Determina si se deberia citar contenido en la respuesta.

    Args:
        query: Pregunta del seguidor
        citation_context: Contexto con citas encontradas
        min_relevance: Umbral minimo de relevancia

    Returns:
        True si se deberia citar
    """
    if not citation_context.citations:
        return False

    # Verificar si hay citas suficientemente relevantes
    top_citation = citation_context.get_top_citations(1)
    if not top_citation:
        return False

    if top_citation[0].relevance_score < min_relevance:
        return False

    # Verificar que la query es una pregunta de conocimiento
    knowledge_indicators = [
        '?', 'qué', 'cómo', 'cuál', 'cuándo', 'dónde', 'por qué',
        'explica', 'cuéntame', 'dime', 'sabes', 'opinas', 'piensas',
        'recomiendas', 'sugieres', 'hablaste', 'dijiste', 'mencionaste'
    ]

    query_lower = query.lower()
    is_knowledge_query = any(ind in query_lower for ind in knowledge_indicators)

    return is_knowledge_query
