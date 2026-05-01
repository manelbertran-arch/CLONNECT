"""
Gemini Embeddings Service for Semantic Search

Uses gemini-embedding-001 (1536 dimensions via outputDimensionality) with pgvector for storage.
Migrated from OpenAI text-embedding-3-small in Sprint 2bis (OpenAI removal).
Embeddings persist in PostgreSQL - no regeneration on deploy.
"""

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# Gemini embedding model config
# gemini-embedding-001: native 3072 dims, supports MRL truncation to 1536
# (text-embedding-004 has native 768 dims — cannot upscale to 1536)
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSIONS = 1536  # matches pgvector schema — no reindex needed

_GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-embedding-001:embedContent"
)

# Embedding cache: avoid repeated Gemini API calls for same query
# Bounded to prevent memory leaks (each embedding = 1536 floats ≈ 12KB)
from core.cache import BoundedTTLCache
_embedding_cache = BoundedTTLCache(max_size=200, ttl_seconds=600)
EMBEDDING_CACHE_TTL = 600  # 10 minutes

# Similarity threshold for semantic search
# Set to 0.35 — context.py adaptive threshold handles final cutoff:
#   top_score >= 0.5 → high confidence (top 3)
#   top_score 0.40-0.5 → medium confidence (top 1)
#   top_score < 0.40 → skip injection entirely
DEFAULT_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.35"))


