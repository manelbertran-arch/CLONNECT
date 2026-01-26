"""
Tone Profile Database Service - PostgreSQL persistence for ToneProfiles.
Replaces JSON file-based storage with proper database persistence.
"""

import json
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# In-memory cache for performance
_tone_cache: Dict[str, Any] = {}


def _get_db_session():
    """Get database session using context manager."""
    try:
        from api.database import get_db_session
        return get_db_session()
    except Exception as e:
        logger.error(f"Failed to get DB session: {e}")
        return None


async def save_tone_profile_db(creator_id: str, profile_data: dict) -> bool:
    """
    Save ToneProfile to PostgreSQL.

    Args:
        creator_id: Creator identifier
        profile_data: Full ToneProfile as dictionary

    Returns:
        True if saved successfully
    """
    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            # Check if exists
            existing = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).first()

            analyzed_count = profile_data.get('analyzed_posts_count', 0)
            confidence = profile_data.get('confidence_score', 0.0)

            if existing:
                # Update existing
                existing.profile_data = profile_data
                existing.analyzed_posts_count = analyzed_count
                existing.confidence_score = confidence
                existing.updated_at = datetime.utcnow()
                logger.info(f"Updated ToneProfile in DB for {creator_id}")
            else:
                # Insert new
                new_profile = ToneProfileModel(
                    creator_id=creator_id,
                    profile_data=profile_data,
                    analyzed_posts_count=analyzed_count,
                    confidence_score=confidence
                )
                db.add(new_profile)
                logger.info(f"Inserted ToneProfile in DB for {creator_id}")

            db.commit()

            # Update cache
            _tone_cache[creator_id] = profile_data

            return True

    except Exception as e:
        logger.error(f"Error saving ToneProfile to DB: {e}")
        return False


async def get_tone_profile_db(creator_id: str) -> Optional[dict]:
    """
    Get ToneProfile from PostgreSQL.

    Args:
        creator_id: Creator identifier

    Returns:
        ToneProfile data as dict, or None if not found
    """
    # Check cache first
    if creator_id in _tone_cache:
        logger.debug(f"ToneProfile for {creator_id} found in cache")
        return _tone_cache[creator_id]

    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            profile = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).first()

            if profile:
                data = profile.profile_data
                _tone_cache[creator_id] = data
                logger.info(f"ToneProfile for {creator_id} loaded from DB")
                return data

    except Exception as e:
        logger.error(f"Error loading ToneProfile from DB: {e}")

    return None


def get_tone_profile_db_sync(creator_id: str) -> Optional[dict]:
    """
    Synchronous version of get_tone_profile_db.
    For use in non-async contexts.
    """
    # Check cache first
    if creator_id in _tone_cache:
        return _tone_cache[creator_id]

    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            profile = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).first()

            if profile:
                data = profile.profile_data
                _tone_cache[creator_id] = data
                logger.info(f"ToneProfile for {creator_id} loaded from DB (sync)")
                return data

    except Exception as e:
        logger.error(f"Error loading ToneProfile from DB (sync): {e}")

    return None


async def delete_tone_profile_db(creator_id: str) -> bool:
    """
    Delete ToneProfile from PostgreSQL.

    Args:
        creator_id: Creator identifier

    Returns:
        True if deleted, False if not found
    """
    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            deleted = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).delete()

            db.commit()

            # Clear cache
            _tone_cache.pop(creator_id, None)

            if deleted:
                logger.info(f"Deleted ToneProfile from DB for {creator_id}")
                return True
            return False

    except Exception as e:
        logger.error(f"Error deleting ToneProfile from DB: {e}")
        return False


def list_profiles_db() -> List[str]:
    """
    List all creator_ids with ToneProfiles in DB.

    Returns:
        List of creator_ids
    """
    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            profiles = db.query(ToneProfileModel.creator_id).all()
            return [p[0] for p in profiles]

    except Exception as e:
        logger.error(f"Error listing ToneProfiles from DB: {e}")
        return []


def clear_cache(creator_id: Optional[str] = None):
    """Clear the in-memory cache."""
    if creator_id:
        _tone_cache.pop(creator_id, None)
        logger.debug(f"Cleared cache for {creator_id}")
    else:
        _tone_cache.clear()
        logger.debug("Cleared all tone profile cache")


# =============================================================================
# CONTENT CHUNKS - RAG/Citation persistence
# =============================================================================

