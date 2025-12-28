"""
RAG (Retrieval-Augmented Generation) modules for Clonnect.
Includes semantic search (FAISS), BM25 lexical search, and HybridRAG.
"""

# Semantic search (original rag.py content)
from .semantic import (
    Document,
    SimpleRAG,
    MockEmbedder,
    MockIndex,
    HybridRAG,
    get_simple_rag,
    get_hybrid_rag,
)

# BM25 lexical search
from .bm25 import BM25Retriever, get_bm25_retriever

__all__ = [
    # Semantic
    "Document",
    "SimpleRAG",
    "MockEmbedder",
    "MockIndex",
    "HybridRAG",
    "get_simple_rag",
    "get_hybrid_rag",
    # BM25
    "BM25Retriever",
    "get_bm25_retriever",
]
