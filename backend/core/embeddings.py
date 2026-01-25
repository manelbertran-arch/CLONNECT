"""
OpenAI Embeddings Service for Semantic Search

Uses text-embedding-3-small (1536 dimensions) with pgvector for storage.
Embeddings persist in PostgreSQL - no regeneration on deploy.
"""

import os
import logging
from typing import List, Optional
import hashlib

logger = logging.getLogger(__name__)

# OpenAI embedding model config
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Similarity threshold for semantic search
# Raised from 0.3 to 0.5 to reduce noise in RAG results
# Lower values = more results but less relevant
# Higher values = fewer results but more precise
DEFAULT_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.5"))


def get_openai_client():
    """Get OpenAI client lazily."""
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, embeddings disabled")
            return None
        return OpenAI(api_key=api_key)
    except ImportError:
        logger.warning("openai package not installed")
        return None


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding for a single text using OpenAI API.

    Args:
        text: Text to embed (max ~8000 tokens for text-embedding-3-small)

    Returns:
        List of 1536 floats, or None if failed
    """
    client = get_openai_client()
    if not client:
        return None

    try:
        # Truncate if too long (rough estimate: 1 token ≈ 4 chars)
        max_chars = 30000  # ~7500 tokens, safe limit
        if len(text) > max_chars:
            text = text[:max_chars]

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )

        embedding = response.data[0].embedding
        logger.debug(f"Generated embedding: {len(embedding)} dimensions")
        return embedding

    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return None


def generate_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in a single API call.
    More efficient than calling generate_embedding() in a loop.

    Args:
        texts: List of texts to embed

    Returns:
        List of embeddings (or None for failed items)
    """
    client = get_openai_client()
    if not client:
        return [None] * len(texts)

    try:
        # Truncate each text
        max_chars = 30000
        truncated = [t[:max_chars] if len(t) > max_chars else t for t in texts]

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=truncated
        )

        # Map results by index
        embeddings = [None] * len(texts)
        for item in response.data:
            embeddings[item.index] = item.embedding

        logger.info(f"Generated {len([e for e in embeddings if e])} embeddings in batch")
        return embeddings

    except Exception as e:
        logger.error(f"Error generating batch embeddings: {e}")
        return [None] * len(texts)


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
            result = db.execute(text("SELECT COUNT(*) FROM content_embeddings LIMIT 1"))
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
            # Convert embedding to pgvector format
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            # Upsert embedding - use string formatting for the vector since
            # psycopg2 doesn't handle the ::vector cast well with parameters
            db.execute(text(f"""
                INSERT INTO content_embeddings (chunk_id, creator_id, content_preview, embedding)
                VALUES (:chunk_id, :creator_id, :content_preview, '{embedding_str}'::vector)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    embedding = '{embedding_str}'::vector,
                    updated_at = NOW()
            """), {
                "chunk_id": chunk_id,
                "creator_id": creator_id,
                "content_preview": content[:500]  # Store preview for debugging
            })
            db.commit()
            return True

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to store embedding: {e}")
        # Re-raise to allow caller to see the actual error
        raise


def search_similar(
    query_embedding: List[float],
    creator_id: str,
    top_k: int = 5,
    min_similarity: float = None
) -> List[dict]:
    """
    Search for similar content using pgvector cosine similarity.

    Args:
        query_embedding: Query vector (1536 floats)
        creator_id: Filter by creator
        top_k: Maximum results
        min_similarity: Minimum similarity threshold (0-1). Default: RAG_MIN_SIMILARITY env var or 0.5

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
            results = db.execute(text("""
                SELECT
                    e.chunk_id,
                    c.content,
                    c.source_url,
                    c.title,
                    c.source_type,
                    1 - (e.embedding <=> :query::vector) as similarity
                FROM content_embeddings e
                JOIN content_chunks c ON e.chunk_id = c.chunk_id
                WHERE e.creator_id = :creator_id
                    AND 1 - (e.embedding <=> :query::vector) >= :min_sim
                ORDER BY e.embedding <=> :query::vector
                LIMIT :top_k
            """), {
                "query": embedding_str,
                "creator_id": creator_id,
                "min_sim": min_similarity,
                "top_k": top_k
            })

            return [
                {
                    "chunk_id": row.chunk_id,
                    "content": row.content,
                    "source_url": row.source_url,
                    "title": row.title,
                    "source_type": row.source_type,
                    "similarity": float(row.similarity)
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
                result = db.execute(text("""
                    SELECT COUNT(*) as count FROM content_embeddings
                    WHERE creator_id = :creator_id
                """), {"creator_id": creator_id})
            else:
                result = db.execute(text("SELECT COUNT(*) as count FROM content_embeddings"))

            row = result.fetchone()
            return {
                "embeddings_count": row.count if row else 0,
                "creator_id": creator_id,
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS
            }

        finally:
            db.close()

    except Exception as e:
        return {"error": str(e)}
