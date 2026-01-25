"""
Citation Service - Gestiona busqueda y citacion de contenido del creador.
Conecta Magic Slice ContentCitation con el sistema existente.

MIGRADO: Usa PostgreSQL como almacenamiento principal con JSON como fallback.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.metrics import (
    record_posts_indexed,
    record_chunks_saved,
    start_ingestion,
    end_ingestion,
    log_ingestion_complete
)

from ingestion import (
    Citation,
    CitationContext,
    ContentChunk,
    ContentCitationEngine,
    ContentType,
    create_chunks_from_content,
    extract_topics_from_query,
    normalize_text,
    should_cite_content,
    split_text,
)

logger = logging.getLogger(__name__)


def _try_load_chunks_from_db(creator_id: str) -> Optional[List[dict]]:
    """Intenta cargar chunks desde PostgreSQL usando RAGDocument (tabla con 108 docs)."""
    try:
        from api.database import SessionLocal
        from api.models import Creator, RAGDocument

        if SessionLocal is None:
            logger.debug("No database configured")
            return None

        db = SessionLocal()
        try:
            # RAGDocument usa creator_id como UUID (FK), necesitamos buscar el creator primero
            creator = db.query(Creator).filter(Creator.name == creator_id).first()
            if not creator:
                logger.warning(f"Creator {creator_id} not found in DB")
                return None

            # Buscar en rag_documents usando el UUID del creator
            chunks = db.query(RAGDocument).filter(RAGDocument.creator_id == creator.id).all()

            if not chunks:
                logger.info(f"No RAG documents found for {creator_id}")
                return None

            result = []
            for c in chunks:
                result.append(
                    {
                        "id": c.doc_id,
                        "chunk_id": c.doc_id,
                        "creator_id": creator_id,  # Usar el nombre, no el UUID
                        "source_type": c.source_type,
                        "source_id": c.content_type or "",  # Mapear content_type → source_id
                        "source_url": c.source_url,
                        "title": c.title,
                        "content": c.content,
                        "chunk_index": c.chunk_index or 0,
                        "total_chunks": c.total_chunks or 1,
                        "metadata": c.extra_data or {},
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                )

            if result:
                logger.info(f"Loaded {len(result)} RAG documents from PostgreSQL for {creator_id}")
            return result
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"DB read failed for RAG documents, will try JSON: {e}")
    return None


def _try_load_chunks_from_json(creator_id: str) -> Optional[List[dict]]:
    """Intenta cargar chunks desde archivo JSON."""
    chunks_path = Path(f"data/content_index/{creator_id}/chunks.json")
    if chunks_path.exists():
        try:
            with open(chunks_path, "r", encoding="utf-8") as f:
                chunks = json.load(f)
            logger.info(f"Loaded {len(chunks)} chunks from JSON for {creator_id}")
            return chunks
        except Exception as e:
            logger.error(f"Error loading chunks from JSON: {e}")
    return None


def _save_chunks_to_db(creator_id: str, chunks_data: List[dict]) -> bool:
    """Guarda chunks en PostgreSQL usando llamada sincrónica."""
    try:
        from api.database import SessionLocal
        from api.models import ContentChunk

        if SessionLocal is None:
            return False

        db = SessionLocal()
        try:
            saved_count = 0
            for chunk in chunks_data:
                # Check if exists
                existing = (
                    db.query(ContentChunk)
                    .filter(ContentChunk.chunk_id == chunk.get("id", chunk.get("chunk_id")))
                    .first()
                )

                if existing:
                    # Update
                    existing.content = chunk.get("content", "")
                    existing.title = chunk.get("title")
                    existing.source_url = chunk.get("source_url")
                else:
                    # Insert
                    new_chunk = ContentChunk(
                        chunk_id=chunk.get("id", chunk.get("chunk_id")),
                        creator_id=creator_id,
                        source_type=chunk.get("source_type", "instagram_post"),
                        source_id=chunk.get("source_id"),
                        source_url=chunk.get("source_url"),
                        title=chunk.get("title"),
                        content=chunk.get("content", ""),
                        chunk_index=chunk.get("chunk_index", 0),
                        total_chunks=chunk.get("total_chunks", 1),
                    )
                    db.add(new_chunk)
                saved_count += 1

            db.commit()

            if saved_count > 0:
                logger.info(f"Saved {saved_count} chunks to PostgreSQL for {creator_id}")
                return True
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error saving chunks to DB: {e}")
    return False


def _save_chunks_to_json(creator_id: str, chunks_data: List[dict], posts_metadata: dict) -> bool:
    """Guarda chunks y metadata en JSON (backup)."""
    try:
        index_dir = Path(f"data/content_index/{creator_id}")
        index_dir.mkdir(parents=True, exist_ok=True)

        with open(index_dir / "chunks.json", "w", encoding="utf-8") as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=2)

        # Serializar fechas en posts_metadata
        posts_serializable = {}
        for pid, meta in posts_metadata.items():
            meta_copy = meta.copy()
            if meta_copy.get("published_date"):
                meta_copy["published_date"] = (
                    meta_copy["published_date"].isoformat()
                    if isinstance(meta_copy["published_date"], datetime)
                    else meta_copy["published_date"]
                )
            posts_serializable[pid] = meta_copy

        with open(index_dir / "posts.json", "w", encoding="utf-8") as f:
            json.dump(posts_serializable, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        logger.error(f"Error saving to JSON: {e}")
        return False


class CreatorContentIndex:
    """
    Indice de contenido de un creador.
    Version simple sin FAISS (para integracion rapida).

    MIGRADO: Usa PostgreSQL con fallback a JSON.
    """

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        self.chunks: List[ContentChunk] = []
        self.posts_metadata: Dict[str, Dict] = {}  # post_id -> metadata
        self._loaded = False
        self._loaded_from_db = False

    def add_post(
        self,
        post_id: str,
        caption: str,
        post_type: str = "instagram_post",
        url: Optional[str] = None,
        published_date: Optional[datetime] = None,
        **metadata,
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
            title=metadata.get("title"),
            metadata={
                "published_date": published_date.isoformat() if published_date else None,
                **metadata,
            },
        )

        self.chunks.extend(chunks)

        # Guardar metadata del post
        self.posts_metadata[post_id] = {
            "post_id": post_id,
            "caption": caption,
            "post_type": post_type,
            "url": url,
            "published_date": published_date,
            "chunk_count": len(chunks),
            **metadata,
        }

        logger.info(f"Added post {post_id} with {len(chunks)} chunks to index")
        return chunks

    def search(
        self, query: str, max_results: int = 5, min_relevance: float = 0.25
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
            title_normalized = normalize_text(chunk.title or "")
            combined_text = f"{content_normalized} {title_normalized}"

            matches = sum(1 for kw in keywords if kw in combined_text)

            if matches > 0:
                relevance = matches / len(keywords)

                if relevance >= min_relevance:
                    # Obtener metadata del post original
                    post_meta = self.posts_metadata.get(chunk.source_id, {})

                    results.append(
                        {
                            "chunk_id": chunk.id,
                            "source_type": chunk.source_type,
                            "source_id": chunk.source_id,
                            "source_url": chunk.source_url,
                            "title": chunk.title,
                            "content": chunk.content,
                            "relevance_score": relevance,
                            "published_date": post_meta.get("published_date"),
                            "platform": "instagram",
                        }
                    )

        # Ordenar por relevancia y limitar
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:max_results]

    def save(self) -> bool:
        """
        Guarda el indice.
        Guarda en: 1) PostgreSQL (principal), 2) JSON (backup)
        """
        # Preparar datos
        chunks_data = [
            {
                "id": c.id,
                "creator_id": c.creator_id,
                "source_type": c.source_type,
                "source_id": c.source_id,
                "source_url": c.source_url,
                "title": c.title,
                "content": c.content,
                "chunk_index": c.chunk_index,
                "total_chunks": c.total_chunks,
                "metadata": c.metadata,  # Use dataclass attribute (not SQLAlchemy extra_data)
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in self.chunks
        ]

        db_success = _save_chunks_to_db(self.creator_id, chunks_data)
        json_success = _save_chunks_to_json(self.creator_id, chunks_data, self.posts_metadata)

        if db_success:
            logger.info(
                f"Saved index for {self.creator_id} to PostgreSQL: {len(self.chunks)} chunks"
            )
        if json_success:
            logger.info(
                f"Saved index for {self.creator_id} to JSON (backup): {len(self.chunks)} chunks"
            )

        return db_success or json_success

    def load(self) -> bool:
        """
        Carga el indice.
        Busca en: 1) PostgreSQL, 2) JSON (fallback)
        """
        if self._loaded:
            return True

        chunks_data = None

        # 1. Intentar PostgreSQL
        chunks_data = _try_load_chunks_from_db(self.creator_id)
        if chunks_data:
            self._loaded_from_db = True

        # 2. Fallback a JSON
        if not chunks_data:
            chunks_data = _try_load_chunks_from_json(self.creator_id)

        if not chunks_data:
            return False

        # Convertir a ContentChunk objects
        self.chunks = [
            ContentChunk(
                id=c.get("id", c.get("chunk_id", "")),
                creator_id=c.get("creator_id", self.creator_id),
                source_type=c.get("source_type"),
                source_id=c.get("source_id"),
                source_url=c.get("source_url"),
                title=c.get("title"),
                content=c.get("content", ""),
                chunk_index=c.get("chunk_index", 0),
                total_chunks=c.get("total_chunks", 1),
                metadata=c.get("metadata", {}),
                created_at=datetime.fromisoformat(c["created_at"]) if c.get("created_at") else None,
            )
            for c in chunks_data
        ]

        # Cargar metadata de posts (solo de JSON)
        posts_path = Path(f"data/content_index/{self.creator_id}/posts.json")
        if posts_path.exists():
            try:
                with open(posts_path, "r", encoding="utf-8") as f:
                    self.posts_metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load posts metadata: {e}")

        self._loaded = True
        source = "PostgreSQL" if self._loaded_from_db else "JSON"
        logger.info(f"Loaded index for {self.creator_id} from {source}: {len(self.chunks)} chunks")
        return True

    @property
    def stats(self) -> Dict:
        """Estadisticas del indice."""
        return {
            "creator_id": self.creator_id,
            "total_chunks": len(self.chunks),
            "total_posts": len(self.posts_metadata),
            "loaded": self._loaded,
            "loaded_from_db": self._loaded_from_db,
        }


# Cache de indices
_index_cache: Dict[str, CreatorContentIndex] = {}


def get_content_index(creator_id: str) -> CreatorContentIndex:
    """Obtiene o crea el indice de contenido de un creador."""
    if creator_id not in _index_cache:
        index = CreatorContentIndex(creator_id)
        index.load()  # Intentar cargar (DB primero, luego JSON)
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
    creator_id: str, query: str, max_results: int = 3, min_relevance: float = 0.4
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
    search_results = index.search(query=query, max_results=max_results, min_relevance=min_relevance)

    # Convertir a Citations
    citations = []
    for result in search_results:
        # Mapear tipo
        content_type_map = {
            "instagram_post": ContentType.INSTAGRAM_POST,
            "instagram_reel": ContentType.INSTAGRAM_REEL,
            "youtube_video": ContentType.YOUTUBE_VIDEO,
            "podcast_episode": ContentType.PODCAST_EPISODE,
            "pdf_ebook": ContentType.PDF_EBOOK,
            "faq": ContentType.FAQ,
        }

        content_type = content_type_map.get(
            result.get("source_type", "instagram_post"), ContentType.INSTAGRAM_POST
        )

        # Parsear fecha si existe
        published_date = None
        if result.get("published_date"):
            try:
                if isinstance(result["published_date"], str):
                    published_date = datetime.fromisoformat(result["published_date"])
                else:
                    published_date = result["published_date"]
            except Exception:
                pass

        citation = Citation(
            content_type=content_type,
            source_id=result["source_id"],
            source_url=result.get("source_url"),
            title=result.get("title"),
            excerpt=result["content"],
            relevance_score=result["relevance_score"],
            published_date=published_date,
            platform=result.get("platform", "instagram"),
        )
        citations.append(citation)

    return CitationContext(query=query, citations=citations, max_citations=max_results)


def get_citation_prompt_section(creator_id: str, query: str, min_relevance: float = 0.25) -> str:
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
        search_results = index.search(query=query, max_results=3, min_relevance=min_relevance)

        if not search_results:
            return ""

        # Convertir a Citations para generar contexto
        citations = []
        for result in search_results:
            content_type_map = {
                "instagram_post": ContentType.INSTAGRAM_POST,
                "instagram_reel": ContentType.INSTAGRAM_REEL,
                "youtube_video": ContentType.YOUTUBE_VIDEO,
                "podcast_episode": ContentType.PODCAST_EPISODE,
                "pdf_ebook": ContentType.PDF_EBOOK,
                "faq": ContentType.FAQ,
            }

            content_type = content_type_map.get(
                result.get("source_type", "instagram_post"), ContentType.INSTAGRAM_POST
            )

            # Parsear fecha si existe
            published_date = None
            if result.get("published_date"):
                try:
                    if isinstance(result["published_date"], str):
                        published_date = datetime.fromisoformat(result["published_date"])
                    else:
                        published_date = result["published_date"]
                except Exception:
                    pass

            citation = Citation(
                content_type=content_type,
                source_id=result["source_id"],
                source_url=result.get("source_url"),
                title=result.get("title"),
                excerpt=result["content"],
                relevance_score=result["relevance_score"],
                published_date=published_date,
                platform=result.get("platform", "instagram"),
            )
            citations.append(citation)

        citation_context = CitationContext(query=query, citations=citations, max_citations=3)

        # Verificar si hay contenido relevante
        if not citation_context.has_relevant_content(min_score=min_relevance):
            return ""

        return citation_context.to_prompt_context()

    except Exception as e:
        logger.error(f"Error getting citation prompt: {e}")
        return ""


async def index_creator_posts(creator_id: str, posts: List[Dict], save: bool = True) -> Dict:
    """
    Indexa posts de un creador.
    Guarda en PostgreSQL + JSON backup.

    Args:
        creator_id: ID del creador
        posts: Lista de posts con caption, post_id, etc.
        save: Si guardar en disco/DB

    Returns:
        Estadisticas de indexacion
    """
    logger.debug(f"[index_creator_posts] Starting for {creator_id} with {len(posts)} posts")

    # Start tracking metrics
    start_ingestion(creator_id)

    index = get_content_index(creator_id)
    logger.debug("[index_creator_posts] Got content index")

    total_chunks = 0
    posts_processed = 0
    for post in posts:
        caption = post.get("caption", "")
        if len(caption) < 20:  # Ignorar posts muy cortos
            continue

        # Parsear fecha si viene como string
        published_date = post.get("published_date") or post.get("timestamp")
        if isinstance(published_date, str):
            try:
                published_date = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
            except Exception:
                published_date = None

        chunks = index.add_post(
            post_id=post.get("post_id", post.get("id", str(hash(caption))[:10])),
            caption=caption,
            post_type=post.get("post_type", "instagram_post"),
            url=post.get("url") or post.get("permalink"),
            published_date=published_date,
            likes=post.get("likes_count"),
            comments=post.get("comments_count"),
        )
        total_chunks += len(chunks)
        posts_processed += 1

    logger.debug(f"[index_creator_posts] Processed {posts_processed} posts, {total_chunks} chunks")

    if save:
        # TEMPORARY: Skip save to avoid N+1 query timeout (1000+ chunks = 2000+ DB queries)
        # TODO: Fix _save_chunks_to_db to use bulk operations
        logger.debug(
            f"[index_creator_posts] SKIPPING index.save() - N+1 query issue causes timeout"
        )
        logger.debug(f"[index_creator_posts] Would save {len(index.chunks)} chunks")
        # index.save()  # DISABLED - causes worker timeout

    # Record metrics
    record_posts_indexed(creator_id, posts_processed)
    if total_chunks > 0:
        record_chunks_saved(creator_id, total_chunks, "instagram_post")

    # End ingestion tracking
    duration = end_ingestion(creator_id, total_chunks)

    result = {
        "creator_id": creator_id,
        "posts_indexed": posts_processed,
        "total_chunks": total_chunks,
        "index_stats": index.stats,
    }

    # Log structured summary
    log_ingestion_complete(
        creator_id=creator_id,
        posts_indexed=posts_processed,
        chunks_saved=total_chunks,
        duration_seconds=duration
    )

    logger.info(f"[index_creator_posts] Done: {result}")
    return result


def delete_content_index(creator_id: str) -> bool:
    """
    Elimina el indice de contenido de un creador.
    Elimina de PostgreSQL y JSON.

    Args:
        creator_id: ID del creador

    Returns:
        True si se elimino de algún lugar
    """
    import shutil

    deleted_any = False

    # 1. Eliminar de PostgreSQL (sync call)
    try:
        from api.database import SessionLocal
        from api.models import ContentChunk

        if SessionLocal:
            db = SessionLocal()
            try:
                deleted_count = (
                    db.query(ContentChunk).filter(ContentChunk.creator_id == creator_id).delete()
                )
                db.commit()

                if deleted_count > 0:
                    logger.info(f"Deleted {deleted_count} chunks from PostgreSQL for {creator_id}")
                    deleted_any = True
            finally:
                db.close()
    except Exception as e:
        logger.warning(f"Could not delete from DB: {e}")

    # 2. Eliminar de JSON
    index_dir = Path(f"data/content_index/{creator_id}")
    if index_dir.exists():
        shutil.rmtree(index_dir)
        logger.info(f"Deleted content index JSON for {creator_id}")
        deleted_any = True

    # 3. Limpiar cache
    if creator_id in _index_cache:
        del _index_cache[creator_id]

    return deleted_any
