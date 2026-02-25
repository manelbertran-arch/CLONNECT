"""
Knowledge management for DM Agent V2.

Functions for adding, batch-adding, and clearing RAG documents.
Each function takes `agent` as first parameter.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def add_knowledge(agent, content: str, metadata: Optional[Dict] = None) -> str:
    """Add knowledge to RAG index. Returns document ID."""
    agent.semantic_rag.add_document(
        doc_id=f"manual_{len(agent.semantic_rag._documents)}",
        text=content,
        metadata=metadata or {},
    )
    return f"manual_{len(agent.semantic_rag._documents) - 1}"


def add_knowledge_batch(agent, documents: List[Dict[str, Any]]) -> List[str]:
    """Add multiple documents to RAG index. Returns list of document IDs."""
    doc_ids = []
    for doc in documents:
        agent.semantic_rag.add_document(
            doc_id=f"batch_{len(agent.semantic_rag._documents)}",
            text=doc.get("content", ""),
            metadata=doc.get("metadata", {}),
        )
        doc_id = f"batch_{len(agent.semantic_rag._documents) - 1}"
        doc_ids.append(doc_id)
    return doc_ids


def clear_knowledge(agent) -> None:
    """Clear all knowledge from RAG index."""
    agent.semantic_rag._documents.clear()
    agent.semantic_rag._doc_list.clear()
