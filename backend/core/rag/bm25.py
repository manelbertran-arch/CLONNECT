"""
BM25 Retriever for Clonnect

Lexical search using BM25 algorithm for FAQ and knowledge base retrieval.
Complements semantic search with exact keyword matching.

BM25 (Best Match 25) is a ranking function used by search engines
to rank documents based on term frequency and document length.
"""

import math
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter

logger = logging.getLogger(__name__)

# Spanish stopwords
STOPWORDS_ES = {
    'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'del', 'se', 'las',
    'por', 'un', 'para', 'con', 'no', 'una', 'su', 'al', 'es', 'lo',
    'como', 'más', 'pero', 'sus', 'le', 'ya', 'o', 'este', 'si', 'porque',
    'esta', 'entre', 'cuando', 'muy', 'sin', 'sobre', 'ser', 'tiene',
    'también', 'me', 'hasta', 'hay', 'donde', 'quien', 'desde', 'todo',
    'nos', 'durante', 'todos', 'uno', 'les', 'ni', 'contra', 'otros',
    'ese', 'eso', 'ante', 'ellos', 'e', 'esto', 'mi', 'antes', 'algunos',
    'qué', 'unos', 'yo', 'otro', 'otras', 'otra', 'él', 'tanto', 'esa',
    'estos', 'mucho', 'quienes', 'nada', 'muchos', 'cual', 'poco', 'ella',
    'estar', 'estas', 'algunas', 'algo', 'nosotros', 'tu', 'tus', 'te'
}

# English stopwords
STOPWORDS_EN = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
    'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
    'she', 'we', 'they', 'what', 'which', 'who', 'whom', 'whose',
    'where', 'when', 'why', 'how', 'all', 'each', 'every', 'both',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also'
}

STOPWORDS = STOPWORDS_ES | STOPWORDS_EN


@dataclass
class BM25Document:
    """Document for BM25 indexing"""
    doc_id: str
    text: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class BM25Result:
    """Search result from BM25"""
    doc_id: str
    text: str
    score: float
    metadata: Dict[str, Any] = None