def _get_gemini_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def generate_embedding(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> Optional[List[float]]:
    """
    Generate embedding for a single text using Gemini gemini-embedding-001.
    Results are cached in-memory with TTL to avoid repeated API calls.

    Args:
        text: Text to embed
        task_type: Gemini task type — RETRIEVAL_DOCUMENT (default, for stored docs),
                   RETRIEVAL_QUERY (for search queries), SEMANTIC_SIMILARITY, etc.

    Returns:
        List of 1536 floats, or None if failed
    """
    if not text or not text.strip():
        return None

    # Include task_type in cache key to avoid cross-task pollution
    cache_key = f"{task_type}:{text.strip().lower()}"
    cached = _embedding_cache.get(cache_key)
    if cached is not None:
        logger.info(f"[EMBEDDING] Cache hit: '{text[:50]}'")
        return cached

    api_key = _get_gemini_api_key()
    if not api_key:
        logger.warning("GOOGLE_API_KEY/GEMINI_API_KEY not set, embeddings disabled")
        return None

    try:
        max_chars = 30000
        if len(text) > max_chars:
            text = text[:max_chars]

        payload = {
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBEDDING_DIMENSIONS,
            "taskType": task_type,
        }

        resp = httpx.post(
            _GEMINI_EMBED_URL,
            params={"key": api_key},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()

        embedding: List[float] = resp.json()["embedding"]["values"]
        _embedding_cache.set(cache_key, embedding)
        logger.info(f"[EMBEDDING] Generated (Gemini): '{text[:50]}'")
        return embedding

    except Exception as e:
        logger.error(f"Error generating embedding (Gemini): {e}")
        return None


def generate_embeddings_batch(
    texts: List[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts (sequential calls with caching).

    Args:
        texts: List of texts to embed
        task_type: Gemini task type (same for all items in the batch)

    Returns:
        List of embeddings (or None for failed items)
    """
    return [generate_embedding(text, task_type=task_type) for text in texts]


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    import math

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


# =============================================================================
# pgvector Database Operations
# =============================================================================


def ensure_pgvector_extension():
    """
    Verify pgvector extension is available.

    NOTE: The extension is pre-installed in Neon. We skip CREATE EXTENSION
    to avoid connection pooler limitations. Just verify it works.
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        if SessionLocal is None:
            logger.warning("No database configured")
            return False

        db = SessionLocal()
        try:
            # Just verify the table exists (extension must be enabled if table exists)
            db.execute(text("SELECT COUNT(*) FROM content_embeddings LIMIT 1"))
            logger.info("pgvector extension verified (content_embeddings table exists)")
            return True
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"pgvector not verified (table may not exist yet): {e}")
        return False


def store_embedding(chunk_id: str, creator_id: str, content: str, embedding: List[float]) -> bool:
    """
    Store embedding in PostgreSQL using pgvector.

    Args:
        chunk_id: Unique ID for the content chunk
        creator_id: Creator this content belongs to
        content: The text content (for reference)
        embedding: The embedding vector (1536 floats)

    Returns:
        True if stored successfully
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        if SessionLocal is None:
            return False

        db = SessionLocal()
        try:
            # Convert embedding to pgvector format with strict validation
            # Validate that all values are actual floats to prevent SQL injection
            validated_floats = []
            for val in embedding:
                f = float(val)  # Raises ValueError/TypeError if not numeric
                validated_floats.append(f)
            embedding_str = "[" + ",".join(str(x) for x in validated_floats) + "]"

            # Upsert embedding - use CAST() instead of ::vector to avoid
            # SQLAlchemy interpreting :: as a bind parameter delimiter
            db.execute(
                text(
                    """
                INSERT INTO content_embeddings (chunk_id, creator_id, content_preview, embedding)
                VALUES (:chunk_id, :creator_id, :content_preview, CAST(:embedding AS vector))
                ON CONFLICT (chunk_id) DO UPDATE SET
                    embedding = CAST(:embedding AS vector),
                    updated_at = NOW()
            """
                ),
                {
                    "chunk_id": chunk_id,
                    "creator_id": creator_id,
                    "content_preview": content[:500],  # Store preview for debugging
                    "embedding": embedding_str,
                },
            )
            db.commit()
            return True

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to store embedding: {e}")
        # Re-raise to allow caller to see the actual error
        raise


def search_similar(
    query_embedding: List[float], creator_id: str, top_k: int = 5, min_similarity: float = None
) -> List[dict]:
    """
    Search for similar content using pgvector cosine similarity.

    Args:
        query_embedding: Query vector (1536 floats)
        creator_id: Filter by creator
        top_k: Maximum results
        min_similarity: Minimum similarity threshold (0-1). Default: RAG_MIN_SIMILARITY env var or 0.35

    Returns:
        List of {chunk_id, content, similarity} dicts
    """
    # Use default from env var if not specified
    if min_similarity is None:
        min_similarity = DEFAULT_MIN_SIMILARITY

    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        if SessionLocal is None:
            return []

        db = SessionLocal()
        try:
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # Use pgvector's <=> operator for cosine distance
            # Cosine similarity = 1 - cosine distance
            # Use CAST() instead of ::vector to avoid SQLAlchemy bind param conflict
            results = db.execute(
                text(
                    """
                SELECT
                    e.chunk_id,
                    c.content,
                    c.source_url,
                    c.title,
                    c.source_type,
                    1 - (e.embedding <=> CAST(:query AS vector)) as similarity
                FROM content_embeddings e
                JOIN content_chunks c ON e.chunk_id = c.chunk_id
                WHERE e.creator_id = :creator_id
                    AND 1 - (e.embedding <=> CAST(:query AS vector)) >= :min_sim
                ORDER BY e.embedding <=> CAST(:query AS vector)
                LIMIT :top_k
            """
                ),
                {
                    "query": embedding_str,
                    "creator_id": creator_id,
                    "min_sim": min_similarity,
                    "top_k": top_k,
                },
            )

            return [
                {
                    "chunk_id": row.chunk_id,
                    "content": row.content,
                    "source_url": row.source_url,
                    "title": row.title,
                    "source_type": row.source_type,
                    "similarity": float(row.similarity),
                }
                for row in results
            ]

        finally:
            db.close()

    except Exception as e:
        logger.error(f"pgvector search failed: {e}")
        return []


def get_embedding_stats(creator_id: str = None) -> dict:
    """Get statistics about stored embeddings."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        if SessionLocal is None:
            return {"error": "No database"}

        db = SessionLocal()
        try:
            if creator_id:
                result = db.execute(
                    text(
                        """
                    SELECT COUNT(*) as count FROM content_embeddings
                    WHERE creator_id = :creator_id
                """
                    ),
                    {"creator_id": creator_id},
                )
            else:
                result = db.execute(text("SELECT COUNT(*) as count FROM content_embeddings"))

            row = result.fetchone()
            return {
                "embeddings_count": row.count if row else 0,
                "creator_id": creator_id,
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
            }

        finally:
            db.close()

    except Exception as e:
        return {"error": str(e)}
