"""
RAG (Retrieval-Augmented Generation) modules for Clonnect.

Uses OpenAI Embeddings + pgvector for semantic search with BM25 fallback.
Embeddings persist in PostgreSQL - no regeneration on deploy.
"""

# Semantic search with OpenAI Embeddings + pgvector
from .semantic import (
    Document,
    SemanticRAG,
    SimpleRAG,
    HybridRAG,
    MockEmbedder,
    MockIndex,
    get_simple_rag,
    get_semantic_rag,
    get_hybrid_rag,
)

# BM25 lexical search
from .bm25 import BM25Retriever, get_bm25_retriever

__all__ = [
    # Semantic (OpenAI + pgvector)
    "Document",
    "SemanticRAG",
    "SimpleRAG",
    "HybridRAG",
    "MockEmbedder",
    "MockIndex",
    "get_simple_rag",
    "get_semantic_rag",
    "get_hybrid_rag",
    # BM25
    "BM25Retriever",
    "get_bm25_retriever",
]
