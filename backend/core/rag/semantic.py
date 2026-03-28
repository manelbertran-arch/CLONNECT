"""
Sistema RAG con OpenAI Embeddings + pgvector

Búsqueda semántica real usando:
- OpenAI text-embedding-3-small (1536 dimensions)
- PostgreSQL pgvector para almacenamiento y búsqueda
- Embeddings persistidos en DB (no se regeneran en cada deploy)

v2.0.0 - Enhanced with optional Reranking and BM25 Hybrid Search
- ENABLE_RERANKING: Cross-encoder reranking for better precision (+100-200ms)
- ENABLE_BM25_HYBRID: Lexical search fusion for exact keyword matching (+50ms)
"""

import os
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# RAG results cache: avoid repeating full search pipeline for same query
# Bounded to prevent memory leaks
from core.cache import BoundedTTLCache
_rag_cache = BoundedTTLCache(max_size=200, ttl_seconds=300)
RAG_CACHE_TTL = 300  # 5 minutes

# =============================================================================
# FEATURE FLAGS - All OFF by default to minimize latency
# =============================================================================

# Cross-encoder reranking: improves relevance but adds ~100-200ms
# Default: FALSE - Railway can timeout downloading models on cold start
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "true").lower() == "true"

# BM25 hybrid search: combines semantic + lexical search
# Default: TRUE - Improves recall for keyword-heavy queries
ENABLE_BM25_HYBRID = os.getenv("ENABLE_BM25_HYBRID", "true").lower() == "true"

