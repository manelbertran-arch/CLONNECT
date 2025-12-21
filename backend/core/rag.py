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
