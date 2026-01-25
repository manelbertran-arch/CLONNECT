"""
Cross-Encoder Reranking para mejorar precisión de RAG.

Mejora la precisión del RAG reordenando resultados con un modelo
que evalúa query+documento juntos (más preciso que embeddings separados).

Dependencias: sentence-transformers>=2.2.0
"""
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("clonnect.reranker")

# Feature flag para activar/desactivar
# Default: FALSE - Railway can timeout downloading models on cold start
# Set ENABLE_RERANKING=true in env vars once models are cached
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "false").lower() == "true"

# Lazy loading para evitar import pesado al inicio
_reranker = None


def get_reranker():
    """Lazy load del modelo Cross-Encoder"""
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info("Loading Cross-Encoder model (ms-marco-MiniLM-L6-v2)...")
            _reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')
            logger.info("Cross-Encoder loaded (FREE, runs locally)")
        except ImportError:
            logger.error("sentence-transformers not installed: pip install sentence-transformers")
            _reranker = None
        except Exception as e:
            logger.error(f"Failed to load Cross-Encoder: {e}")
            _reranker = None
    return _reranker


def rerank(
    query: str,
    docs: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    text_key: str = "content"
) -> List[Dict[str, Any]]:
    """
    Reordena documentos usando Cross-Encoder para mejor precisión.

    Args:
        query: Query de búsqueda
        docs: Documentos a reordenar (deben tener key 'content' o especificar text_key)
        top_k: Número de resultados a devolver (None = todos)
        text_key: Key del texto en cada documento

    Returns:
        Lista de documentos reordenados por relevancia real
        Cada doc incluye 'rerank_score' con el score del Cross-Encoder
    """
    if not ENABLE_RERANKING:
        logger.debug("Reranking disabled (ENABLE_RERANKING=false)")
        return docs[:top_k] if top_k else docs

    reranker = get_reranker()

    if not reranker:
        logger.warning("Reranker not available, returning docs as-is")
        return docs[:top_k] if top_k else docs

    if not docs:
        return []

    if not query or not query.strip():
        return docs[:top_k] if top_k else docs

    try:
        # Preparar pares (query, doc_text)
        pairs = [(query, doc.get(text_key, "")) for doc in docs]

        # Obtener scores de cross-encoder
        scores = reranker.predict(pairs)

        # Añadir scores y crear copia para no mutar original
        reranked_docs = []
        for doc, score in zip(docs, scores):
            doc_copy = doc.copy()
            doc_copy["rerank_score"] = float(score)
            reranked_docs.append(doc_copy)

        # Ordenar por rerank_score descendente
        reranked_docs.sort(key=lambda x: x["rerank_score"], reverse=True)

        logger.debug(f"Reranked {len(docs)} docs (top score: {reranked_docs[0]['rerank_score']:.3f})")

        return reranked_docs[:top_k] if top_k else reranked_docs

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
