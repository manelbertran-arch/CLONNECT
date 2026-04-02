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

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("clonnect.semantic_memory_pgvector")

# Feature flag - separate from ENABLE_SEMANTIC_MEMORY (ChromaDB version)
# Set to "true" to enable pgvector-based semantic memory
ENABLE_SEMANTIC_MEMORY_PGVECTOR = (
    os.getenv("ENABLE_SEMANTIC_MEMORY_PGVECTOR", "true").lower() == "true"
)

# Minimum message length to store (avoid storing greetings like "hola", "ok")
MIN_MESSAGE_LENGTH = 20

# Default similarity threshold for search
DEFAULT_MIN_SIMILARITY = 0.70

# O2 (SimpleMem): Semantic density gating — skip messages that duplicate existing knowledge.
# If a new message has cosine similarity >= this threshold to an existing message, skip it.
REDUNDANCY_THRESHOLD = 0.92

# O3 (EMem): Simple coreference patterns — resolve pronouns before embedding.
# Maps pronoun phrases to placeholders that get filled with actual names.
import re
_COREF_PATTERNS_ES = [
    (re.compile(r"\b(ella|él)\s+(me dijo|dijo que|comentó)\b", re.IGNORECASE), "{name} {verb}"),
    (re.compile(r"\b(le|les)\s+(dije|comenté|pregunté)\b", re.IGNORECASE), "a {name} {verb}"),
]
_COREF_PATTERNS_EN = [
    (re.compile(r"\b(she|he)\s+(told me|said|mentioned)\b", re.IGNORECASE), "{name} {verb}"),
    (re.compile(r"\bI told (her|him)\b", re.IGNORECASE), "I told {name}"),
]


