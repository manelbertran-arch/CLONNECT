"""
Semantic Memory - Memoria de conversaciones con búsqueda semántica.

Permite:
- Guardar historial de conversaciones por lead
- Buscar en el historial por SIGNIFICADO (no solo keywords)
- "¿Cómo sabe eso de mí?" - El bot recuerda contexto relevante

Dependencias: chromadb>=0.4.22, sentence-transformers>=2.2.0
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("clonnect.semantic_memory")

# Feature flag
ENABLE_SEMANTIC_MEMORY = os.getenv("ENABLE_SEMANTIC_MEMORY", "true").lower() == "true"

# Lazy loading
_embeddings_model = None
_chroma_available = False

try:
    import chromadb
    _chroma_available = True
except ImportError:
    logger.warning("ChromaDB not installed. Semantic search disabled. Install: pip install chromadb")


def _get_embeddings():
    """Lazy load del modelo de embeddings"""
    global _embeddings_model
    if _embeddings_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model for semantic memory...")
            _embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Embedding model loaded")
        except ImportError:
            logger.error("sentence-transformers not installed")
    return _embeddings_model


class ConversationMemory:
    """
    Memoria de conversación con búsqueda semántica.

    Uso:
        >>> memory = ConversationMemory("lead_123", "creator_456")
        >>> memory.add_message("user", "Me interesa el curso pero es caro")
        >>> memory.add_message("assistant", "Tenemos opciones de pago...")
        >>>
        >>> # Días después, en nueva conversación:
        >>> context = memory.search("opciones de pago")
        >>> # Retorna: mensajes donde se habló de pagos
    """

    def __init__(
        self,
        user_id: str,
        creator_id: str,
        storage_path: str = "data/memory"
    ):
        self.user_id = user_id
        self.creator_id = creator_id
        self.storage_path = Path(storage_path) / creator_id / user_id
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Historial JSON (backup y fallback)
        self.history: List[Dict[str, str]] = []
        self.history_file = self.storage_path / "history.json"

        # Vector store
        self.collection = None

        if ENABLE_SEMANTIC_MEMORY and _chroma_available:
            self._init_vector_store()

        self._load_history()

    def _init_vector_store(self):
        """Inicializa ChromaDB"""
        try:
            client = chromadb.PersistentClient(
                path=str(self.storage_path / "chroma")
            )
            self.collection = client.get_or_create_collection(
                name=f"memory_{self.creator_id}_{self.user_id}"[:63],  # ChromaDB limit
                metadata={"user_id": self.user_id, "creator_id": self.creator_id}
            )
            logger.debug(f"Initialized semantic memory for {self.user_id}")
        except Exception as e:
            logger.error(f"Failed to init vector store: {e}")
            self.collection = None

    def _load_history(self):
        """Carga historial desde JSON"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            self.history = []

    def _save_history(self):
        """Guarda historial a JSON"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                # Guardar últimos 200 mensajes
                json.dump(self.history[-200:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving history: {e}")

    def add_message(self, role: str, content: str, metadata: Dict = None):
        """
        Añade mensaje al historial y al vector store.

        Args:
            role: "user" o "assistant"
            content: Contenido del mensaje
            metadata: Metadata adicional
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
            **(metadata or {})
        }

        self.history.append(message)

        # Añadir a vector store (solo mensajes significativos)
        if self.collection and len(content) > 20:
            try:
                embeddings = _get_embeddings()
                if embeddings:
                    embedding = embeddings.encode(content).tolist()
                    msg_id = f"{timestamp}_{len(self.history)}"

                    self.collection.add(
                        ids=[msg_id],
                        embeddings=[embedding],
                        documents=[content],
                        metadatas=[{"role": role, "timestamp": timestamp}]
                    )
            except Exception as e:
                logger.warning(f"Could not add to vector store: {e}")

        self._save_history()

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Busca mensajes relevantes en el historial.

        Args:
            query: Texto para buscar contexto relevante
            k: Número de resultados

        Returns:
            Lista de mensajes relevantes con scores
        """
        if not self.collection or not ENABLE_SEMANTIC_MEMORY:
            # Fallback: últimos k mensajes
            return self.history[-k:]

        try:
            embeddings = _get_embeddings()
            if not embeddings:
                return self.history[-k:]

            query_embedding = embeddings.encode(query).tolist()

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(k, self.collection.count() or 1)
            )

            relevant = []
            if results and results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                    distance = results['distances'][0][i] if results['distances'] else 0

                    relevant.append({
                        "content": doc,
                        "role": metadata.get("role", "unknown"),
                        "timestamp": metadata.get("timestamp", ""),
                        "relevance_score": 1 - distance
                    })

            return relevant
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return self.history[-k:]

    def get_recent(self, n: int = 10) -> List[Dict[str, str]]:
        """Obtiene los últimos n mensajes"""
        return self.history[-n:]

    def get_context_for_query(self, query: str, recent_n: int = 5, semantic_k: int = 3) -> str:
        """
        Obtiene contexto combinado: mensajes recientes + relevantes semánticamente.

        Returns:
            String formateado con el contexto para el prompt
        """
        context_parts = []

        # Mensajes recientes
        recent = self.get_recent(recent_n)
        if recent:
            context_parts.append("CONVERSACION RECIENTE:")
            for msg in recent:
                role = "Usuario" if msg["role"] == "user" else "Asistente"
                context_parts.append(f"{role}: {msg['content'][:200]}")

        # Mensajes relevantes del pasado
        if ENABLE_SEMANTIC_MEMORY and self.collection:
            relevant = self.search(query, k=semantic_k)
            # Filtrar los que ya están en recientes
            recent_contents = {m["content"] for m in recent}
            relevant = [r for r in relevant if r["content"] not in recent_contents]

            if relevant:
                context_parts.append("\nCONTEXTO RELEVANTE DE CONVERSACIONES ANTERIORES:")
                for msg in relevant:
                    role = "Usuario" if msg["role"] == "user" else "Asistente"
                    context_parts.append(f"{role}: {msg['content'][:200]}")

        return "\n".join(context_parts) if context_parts else ""

    def clear(self):
        """Limpia todo el historial"""
        self.history = []
        self._save_history()
        if self.collection:
            try:
                # Eliminar todos los documentos
                ids = self.collection.get()['ids']
                if ids:
                    self.collection.delete(ids=ids)
            except Exception as e:
                logger.warning(f"Could not clear vector store: {e}")


# Cache global
_memories: Dict[str, ConversationMemory] = {}


def get_conversation_memory(
    user_id: str,
    creator_id: str,
    storage_path: str = "data/memory"
) -> ConversationMemory:
    """Obtiene o crea memoria de conversación"""
    cache_key = f"{creator_id}:{user_id}"
    if cache_key not in _memories:
        _memories[cache_key] = ConversationMemory(user_id, creator_id, storage_path)
    return _memories[cache_key]


def clear_memory_cache():
    """Limpia cache de memorias"""
    global _memories
    _memories = {}
