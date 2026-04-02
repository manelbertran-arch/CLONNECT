"""RelationshipDNAService for dm_agent integration.

Orchestrates RelationshipDNA functionality:
- Loading DNA for leads
- Creating DNA for new leads
- Generating prompt instructions
- Recording interactions

Part of RELATIONSHIP-DNA feature.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.cache import BoundedTTLCache
from services.bot_instructions_generator import BotInstructionsGenerator
from services.relationship_dna_repository import (
    create_relationship_dna,
    get_or_create_relationship_dna,
    get_relationship_dna,
    update_relationship_dna,
)

logger = logging.getLogger(__name__)


class RelationshipDNAService:
    """Service for managing RelationshipDNA in dm_agent context.

    Provides a clean interface for:
    - Loading DNA for leads
    - Generating prompt instructions from DNA
    - Recording interactions to update DNA
    """

    def __init__(self):
        """Initialize the service."""
        self._instructions_generator = BotInstructionsGenerator()
        self._cache = BoundedTTLCache(max_size=500, ttl_seconds=300)

    def get_dna_for_lead(self, creator_id: str, follower_id: str) -> Optional[Dict]:
        """Get DNA for a lead if it exists.

        Args:
            creator_id: Creator identifier
            follower_id: Lead/follower identifier

        Returns:
            DNA dict if exists, None otherwise
        """
        cache_key = f"{creator_id}:{follower_id}"

        # Check cache first
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Load from database
        dna = get_relationship_dna(creator_id, follower_id)

        if dna:
            self._cache.set(cache_key, dna)

        return dna

    def get_or_create_dna(
        self,
        creator_id: str,
        follower_id: str,
        messages: Optional[List[Dict]] = None,
    ) -> Optional[Dict]:
        """Get existing DNA or create new one.

        Args:
            creator_id: Creator identifier
            follower_id: Lead/follower identifier
            messages: Optional conversation history for analysis

        Returns:
            DNA dict
        """
        # Try to get existing
        dna = self.get_dna_for_lead(creator_id, follower_id)
        if dna:
            return dna

        # Create new DNA with defaults
        dna = get_or_create_relationship_dna(creator_id, follower_id)

        if dna:
            cache_key = f"{creator_id}:{follower_id}"
            self._cache.set(cache_key, dna)

        return dna

    def get_prompt_instructions(self, dna_data: Optional[Dict]) -> str:
        """Generate prompt instructions from DNA data.

        This is the key integration point - generates instructions
        that can be added to the system prompt.

        Args:
            dna_data: DNA dict or None

        Returns:
            String with instructions or empty string if no DNA
        """
        if not dna_data:
            return ""

        # Use the BotInstructionsGenerator
        return self._instructions_generator.generate(dna_data)

    def get_instructions_for_lead(
        self, creator_id: str, follower_id: str
    ) -> str:
        """Convenience method to get instructions for a lead.

        Args:
            creator_id: Creator identifier
            follower_id: Lead/follower identifier

        Returns:
            Instructions string or empty string
        """
        dna = self.get_dna_for_lead(creator_id, follower_id)
        return self.get_prompt_instructions(dna)

    def record_interaction(
        self, creator_id: str, follower_id: str
    ) -> bool:
        """Record that an interaction happened with a lead.

        Updates the DNA's interaction count and timestamp.

        Args:
            creator_id: Creator identifier
            follower_id: Lead/follower identifier

        Returns:
            True if updated, False otherwise
        """
        # Get current DNA
        dna = self.get_dna_for_lead(creator_id, follower_id)

        if not dna:
            return False

        # Update with new interaction data
        current_count = dna.get("total_messages_analyzed", 0)

        result = update_relationship_dna(
            creator_id,
            follower_id,
            {
                "total_messages_analyzed": current_count + 1,
                "last_analyzed_at": datetime.now(timezone.utc),
            },
        )

        # Invalidate cache
        cache_key = f"{creator_id}:{follower_id}"
        self._cache.pop(cache_key)

        return result

    def analyze_and_update_dna(
        self,
        creator_id: str,
        follower_id: str,
        messages: List[Dict],
    ) -> Optional[Dict]:
        """Analyze conversation and update DNA.

        Full analysis pipeline - should be called periodically,
        not on every message.

        Args:
            creator_id: Creator identifier
            follower_id: Lead/follower identifier
            messages: Full conversation history

        Returns:
            Updated DNA dict
        """
        from services.relationship_analyzer import RelationshipAnalyzer
        from services.vocabulary_extractor import build_global_corpus

        analyzer = RelationshipAnalyzer()

        # Get or create DNA
        existing = self.get_dna_for_lead(creator_id, follower_id)

        # Check if update needed
        if existing and not analyzer.should_update_dna(
            existing, len(messages)
        ):
            return existing

        # Build global corpus for TF-IDF distinctiveness
        global_vocab, total_leads, leads_per_word = build_global_corpus(creator_id)

        # Run full analysis
        analysis = analyzer.analyze(
            creator_id, follower_id, messages,
            global_vocab=global_vocab, total_leads=total_leads,
            leads_per_word=leads_per_word,
        )

        if not existing:
            # Create new DNA
            dna = create_relationship_dna(
                creator_id=creator_id,
                follower_id=follower_id,
                relationship_type=analysis.get("relationship_type"),
                trust_score=analysis.get("trust_score", 0.0),
                depth_level=analysis.get("depth_level", 0),
                vocabulary_uses=analysis.get("vocabulary_uses", []),
                vocabulary_avoids=analysis.get("vocabulary_avoids", []),
                emojis=analysis.get("emojis", []),
                bot_instructions=analysis.get("bot_instructions"),
                golden_examples=analysis.get("golden_examples", []),
            )
        else:
            # Update existing DNA
            update_relationship_dna(
                creator_id,
                follower_id,
                {
                    "relationship_type": analysis.get("relationship_type"),
                    "trust_score": analysis.get("trust_score"),
                    "depth_level": analysis.get("depth_level"),
                    "vocabulary_uses": analysis.get("vocabulary_uses"),
                    "vocabulary_avoids": analysis.get("vocabulary_avoids"),
                    "emojis": analysis.get("emojis"),
                    "avg_message_length": analysis.get("avg_message_length"),
                    "questions_frequency": analysis.get("questions_frequency"),
                    "multi_message_frequency": analysis.get("multi_message_frequency"),
                    "tone_description": analysis.get("tone_description"),
                    "recurring_topics": analysis.get("recurring_topics"),
                    "bot_instructions": analysis.get("bot_instructions"),
                    "golden_examples": analysis.get("golden_examples"),
                    "total_messages_analyzed": len(messages),
                    "last_analyzed_at": datetime.now(timezone.utc),
                },
            )
            dna = self.get_dna_for_lead(creator_id, follower_id)

        # Invalidate cache
        cache_key = f"{creator_id}:{follower_id}"
        self._cache.pop(cache_key)

        return dna

    def clear_cache(self, creator_id: str = None, follower_id: str = None):
        """Clear cache for specific lead or all leads.

        Args:
            creator_id: Optional creator to filter
            follower_id: Optional follower to filter
        """
        if creator_id and follower_id:
            cache_key = f"{creator_id}:{follower_id}"
            self._cache.pop(cache_key)
        else:
            # BoundedTTLCache doesn't support prefix iteration;
            # clear all entries (rare operation, acceptable).
            self._cache.clear()


# Module-level singleton for dm_agent integration
_dna_service: Optional[RelationshipDNAService] = None


def get_dna_service() -> RelationshipDNAService:
    """Get the singleton DNA service instance."""
    global _dna_service
    if _dna_service is None:
        _dna_service = RelationshipDNAService()
    return _dna_service
