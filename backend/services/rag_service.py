"""
RAG (Retrieval-Augmented Generation) Service.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Provides document indexing, semantic search, and retrieval functionality.
"""
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """
    Represents a chunk of document for RAG indexing.

    Attributes:
        content: The text content of the chunk
        metadata: Optional metadata (source, type, etc.)
        chunk_id: Unique identifier (auto-generated if not provided)
        embedding: Optional embedding vector
        created_at: Timestamp of creation
    """

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Generate chunk_id if not provided."""
        if not self.chunk_id:
            self.chunk_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate unique ID based on content hash."""
        content_hash = hashlib.md5(self.content.encode()).hexdigest()[:12]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:14]
        return f"chunk_{content_hash}_{timestamp}"


class RAGService:
    """
    RAG service for document indexing and semantic retrieval.

    Provides:
    - Document indexing with metadata
    - Keyword-based similarity search (with embedding support ready)
    - Configurable similarity thresholds
    """

    # Common stop words to filter out
    STOP_WORDS = {
        "el", "la", "los", "las", "un", "una", "unos", "unas",
        "de", "del", "en", "con", "por", "para", "que", "qué",
        "es", "son", "está", "están", "ser", "al", "lo",
        "the", "a", "an", "and", "or", "but", "in", "on", "at",
        "to", "for", "of", "with", "by", "is", "are", "was", "were",
    }

    def __init__(
        self,
        similarity_threshold: float = 0.1,
        embedding_model: Optional[str] = None,
    ) -> None:
        """
        Initialize RAG service.

        Args:
            similarity_threshold: Minimum similarity score for results (0-1)
            embedding_model: Optional embedding model name for future use
        """
        self.similarity_threshold = similarity_threshold
        self.embedding_model = embedding_model
        self._documents: Dict[str, DocumentChunk] = {}
        self._embeddings_cache: Dict[str, List[float]] = {}

        logger.info(
            f"[RAGService] Initialized with threshold={similarity_threshold}, "
            f"model={embedding_model or 'keyword-based'}"
        )

    def add_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a document to the index.

        Args:
            content: Document text content
            metadata: Optional metadata dictionary

        Returns:
            Document ID (chunk_id)
        """
        if not content or not content.strip():
            raise ValueError("Document content cannot be empty")

        chunk = DocumentChunk(
            content=content.strip(),
            metadata=metadata or {},
        )

        # Generate embedding if model available
        if self.embedding_model:
            chunk.embedding = self._generate_embedding(content)

        self._documents[chunk.chunk_id] = chunk
        logger.debug(
            f"[RAGService] Added document {chunk.chunk_id}, "
            f"total: {len(self._documents)}"
        )

        return chunk.chunk_id

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents for a query.

        Args:
            query: Search query
            top_k: Maximum number of results to return
            filter_metadata: Optional metadata filter

        Returns:
            List of results with content, metadata, score, and chunk_id
        """
        if not self._documents:
            return []

        if not query or not query.strip():
            return []

        # Score all documents
        scored_docs: List[Tuple[float, DocumentChunk]] = []

        for doc in self._documents.values():
            # Apply metadata filter
            if filter_metadata:
                if not self._matches_filter(doc.metadata, filter_metadata):
                    continue

            # Calculate similarity
            score = self._calculate_similarity(query, doc.content)

            if score >= self.similarity_threshold:
                scored_docs.append((score, doc))

        # Sort by score descending
        scored_docs.sort(key=lambda x: x[0], reverse=True)

        # Return top_k results
        results = []
        for score, doc in scored_docs[:top_k]:
            results.append({
                "content": doc.content,
                "metadata": doc.metadata,
                "score": score,
                "chunk_id": doc.chunk_id,
            })

        logger.debug(
            f"[RAGService] Retrieved {len(results)} results for query: "
            f"'{query[:50]}...'"
        )

        return results

    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        Compute similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score between 0 and 1
        """
        return self._calculate_similarity(text1, text2)

    def clear_index(self) -> None:
        """Clear all documents from the index."""
        count = len(self._documents)
        self._documents.clear()
        self._embeddings_cache.clear()
        logger.info(f"[RAGService] Cleared {count} documents from index")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get index statistics.

        Returns:
            Dictionary with index stats
        """
        return {
            "total_documents": len(self._documents),
            "similarity_threshold": self.similarity_threshold,
            "embedding_model": self.embedding_model,
            "cache_size": len(self._embeddings_cache),
        }

    def _calculate_similarity(self, query: str, content: str) -> float:
        """
        Calculate similarity between query and content.

        Uses keyword-based Jaccard similarity when no embedding model.
        """
        if self.embedding_model:
            return self._embedding_similarity(query, content)

        return self._keyword_similarity(query, content)

    def _keyword_similarity(self, query: str, content: str) -> float:
        """
        Calculate keyword-based Jaccard similarity.

        Args:
            query: Search query
            content: Document content

        Returns:
            Similarity score between 0 and 1
        """
        query_tokens = self._tokenize(query.lower())
        content_tokens = self._tokenize(content.lower())

        if not query_tokens or not content_tokens:
            return 0.0

        # Convert to sets for Jaccard calculation
        query_set = set(query_tokens)
        content_set = set(content_tokens)

        intersection = query_set & content_set
        union = query_set | content_set

        if not union:
            return 0.0

        # Basic Jaccard similarity
        jaccard = len(intersection) / len(union)

        # Boost if query terms appear in content (coverage bonus)
        coverage = len(intersection) / len(query_set) if query_set else 0

        # Weighted combination
        return 0.6 * jaccard + 0.4 * coverage

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into words.

        Removes punctuation, stop words, and short tokens.
        """
        # Remove punctuation
        text = re.sub(r"[^\w\s]", " ", text)

        # Split into tokens
        tokens = text.split()

        # Filter stop words and short tokens
        filtered = [
            t for t in tokens
            if len(t) > 2 and t not in self.STOP_WORDS
        ]

        return filtered

    def _embedding_similarity(self, query: str, content: str) -> float:
        """Calculate embedding-based cosine similarity."""
        query_emb = self._generate_embedding(query)
        content_emb = self._generate_embedding(content)

        if not query_emb or not content_emb:
            # Fall back to keyword similarity
            return self._keyword_similarity(query, content)

        return self._cosine_similarity(query_emb, content_emb)

    def _cosine_similarity(
        self, vec1: List[float], vec2: List[float]
    ) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text.

        Placeholder for actual embedding generation.
        Can be extended to use sentence-transformers or OpenAI embeddings.
        """
        # Check cache
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._embeddings_cache:
            return self._embeddings_cache[cache_key]

        # TODO: Implement actual embedding generation
        # For now, return None to use keyword similarity
        return None

    def _matches_filter(
        self,
        metadata: Dict[str, Any],
        filter_dict: Dict[str, Any],
    ) -> bool:
        """Check if metadata matches all filter criteria."""
        for key, value in filter_dict.items():
            if key not in metadata:
                return False
            if metadata[key] != value:
                return False
        return True
