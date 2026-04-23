"""
Instagram Posts repository — PostgreSQL persistence for raw IG post content.

Domain
------
Source-of-truth content lake for a creator's Instagram posts. Rows are
populated from the Instagram Graph API (ingestion v2) and from the feed
webhook on new posts. Downstream: `auto_configurator` mines captions to
refine the tone profile; the ingestion pipeline splits captions into
content chunks for RAG.

Pipeline phase
--------------
INGESTIÓN batch + webhook-driven refresh. Never read from the DM hot path.

Storage
-------
Table: `instagram_posts` (SQLAlchemy model `api.models.InstagramPost`).
Natural key: `(creator_id, post_id)`.

Public accessors
----------------
- save_instagram_posts_db(creator_id, posts)      -> int (rows processed)
- get_instagram_posts_db(creator_id)              -> List[dict]  (ORDER BY post_timestamp DESC)
- delete_instagram_posts_db(creator_id)           -> int (rows deleted)
- get_instagram_posts_count_db(creator_id)        -> int (sync count)

Notes
-----
- Hashtags and mentions are parsed from the caption at save-time via simple
  whitespace-split. Edge cases (emojis adjacent to '#', etc.) are kept
  forgiving — a malformed tag yields a no-op rather than a hard error.
- Timestamps are parsed via `dateutil.parser.parse`; malformed timestamps
  are logged as a warning and the row is saved with `timestamp=None`.
"""

from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)


async def save_instagram_posts_db(creator_id: str, posts: List[dict]) -> int:
    """Upsert Instagram posts for a creator. Returns count of rows processed."""
    try:
        from api.database import get_db_session
        from api.models import InstagramPost
        from dateutil.parser import parse as parse_date

        saved_count = 0

        with get_db_session() as db:
            for post in posts:
                post_id = post.get("id", post.get("post_id", ""))

                existing = db.query(InstagramPost).filter(
                    InstagramPost.creator_id == creator_id,
                    InstagramPost.post_id == post_id,
                ).first()

                timestamp = None
                if post.get("timestamp"):
                    try:
                        timestamp = parse_date(post["timestamp"])
                    except (ValueError, TypeError) as e:
                        logger.warning("Failed to parse post timestamp: %s", e)

                caption = post.get("caption", "") or ""
                hashtags = [tag.strip("#") for tag in caption.split() if tag.startswith("#")]
                mentions = [m.strip("@") for m in caption.split() if m.startswith("@")]

                if existing:
                    existing.caption = caption
                    existing.permalink = post.get("permalink")
                    existing.media_type = post.get("media_type")
                    existing.media_url = post.get("media_url")
                    existing.thumbnail_url = post.get("thumbnail_url")
                    existing.post_timestamp = timestamp
                    existing.likes_count = post.get("like_count", 0)
                    existing.comments_count = post.get("comments_count", 0)
                    existing.hashtags = hashtags
                    existing.mentions = mentions
                else:
                    new_post = InstagramPost(
                        creator_id=creator_id,
                        post_id=post_id,
                        caption=caption,
                        permalink=post.get("permalink"),
                        media_type=post.get("media_type"),
                        media_url=post.get("media_url"),
                        thumbnail_url=post.get("thumbnail_url"),
                        post_timestamp=timestamp,
                        likes_count=post.get("like_count", 0),
                        comments_count=post.get("comments_count", 0),
                        hashtags=hashtags,
                        mentions=mentions,
                    )
                    db.add(new_post)

                saved_count += 1

            db.commit()
            logger.info("Saved %d Instagram posts to DB for %s", saved_count, creator_id)

        return saved_count

    except Exception as e:
        logger.error("Error saving Instagram posts to DB: %s", e)
        return 0


async def get_instagram_posts_db(creator_id: str) -> List[dict]:
    """Get all Instagram posts for a creator, newest first."""
    try:
        from api.database import get_db_session
        from api.models import InstagramPost

        with get_db_session() as db:
            posts = db.query(InstagramPost).filter(
                InstagramPost.creator_id == creator_id
            ).order_by(InstagramPost.post_timestamp.desc()).all()

            result = []
            for p in posts:
                result.append({
                    "id": p.post_id,
                    "caption": p.caption,
                    "permalink": p.permalink,
                    "media_type": p.media_type,
                    "media_url": p.media_url,
                    "thumbnail_url": p.thumbnail_url,
                    "timestamp": p.post_timestamp.isoformat() if p.post_timestamp else None,
                    "like_count": p.likes_count,
                    "comments_count": p.comments_count,
                    "hashtags": p.hashtags or [],
                    "mentions": p.mentions or [],
                })

            logger.info("Loaded %d Instagram posts from DB for %s", len(result), creator_id)
            return result

    except Exception as e:
        logger.error("Error loading Instagram posts from DB: %s", e)
        return []


async def delete_instagram_posts_db(creator_id: str) -> int:
    """Delete all Instagram posts for a creator. Returns count deleted."""
    try:
        from api.database import get_db_session
        from api.models import InstagramPost

        with get_db_session() as db:
            deleted = db.query(InstagramPost).filter(
                InstagramPost.creator_id == creator_id
            ).delete()

            db.commit()
            logger.info("Deleted %d Instagram posts from DB for %s", deleted, creator_id)
            return deleted

    except Exception as e:
        logger.error("Error deleting Instagram posts from DB: %s", e)
        return 0


def get_instagram_posts_count_db(creator_id: str) -> int:
    """Synchronous count of Instagram posts for a creator (for admin/debug)."""
    try:
        from api.database import get_db_session
        from api.models import InstagramPost

        with get_db_session() as db:
            return db.query(InstagramPost).filter(
                InstagramPost.creator_id == creator_id
            ).count()

    except Exception as e:
        logger.error("Error counting Instagram posts: %s", e)
        return 0
