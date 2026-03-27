"""
Cross-Encoder Reranking para mejorar precisión de RAG.

Mejora la precisión del RAG reordenando resultados con un modelo
que evalúa query+documento juntos (más preciso que embeddings separados).

Providers:
  - "local" (default): sentence-transformers CrossEncoder (ms-marco-MiniLM-L6-v2)
    - FREE, runs locally, ~100-200ms latency
    - Requires: pip install sentence-transformers
  - "cohere": Cohere Rerank API (rerank-v3.5)
    - Better quality, ~200-400ms latency, paid API
    - Requires: COHERE_API_KEY env var
    - NOT ACTIVATED — skeleton only, needs testing before production use

Toggle: RERANKER_PROVIDER=local|cohere (default: local)
"""
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("clonnect.reranker")

# Feature flag para activar/desactivar
# Default: FALSE - Railway can timeout downloading models on cold start
# Set ENABLE_RERANKING=true in env vars once models are cached
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "true").lower() == "true"

# Reranker provider: "local" (free, sentence-transformers) or "cohere" (paid API)
RERANKER_PROVIDER = os.getenv("RERANKER_PROVIDER", "local").lower()

# Cohere API key (only needed if RERANKER_PROVIDER=cohere)
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

# Lazy loading para evitar import pesado al inicio
_reranker = None


# Reranker model: multilingual by default for CA/ES/EN/IT support.
# Override via RERANKER_MODEL env var if needed.
RERANKER_MODEL = os.getenv(
    "RERANKER_MODEL",
    "nreimers/mmarco-mMiniLMv2-L12-H384-v1",  # multilingual CA/ES/EN/IT (was: cross-encoder/ms-marco-MiniLM-L6-v2)
)


def get_reranker():
    """Lazy load del modelo Cross-Encoder (multilingual by default)."""
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info("Loading Cross-Encoder model (%s)...", RERANKER_MODEL)
            _reranker = CrossEncoder(RERANKER_MODEL)
            logger.info("Cross-Encoder loaded: %s (FREE, runs locally)", RERANKER_MODEL)
        except ImportError:
            logger.error("sentence-transformers not installed: pip install sentence-transformers")
            _reranker = None
        except Exception as e:
            logger.error(f"Failed to load Cross-Encoder: {e}")
            _reranker = None
    return _reranker


def warmup_reranker() -> None:
    """Pre-load model and run a dummy prediction to warm up the JIT/caches."""
    if not ENABLE_RERANKING:
        return
    reranker = get_reranker()
    if reranker:
        try:
            reranker.predict([("warmup query", "warmup document")])
            logger.info("Reranker warmed up successfully")
        except Exception as e:
            logger.warning(f"Reranker warmup failed: {e}")


def _rerank_cohere(
    query: str,
    docs: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    text_key: str = "content",
) -> List[Dict[str, Any]]:
    """
    Rerank using Cohere Rerank API (rerank-v3.5).

    NOT ACTIVATED — skeleton for future use. Requires COHERE_API_KEY.
    Cohere rerank-v3.5: ~200-400ms, better quality than local cross-encoder.
    Pricing: ~$1/1000 searches (check cohere.com/pricing).
    """
    if not COHERE_API_KEY:
        logger.warning("COHERE_API_KEY not set, falling back to local reranker")
        return _rerank_local(query, docs, top_k, text_key)

    try:
        import httpx

        texts = [doc.get(text_key, "") for doc in docs]
        response = httpx.post(
            "https://api.cohere.com/v2/rerank",
            headers={
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "rerank-v3.5",
                "query": query,
                "documents": texts,
                "top_n": top_k or len(docs),
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        reranked_docs = []
        for result in data.get("results", []):
            idx = result["index"]
            doc_copy = docs[idx].copy()
            doc_copy["rerank_score"] = float(result["relevance_score"])
            doc_copy["reranker"] = "cohere"
            reranked_docs.append(doc_copy)

        reranked_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        logger.debug(f"Cohere reranked {len(docs)} docs (top: {reranked_docs[0]['rerank_score']:.3f})")
        return reranked_docs[:top_k] if top_k else reranked_docs

    except Exception as e:
        logger.error(f"Cohere reranking failed: {e}, falling back to local")
        return _rerank_local(query, docs, top_k, text_key)


def _rerank_local(
    query: str,
    docs: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    text_key: str = "content",
) -> List[Dict[str, Any]]:
    """Rerank using local Cross-Encoder model (ms-marco-MiniLM-L6-v2)."""
    reranker = get_reranker()
    if not reranker:
        logger.warning("Reranker not available, returning docs as-is")
        return docs[:top_k] if top_k else docs

    pairs = [(query, doc.get(text_key, "")) for doc in docs]
    scores = reranker.predict(pairs)

    reranked_docs = []
    for doc, score in zip(docs, scores):
        doc_copy = doc.copy()
        doc_copy["rerank_score"] = float(score)
        doc_copy["reranker"] = "local"
        reranked_docs.append(doc_copy)

    reranked_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
    logger.debug(f"Local reranked {len(docs)} docs (top: {reranked_docs[0]['rerank_score']:.3f})")
    return reranked_docs[:top_k] if top_k else reranked_docs


def rerank(
    query: str,
    docs: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    text_key: str = "content"
) -> List[Dict[str, Any]]:
    """
    Reordena documentos usando Cross-Encoder para mejor precisión.

    Dispatches to local (default) or Cohere based on RERANKER_PROVIDER env var.

    Args:
        query: Query de búsqueda
        docs: Documentos a reordenar (deben tener key 'content' o especificar text_key)
        top_k: Número de resultados a devolver (None = todos)
        text_key: Key del texto en cada documento

    Returns:
        Lista de documentos reordenados por relevancia real
        Cada doc incluye 'rerank_score' con el score del reranker
    """
    if not ENABLE_RERANKING:
        logger.debug("Reranking disabled (ENABLE_RERANKING=false)")
        return docs[:top_k] if top_k else docs

    if not docs:
        return []

    if not query or not query.strip():
        return docs[:top_k] if top_k else docs

    try:
        if RERANKER_PROVIDER == "cohere":
            return _rerank_cohere(query, docs, top_k, text_key)
        return _rerank_local(query, docs, top_k, text_key)
    except Exception as e:
        logger.error(f"Reranking failed: {e}")
        return docs[:top_k] if top_k else docs


def rerank_with_threshold(
    query: str,
    docs: List[Dict[str, Any]],
    threshold: float = 0.0,
    top_k: Optional[int] = None,
    text_key: str = "content"
) -> List[Dict[str, Any]]:
    """
    Rerank con filtro por threshold mínimo de relevancia.

    Args:
        query: Query de búsqueda
        docs: Documentos a reordenar
        threshold: Score mínimo para incluir un documento
        top_k: Número máximo de resultados
        text_key: Key del texto en cada documento

    Returns:
        Documentos reordenados que superan el threshold
    """
    reranked = rerank(query, docs, top_k=None, text_key=text_key)
    filtered = [d for d in reranked if d.get("rerank_score", 0) >= threshold]
    return filtered[:top_k] if top_k else filtered
