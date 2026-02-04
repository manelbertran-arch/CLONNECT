"""PostContext Service - Orchestrates post context analysis.

Main service that:
1. Checks for cached context
2. Refreshes if expired
3. Provides prompt instructions for dm_agent

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from models.post_context import PostContext
from services.instagram_post_fetcher import fetch_creator_posts
from services.post_analyzer import analyze_creator_posts
from services.post_context_repository import (
    create_post_context,
    get_post_context,
    update_post_context,
)

logger = logging.getLogger(__name__)

# Cache TTL in hours
CACHE_TTL_HOURS = 6

# How many days of posts to analyze
POSTS_LOOKBACK_DAYS = 7

# Max posts to analyze
MAX_POSTS = 10


class PostContextService:
    """Orchestrates post context fetching, analysis, and caching."""

    def __init__(self, cache_ttl_hours: int = CACHE_TTL_HOURS):
        """Initialize service.

        Args:
            cache_ttl_hours: How long to cache context
        """
        self.cache_ttl_hours = cache_ttl_hours

    async def get_or_refresh(self, creator_id: str) -> Dict[str, Any]:
        """Get cached context or refresh if needed.

        Args:
            creator_id: Creator identifier

        Returns:
            Context dict with promotions, topics, instructions
        """
        try:
            # Check cache
            cached = get_post_context(creator_id)

            if cached and not self._is_expired(cached):
                logger.debug(f"Using cached context for {creator_id}")
                return cached

            # Refresh if expired or missing
            logger.info(f"Refreshing context for {creator_id}")
            return await self._refresh_context(creator_id)

        except Exception as e:
            logger.error(f"Error in get_or_refresh for {creator_id}: {e}")
            return self._default_context(creator_id)

    async def get_prompt_instructions(self, creator_id: str) -> str:
        """Get prompt instructions for dm_agent.

        Args:
            creator_id: Creator identifier

        Returns:
            String to add to bot prompt
        """
        context = get_post_context(creator_id)

        if not context:
            return "Sin contexto especial de posts recientes."

        # Build prompt addition from context
        ctx = PostContext(
            creator_id=context["creator_id"],
            active_promotion=context.get("active_promotion"),
            promotion_urgency=context.get("promotion_urgency"),
            recent_topics=context.get("recent_topics", []),
            recent_products=context.get("recent_products", []),
            availability_hint=context.get("availability_hint"),
            context_instructions=context.get(
                "context_instructions", "Sin contexto especial."
            ),
            expires_at=context.get("expires_at", datetime.now(timezone.utc)),
        )

        return ctx.to_prompt_addition()

    async def force_refresh(self, creator_id: str) -> Dict[str, Any]:
        """Force refresh context regardless of cache.

        Args:
            creator_id: Creator identifier

        Returns:
            Fresh context dict
        """
        logger.info(f"Force refreshing context for {creator_id}")
        return await self._refresh_context(creator_id)

    async def _refresh_context(self, creator_id: str) -> Dict[str, Any]:
        """Fetch posts, analyze, and save context.

        Args:
            creator_id: Creator identifier

        Returns:
            Fresh context dict
        """
        try:
            # Fetch recent posts
            posts = await fetch_creator_posts(
                creator_id,
                days=POSTS_LOOKBACK_DAYS,
                limit=MAX_POSTS,
            )

            if not posts:
                logger.warning(f"No posts found for {creator_id}")
                return self._save_default_context(creator_id)

            # Analyze posts with LLM
            analysis = await analyze_creator_posts(posts)

            # Build context data
            context_data = {
                "creator_id": creator_id,
                "active_promotion": analysis.get("active_promotion"),
                "promotion_deadline": analysis.get("promotion_deadline"),
                "promotion_urgency": analysis.get("promotion_urgency"),
                "recent_topics": analysis.get("recent_topics", []),
                "recent_products": analysis.get("recent_products", []),
                "availability_hint": analysis.get("availability_hint"),
                "context_instructions": analysis.get(
                    "context_instructions", "Contexto extraído de posts."
                ),
                "posts_analyzed": len(posts),
                "analyzed_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc)
                + timedelta(hours=self.cache_ttl_hours),
                "source_posts": [p.get("id") for p in posts if p.get("id")],
            }

            # Save to database
            existing = get_post_context(creator_id)
            if existing:
                update_post_context(creator_id, context_data)
            else:
                create_post_context(context_data)

            logger.info(
                f"Refreshed context for {creator_id}: "
                f"promo={bool(analysis.get('active_promotion'))}, "
                f"topics={len(analysis.get('recent_topics', []))}"
            )

            return context_data

        except Exception as e:
            logger.error(f"Error refreshing context for {creator_id}: {e}")
            return self._default_context(creator_id)

    def _is_expired(self, context: Dict[str, Any]) -> bool:
        """Check if context is expired.

        Args:
            context: Context dict

        Returns:
            True if expired
        """
        expires_at = context.get("expires_at")

        if not expires_at:
            return True

        # Handle datetime object or string
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        # Handle naive datetime
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return datetime.now(timezone.utc) > expires_at

    def _default_context(self, creator_id: str) -> Dict[str, Any]:
        """Return default context when refresh fails.

        Args:
            creator_id: Creator identifier

        Returns:
            Default context dict
        """
        return {
            "creator_id": creator_id,
            "active_promotion": None,
            "promotion_deadline": None,
            "promotion_urgency": None,
            "recent_topics": [],
            "recent_products": [],
            "availability_hint": None,
            "context_instructions": "Sin contexto especial disponible.",
            "posts_analyzed": 0,
            "analyzed_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "source_posts": [],
        }

    def _save_default_context(self, creator_id: str) -> Dict[str, Any]:
        """Save default context when no posts found.

        Args:
            creator_id: Creator identifier

        Returns:
            Default context dict
        """
        context = self._default_context(creator_id)
        context["context_instructions"] = "Sin posts recientes para analizar."

        existing = get_post_context(creator_id)
        if existing:
            update_post_context(creator_id, context)
        else:
            create_post_context(context)

        return context


# Module-level service instance
_service: Optional[PostContextService] = None


def get_post_context_service() -> PostContextService:
    """Get singleton service instance.

    Returns:
        PostContextService instance
    """
    global _service
    if _service is None:
        _service = PostContextService()
    return _service


# Convenience functions
async def get_creator_post_context(creator_id: str) -> Dict[str, Any]:
    """Get or refresh post context for creator.

    Args:
        creator_id: Creator identifier

    Returns:
        Context dict
    """
    service = get_post_context_service()
    return await service.get_or_refresh(creator_id)


async def get_creator_prompt_instructions(creator_id: str) -> str:
    """Get prompt instructions for creator.

    Args:
        creator_id: Creator identifier

    Returns:
        Instructions string
    """
    service = get_post_context_service()
    return await service.get_prompt_instructions(creator_id)