def _resolve_coreferences(content: str, lead_name: Optional[str] = None) -> str:
    """O3 (EMem): Resolve pronouns to actual names before embedding.

    This improves retrieval quality — "she told me about her business" becomes
    "Maria told me about her business", making it findable when searching for "Maria".
    """
    if not lead_name or len(lead_name) < 2:
        return content
    resolved = content
    for pattern, template in _COREF_PATTERNS_ES + _COREF_PATTERNS_EN:
        match = pattern.search(resolved)
        if match:
            groups = match.groups()
            replacement = template.format(name=lead_name, verb=groups[-1] if len(groups) > 1 else "")
            resolved = pattern.sub(replacement.strip(), resolved, count=1)
    return resolved


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
        self, role: str, content: str, metadata: Optional[Dict] = None,
        lead_name: Optional[str] = None,
    ) -> bool:
        """
        Add a message to semantic memory.

        Generates an embedding and stores it in PostgreSQL with pgvector.
        Messages shorter than MIN_MESSAGE_LENGTH are skipped (greetings, etc.)

        Optimizations applied:
          O2 (SimpleMem): Semantic density gating — skip if ≥92% similar to existing.
          O3 (EMem): Coreference resolution — resolve pronouns to lead_name before embedding.

        Args:
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata (intent, products mentioned, etc.)
            lead_name: Optional lead name for coreference resolution

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
            from api.database import get_db_session
            from core.embeddings import generate_embedding
            from sqlalchemy import text

            # O3 (EMem): Resolve coreferences before embedding
            resolved_content = _resolve_coreferences(content, lead_name)

            # Generate embedding
            embedding = generate_embedding(resolved_content)
            if not embedding:
                logger.warning("Failed to generate embedding for message")
                return False

            # Convert embedding to pgvector format
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            with get_db_session() as db:
                # O2 (SimpleMem): Semantic density gating — check if redundant
                dup_check = db.execute(
                    text(
                        """
                    SELECT 1
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                      AND follower_id = :follower_id
                      AND 1 - (embedding <=> CAST(:query AS vector)) >= :threshold
                    LIMIT 1
                    """
                    ),
                    {
                        "query": embedding_str,
                        "creator_id": self.creator_id,
                        "follower_id": self.follower_id,
                        "threshold": REDUNDANCY_THRESHOLD,
                    },
                ).fetchone()

                if dup_check:
                    logger.debug(f"Skipping redundant message (≥{REDUNDANCY_THRESHOLD} sim): {content[:50]}...")
                    return False

                # Store in database
                db.execute(
                    text(
                        """
                    INSERT INTO conversation_embeddings
                    (creator_id, follower_id, message_role, content, embedding, msg_metadata)
                    VALUES (:creator_id, :follower_id, :role, :content, CAST(:embedding AS vector), :metadata)
                    """
                    ),
                    {
                        "creator_id": self.creator_id,
                        "follower_id": self.follower_id,
                        "role": role,
                        "content": resolved_content,
                        "embedding": embedding_str,
                        "metadata": json.dumps(metadata or {}),
                    },
                )
                db.commit()

            logger.debug(f"Saved message to semantic memory: {resolved_content[:50]}...")
            return True

        except Exception as e:
            logger.error(f"Error saving to semantic memory: {e}")
            return False

    def search(
        self, query: str, k: int = 5, min_similarity: float = DEFAULT_MIN_SIMILARITY
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
            from api.database import get_db_session
            from core.embeddings import generate_embedding
            from sqlalchemy import text

            # Generate embedding for query
            query_embedding = generate_embedding(query)
            if not query_embedding:
                logger.warning("Failed to generate query embedding")
                return []

            # Convert to pgvector format
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            with get_db_session() as db:
                # Search using cosine similarity with temporal decay boost (O5, Memobase).
                # score = cosine_similarity * recency_boost
                # recency_boost = 1.0 for messages from today, decays to 0.7 over 90 days.
                # This prevents stale old messages from dominating when similarity is equal.
                results = db.execute(
                    text(
                        """
                    SELECT
                        content,
                        message_role,
                        msg_metadata,
                        created_at,
                        (1 - (embedding <=> CAST(:query AS vector)))
                          * (0.7 + 0.3 * GREATEST(0, 1.0 - EXTRACT(EPOCH FROM (NOW() - created_at)) / (90 * 86400)))
                          as similarity
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                      AND follower_id = :follower_id
                      AND 1 - (embedding <=> CAST(:query AS vector)) >= :min_sim
                    ORDER BY similarity DESC
                    LIMIT :k
                """
                    ),
                    {
                        "query": embedding_str,
                        "creator_id": self.creator_id,
                        "follower_id": self.follower_id,
                        "min_sim": min_similarity,
                        "k": k,
                    },
                )

                matches = []
                for row in results:
                    matches.append(
                        {
                            "content": row.content,
                            "role": row.message_role,
                            "similarity": round(float(row.similarity), 3),
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                            "metadata": row.msg_metadata or {},
                        }
                    )

                return matches

        except Exception as e:
            logger.error(f"Error searching semantic memory: {e}")
            return []

    def get_context_for_response(
        self,
        current_message: str,
        recent_messages: Optional[List[Dict]] = None,
        max_context_chars: int = 2000,
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
                h for h in relevant_history if h["content"][:100] not in recent_contents
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

                line = f'- {role_label} dijo: "{content_preview}"'

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
                result = db.execute(
                    text(
                        """
                    SELECT
                        COUNT(*) as total,
                        MIN(created_at) as first_contact,
                        MAX(created_at) as last_contact
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                      AND follower_id = :follower_id
                      AND message_role = 'user'
                """
                    ),
                    {"creator_id": self.creator_id, "follower_id": self.follower_id},
                )

                row = result.fetchone()
                if not row or not row.total:
                    return {"total_messages": 0}

                # Get sample messages for topics
                samples = db.execute(
                    text(
                        """
                    SELECT content
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                      AND follower_id = :follower_id
                      AND message_role = 'user'
                    ORDER BY created_at DESC
                    LIMIT 5
                """
                    ),
                    {"creator_id": self.creator_id, "follower_id": self.follower_id},
                )

                sample_topics = [r.content[:100] for r in samples]

                return {
                    "total_messages": row.total,
                    "first_contact": row.first_contact.isoformat() if row.first_contact else None,
                    "last_contact": row.last_contact.isoformat() if row.last_contact else None,
                    "sample_topics": sample_topics,
                }

        except Exception as e:
            logger.error(f"Error getting user summary: {e}")
            return {}


# =============================================================================
# Factory and Cache
# =============================================================================

from core.cache import BoundedTTLCache

# BUG-EP-01 fix: Replace unbounded dict with BoundedTTLCache (LRU + TTL)
_memory_cache: BoundedTTLCache = BoundedTTLCache(max_size=500, ttl_seconds=600)


def get_semantic_memory(creator_id: str, follower_id: str) -> SemanticMemoryPgvector:
    """
    Factory function to get a SemanticMemoryPgvector instance.

    Uses BoundedTTLCache with LRU eviction and 10-min TTL.

    Args:
        creator_id: Creator identifier
        follower_id: Follower identifier

    Returns:
        SemanticMemoryPgvector instance
    """
    cache_key = f"{creator_id}:{follower_id}"

    cached = _memory_cache.get(cache_key)
    if cached is not None:
        return cached

    instance = SemanticMemoryPgvector(creator_id, follower_id)
    _memory_cache.set(cache_key, instance)
    return instance


def clear_memory_cache():
    """Clear the memory cache (useful for tests)."""
    _memory_cache.clear()


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
                result = db.execute(
                    text(
                        """
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT follower_id) as followers
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                """
                    ),
                    {"creator_id": creator_id},
                )
            else:
                result = db.execute(
                    text(
                        """
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT creator_id) as creators,
                        COUNT(DISTINCT follower_id) as followers
                    FROM conversation_embeddings
                """
                    )
                )

            row = result.fetchone()
            if row:
                stats = {"enabled": True, "total_embeddings": row.total, "followers": row.followers}
                if not creator_id and hasattr(row, "creators"):
                    stats["creators"] = row.creators
                return stats

            return {"enabled": True, "total_embeddings": 0}

    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        return {"enabled": True, "error": str(e)}
