"""
Content Refresh Service — Auto-refresh creator content every 24h.

Re-scrapes Instagram posts via Graph API, chunks them, embeds them,
and stores in content_chunks + content_embeddings (pgvector).

SAFE: Never touches messages, leads, follower_memories, conversation_states,
      conversation_embeddings.

Uses existing pipeline:
  - ingestion.v2.instagram_ingestion.ingest_instagram_v2() for scraping + DB persistence
  - core.embeddings.generate_embedding() + store_embedding() for pgvector
  - core.rag.get_simple_rag().add_document() for in-memory RAG hydration
"""

import asyncio
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

# Configuration
CONTENT_REFRESH_INTERVAL = int(os.getenv("CONTENT_REFRESH_INTERVAL_SECONDS", "86400"))  # 24h
CONTENT_REFRESH_INITIAL_DELAY = int(os.getenv("CONTENT_REFRESH_INITIAL_DELAY", "120"))  # 2 min
CONTENT_REFRESH_MAX_POSTS = int(os.getenv("CONTENT_REFRESH_MAX_POSTS", "20"))
CONTENT_REFRESH_ENABLED = os.getenv("CONTENT_REFRESH_ENABLED", "true").lower() == "true"


async def refresh_creator_content(creator_id: str) -> Dict:
    """
    Refresh content for a single creator.

    Flow:
      1. Look up creator in DB (verify bot_active, has IG token)
      2. Call ingest_instagram_v2 with clean_before=False (append, don't delete)
      3. Generate embeddings for new chunks and store in pgvector
      4. Add new chunks to in-memory RAG for immediate search
      5. Return stats

    Args:
        creator_id: Creator UUID or name

    Returns:
        Dict with stats: new_posts, new_chunks, new_embeddings, errors
    """
    from sqlalchemy import or_

    from api.database import get_db_session
    from api.models import Creator

    result = {
        "creator_id": creator_id,
        "success": False,
        "new_posts": 0,
        "new_chunks": 0,
        "new_embeddings": 0,
        "errors": [],
    }

    # Step 1: Look up creator and verify eligibility
    try:
        with get_db_session() as db:
            creator = (
                db.query(Creator)
                .filter(
                    or_(
                        Creator.name == creator_id,
                        Creator.id == creator_id if len(creator_id) > 20 else False,
                    )
                )
                .first()
            )

            if not creator:
                result["errors"].append(f"Creator {creator_id} not found")
                return result

            if not creator.bot_active:
                result["errors"].append(f"Creator {creator_id} bot is not active")
                return result

            if not creator.instagram_token:
                result["errors"].append(f"Creator {creator_id} has no Instagram token")
                return result

            # instagram_user_id = IG Business Account ID (for graph.instagram.com/media)
            # instagram_page_id = Facebook Page ID (for webhook routing / messaging)
            # When token is EAA (Page token), graph.instagram.com needs IGAAT — use env var fallback
            access_token = creator.instagram_token
            if access_token and access_token.startswith("EAA"):
                igaat_fallback = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
                if igaat_fallback and igaat_fallback.startswith("IGAAT"):
                    access_token = igaat_fallback

            instagram_business_id = creator.instagram_user_id or creator.instagram_page_id
            ig_username = creator.name
            creator_name = creator.name

    except Exception as e:
        result["errors"].append(f"DB lookup failed: {e}")
        return result

    # Step 2: Run IG ingestion V2 with clean_before=False (append only)
    try:
        from ingestion.v2.instagram_ingestion import ingest_instagram_v2

        ig_result = await ingest_instagram_v2(
            creator_id=creator_id,
            instagram_username=ig_username,
            max_posts=CONTENT_REFRESH_MAX_POSTS,
            clean_before=False,  # APPEND — never delete existing content
            access_token=access_token,
            instagram_business_id=instagram_business_id,
        )

        result["new_posts"] = ig_result.posts_saved_db
        result["new_chunks"] = ig_result.rag_chunks_created

        if ig_result.errors:
            result["errors"].extend(ig_result.errors[:5])

    except Exception as e:
        logger.error(f"[CONTENT-REFRESH] IG ingestion failed for {creator_name}: {e}")
        result["errors"].append(f"IG ingestion failed: {e}")
        return result

    # Step 3: Generate embeddings for new chunks and store in pgvector
    if result["new_chunks"] > 0:
        try:
            embeddings_stored = await _embed_new_chunks(creator_id)
            result["new_embeddings"] = embeddings_stored
        except Exception as e:
            logger.error(f"[CONTENT-REFRESH] Embedding failed for {creator_name}: {e}")
            result["errors"].append(f"Embedding failed: {e}")

    # Step 4: Hydrate in-memory RAG with new chunks
    if result["new_chunks"] > 0:
        try:
            _hydrate_rag_for_creator(creator_id)
        except Exception as e:
            logger.warning(f"[CONTENT-REFRESH] RAG hydration failed for {creator_name}: {e}")

    result["success"] = True
    logger.info(
        f"[CONTENT-REFRESH] Refreshed {creator_name}: "
        f"{result['new_posts']} new posts, "
        f"{result['new_chunks']} new chunks, "
        f"{result['new_embeddings']} new embeddings"
    )

    return result


