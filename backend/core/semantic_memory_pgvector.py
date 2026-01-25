"""
Semantic Memory with pgvector - Long-term conversation memory with semantic search.

Uses the same pgvector infrastructure as the RAG system.
Allows the bot to search through ALL conversation history by meaning.

Example:
    User: "What did I tell you about my business 2 months ago?"
    -> Semantic search finds the relevant messages, even if they were from months ago.

This module replaces/complements the ChromaDB-based semantic_memory.py with a
pgvector-based implementation that uses the same PostgreSQL database.

Usage:
    from core.semantic_memory_pgvector import get_semantic_memory, ENABLE_SEMANTIC_MEMORY_PGVECTOR

    if ENABLE_SEMANTIC_MEMORY_PGVECTOR:
        memory = get_semantic_memory(creator_id, follower_id)
        memory.add_message("user", "I have an online clothing store")

        # Later...
        context = memory.get_context_for_response("Tell me about their business")
        # Returns: "RELEVANT HISTORY:\n- User said: 'I have an online clothing store'"
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("clonnect.semantic_memory_pgvector")

# Feature flag - separate from ENABLE_SEMANTIC_MEMORY (ChromaDB version)
# Set to "true" to enable pgvector-based semantic memory
ENABLE_SEMANTIC_MEMORY_PGVECTOR = os.getenv("ENABLE_SEMANTIC_MEMORY_PGVECTOR", "false").lower() == "true"

# Minimum message length to store (avoid storing greetings like "hola", "ok")
MIN_MESSAGE_LENGTH = 20

# Default similarity threshold for search
DEFAULT_MIN_SIMILARITY = 0.70


class SemanticMemoryPgvector:
    """
    Semantic memory for conversations using pgvector.

    Stores message embeddings in PostgreSQL with pgvector for semantic search.
    Uses the same embedding model (text-embedding-3-small, 1536 dims) as RAG.

    Attributes:
        creator_id: The creator's identifier
        follower_id: The follower/user's identifier
    """

    def __init__(self, creator_id: str, follower_id: str):
        """
        Initialize semantic memory for a creator-follower pair.

        Args:
            creator_id: Creator identifier
            follower_id: Follower identifier
        """
        self.creator_id = creator_id
        self.follower_id = follower_id

    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Add a message to semantic memory.

        Generates an embedding and stores it in PostgreSQL with pgvector.
        Messages shorter than MIN_MESSAGE_LENGTH are skipped (greetings, etc.)

        Args:
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata (intent, products mentioned, etc.)

        Returns:
            True if saved successfully, False otherwise
        """
        if not ENABLE_SEMANTIC_MEMORY_PGVECTOR:
            return False

        # Skip short messages (greetings, acknowledgments)
        if len(content.strip()) < MIN_MESSAGE_LENGTH:
            logger.debug(f"Skipping short message ({len(content)} chars < {MIN_MESSAGE_LENGTH})")
            return False

        try:
            from core.embeddings import generate_embedding
            from api.database import get_db_session
            from sqlalchemy import text

            # Generate embedding
            embedding = generate_embedding(content)
            if not embedding:
                logger.warning("Failed to generate embedding for message")
                return False

            # Convert embedding to pgvector format
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            # Store in database
            with get_db_session() as db:
                db.execute(text("""
                    INSERT INTO conversation_embeddings
                    (creator_id, follower_id, message_role, content, embedding, msg_metadata)
                    VALUES (:creator_id, :follower_id, :role, :content, :embedding::vector, :metadata)
                """), {
                    "creator_id": self.creator_id,
                    "follower_id": self.follower_id,
                    "role": role,
                    "content": content,
                    "embedding": embedding_str,
                    "metadata": metadata or {}
                })
                db.commit()

            logger.debug(f"Saved message to semantic memory: {content[:50]}...")
            return True

        except Exception as e:
            logger.error(f"Error saving to semantic memory: {e}")
            return False

    def search(
        self,
        query: str,
        k: int = 5,
        min_similarity: float = DEFAULT_MIN_SIMILARITY
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant messages in conversation history.

        Uses pgvector cosine similarity to find semantically similar messages.

        Args:
            query: Search query text
            k: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of matching messages with similarity scores:
            [{"content": "...", "role": "user", "similarity": 0.85, "created_at": "...", "metadata": {...}}]
        """
        if not ENABLE_SEMANTIC_MEMORY_PGVECTOR:
            return []

        try:
            from core.embeddings import generate_embedding
            from api.database import get_db_session
            from sqlalchemy import text

            # Generate embedding for query
            query_embedding = generate_embedding(query)
            if not query_embedding:
                logger.warning("Failed to generate query embedding")
                return []

            # Convert to pgvector format
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            with get_db_session() as db:
                # Search using cosine similarity
                # cosine_distance = 1 - cosine_similarity, so similarity = 1 - distance
                results = db.execute(text("""
                    SELECT
                        content,
                        message_role,
                        msg_metadata,
                        created_at,
                        1 - (embedding <=> :query::vector) as similarity
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                      AND follower_id = :follower_id
                      AND 1 - (embedding <=> :query::vector) >= :min_sim
                    ORDER BY embedding <=> :query::vector
                    LIMIT :k
                """), {
                    "query": embedding_str,
                    "creator_id": self.creator_id,
                    "follower_id": self.follower_id,
                    "min_sim": min_similarity,
                    "k": k
                })

                matches = []
                for row in results:
                    matches.append({
                        "content": row.content,
                        "role": row.message_role,
                        "similarity": round(float(row.similarity), 3),
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "metadata": row.msg_metadata or {}
                    })

                return matches

        except Exception as e:
            logger.error(f"Error searching semantic memory: {e}")
            return []

    def get_context_for_response(
        self,
        current_message: str,
        recent_messages: Optional[List[Dict]] = None,
        max_context_chars: int = 2000
    ) -> str:
        """
        Generate enriched context for LLM response.

        Combines semantically relevant historical messages to provide
        context that the bot might have "forgotten" if only using recent messages.

        Args:
            current_message: Current user message
            recent_messages: List of recent messages (to avoid duplicates)
            max_context_chars: Maximum characters for context

        Returns:
            Formatted context string for prompt injection, or empty string
        """
        if not ENABLE_SEMANTIC_MEMORY_PGVECTOR:
            return ""

        try:
            # Search for relevant history
            relevant_history = self.search(current_message, k=3, min_similarity=0.75)

            if not relevant_history:
                return ""

            # Filter out messages that are in recent_messages to avoid duplication
            recent_contents = set()
            if recent_messages:
                for msg in recent_messages:
                    content = msg.get("content", "") or msg.get("text", "")
                    if content:
                        recent_contents.add(content[:100])  # First 100 chars for comparison

            unique_history = [
                h for h in relevant_history
                if h["content"][:100] not in recent_contents
            ]

            if not unique_history:
                return ""

            # Build context string
            context_parts = ["CONTEXTO HISTORICO RELEVANTE:"]
            chars_used = len(context_parts[0])

            for h in unique_history:
                role_label = "Usuario" if h["role"] == "user" else "Tu"
                content_preview = h["content"][:300]
                if len(h["content"]) > 300:
                    content_preview += "..."

                line = f"- {role_label} dijo: \"{content_preview}\""

                if chars_used + len(line) > max_context_chars:
                    break

                context_parts.append(line)
                chars_used += len(line)

            if len(context_parts) > 1:
                return "\n".join(context_parts)

            return ""

        except Exception as e:
            logger.error(f"Error getting context for response: {e}")
            return ""

    def get_user_summary(self) -> Dict[str, Any]:
        """
        Generate a summary of the user based on their conversation history.

        Returns:
            Dict with summary: total_messages, first_contact, last_contact, sample_topics
        """
        if not ENABLE_SEMANTIC_MEMORY_PGVECTOR:
            return {}

        try:
            from api.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as db:
                # Get message stats
                result = db.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        MIN(created_at) as first_contact,
                        MAX(created_at) as last_contact
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                      AND follower_id = :follower_id
                      AND message_role = 'user'
                """), {
                    "creator_id": self.creator_id,
                    "follower_id": self.follower_id
                })

                row = result.fetchone()
                if not row or not row.total:
                    return {"total_messages": 0}

                # Get sample messages for topics
                samples = db.execute(text("""
                    SELECT content
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                      AND follower_id = :follower_id
                      AND message_role = 'user'
                    ORDER BY created_at DESC
                    LIMIT 5
                """), {
                    "creator_id": self.creator_id,
                    "follower_id": self.follower_id
                })

                sample_topics = [r.content[:100] for r in samples]

                return {
                    "total_messages": row.total,
                    "first_contact": row.first_contact.isoformat() if row.first_contact else None,
                    "last_contact": row.last_contact.isoformat() if row.last_contact else None,
                    "sample_topics": sample_topics
                }

        except Exception as e:
            logger.error(f"Error getting user summary: {e}")
            return {}


