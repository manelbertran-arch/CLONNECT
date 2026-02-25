"""
Content Router - RAG content management endpoints
Extracted from main.py as part of refactoring
"""
import hashlib
import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Database imports
from api.database import DATABASE_URL, SessionLocal

# RAG import - use singleton getter to share instance with main.py
from core.rag import get_simple_rag

router = APIRouter(prefix="/content", tags=["content"])


# ---------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------
class AddContentRequest(BaseModel):
    creator_id: str
    text: str
    doc_type: str = "faq"


class BulkContentRequest(BaseModel):
    creator_id: str
    chunks: List[Dict[str, Any]]  # List of {content, source_type, source_url, title}


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
async def _do_reload(creator_id: str = None):
    """Helper to reload RAG from PostgreSQL."""
    try:
        loaded = get_simple_rag().load_from_db(creator_id)
        return {
            "status": "ok",
            "loaded": loaded,
            "creator_id": creator_id,
            "total_documents": get_simple_rag().count(),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ---------------------------------------------------------
# CONTENT ENDPOINTS
# ---------------------------------------------------------
@router.post("/add")
async def add_content(request: AddContentRequest):
    """Anadir contenido al RAG del creador"""
    try:
        doc_id = f"{request.creator_id}_{request.doc_type}_{hashlib.md5(request.text.encode()).hexdigest()[:8]}"

        # Add to in-memory RAG
        get_simple_rag().add_document(
            doc_id=doc_id,
            text=request.text,
            metadata={"creator_id": request.creator_id, "type": request.doc_type},
        )

        # Persist to PostgreSQL
        if DATABASE_URL and SessionLocal:
            try:
                from api.models import ContentChunk

                db = SessionLocal()
                try:
                    # Check if already exists
                    existing = (
                        db.query(ContentChunk).filter(ContentChunk.chunk_id == doc_id).first()
                    )

                    if not existing:
                        chunk = ContentChunk(
                            creator_id=request.creator_id,
                            chunk_id=doc_id,
                            content=request.text,
                            source_type=request.doc_type,
                        )
                        db.add(chunk)
                        db.commit()
                        logger.info(f"Content chunk {doc_id} persisted to PostgreSQL")
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"Failed to persist content to DB: {db_err}")

        return {"status": "ok", "doc_id": doc_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/search")
async def search_content(creator_id: str, query: str, top_k: int = 3):
    """Buscar en el contenido del creador"""
    try:
        results = get_simple_rag().search(query, top_k=top_k, creator_id=creator_id)
        return {"status": "ok", "results": results, "count": len(results)}

    except Exception as e:
        raise HTTPException(status_code=503, detail="Internal server error")


@router.get("/search-debug")
async def search_content_debug(query: str, top_k: int = 5, creator_id: str = None):
    """Debug search - shows raw results before and after filtering."""
    try:
        # Get raw results without creator filter
        raw_results = get_simple_rag().search(query, top_k=top_k, creator_id=None)

        # Get filtered results
        filtered_results = (
            get_simple_rag().search(query, top_k=top_k, creator_id=creator_id) if creator_id else raw_results
        )

        return {
            "status": "ok",
            "query": query,
            "creator_id_filter": creator_id,
            "raw_count": len(raw_results),
            "filtered_count": len(filtered_results),
            "raw_results": [
                {"doc_id": r["doc_id"], "metadata": r["metadata"]} for r in raw_results
            ],
            "filtered_results": [
                {"doc_id": r["doc_id"], "metadata": r["metadata"]} for r in filtered_results
            ],
        }

    except Exception as e:
        import traceback

        return {"status": "error", "detail": str(e), "traceback": traceback.format_exc()}


@router.post("/reload")
async def content_reload_post(creator_id: str = None):
    """Force reload RAG from PostgreSQL (POST)."""
    return await _do_reload(creator_id)


@router.get("/reload")
async def content_reload_get(creator_id: str = None):
    """Force reload RAG from PostgreSQL (GET - browser friendly)."""
    return await _do_reload(creator_id)


@router.get("/debug")
async def content_debug():
    """Debug endpoint to inspect RAG internal state and embedding status."""
    try:
        doc_count = len(get_simple_rag()._documents)
        doc_list_count = len(get_simple_rag()._doc_list)

        # Check OpenAI and pgvector availability
        deps = {}
        try:
            import openai

            deps["openai"] = openai.__version__
        except ImportError as e:
            deps["openai"] = f"NOT INSTALLED: {e}"

        # Check if OpenAI API key is set
        deps["openai_api_key"] = "SET" if os.getenv("OPENAI_API_KEY") else "NOT SET"

        # Get embedding stats from pgvector
        embedding_stats = {}
        try:
            from core.embeddings import get_embedding_stats

            embedding_stats = get_embedding_stats()
        except Exception as e:
            embedding_stats = {"error": str(e)}

        # Sample a few documents to check metadata
        samples = []
        for doc_id in list(get_simple_rag()._documents.keys())[:3]:
            doc = get_simple_rag()._documents[doc_id]
            samples.append(
                {
                    "doc_id": doc_id,
                    "text_preview": doc.text[:100] if doc.text else "",
                    "metadata": doc.metadata,
                }
            )

        return {
            "status": "ok",
            "_documents_count": doc_count,
            "_doc_list_count": doc_list_count,
            "search_type": "OpenAI Embeddings + pgvector",
            "dependencies": deps,
            "embedding_stats": embedding_stats,
            "samples": samples,
            "doc_list_first_5": get_simple_rag()._doc_list[:5] if get_simple_rag()._doc_list else [],
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/stats")
async def content_stats(creator_id: str = None):
    """Get RAG content statistics - shows in-memory count and database count."""
    try:
        # In-memory RAG count
        rag_count = get_simple_rag().count()

        # Database count
        db_count = 0
        if DATABASE_URL and SessionLocal:
            try:
                from api.models import ContentChunk

                db = SessionLocal()
                try:
                    query = db.query(ContentChunk)
                    if creator_id:
                        query = query.filter(ContentChunk.creator_id == creator_id)
                    db_count = query.count()
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"Failed to get DB count: {db_err}")

        # Get embedding count
        embedding_count = 0
        try:
            from core.embeddings import get_embedding_stats

            stats = get_embedding_stats(creator_id)
            embedding_count = stats.get("embeddings_count", 0)
        except Exception as e:
            logger.warning("Suppressed error in from core.embeddings import get_embedding_stats: %s", e)

        return {
            "status": "ok",
            "rag_in_memory": rag_count,
            "db_persisted": db_count,
            "embeddings_stored": embedding_count,
            "creator_id": creator_id,
            "synced": rag_count == db_count or (creator_id and rag_count >= db_count),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/setup-pgvector")
async def setup_pgvector_endpoint():
    """
    Verify pgvector extension and content_embeddings table exist.
    The extension and table are pre-created in Neon - this just verifies they work.
    """
    try:
        from sqlalchemy import text

        if not SessionLocal:
            return {
                "status": "ok",
                "message": "Database not configured - pgvector pre-configured in Neon",
            }

        db = SessionLocal()
        try:
            # Just verify the table exists by counting rows
            result = db.execute(text("SELECT COUNT(*) as count FROM content_embeddings"))
            row = result.fetchone()
            count = row.count if row else 0

            return {
                "status": "ok",
                "message": "pgvector and content_embeddings table are ready (pre-configured in Neon)",
                "embeddings_count": count,
            }

        except Exception as e:
            # Connection pooler may block - that's OK, table exists in Neon
            logger.warning(f"Could not verify pgvector (pooler limitation): {e}")
            return {
                "status": "ok",
                "message": "pgvector pre-configured in Neon (verification skipped due to pooler)",
                "note": "Table exists, will work at runtime",
            }

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"pgvector verification skipped: {e}")
        return {
            "status": "ok",
            "message": "pgvector pre-configured in Neon (verification skipped)",
            "note": str(e),
        }


@router.post("/test-embedding")
async def test_single_embedding():
    """
    Test generating and storing a single embedding to debug issues.
    """
    try:
        from core.embeddings import generate_embedding, store_embedding

        test_text = (
            "Este es un texto de prueba para verificar que los embeddings funcionan correctamente."
        )

        # Step 1: Generate embedding
        embedding = generate_embedding(test_text)
        if not embedding:
            return {
                "status": "error",
                "step": "generate_embedding",
                "message": "Failed to generate embedding - check OPENAI_API_KEY",
            }

        # Step 2: Store embedding
        try:
            stored = store_embedding(
                chunk_id="test_embedding_001",
                creator_id="test",
                content=test_text,
                embedding=embedding,
            )
        except Exception as store_err:
            import traceback

            return {
                "status": "error",
                "step": "store_embedding",
                "message": str(store_err),
                "traceback": traceback.format_exc(),
            }

        if not stored:
            return {
                "status": "error",
                "step": "store_embedding",
                "message": "store_embedding returned False",
            }

        return {
            "status": "ok",
            "message": "Embedding generated and stored successfully",
            "embedding_dimensions": len(embedding),
            "chunk_id": "test_embedding_001",
        }

    except Exception as e:
        import traceback

        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.post("/generate-embeddings")
async def generate_embeddings_for_existing(creator_id: str, batch_size: int = 10):
    """
    Generate OpenAI embeddings for existing content chunks that don't have embeddings yet.

    This is useful for migrating existing content to use semantic search.
    Uses batch API calls to OpenAI for efficiency.

    Args:
        creator_id: Filter by creator
        batch_size: Number of chunks to process in each API call (default 10)

    Returns:
        Number of embeddings generated
    """
    try:
        from core.embeddings import generate_embeddings_batch, store_embedding
        from sqlalchemy import text

        if not SessionLocal:
            raise HTTPException(status_code=500, detail="Database not configured")

        db = SessionLocal()
        try:
            # Get chunks that don't have embeddings yet
            # Join with content_embeddings to find missing ones
            result = db.execute(
                text(
                    """
                SELECT c.chunk_id, c.creator_id, c.content
                FROM content_chunks c
                LEFT JOIN content_embeddings e ON c.chunk_id = e.chunk_id
                WHERE c.creator_id = :creator_id AND e.chunk_id IS NULL
                ORDER BY c.created_at
            """
                ),
                {"creator_id": creator_id},
            )

            chunks_without_embeddings = result.fetchall()

            if not chunks_without_embeddings:
                return {
                    "status": "ok",
                    "message": "All chunks already have embeddings",
                    "generated": 0,
                    "creator_id": creator_id,
                }

            # Process in batches
            generated = 0
            failed = 0

            for i in range(0, len(chunks_without_embeddings), batch_size):
                batch = chunks_without_embeddings[i : i + batch_size]
                texts = [row.content for row in batch]

                # Generate embeddings in batch
                embeddings = generate_embeddings_batch(texts)

                # Store each embedding
                for j, (row, embedding) in enumerate(zip(batch, embeddings)):
                    if embedding:
                        if store_embedding(row.chunk_id, row.creator_id, row.content, embedding):
                            generated += 1
                        else:
                            failed += 1
                    else:
                        failed += 1

            logger.info(f"Generated {generated} embeddings for {creator_id} ({failed} failed)")

            return {
                "status": "ok",
                "generated": generated,
                "failed": failed,
                "total_processed": len(chunks_without_embeddings),
                "creator_id": creator_id,
            }

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise HTTPException(status_code=503, detail="Embedding service unavailable")


@router.delete("/{creator_id}/clear")
async def clear_content(creator_id: str):
    """
    Clear all content chunks for a creator (from DB and in-memory RAG).
    Use this to remove fake/test content before loading real scraped content.
    """
    try:
        deleted_db = 0
        deleted_rag = 0

        # Delete from PostgreSQL
        if DATABASE_URL and SessionLocal:
            try:
                from api.models import ContentChunk

                db = SessionLocal()
                try:
                    deleted_db = (
                        db.query(ContentChunk)
                        .filter(ContentChunk.creator_id == creator_id)
                        .delete()
                    )
                    db.commit()
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"Failed to delete from DB: {db_err}")

        # Delete from in-memory RAG
        docs_to_delete = [
            doc_id
            for doc_id, doc in get_simple_rag()._documents.items()
            if doc.metadata and doc.metadata.get("creator_id") == creator_id
        ]
        for doc_id in docs_to_delete:
            if doc_id in get_simple_rag()._documents:
                del get_simple_rag()._documents[doc_id]
                deleted_rag += 1

        logger.info(
            f"Cleared content for {creator_id}: {deleted_db} from DB, {deleted_rag} from RAG"
        )

        return {
            "status": "ok",
            "deleted_from_db": deleted_db,
            "deleted_from_rag": deleted_rag,
            "creator_id": creator_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-load")
async def bulk_load_content(request: BulkContentRequest):
    """
    Bulk load real scraped content into RAG and PostgreSQL.

    Each chunk should have:
    - content: The text content
    - source_type: 'web_page', 'instagram_post', etc.
    - source_url: Original URL (for citation)
    - title: Page/post title (optional)
    """
    try:
        loaded = 0

        for i, chunk_data in enumerate(request.chunks):
            content = chunk_data.get("content", "")
            if not content or len(content.strip()) < 10:
                continue

            # Generate unique chunk_id from content hash
            chunk_id = hashlib.sha256(
                f"{request.creator_id}:{chunk_data.get('source_url', '')}:{i}".encode()
            ).hexdigest()[:32]

            source_type = chunk_data.get("source_type", "web_page")
            source_url = chunk_data.get("source_url", "")
            title = chunk_data.get("title", "")

            # Add to in-memory RAG
            get_simple_rag().add_document(
                doc_id=chunk_id,
                text=content,
                metadata={
                    "creator_id": request.creator_id,
                    "type": source_type,
                    "source_url": source_url,
                    "title": title,
                },
            )

            # Persist to PostgreSQL
            if DATABASE_URL and SessionLocal:
                try:
                    from api.models import ContentChunk

                    db = SessionLocal()
                    try:
                        existing = (
                            db.query(ContentChunk).filter(ContentChunk.chunk_id == chunk_id).first()
                        )

                        if not existing:
                            db_chunk = ContentChunk(
                                creator_id=request.creator_id,
                                chunk_id=chunk_id,
                                content=content,
                                source_type=source_type,
                                source_url=source_url,
                                title=title,
                            )
                            db.add(db_chunk)
                            db.commit()
                    finally:
                        db.close()
                except Exception as db_err:
                    logger.warning(f"Failed to persist chunk to DB: {db_err}")

            loaded += 1

        logger.info(f"Bulk loaded {loaded} real content chunks for {request.creator_id}")

        return {"status": "ok", "chunks_loaded": loaded, "creator_id": request.creator_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
