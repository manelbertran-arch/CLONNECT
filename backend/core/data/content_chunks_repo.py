"""
Content Chunks repository — PostgreSQL persistence for RAG chunks.

Domain
------
Stores text chunks derived from creator content (Instagram captions, YouTube
transcripts, etc.) alongside their metadata and source references. Downstream
the retrieval layer (Self-RAG gate) reads these rows; embeddings (pgvector
column) are managed by the ingestion pipeline outside this module.

Pipeline phase
--------------
INGESTIÓN batch. Written by `ingestion/v2/instagram_ingestion.py`,
`ingestion/v2/youtube_ingestion.py`, and the feed webhook handler. Never
written from the DM hot path.

Storage
-------
Table: `content_chunks` (SQLAlchemy model `api.models.ContentChunk`).
Natural key: `(creator_id, chunk_id)`.
Note: the domain column was renamed `metadata` → `extra_data` on 2026-01-10
(commit 0264a352) because `metadata` is reserved by SQLAlchemy.

Public accessors
----------------
- save_content_chunks_db(creator_id, chunks)                    -> int (rows processed)
- get_content_chunks_db(creator_id)                             -> List[dict]
- delete_content_chunks_db(creator_id, source_type=None)        -> int (rows deleted)

Notes
-----
- No in-memory cache — chunks are loaded in bulk by the retrieval layer which
  manages its own index-level cache.
- Error contract: on exception, `save` and `delete` return 0, `get` returns [].
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


async def save_content_chunks_db(creator_id: str, chunks: List[dict]) -> int:
    """Upsert content chunks for a creator. Returns count of rows processed."""
    try:
        from api.database import get_db_session
        from api.models import ContentChunk

        saved_count = 0

        with get_db_session() as db:
            for chunk in chunks:
                chunk_id = chunk.get("id", chunk.get("chunk_id", ""))
                existing = db.query(ContentChunk).filter(
                    ContentChunk.creator_id == creator_id,
                    ContentChunk.chunk_id == chunk_id,
                ).first()

                if existing:
                    existing.content = chunk.get("content", "")
                    existing.source_type = chunk.get("source_type")
                    existing.source_id = chunk.get("source_id")
                    existing.source_url = chunk.get("source_url")
                    existing.title = chunk.get("title")
                    existing.chunk_index = chunk.get("chunk_index", 0)
                    existing.total_chunks = chunk.get("total_chunks", 1)
                    existing.extra_data = chunk.get("metadata", {})
                else:
                    new_chunk = ContentChunk(
                        creator_id=creator_id,
                        chunk_id=chunk_id,
                        content=chunk.get("content", ""),
                        source_type=chunk.get("source_type"),
                        source_id=chunk.get("source_id"),
                        source_url=chunk.get("source_url"),
                        title=chunk.get("title"),
                        chunk_index=chunk.get("chunk_index", 0),
                        total_chunks=chunk.get("total_chunks", 1),
                        extra_data=chunk.get("metadata", {}),
                    )
                    db.add(new_chunk)

                saved_count += 1

            db.commit()
            logger.info("Saved %d content chunks to DB for %s", saved_count, creator_id)

        return saved_count

    except Exception as e:
        logger.error("Error saving content chunks to DB: %s", e)
        return 0


async def get_content_chunks_db(creator_id: str) -> List[dict]:
    """Get all content chunks for a creator."""
    try:
        from api.database import get_db_session
        from api.models import ContentChunk

        with get_db_session() as db:
            chunks = db.query(ContentChunk).filter(
                ContentChunk.creator_id == creator_id
            ).all()

            result = []
            for c in chunks:
                result.append({
                    "id": c.chunk_id,
                    "creator_id": c.creator_id,
                    "content": c.content,
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                    "source_url": c.source_url,
                    "title": c.title,
                    "chunk_index": c.chunk_index,
                    "total_chunks": c.total_chunks,
                    "metadata": c.extra_data or {},  # DB col is extra_data; API shape is "metadata"
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                })

            logger.info("Loaded %d content chunks from DB for %s", len(result), creator_id)
            return result

    except Exception as e:
        logger.error("Error loading content chunks from DB: %s", e)
        return []


async def delete_content_chunks_db(
    creator_id: str,
    source_type: Optional[str] = None,
) -> int:
    """Delete chunks for a creator. Optional `source_type` filter (e.g. 'youtube')."""
    try:
        from api.database import get_db_session
        from api.models import ContentChunk

        with get_db_session() as db:
            query = db.query(ContentChunk).filter(
                ContentChunk.creator_id == creator_id
            )

            if source_type:
                query = query.filter(ContentChunk.source_type == source_type)

            deleted = query.delete()

            db.commit()
            type_info = f" (source_type={source_type})" if source_type else ""
            logger.info("Deleted %d content chunks from DB for %s%s", deleted, creator_id, type_info)
            return deleted

    except Exception as e:
        logger.error("Error deleting content chunks from DB: %s", e)
        return 0