# Hybrid weights: semantic vs BM25 (must sum to 1.0)
HYBRID_SEMANTIC_WEIGHT = float(os.getenv("HYBRID_SEMANTIC_WEIGHT", "0.7"))
HYBRID_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", "0.3"))


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

    # Intents that don't need RAG (simple social interactions)
    SKIP_RAG_INTENTS = frozenset({"greeting", "farewell", "thanks", "saludo", "despedida"})

    def search(self, query: str, top_k: int = 5, creator_id: str = None,
               intent: str = None) -> List[Dict]:
        """
        Search for relevant documents using semantic similarity.
        Results are cached by query+creator_id with TTL.

        Enhanced search pipeline:
        1. Semantic search (OpenAI embeddings + pgvector)
        2. Optional: BM25 hybrid fusion (if ENABLE_BM25_HYBRID=true)
        3. Optional: Cross-encoder reranking (if ENABLE_RERANKING=true)

        Args:
            query: Search query
            top_k: Number of results to return
            creator_id: Filter by creator
            intent: Optional intent to skip RAG for simple intents

        Returns:
            List of documents with scores
        """
        # Skip RAG for simple intents that don't need knowledge retrieval
        if intent and intent in self.SKIP_RAG_INTENTS:
            logger.info(f"[RAG] Skipped search for intent={intent}")
            return []
        if not creator_id:
            logger.warning("search() called without creator_id")
            return []

        # Check RAG results cache
        cache_key = f"{creator_id}:{query.strip().lower()}"
        cached = _rag_cache.get(cache_key)
        if cached is not None:
            logger.info(f"[RAG] Cache hit: '{query[:50]}'")
            return cached

        t0 = time.time()

        # Get more results initially if we're going to rerank
        # Cap at 12 to keep reranking fast (cross-encoder is O(n))
        initial_top_k = min(top_k * 2, 12) if ENABLE_RERANKING else top_k

        # Step 1: Semantic search (embedding API + pgvector)
        semantic_results = self._semantic_search(query, initial_top_k, creator_id)
        t1 = time.time()

        # Step 2: BM25 hybrid fusion (optional)
        if ENABLE_BM25_HYBRID and semantic_results:
            semantic_results = self._hybrid_with_bm25(query, semantic_results, creator_id, initial_top_k)
        t2 = time.time()

        # Step 3: Reranking (optional)
        if ENABLE_RERANKING and semantic_results:
            semantic_results = self._rerank_results(query, semantic_results, top_k)
        else:
            semantic_results = semantic_results[:top_k]
        t3 = time.time()

        logger.info(
            f"[RAG_TIMING] semantic={int((t1-t0)*1000)}ms "
            f"bm25={int((t2-t1)*1000)}ms "
            f"rerank={int((t3-t2)*1000)}ms "
            f"total={int((t3-t0)*1000)}ms"
        )

        # Step 4: Source-type boost — structured data outranks social captions.
        # product_catalog and faq chunks contain verified facts (prices, schedules);
        # IG captions are motivational/promotional with less factual value.
        _SOURCE_BOOSTS = {
            "product_catalog": 0.15,
            "faq": 0.10,
            "objection_handling": 0.10,
            "expertise": 0.08,
            "policies": 0.08,
            "values": 0.05,
        }
        for result in semantic_results:
            source_type = result.get("metadata", {}).get("type", "")
            boost = _SOURCE_BOOSTS.get(source_type, 0)
            if boost:
                result["score"] = result.get("score", 0) + boost
        semantic_results.sort(key=lambda r: r.get("score", 0), reverse=True)

        # Log retrieval quality
        if semantic_results:
            scores = [r.get("score", 0) for r in semantic_results]
            logger.debug(
                "RAG search: query=%s results=%d top_score=%.3f avg_score=%.3f",
                query[:50], len(semantic_results),
                max(scores) if scores else 0,
                sum(scores) / len(scores) if scores else 0,
            )

        # Store in cache
        _rag_cache.set(cache_key, semantic_results)

        return semantic_results

    def _semantic_search(self, query: str, top_k: int, creator_id: str) -> List[Dict]:
        """Core semantic search using OpenAI embeddings + pgvector."""
        if self._check_embeddings_available():
            try:
                from core.embeddings import generate_embedding, search_similar

                query_embedding = generate_embedding(query)
                if query_embedding:
                    results = search_similar(
                        query_embedding=query_embedding,
                        creator_id=creator_id,
                        top_k=top_k
                    )

                    if results:
                        logger.info(f"Semantic search: '{query[:30]}...' -> {len(results)} results")
                        return [
                            {
                                "doc_id": r["chunk_id"],
                                "text": r["content"],
                                "content": r["content"],  # Alias for reranker
                                "metadata": {
                                    "creator_id": creator_id,
                                    "source_url": r.get("source_url"),
                                    "title": r.get("title"),
                                    "type": r.get("source_type")
                                },
                                "score": r["similarity"],
                                "search_type": "semantic"
                            }
                            for r in results
                        ]

            except Exception as e:
                logger.error(f"Semantic search failed: {e}")

        # Fallback
        logger.debug("Using fallback text search")
        return self._fallback_search(query, top_k, creator_id)

    def _hybrid_with_bm25(self, query: str, semantic_results: List[Dict], creator_id: str, top_k: int) -> List[Dict]:
        """
        Combine semantic results with BM25 lexical search using Reciprocal Rank Fusion.

        RRF formula: score = sum(1 / (k + rank)) for each result list
        """
        try:
            from core.rag.bm25 import get_bm25_retriever

            bm25 = get_bm25_retriever(creator_id)

            # Build BM25 index from semantic results if not already indexed
            if bm25.corpus_size == 0:
                # Index documents from memory cache
                for doc_id, doc in self._documents.items():
                    if doc.metadata and doc.metadata.get("creator_id") == creator_id:
                        bm25.add_document(doc_id, doc.text, doc.metadata)

            # BM25 search
            bm25_results = bm25.search(query, top_k=top_k)

            if not bm25_results:
                return semantic_results

            # Convert BM25 results to dict format
            bm25_dicts = [
                {
                    "doc_id": r.doc_id,
                    "text": r.text,
                    "content": r.text,
                    "metadata": r.metadata,
                    "score": r.score,
                    "search_type": "bm25"
                }
                for r in bm25_results
            ]

            # Weighted Reciprocal Rank Fusion (0.7 semantic + 0.3 BM25)
            fused = self._reciprocal_rank_fusion(
                semantic_results, bm25_dicts,
                k=60,
                weights=[HYBRID_SEMANTIC_WEIGHT, HYBRID_BM25_WEIGHT],
            )

            logger.info(
                f"BM25 hybrid: {len(semantic_results)} semantic + {len(bm25_results)} bm25 "
                f"-> {len(fused)} fused (weights={HYBRID_SEMANTIC_WEIGHT}/{HYBRID_BM25_WEIGHT})"
            )
            return fused

        except Exception as e:
            logger.error(f"BM25 hybrid search failed: {e}")
            return semantic_results

    def _reciprocal_rank_fusion(
        self, *result_lists, k: int = 60, weights: List[float] = None
    ) -> List[Dict]:
        """
        Combine multiple ranked lists using Weighted Reciprocal Rank Fusion.

        Args:
            result_lists: Multiple lists of results
            k: Ranking constant (default 60)
            weights: Per-list weights (e.g. [0.7, 0.3]). Default: equal weights.

        Returns:
            Fused and re-ranked results
        """
        doc_scores = {}
        doc_data = {}

        for list_idx, results in enumerate(result_lists):
            w = weights[list_idx] if weights and list_idx < len(weights) else 1.0
            for rank, doc in enumerate(results):
                doc_id = doc.get("doc_id")
                if not doc_id:
                    continue

                # Weighted RRF score contribution
                rrf_score = w / (k + rank + 1)

                if doc_id in doc_scores:
                    doc_scores[doc_id] += rrf_score
                else:
                    doc_scores[doc_id] = rrf_score
                    doc_data[doc_id] = doc

        # Sort by fused score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        # Build result list
        fused_results = []
        for doc_id, fused_score in sorted_docs:
            doc = doc_data[doc_id].copy()
            doc["rrf_score"] = fused_score
            doc["search_type"] = "hybrid"
            fused_results.append(doc)

        return fused_results

    def _rerank_results(self, query: str, results: List[Dict], top_k: int) -> List[Dict]:
        """
        Rerank results using Cross-Encoder for better precision.

        Cross-encoder evaluates query+document together, more accurate than
        comparing embeddings separately.
        """
        try:
            from core.rag.reranker import rerank

            # Rerank expects 'content' key
            reranked = rerank(query, results, top_k=top_k, text_key="content")

            if reranked:
                logger.info(f"Reranked {len(results)} -> {len(reranked)} results")
                for doc in reranked:
                    doc["search_type"] = "reranked"
                return reranked

        except Exception as e:
            logger.error(f"Reranking failed: {e}")

        return results[:top_k]

    def _prebuild_bm25_indexes(self) -> None:
        """Pre-build BM25 indexes for all creators from loaded documents."""
        try:
            from core.rag.bm25 import get_bm25_retriever

            # Group documents by creator_id
            creators: dict = {}
            for doc_id, doc in self._documents.items():
                cid = doc.metadata.get("creator_id") if doc.metadata else None
                if cid:
                    creators.setdefault(cid, []).append(doc)

            for cid, docs in creators.items():
                bm25 = get_bm25_retriever(cid)
                if bm25.corpus_size == 0:
                    for doc in docs:
                        bm25.add_document(doc.doc_id, doc.text, doc.metadata)
                    logger.info(f"[BM25] Pre-built index for {cid}: {bm25.corpus_size} docs")
        except Exception as e:
            logger.warning(f"[BM25] Pre-build failed: {e}")

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

                chunks = query.limit(500).all()
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

                # Pre-build BM25 indexes for all creators to avoid first-search penalty
                if ENABLE_BM25_HYBRID and loaded > 0:
                    self._prebuild_bm25_indexes()

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


class MockIndex:
    """Deprecated: pgvector used instead."""