async def save_content_chunks_db(creator_id: str, chunks: List[dict]) -> int:
    """
    Save content chunks to PostgreSQL.
    Replaces data/content_index/{creator_id}/chunks.json

    Args:
        creator_id: Creator identifier
        chunks: List of chunk dictionaries

    Returns:
        Number of chunks saved
    """
    try:
        from api.database import get_db_session
        from api.models import ContentChunk

        saved_count = 0

        with get_db_session() as db:
            for chunk in chunks:
                # Check if exists (by creator_id + chunk_id)
                chunk_id = chunk.get('id', chunk.get('chunk_id', ''))
                existing = db.query(ContentChunk).filter(
                    ContentChunk.creator_id == creator_id,
                    ContentChunk.chunk_id == chunk_id
                ).first()

                if existing:
                    # Update
                    existing.content = chunk.get('content', '')
                    existing.source_type = chunk.get('source_type')
                    existing.source_id = chunk.get('source_id')
                    existing.source_url = chunk.get('source_url')
                    existing.title = chunk.get('title')
                    existing.chunk_index = chunk.get('chunk_index', 0)
                    existing.total_chunks = chunk.get('total_chunks', 1)
                    existing.extra_data = chunk.get('metadata', {})
                else:
                    # Insert
                    new_chunk = ContentChunk(
                        creator_id=creator_id,
                        chunk_id=chunk_id,
                        content=chunk.get('content', ''),
                        source_type=chunk.get('source_type'),
                        source_id=chunk.get('source_id'),
                        source_url=chunk.get('source_url'),
                        title=chunk.get('title'),
                        chunk_index=chunk.get('chunk_index', 0),
                        total_chunks=chunk.get('total_chunks', 1),
                        extra_data=chunk.get('metadata', {})
                    )
                    db.add(new_chunk)

                saved_count += 1

            db.commit()
            logger.info(f"Saved {saved_count} content chunks to DB for {creator_id}")

        return saved_count

    except Exception as e:
        logger.error(f"Error saving content chunks to DB: {e}")
        return 0


async def get_content_chunks_db(creator_id: str) -> List[dict]:
    """
    Get all content chunks for a creator from PostgreSQL.

    Args:
        creator_id: Creator identifier

    Returns:
        List of chunk dictionaries
    """
    try:
        from api.database import get_db_session
        from api.models import ContentChunk

        with get_db_session() as db:
            chunks = db.query(ContentChunk).filter(
                ContentChunk.creator_id == creator_id
            ).all()

            result = []
            for c in chunks:
                result.append({
                    'id': c.chunk_id,
                    'creator_id': c.creator_id,
                    'content': c.content,
                    'source_type': c.source_type,
                    'source_id': c.source_id,
                    'source_url': c.source_url,
                    'title': c.title,
                    'chunk_index': c.chunk_index,
                    'total_chunks': c.total_chunks,
                    'metadata': c.extra_data or {},  # SQLAlchemy column renamed from metadata
                    'created_at': c.created_at.isoformat() if c.created_at else None
                })

            logger.info(f"Loaded {len(result)} content chunks from DB for {creator_id}")
            return result

    except Exception as e:
        logger.error(f"Error loading content chunks from DB: {e}")
        return []


async def delete_content_chunks_db(creator_id: str) -> int:
    """
    Delete all content chunks for a creator.

    Args:
        creator_id: Creator identifier

    Returns:
        Number of chunks deleted
    """
    try:
        from api.database import get_db_session
        from api.models import ContentChunk

        with get_db_session() as db:
            deleted = db.query(ContentChunk).filter(
                ContentChunk.creator_id == creator_id
            ).delete()

            db.commit()
            logger.info(f"Deleted {deleted} content chunks from DB for {creator_id}")
            return deleted

    except Exception as e:
        logger.error(f"Error deleting content chunks from DB: {e}")
        return 0


# =============================================================================
# INSTAGRAM POSTS - Post persistence
# =============================================================================

