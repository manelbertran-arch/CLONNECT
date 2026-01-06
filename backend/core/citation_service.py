"""
Citation Service - Gestiona busqueda y citacion de contenido del creador.
Conecta Magic Slice ContentCitation con el sistema existente.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from ingestion import (
    ContentChunk,
    Citation,
    CitationContext,
    ContentType,
    ContentCitationEngine,
    create_chunks_from_content,
    split_text,
    extract_topics_from_query,
    should_cite_content,
    normalize_text
)

logger = logging.getLogger(__name__)


class CreatorContentIndex:
    """
    Indice de contenido de un creador.
    Version simple sin FAISS (para integracion rapida).
    """

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        self.chunks: List[ContentChunk] = []
        self.posts_metadata: Dict[str, Dict] = {}  # post_id -> metadata
        self._loaded = False

    def add_post(
        self,
        post_id: str,
        caption: str,
        post_type: str = "instagram_post",
        url: Optional[str] = None,
        published_date: Optional[datetime] = None,
        **metadata
    ) -> List[ContentChunk]:
        """
        Anade un post al indice.

        Returns:
            Lista de chunks creados
        """
        # Crear chunks del contenido
        chunks = create_chunks_from_content(
            creator_id=self.creator_id,
            source_type=post_type,
            source_id=post_id,
            content=caption,
            source_url=url,
            title=metadata.get('title'),
            metadata={
                'published_date': published_date.isoformat() if published_date else None,
                **metadata
            }
        )

        self.chunks.extend(chunks)

        # Guardar metadata del post
        self.posts_metadata[post_id] = {
            'post_id': post_id,
            'caption': caption,
            'post_type': post_type,
            'url': url,
            'published_date': published_date,
            'chunk_count': len(chunks),
            **metadata
        }

        logger.info(f"Added post {post_id} with {len(chunks)} chunks to index")
        return chunks

    def search(
        self,
        query: str,
        max_results: int = 5,
        min_relevance: float = 0.25
    ) -> List[Dict[str, Any]]:
        """
        Busqueda simple por keywords con normalizacion de acentos.
        (En produccion usar embeddings + FAISS)
        """
        if not self.chunks:
            logger.debug(f"No chunks loaded for search")
            return []

        # Extraer keywords de la query (ya normalizadas sin acentos)
        keywords = extract_topics_from_query(query)
        if not keywords:
            logger.debug(f"No keywords extracted from query: {query}")
            return []

        logger.debug(f"Searching with keywords: {keywords}")

        results = []

        for chunk in self.chunks:
            # Normalizar contenido (quitar acentos) para matching
            content_normalized = normalize_text(chunk.content)
            # También buscar en el título
            title_normalized = normalize_text(chunk.title or '')
            combined_text = f"{content_normalized} {title_normalized}"

            matches = sum(1 for kw in keywords if kw in combined_text)

            if matches > 0:
                relevance = matches / len(keywords)

                if relevance >= min_relevance:
                    # Obtener metadata del post original
                    post_meta = self.posts_metadata.get(chunk.source_id, {})

                    results.append({
                        'chunk_id': chunk.id,
                        'source_type': chunk.source_type,
                        'source_id': chunk.source_id,
                        'source_url': chunk.source_url,
                        'title': chunk.title,
                        'content': chunk.content,
                        'relevance_score': relevance,
                        'published_date': post_meta.get('published_date'),
                        'platform': 'instagram'
                    })

        # Ordenar por relevancia y limitar
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results[:max_results]

    def save(self) -> bool:
        """Guarda el indice en disco."""
        try:
            index_dir = Path(f"data/content_index/{self.creator_id}")
            index_dir.mkdir(parents=True, exist_ok=True)

            # Guardar chunks
            chunks_data = [
                {
                    'id': c.id,
                    'creator_id': c.creator_id,
                    'source_type': c.source_type,
                    'source_id': c.source_id,
                    'source_url': c.source_url,
                    'title': c.title,
                    'content': c.content,
                    'chunk_index': c.chunk_index,
                    'total_chunks': c.total_chunks,
                    'metadata': c.metadata,
                    'created_at': c.created_at.isoformat() if c.created_at else None
                }
                for c in self.chunks
            ]

            with open(index_dir / "chunks.json", 'w', encoding='utf-8') as f:
                json.dump(chunks_data, f, ensure_ascii=False, indent=2)

            # Guardar metadata de posts
            with open(index_dir / "posts.json", 'w', encoding='utf-8') as f:
                # Serializar fechas
                posts_serializable = {}
                for pid, meta in self.posts_metadata.items():
                    meta_copy = meta.copy()
                    if meta_copy.get('published_date'):
                        meta_copy['published_date'] = meta_copy['published_date'].isoformat() \
                            if isinstance(meta_copy['published_date'], datetime) \
                            else meta_copy['published_date']
                    posts_serializable[pid] = meta_copy

                json.dump(posts_serializable, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved index for {self.creator_id}: {len(self.chunks)} chunks")
            return True

        except Exception as e:
            logger.error(f"Error saving index: {e}")
            return False

    def load(self) -> bool:
        """Carga el indice desde disco."""
        if self._loaded:
            return True

        try:
            index_dir = Path(f"data/content_index/{self.creator_id}")

            chunks_path = index_dir / "chunks.json"
            posts_path = index_dir / "posts.json"

            if not chunks_path.exists():
                return False

            # Cargar chunks
            with open(chunks_path, 'r', encoding='utf-8') as f:
                chunks_data = json.load(f)

            self.chunks = [
                ContentChunk(
                    id=c['id'],
                    creator_id=c['creator_id'],
                    source_type=c['source_type'],
                    source_id=c['source_id'],
                    source_url=c.get('source_url'),
                    title=c.get('title'),
                    content=c['content'],
                    chunk_index=c['chunk_index'],
                    total_chunks=c['total_chunks'],
                    metadata=c.get('metadata', {}),
                    created_at=datetime.fromisoformat(c['created_at']) if c.get('created_at') else None
                )
                for c in chunks_data
            ]

            # Cargar metadata de posts
            if posts_path.exists():
                with open(posts_path, 'r', encoding='utf-8') as f:
                    self.posts_metadata = json.load(f)

            self._loaded = True
            logger.info(f"Loaded index for {self.creator_id}: {len(self.chunks)} chunks")
            return True

        except Exception as e:
            logger.error(f"Error loading index: {e}")
            return False

    @property
    def stats(self) -> Dict:
        """Estadisticas del indice."""
        return {
            'creator_id': self.creator_id,
            'total_chunks': len(self.chunks),
            'total_posts': len(self.posts_metadata),
            'loaded': self._loaded
        }


# Cache de indices
_index_cache: Dict[str, CreatorContentIndex] = {}


def get_content_index(creator_id: str) -> CreatorContentIndex:
    """Obtiene o crea el indice de contenido de un creador."""
    if creator_id not in _index_cache:
        index = CreatorContentIndex(creator_id)
        index.load()  # Intentar cargar de disco
        _index_cache[creator_id] = index

    return _index_cache[creator_id]


def clear_index_cache(creator_id: Optional[str] = None) -> None:
    """Limpia el cache de indices."""
    global _index_cache
    if creator_id:
        _index_cache.pop(creator_id, None)
    else:
        _index_cache.clear()


def reload_creator_index(creator_id: str) -> bool:
    """
    Recarga el índice de un creador desde disco.
    Útil después de añadir nuevo contenido.

    Args:
        creator_id: ID del creador

    Returns:
        True si se recargó correctamente
    """
    global _index_cache

    # Eliminar del cache si existe
    _index_cache.pop(creator_id, None)

    # Crear nuevo índice y cargar
    index = CreatorContentIndex(creator_id)
    loaded = index.load()

    if loaded:
        _index_cache[creator_id] = index
        logger.info(f"Reloaded index for {creator_id}: {len(index.chunks)} chunks")

    return loaded


async def find_relevant_citations(
    creator_id: str,
    query: str,
    max_results: int = 3,
    min_relevance: float = 0.4
) -> CitationContext:
    """
    Busca contenido relevante y retorna CitationContext.

    Args:
        creator_id: ID del creador
        query: Mensaje del seguidor
        max_results: Maximo de citas
        min_relevance: Relevancia minima

    Returns:
        CitationContext listo para inyectar en prompt
    """
    index = get_content_index(creator_id)

    # Buscar contenido relevante
    search_results = index.search(
        query=query,
        max_results=max_results,
        min_relevance=min_relevance
    )

    # Convertir a Citations
    citations = []
    for result in search_results:
        # Mapear tipo
        content_type_map = {
            'instagram_post': ContentType.INSTAGRAM_POST,
            'instagram_reel': ContentType.INSTAGRAM_REEL,
            'youtube_video': ContentType.YOUTUBE_VIDEO,
            'podcast_episode': ContentType.PODCAST_EPISODE,
            'pdf_ebook': ContentType.PDF_EBOOK,
            'faq': ContentType.FAQ
        }

        content_type = content_type_map.get(
            result.get('source_type', 'instagram_post'),
            ContentType.INSTAGRAM_POST
        )

        # Parsear fecha si existe
        published_date = None
        if result.get('published_date'):
            try:
                if isinstance(result['published_date'], str):
                    published_date = datetime.fromisoformat(result['published_date'])
                else:
                    published_date = result['published_date']
            except Exception:
                pass

        citation = Citation(
            content_type=content_type,
            source_id=result['source_id'],
            source_url=result.get('source_url'),
            title=result.get('title'),
            excerpt=result['content'],
            relevance_score=result['relevance_score'],
            published_date=published_date,
            platform=result.get('platform', 'instagram')
        )
        citations.append(citation)

    return CitationContext(
        query=query,
        citations=citations,
        max_citations=max_results
    )


def get_citation_prompt_section(
    creator_id: str,
    query: str,
    min_relevance: float = 0.25
) -> str:
    """
    Version sincrona para obtener seccion de citas.

    Returns:
        String para inyectar en system prompt, o vacio si no hay citas relevantes
    """
    import asyncio

    try:
        # Obtener indice y buscar
        index = get_content_index(creator_id)

        # Buscar contenido relevante
        search_results = index.search(
            query=query,
            max_results=3,
            min_relevance=min_relevance
        )

        if not search_results:
            return ""

        # Convertir a Citations para generar contexto
        citations = []
        for result in search_results:
            content_type_map = {
                'instagram_post': ContentType.INSTAGRAM_POST,
                'instagram_reel': ContentType.INSTAGRAM_REEL,
                'youtube_video': ContentType.YOUTUBE_VIDEO,
                'podcast_episode': ContentType.PODCAST_EPISODE,
                'pdf_ebook': ContentType.PDF_EBOOK,
                'faq': ContentType.FAQ
            }

            content_type = content_type_map.get(
                result.get('source_type', 'instagram_post'),
                ContentType.INSTAGRAM_POST
            )

            # Parsear fecha si existe
            published_date = None
            if result.get('published_date'):
                try:
                    if isinstance(result['published_date'], str):
                        published_date = datetime.fromisoformat(result['published_date'])
                    else:
                        published_date = result['published_date']
                except Exception:
                    pass

            citation = Citation(
                content_type=content_type,
                source_id=result['source_id'],
                source_url=result.get('source_url'),
                title=result.get('title'),
                excerpt=result['content'],
                relevance_score=result['relevance_score'],
                published_date=published_date,
                platform=result.get('platform', 'instagram')
            )
            citations.append(citation)

        citation_context = CitationContext(
            query=query,
            citations=citations,
            max_citations=3
        )

        # Verificar si hay contenido relevante
        if not citation_context.has_relevant_content(min_score=min_relevance):
            return ""

        return citation_context.to_prompt_context()

    except Exception as e:
        logger.error(f"Error getting citation prompt: {e}")
        return ""


async def index_creator_posts(
    creator_id: str,
    posts: List[Dict],
    save: bool = True
) -> Dict:
    """
    Indexa posts de un creador.

    Args:
        creator_id: ID del creador
        posts: Lista de posts con caption, post_id, etc.
        save: Si guardar en disco

    Returns:
        Estadisticas de indexacion
    """
    index = get_content_index(creator_id)

    total_chunks = 0
    for post in posts:
        caption = post.get('caption', '')
        if len(caption) < 20:  # Ignorar posts muy cortos
            continue

        # Parsear fecha si viene como string
        published_date = post.get('published_date') or post.get('timestamp')
        if isinstance(published_date, str):
            try:
                published_date = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
            except Exception:
                published_date = None

        chunks = index.add_post(
            post_id=post.get('post_id', post.get('id', str(hash(caption))[:10])),
            caption=caption,
            post_type=post.get('post_type', 'instagram_post'),
            url=post.get('url') or post.get('permalink'),
            published_date=published_date,
            likes=post.get('likes_count'),
            comments=post.get('comments_count')
        )
        total_chunks += len(chunks)

    if save:
        index.save()

    return {
        'creator_id': creator_id,
        'posts_indexed': len([p for p in posts if len(p.get('caption', '')) >= 20]),
        'total_chunks': total_chunks,
        'index_stats': index.stats
    }


def delete_content_index(creator_id: str) -> bool:
    """
    Elimina el indice de contenido de un creador.

    Args:
        creator_id: ID del creador

    Returns:
        True si se elimino, False si no existia
    """
    import shutil

    index_dir = Path(f"data/content_index/{creator_id}")
    if index_dir.exists():
        shutil.rmtree(index_dir)
        # Limpiar cache
        if creator_id in _index_cache:
            del _index_cache[creator_id]
        logger.info(f"Deleted content index for {creator_id}")
        return True
    return False
