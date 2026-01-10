"""
Sistema RAG con OpenAI Embeddings + pgvector

Búsqueda semántica real usando:
- OpenAI text-embedding-3-small (1536 dimensions)
- PostgreSQL pgvector para almacenamiento y búsqueda
- Embeddings persistidos en DB (no se regeneran en cada deploy)
"""

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Documento indexado"""
    doc_id: str
    text: str
    metadata: Dict[str, Any] = None

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "metadata": self.metadata or {}
        }


class SemanticRAG:
    """
    RAG con búsqueda semántica usando OpenAI Embeddings + pgvector.

    - Embeddings generados con OpenAI API (text-embedding-3-small)
    - Almacenados en PostgreSQL con pgvector
    - Búsqueda por cosine similarity
    - Persistencia: embeddings sobreviven redeploys
    """

    def __init__(self):
        self._embeddings_available = None
        # In-memory cache for documents (loaded from DB)
        self._documents: Dict[str, Document] = {}
        self._doc_list: List[str] = []

    def _check_embeddings_available(self) -> bool:
        """Check if OpenAI embeddings are available."""
        if self._embeddings_available is None:
            api_key = os.getenv("OPENAI_API_KEY")
            self._embeddings_available = bool(api_key)
            if not self._embeddings_available:
                logger.warning("OPENAI_API_KEY not set - semantic search disabled")
        return self._embeddings_available

    def add_document(self, doc_id: str, text: str, metadata: Dict = None):
        """
        Add document and generate embedding.

        If OpenAI is available, generates and stores embedding in pgvector.
        Always adds to in-memory cache for fallback search.
        """
        doc = Document(doc_id=doc_id, text=text, metadata=metadata)
        self._documents[doc_id] = doc
        if doc_id not in self._doc_list:
            self._doc_list.append(doc_id)

        # Generate and store embedding if OpenAI available
        if self._check_embeddings_available():
            try:
                from core.embeddings import generate_embedding, store_embedding

                embedding = generate_embedding(text)
                if embedding:
                    creator_id = metadata.get("creator_id", "unknown") if metadata else "unknown"
                    store_embedding(doc_id, creator_id, text, embedding)
                    logger.debug(f"Stored embedding for {doc_id}")
            except Exception as e:
                logger.error(f"Error storing embedding: {e}")

    def search(self, query: str, top_k: int = 5, creator_id: str = None) -> List[Dict]:
        """
        Search for relevant documents using semantic similarity.

        Uses pgvector cosine similarity if embeddings are available,
        falls back to simple text matching otherwise.
        """
        if not creator_id:
            logger.warning("search() called without creator_id")
            return []

        # Try semantic search with pgvector
        if self._check_embeddings_available():
            try:
                from core.embeddings import generate_embedding, search_similar

                # Generate query embedding
                query_embedding = generate_embedding(query)
                if query_embedding:
                    results = search_similar(
                        query_embedding=query_embedding,
                        creator_id=creator_id,
                        top_k=top_k,
                        min_similarity=0.3
                    )

                    if results:
                        logger.info(f"Semantic search: '{query[:30]}...' -> {len(results)} results")
                        return [
                            {
                                "doc_id": r["chunk_id"],
                                "text": r["content"],
                                "metadata": {
                                    "creator_id": creator_id,
                                    "source_url": r.get("source_url"),
                                    "title": r.get("title"),
                                    "type": r.get("source_type")
                                },
                                "score": r["similarity"]
                            }
                            for r in results
                        ]

            except Exception as e:
                logger.error(f"Semantic search failed: {e}")

        # Fallback: simple text search in memory
        logger.debug("Using fallback text search")
        return self._fallback_search(query, top_k, creator_id)

    def _fallback_search(self, query: str, top_k: int, creator_id: str) -> List[Dict]:
        """Simple keyword-based fallback search."""
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for doc_id, doc in self._documents.items():
            # Filter by creator_id
            if doc.metadata and doc.metadata.get("creator_id") != creator_id:
                continue

            # Simple word overlap scoring
            doc_lower = doc.text.lower()
            doc_words = set(doc_lower.split())
            overlap = len(query_words & doc_words)

            if overlap > 0 or any(w in doc_lower for w in query_words):
                score = overlap / max(len(query_words), 1)
                results.append({
                    "doc_id": doc.doc_id,
                    "text": doc.text,
                    "metadata": doc.metadata,
                    "score": min(score, 1.0)
                })

        # Sort by score and return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_document(self, doc_id: str):
        """Delete document from memory and DB."""
        if doc_id in self._documents:
            del self._documents[doc_id]
        if doc_id in self._doc_list:
            self._doc_list.remove(doc_id)

        # Also delete from embeddings table
        try:
            from api.database import SessionLocal
            from sqlalchemy import text

            if SessionLocal:
                db = SessionLocal()
                try:
                    db.execute(text(
                        "DELETE FROM content_embeddings WHERE chunk_id = :chunk_id"
                    ), {"chunk_id": doc_id})
                    db.commit()
                finally:
                    db.close()
        except Exception as e:
            logger.error(f"Error deleting embedding: {e}")

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document by ID."""
        return self._documents.get(doc_id)

    def count(self) -> int:
        """Count documents in memory."""
        return len(self._documents)

    def load_from_db(self, creator_id: str = None) -> int:
        """
        Load documents from PostgreSQL content_chunks table.
        Does NOT regenerate embeddings - those are persisted separately.
        """
        try:
            from api.database import SessionLocal
            from api.models import ContentChunk

            if SessionLocal is None:
                logger.warning("No database configured, skipping RAG hydration")
                return 0

            db = SessionLocal()
            try:
                query = db.query(ContentChunk)
                if creator_id:
                    query = query.filter(ContentChunk.creator_id == creator_id)

                chunks = query.all()
                loaded = 0

                for chunk in chunks:
                    # Skip if already loaded
                    if chunk.chunk_id in self._documents:
                        continue

                    # Add to memory (don't regenerate embedding - it's in pgvector)
                    doc = Document(
                        doc_id=chunk.chunk_id,
                        text=chunk.content,
                        metadata={
                            "creator_id": chunk.creator_id,
                            "type": chunk.source_type or "content",
                            "source_url": chunk.source_url,
                            "title": chunk.title
                        }
                    )
                    self._documents[chunk.chunk_id] = doc
                    if chunk.chunk_id not in self._doc_list:
                        self._doc_list.append(chunk.chunk_id)
                    loaded += 1

                logger.info(f"RAG hydrated: loaded {loaded} documents from PostgreSQL" +
                           (f" for {creator_id}" if creator_id else ""))
                return loaded

            finally:
                db.close()

        except ImportError:
            logger.warning("Database modules not available, skipping RAG hydration")
            return 0
        except Exception as e:
            logger.error(f"Error loading RAG from database: {e}")
            return 0


# Keep SimpleRAG as alias for backward compatibility
SimpleRAG = SemanticRAG

# HybridRAG is now just SemanticRAG (OpenAI + pgvector handles both semantic and fallback)
HybridRAG = SemanticRAG


# Singleton instance
_rag_instance: Optional[SemanticRAG] = None


def get_simple_rag() -> SemanticRAG:
    """Get or create RAG singleton."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = SemanticRAG()
    return _rag_instance


def get_semantic_rag() -> SemanticRAG:
    """Get or create RAG singleton (alias)."""
    return get_simple_rag()


def get_hybrid_rag() -> SemanticRAG:
    """Get or create RAG singleton (alias for backward compatibility)."""
    return get_simple_rag()


# Backward compatibility stubs (no longer needed with OpenAI + pgvector)
class MockEmbedder:
    """Deprecated: OpenAI embeddings used instead."""
    pass


class MockIndex:
    """Deprecated: pgvector used instead."""
    pass