async def save_instagram_posts_db(creator_id: str, posts: List[dict]) -> int:
    """
    Save Instagram posts to PostgreSQL.

    Args:
        creator_id: Creator identifier
        posts: List of post dictionaries

    Returns:
        Number of posts saved
    """
    try:
        from api.database import get_db_session
        from api.models import InstagramPost
        from dateutil.parser import parse as parse_date

        saved_count = 0

        with get_db_session() as db:
            for post in posts:
                post_id = post.get('id', post.get('post_id', ''))

                # Check if exists
                existing = db.query(InstagramPost).filter(
                    InstagramPost.creator_id == creator_id,
                    InstagramPost.post_id == post_id
                ).first()

                # Parse timestamp
                timestamp = None
                if post.get('timestamp'):
                    try:
                        timestamp = parse_date(post['timestamp'])
                    except:
                        pass

                # Extract hashtags from caption
                caption = post.get('caption', '') or ''
                hashtags = [tag.strip('#') for tag in caption.split() if tag.startswith('#')]
                mentions = [m.strip('@') for m in caption.split() if m.startswith('@')]

                # Extract comments data for analytics
                comments_data = post.get('comments', [])

                if existing:
                    # Update
                    existing.caption = caption
                    existing.permalink = post.get('permalink')
                    existing.media_type = post.get('media_type')
                    existing.media_url = post.get('media_url')
                    existing.thumbnail_url = post.get('thumbnail_url')
                    existing.post_timestamp = timestamp
                    existing.likes_count = post.get('like_count', 0)
                    existing.comments_count = post.get('comments_count', 0)
                    existing.hashtags = hashtags
                    existing.mentions = mentions
                    existing.comments = comments_data  # Full comment data for analytics
                else:
                    # Insert
                    new_post = InstagramPost(
                        creator_id=creator_id,
                        post_id=post_id,
                        caption=caption,
                        permalink=post.get('permalink'),
                        media_type=post.get('media_type'),
                        media_url=post.get('media_url'),
                        thumbnail_url=post.get('thumbnail_url'),
                        post_timestamp=timestamp,
                        likes_count=post.get('like_count', 0),
                        comments_count=post.get('comments_count', 0),
                        hashtags=hashtags,
                        mentions=mentions,
                        comments=comments_data  # Full comment data for analytics
                    )
                    db.add(new_post)

                saved_count += 1

            db.commit()
            logger.info(f"Saved {saved_count} Instagram posts to DB for {creator_id}")

        return saved_count

    except Exception as e:
        logger.error(f"Error saving Instagram posts to DB: {e}")
        import traceback
        traceback.print_exc()
        return 0


async def get_instagram_posts_db(creator_id: str) -> List[dict]:
    """
    Get all Instagram posts for a creator from PostgreSQL.

    Args:
        creator_id: Creator identifier

    Returns:
        List of post dictionaries
    """
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
                    'id': p.post_id,
                    'caption': p.caption,
                    'permalink': p.permalink,
                    'media_type': p.media_type,
                    'media_url': p.media_url,
                    'thumbnail_url': p.thumbnail_url,
                    'timestamp': p.post_timestamp.isoformat() if p.post_timestamp else None,
                    'like_count': p.likes_count,
                    'comments_count': p.comments_count,
                    'hashtags': p.hashtags or [],
                    'mentions': p.mentions or []
                })

            logger.info(f"Loaded {len(result)} Instagram posts from DB for {creator_id}")
            return result

    except Exception as e:
        logger.error(f"Error loading Instagram posts from DB: {e}")
        return []


async def delete_instagram_posts_db(creator_id: str) -> int:
    """
    Delete all Instagram posts for a creator.

    Args:
        creator_id: Creator identifier

    Returns:
        Number of posts deleted
    """
    try:
        from api.database import get_db_session
        from api.models import InstagramPost

        with get_db_session() as db:
            deleted = db.query(InstagramPost).filter(
                InstagramPost.creator_id == creator_id
            ).delete()

            db.commit()
            logger.info(f"Deleted {deleted} Instagram posts from DB for {creator_id}")
            return deleted

    except Exception as e:
        logger.error(f"Error deleting Instagram posts from DB: {e}")
        return 0


def get_instagram_posts_count_db(creator_id: str) -> int:
    """
    Get count of Instagram posts for a creator.
    Synchronous version for quick checks.
    """
    try:
        from api.database import get_db_session
        from api.models import InstagramPost

        with get_db_session() as db:
            count = db.query(InstagramPost).filter(
                InstagramPost.creator_id == creator_id
            ).count()
            return count

    except Exception as e:
        logger.error(f"Error counting Instagram posts: {e}")
        return 0