# =============================================================================
# Factory and Cache
# =============================================================================

# Cache of memory instances by creator+follower
_memory_cache: Dict[str, SemanticMemoryPgvector] = {}


def get_semantic_memory(creator_id: str, follower_id: str) -> SemanticMemoryPgvector:
    """
    Factory function to get a SemanticMemoryPgvector instance.

    Uses caching to reuse instances for the same creator-follower pair.

    Args:
        creator_id: Creator identifier
        follower_id: Follower identifier

    Returns:
        SemanticMemoryPgvector instance
    """
    cache_key = f"{creator_id}:{follower_id}"

    if cache_key not in _memory_cache:
        _memory_cache[cache_key] = SemanticMemoryPgvector(creator_id, follower_id)

    return _memory_cache[cache_key]


def clear_memory_cache():
    """Clear the memory cache (useful for tests)."""
    global _memory_cache
    _memory_cache = {}


# =============================================================================
# Utility Functions
# =============================================================================

def get_memory_stats(creator_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get statistics about stored conversation embeddings.

    Args:
        creator_id: Optional filter by creator

    Returns:
        Dict with stats: total_embeddings, creators_count, etc.
    """
    if not ENABLE_SEMANTIC_MEMORY_PGVECTOR:
        return {"enabled": False}

    try:
        from api.database import get_db_session
        from sqlalchemy import text

        with get_db_session() as db:
            if creator_id:
                result = db.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT follower_id) as followers
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                """), {"creator_id": creator_id})
            else:
                result = db.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT creator_id) as creators,
                        COUNT(DISTINCT follower_id) as followers
                    FROM conversation_embeddings
                """))

            row = result.fetchone()
            if row:
                stats = {
                    "enabled": True,
                    "total_embeddings": row.total,
                    "followers": row.followers
                }
                if not creator_id and hasattr(row, 'creators'):
                    stats["creators"] = row.creators
                return stats

            return {"enabled": True, "total_embeddings": 0}

    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        return {"enabled": True, "error": str(e)}
