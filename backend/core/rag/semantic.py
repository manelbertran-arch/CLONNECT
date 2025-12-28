"""
Sistema RAG simplificado para Clonnect Creators
Solo busqueda semantica basica, sin complejidad enterprise
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


class SimpleRAG:
    """
    RAG simplificado usando sentence-transformers + FAISS
    Sin reranking, sin BM25, sin complejidad
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._index = None
        self._documents: Dict[str, Document] = {}
        self._doc_list: List[str] = []  # Ordenado para mapear indices

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                logger.warning("sentence-transformers not installed, using mock")
                self._model = MockEmbedder()
        return self._model

    def _get_index(self):
        if self._index is None:
            try:
                import faiss
                # Crear indice FAISS (384 dimensiones para MiniLM)
                self._index = faiss.IndexFlatL2(384)
            except ImportError:
                logger.warning("faiss not installed, using mock")
                self._index = MockIndex()
        return self._index

    def add_document(self, doc_id: str, text: str, metadata: Dict = None):
        """Anadir documento al indice"""
        doc = Document(doc_id=doc_id, text=text, metadata=metadata)
        self._documents[doc_id] = doc
        self._doc_list.append(doc_id)

        # Generar embedding y anadir al indice
        model = self._get_model()
        index = self._get_index()

        try:
            import numpy as np
            embedding = model.encode([text])
            if isinstance(embedding, list):
                embedding = np.array(embedding)
            index.add(embedding.astype('float32'))
        except Exception as e:
            logger.error(f"Error adding document: {e}")

    def search(self, query: str, top_k: int = 3, creator_id: str = None) -> List[Dict]:
        """Buscar documentos relevantes"""
        if not self._documents:
            return []

        model = self._get_model()
        index = self._get_index()

        try:
            import numpy as np
            query_embedding = model.encode([query])
            if isinstance(query_embedding, list):
                query_embedding = np.array(query_embedding)

            distances, indices = index.search(query_embedding.astype('float32'), min(top_k, len(self._doc_list)))

            results = []

            for i, idx in enumerate(indices[0]):
                if idx < len(self._doc_list) and idx >= 0:
                    doc_id = self._doc_list[idx]
                    doc = self._documents.get(doc_id)

                    if doc:
                        # Filtrar por creator_id si se especifica
                        if creator_id and doc.metadata:
                            if doc.metadata.get("creator_id") != creator_id:
                                continue

                        results.append({
                            "doc_id": doc.doc_id,
                            "text": doc.text,
                            "metadata": doc.metadata,
                            "score": float(1 / (1 + distances[0][i]))  # Convertir distancia a score
                        })

            return results

        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []

    def delete_document(self, doc_id: str):
        """Eliminar documento (nota: FAISS no soporta delete eficiente)"""
        if doc_id in self._documents:
            del self._documents[doc_id]
            # Para delete real, habria que reconstruir el indice
            logger.warning("Document deleted from dict, but FAISS index not updated")

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Obtener documento por ID"""
        return self._documents.get(doc_id)

    def count(self) -> int:
        """Contar documentos indexados"""
        return len(self._documents)


class MockEmbedder:
    """Mock para cuando no hay sentence-transformers"""
    def encode(self, texts):
        import random
        return [[random.random() for _ in range(384)] for _ in texts]


class MockIndex:
    """Mock para cuando no hay FAISS"""
    def __init__(self):
        self.vectors = []

    def add(self, vectors):
        import numpy as np
        for v in vectors:
            self.vectors.append(v)

    def search(self, query, k):
        import numpy as np
        n = min(k, len(self.vectors))
        return np.zeros((1, n)), np.arange(n).reshape(1, -1)


class HybridRAG:
    """
    Hybrid RAG combining semantic search (FAISS) with lexical search (BM25).

    Benefits:
    - Semantic: understands meaning, handles synonyms
    - BM25: exact keyword matching, important for product names, technical terms
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", bm25_weight: float = 0.3):
        """
        Initialize HybridRAG.

        Args:
            model_name: Sentence transformer model for semantic search
            bm25_weight: Weight for BM25 scores (0.0-1.0), semantic gets (1-bm25_weight)
        """
        self.semantic_rag = SimpleRAG(model_name)
        self.bm25_weight = bm25_weight
        self._bm25 = None

    def _get_bm25(self):
        """Lazy load BM25 retriever"""
        if self._bm25 is None:
            try:
                from .bm25 import BM25Retriever
                self._bm25 = BM25Retriever()
            except ImportError:
                logger.warning("BM25 module not available, using semantic only")
        return self._bm25

    def add_document(self, doc_id: str, text: str, metadata: Dict = None):
        """Add document to both semantic and BM25 indices"""
        # Add to semantic index
        self.semantic_rag.add_document(doc_id, text, metadata)

        # Add to BM25 index
        bm25 = self._get_bm25()
        if bm25:
            bm25.add_document(doc_id, text, metadata)
            logger.debug(f"Document {doc_id} added to hybrid index")

    def search(
        self,
        query: str,
        top_k: int = 5,
        creator_id: str = None,
        use_hybrid: bool = True
    ) -> List[Dict]:
        """
        Search using hybrid semantic + BM25.

        Args:
            query: Search query
            top_k: Maximum results
            creator_id: Optional creator filter
            use_hybrid: If False, use semantic only

        Returns:
            List of results with combined scores
        """
        # Get semantic results
        semantic_results = self.semantic_rag.search(query, top_k * 2, creator_id)

        if not use_hybrid:
            return semantic_results[:top_k]

        # Get BM25 results
        bm25 = self._get_bm25()
        if not bm25:
            return semantic_results[:top_k]

        try:
            filter_metadata = {"creator_id": creator_id} if creator_id else None
            bm25_results = bm25.search(query, top_k * 2, filter_metadata=filter_metadata)

            # Combine scores
            combined = {}

            # Add semantic scores (normalized)
            max_semantic = max((r["score"] for r in semantic_results), default=1)
            for r in semantic_results:
                doc_id = r["doc_id"]
                norm_score = r["score"] / max_semantic if max_semantic > 0 else 0
                combined[doc_id] = {
                    "doc_id": doc_id,
                    "text": r["text"],
                    "metadata": r["metadata"],
                    "semantic_score": norm_score,
                    "bm25_score": 0,
                    "combined_score": norm_score * (1 - self.bm25_weight)
                }

            # Add BM25 scores (normalized)
            max_bm25 = max((r.score for r in bm25_results), default=1)
            for r in bm25_results:
                doc_id = r.doc_id
                norm_score = r.score / max_bm25 if max_bm25 > 0 else 0

                if doc_id in combined:
                    combined[doc_id]["bm25_score"] = norm_score
                    combined[doc_id]["combined_score"] += norm_score * self.bm25_weight
                else:
                    combined[doc_id] = {
                        "doc_id": doc_id,
                        "text": r.text,
                        "metadata": r.metadata,
                        "semantic_score": 0,
                        "bm25_score": norm_score,
                        "combined_score": norm_score * self.bm25_weight
                    }

            # Sort by combined score and return top_k
            sorted_results = sorted(
                combined.values(),
                key=lambda x: x["combined_score"],
                reverse=True
            )

            # Format results
            results = []
            for r in sorted_results[:top_k]:
                results.append({
                    "doc_id": r["doc_id"],
                    "text": r["text"],
                    "metadata": r["metadata"],
                    "score": r["combined_score"],
                    "semantic_score": r["semantic_score"],
                    "bm25_score": r["bm25_score"]
                })

            logger.info(f"Hybrid search: query='{query[:30]}...', results={len(results)}")
            return results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}, falling back to semantic")
            return semantic_results[:top_k]

    def delete_document(self, doc_id: str):
        """Delete from both indices"""
        self.semantic_rag.delete_document(doc_id)
        bm25 = self._get_bm25()
        if bm25:
            bm25.remove_document(doc_id)

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document by ID"""
        return self.semantic_rag.get_document(doc_id)

    def count(self) -> int:
        """Count indexed documents"""
        return self.semantic_rag.count()


# Singleton instances
_simple_rag: Optional[SimpleRAG] = None
_hybrid_rag: Optional[HybridRAG] = None


def get_simple_rag() -> SimpleRAG:
    """Get or create SimpleRAG singleton"""
    global _simple_rag
    if _simple_rag is None:
        _simple_rag = SimpleRAG()
    return _simple_rag


def get_hybrid_rag(bm25_weight: float = 0.3) -> HybridRAG:
    """Get or create HybridRAG singleton"""
    global _hybrid_rag
    if _hybrid_rag is None:
        _hybrid_rag = HybridRAG(bm25_weight=bm25_weight)
    return _hybrid_rag