async def _embed_new_chunks(creator_id: str) -> int:
    """
    Generate embeddings for content_chunks that don't have a matching
    content_embeddings row yet, and store them in pgvector.

    Returns number of embeddings stored.
    """
    from api.database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # Find chunks without embeddings
        rows = db.execute(
            text("""
                SELECT cc.chunk_id, cc.content
                FROM content_chunks cc
                LEFT JOIN content_embeddings ce ON cc.chunk_id = ce.chunk_id
                WHERE cc.creator_id = :creator_id
                  AND ce.chunk_id IS NULL
                  AND LENGTH(cc.content) > 50
                ORDER BY cc.created_at DESC
                LIMIT 100
            """),
            {"creator_id": creator_id},
        ).fetchall()

        if not rows:
            return 0

        from core.embeddings import generate_embedding, store_embedding

        stored = 0
        for row in rows:
            embedding = generate_embedding(row.content)
            if embedding:
                store_embedding(row.chunk_id, creator_id, row.content, embedding)
                stored += 1

        logger.info(f"[CONTENT-REFRESH] Stored {stored}/{len(rows)} embeddings for {creator_id}")
        return stored

    except Exception as e:
        logger.error(f"[CONTENT-REFRESH] Embedding error for {creator_id}: {e}")
        return 0
    finally:
        db.close()


def _hydrate_rag_for_creator(creator_id: str):
    """Reload RAG documents from DB for this creator."""
    try:
        from core.rag import get_simple_rag

        rag = get_simple_rag()
        loaded = rag.load_from_db(creator_id=creator_id)
        logger.info(f"[CONTENT-REFRESH] RAG hydrated with {loaded} docs for {creator_id}")
    except Exception as e:
        logger.warning(f"[CONTENT-REFRESH] RAG hydration failed: {e}")


async def refresh_all_active_creators() -> Dict:
    """
    Refresh content for all creators with bot_active=True and a valid IG token.

    Returns summary stats.
    """
    from api.database import get_db_session
    from api.models import Creator

    summary = {
        "refreshed": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    try:
        with get_db_session() as db:
            creators = (
                db.query(Creator)
                .filter(
                    Creator.bot_active == True,  # noqa: E712
                    Creator.instagram_token.isnot(None),
                )
                .all()
            )
            creator_ids = [(str(c.id), c.name) for c in creators]

    except Exception as e:
        logger.error(f"[CONTENT-REFRESH] Failed to get active creators: {e}")
        summary["details"].append({"error": str(e)})
        return summary

    logger.info(f"[CONTENT-REFRESH] Starting refresh for {len(creator_ids)} active creators")

    for _creator_uuid, creator_name in creator_ids:
        try:
            # Use slug (creator name), not UUID — chunks and search both use slug
            result = await refresh_creator_content(creator_name)

            if result["success"]:
                summary["refreshed"] += 1
            else:
                summary["failed"] += 1

            summary["details"].append({
                "creator": creator_name,
                "new_posts": result.get("new_posts", 0),
                "new_chunks": result.get("new_chunks", 0),
                "new_embeddings": result.get("new_embeddings", 0),
                "errors": result.get("errors", []),
            })

        except Exception as e:
            logger.error(f"[CONTENT-REFRESH] Failed for {creator_name}: {e}")
            summary["failed"] += 1
            summary["details"].append({
                "creator": creator_name,
                "error": str(e),
            })

        # Small delay between creators to avoid rate limits
        await asyncio.sleep(5)

    logger.info(
        f"[CONTENT-REFRESH] Completed: {summary['refreshed']} refreshed, "
        f"{summary['failed']} failed, {summary['skipped']} skipped"
    )

    return summary


async def content_refresh_loop():
    """
    Background loop that refreshes all active creators every 24h.

    Follows the same asyncio pattern as token_refresh_scheduler in startup.py.
    """
    await asyncio.sleep(CONTENT_REFRESH_INITIAL_DELAY)
    logger.info(
        "[CONTENT-REFRESH] Scheduler started — "
        f"runs every {CONTENT_REFRESH_INTERVAL}s ({CONTENT_REFRESH_INTERVAL // 3600}h), "
        f"max {CONTENT_REFRESH_MAX_POSTS} posts/creator"
    )

    while True:
        if CONTENT_REFRESH_ENABLED:
            try:
                summary = await refresh_all_active_creators()
                logger.info(
                    "[CONTENT-REFRESH] Cycle complete: "
                    f"{summary['refreshed']} refreshed, {summary['failed']} failed"
                )
            except Exception as e:
                logger.error(f"[CONTENT-REFRESH] Scheduler error: {e}")
        else:
            logger.debug("[CONTENT-REFRESH] Disabled via CONTENT_REFRESH_ENABLED=false")

        await asyncio.sleep(CONTENT_REFRESH_INTERVAL)