class BM25Retriever:
    """
    BM25-based document retriever for lexical search.

    Parameters:
        k1: Term frequency saturation parameter (default: 1.5)
        b: Document length normalization parameter (default: 0.75)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: Dict[str, BM25Document] = {}
        self.doc_lengths: Dict[str, int] = {}
        self.avg_doc_length: float = 0.0
        self.term_doc_freq: Dict[str, int] = {}  # How many docs contain each term
        self.doc_term_freq: Dict[str, Counter] = {}  # Term frequencies per doc
        self.corpus_size: int = 0

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize and normalize text.

        Args:
            text: Input text

        Returns:
            List of tokens
        """
        # Lowercase
        text = text.lower()

        # Remove punctuation and split
        tokens = re.findall(r'\b\w+\b', text)

        # Remove stopwords and short tokens
        tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]

        return tokens

    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None):
        """
        Add a document to the index.

        Args:
            doc_id: Unique document identifier
            text: Document text content
            metadata: Optional metadata
        """
        doc = BM25Document(doc_id=doc_id, text=text, metadata=metadata)
        tokens = self._tokenize(text)

        # Store document
        self.documents[doc_id] = doc
        self.doc_lengths[doc_id] = len(tokens)
        self.doc_term_freq[doc_id] = Counter(tokens)

        # Update term document frequencies
        unique_terms = set(tokens)
        for term in unique_terms:
            self.term_doc_freq[term] = self.term_doc_freq.get(term, 0) + 1

        # Update corpus stats
        self.corpus_size = len(self.documents)
        total_length = sum(self.doc_lengths.values())
        self.avg_doc_length = total_length / self.corpus_size if self.corpus_size > 0 else 0

        logger.debug(f"Added document {doc_id} with {len(tokens)} tokens")

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        Add multiple documents at once.

        Args:
            documents: List of dicts with 'id', 'text', and optionally 'metadata'
        """
        for doc in documents:
            self.add_document(
                doc_id=doc.get("id", doc.get("doc_id", "")),
                text=doc.get("text", doc.get("content", "")),
                metadata=doc.get("metadata")
            )

    def _idf(self, term: str) -> float:
        """
        Calculate Inverse Document Frequency for a term.

        Args:
            term: The term

        Returns:
            IDF score
        """
        n = self.corpus_size
        df = self.term_doc_freq.get(term, 0)

        if df == 0:
            return 0.0

        # Standard IDF formula with smoothing
        return math.log((n - df + 0.5) / (df + 0.5) + 1)

    def _score_document(self, doc_id: str, query_terms: List[str]) -> float:
        """
        Calculate BM25 score for a document given query terms.

        Args:
            doc_id: Document ID
            query_terms: List of query tokens

        Returns:
            BM25 score
        """
        score = 0.0
        doc_length = self.doc_lengths.get(doc_id, 0)
        term_freqs = self.doc_term_freq.get(doc_id, Counter())

        for term in query_terms:
            if term not in term_freqs:
                continue

            # Term frequency in document
            tf = term_freqs[term]

            # IDF
            idf = self._idf(term)

            # BM25 formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / self.avg_doc_length)

            score += idf * (numerator / denominator)

        return score

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        filter_metadata: Dict[str, Any] = None
    ) -> List[BM25Result]:
        """
        Search for documents matching the query.

        Args:
            query: Search query
            top_k: Maximum number of results
            min_score: Minimum score threshold
            filter_metadata: Optional metadata filter

        Returns:
            List of BM25Result sorted by score descending
        """
        if not self.documents:
            return []

        query_terms = self._tokenize(query)

        if not query_terms:
            logger.debug("No valid query terms after tokenization")
            return []

        # Score all documents
        scores: List[Tuple[str, float]] = []

        for doc_id in self.documents:
            # Apply metadata filter if specified
            if filter_metadata:
                doc = self.documents[doc_id]
                if doc.metadata:
                    skip = False
                    for key, value in filter_metadata.items():
                        if doc.metadata.get(key) != value:
                            skip = True
                            break
                    if skip:
                        continue

            score = self._score_document(doc_id, query_terms)
            if score > min_score:
                scores.append((doc_id, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        # Build results
        results = []
        for doc_id, score in scores[:top_k]:
            doc = self.documents[doc_id]
            results.append(BM25Result(
                doc_id=doc_id,
                text=doc.text,
                score=score,
                metadata=doc.metadata
            ))

        logger.info(f"BM25 search: query='{query[:50]}...', results={len(results)}")
        return results

    def remove_document(self, doc_id: str) -> bool:
        """
        Remove a document from the index.

        Args:
            doc_id: Document ID to remove

        Returns:
            True if removed, False if not found
        """
        if doc_id not in self.documents:
            return False

        # Get terms to update frequencies
        term_freqs = self.doc_term_freq.get(doc_id, Counter())
        for term in term_freqs:
            if term in self.term_doc_freq:
                self.term_doc_freq[term] -= 1
                if self.term_doc_freq[term] <= 0:
                    del self.term_doc_freq[term]

        # Remove document
        del self.documents[doc_id]
        del self.doc_lengths[doc_id]
        del self.doc_term_freq[doc_id]

        # Update corpus stats
        self.corpus_size = len(self.documents)
        if self.corpus_size > 0:
            self.avg_doc_length = sum(self.doc_lengths.values()) / self.corpus_size
        else:
            self.avg_doc_length = 0

        return True

    def clear(self):
        """Clear all documents from the index"""
        self.documents.clear()
        self.doc_lengths.clear()
        self.term_doc_freq.clear()
        self.doc_term_freq.clear()
        self.corpus_size = 0
        self.avg_doc_length = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        return {
            "corpus_size": self.corpus_size,
            "avg_doc_length": self.avg_doc_length,
            "vocabulary_size": len(self.term_doc_freq),
            "k1": self.k1,
            "b": self.b
        }


# Singleton instances per creator
_retrievers: Dict[str, BM25Retriever] = {}


def get_bm25_retriever(creator_id: str = "default") -> BM25Retriever:
    """
    Get or create a BM25 retriever for a creator.

    Args:
        creator_id: Creator ID for scoping

    Returns:
        BM25Retriever instance
    """
    if creator_id not in _retrievers:
        _retrievers[creator_id] = BM25Retriever()
    return _retrievers[creator_id]


def reset_retrievers():
    """Reset all retrievers (for testing)"""
    global _retrievers
    _retrievers = {}
