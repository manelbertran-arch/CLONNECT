"""Instagram Post Fetcher - Fetches recent posts from Instagram Graph API.

Retrieves creator's recent posts for context analysis.
Uses Instagram Graph API with creator's stored access token.

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Instagram Graph API base URL
INSTAGRAM_API_BASE = "https://graph.instagram.com"


def get_session():
    """Get database session."""
    try:
        from api.services.db_service import get_session as db_get_session

        return db_get_session()
    except ImportError:
        logger.warning("Database service not available")
        return None


class InstagramPostFetcher:
    """Fetches recent posts from Instagram Graph API."""

    def __init__(self, timeout: int = 30):
        """Initialize fetcher.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    async def fetch_recent_posts(
        self,
        creator_id: str,
        days: int = 7,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fetch recent posts from creator's Instagram.

        Args:
            creator_id: Creator identifier
            days: Number of days to look back
            limit: Maximum number of posts to fetch

        Returns:
            List of post dicts with id, caption, timestamp, media_type
        """
        try:
            # Get creator's Instagram credentials
            token, user_id = self._get_creator_credentials(creator_id)

            if not token or not user_id:
                logger.warning(f"No Instagram credentials for {creator_id}")
                return []

            # Fetch posts from API
            response = await self._call_instagram_api(user_id, token, limit)

            if not response or "data" not in response:
                return []

            # Filter and format posts
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            posts = []

            for post_data in response.get("data", []):
                post = self._format_post(post_data)
                if post and self._is_within_date_range(post, cutoff_date):
                    posts.append(post)

            logger.info(f"Fetched {len(posts)} posts for {creator_id}")
            return posts

        except Exception as e:
            logger.error(f"Error fetching posts for {creator_id}: {e}")
            return []

    def _get_creator_credentials(self, creator_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Get Instagram token and user ID for creator.

        Args:
            creator_id: Creator identifier

        Returns:
            Tuple of (token, user_id) or (None, None) if not found
        """
        session = get_session()
        if not session:
            return None, None

        try:
            from api.models import Creator

            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                logger.warning(f"Creator not found: {creator_id}")
                return None, None

            return creator.instagram_token, creator.instagram_user_id

        except Exception as e:
            logger.error(f"Error getting credentials for {creator_id}: {e}")
            return None, None
        finally:
            session.close()

    async def _call_instagram_api(
        self,
        user_id: str,
        token: str,
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        """Call Instagram Graph API to fetch media.

        Args:
            user_id: Instagram user ID
            token: Access token
            limit: Max items to fetch

        Returns:
            API response dict or None on error
        """
        url = f"{INSTAGRAM_API_BASE}/{user_id}/media"
        params = {
            "access_token": token,
            "fields": "id,caption,timestamp,media_type,permalink,thumbnail_url",
            "limit": limit,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Instagram API HTTP error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Instagram API error: {e}")
            return None

    def _format_post(self, post_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Format raw API response to standard post format.

        Args:
            post_data: Raw post data from API

        Returns:
            Formatted post dict or None if invalid
        """
        try:
            return {
                "id": post_data.get("id"),
                "caption": post_data.get("caption", ""),
                "timestamp": post_data.get("timestamp"),
                "media_type": post_data.get("media_type"),
                "permalink": post_data.get("permalink"),
            }
        except Exception as e:
            logger.error(f"Error formatting post: {e}")
            return None

    def _is_within_date_range(
        self,
        post: Dict[str, Any],
        cutoff_date: datetime,
    ) -> bool:
        """Check if post is within date range.

        Args:
            post: Post dict with timestamp
            cutoff_date: Earliest allowed date

        Returns:
            True if post is recent enough
        """
        try:
            timestamp_str = post.get("timestamp")
            if not timestamp_str:
                return False

            # Parse Instagram timestamp format
            post_date = datetime.strptime(
                timestamp_str, "%Y-%m-%dT%H:%M:%S%z"
            )

            return post_date >= cutoff_date

        except Exception as e:
            logger.error(f"Error parsing timestamp: {e}")
            return False


# Module-level function for easy access
async def fetch_creator_posts(
    creator_id: str,
    days: int = 7,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Convenience function to fetch creator's posts.

    Args:
        creator_id: Creator identifier
        days: Days to look back
        limit: Max posts

    Returns:
        List of post dicts
    """
    fetcher = InstagramPostFetcher()
    return await fetcher.fetch_recent_posts(creator_id, days, limit)
