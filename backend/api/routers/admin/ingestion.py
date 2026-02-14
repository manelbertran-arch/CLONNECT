"""
Re-ingestion endpoints for refreshing creator content.

POST /admin/ingestion/refresh-ig-posts/{creator_id}   - Re-scrape IG posts via Graph API
POST /admin/ingestion/refresh-content/{creator_id}    - Re-scrape website + products + RAG
POST /admin/ingestion/full-refresh/{creator_id}       - All of the above in sequence
GET  /admin/ingestion/status/{creator_id}             - Data counts for pre/post comparison

SAFE: Never touches messages, leads, follower_memories, conversation_states.
IDEMPOTENT: Instagram uses clean_before=false (append new); website uses clean_before=true (replace).
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class RefreshResult(BaseModel):
    """Result of a refresh operation."""
    success: bool
    operation: str
    details: dict = {}
    error: Optional[str] = None


@router.get("/ingestion/status/{creator_id}")
async def get_ingestion_status(creator_id: str):
    """
    Get current data counts for a creator (for pre/post refresh comparison).

    Returns counts for:
    - instagram_posts, content_chunks, products, leads, messages,
      follower_memories, conversation_embeddings
    """
    try:
        from sqlalchemy import text

        from api.database import SessionLocal

        session = SessionLocal()
        try:
            # Resolve creator UUID
            creator_row = session.execute(
                text("SELECT id, name FROM creators WHERE id::text = :cid OR name = :cid"),
                {"cid": creator_id},
            ).fetchone()

            if not creator_row:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            cid = str(creator_row[0])
            creator_name = creator_row[1]

            # Count all relevant tables
            counts = {}
            tables = [
                ("instagram_posts", f"SELECT COUNT(*) FROM instagram_posts WHERE creator_id = '{cid}'"),
                ("content_chunks", f"SELECT COUNT(*) FROM content_chunks WHERE creator_id = '{cid}'"),
                ("products", f"SELECT COUNT(*) FROM products WHERE creator_id = '{cid}'"),
                ("leads", f"SELECT COUNT(*) FROM leads WHERE creator_id = '{cid}'"),
                ("messages", f"SELECT COUNT(*) FROM messages WHERE creator_id = '{cid}'"),
            ]

            # Optional tables that may not exist
            optional_tables = [
                ("follower_memories", f"SELECT COUNT(*) FROM follower_memories WHERE creator_id = '{cid}'"),
                ("conversation_embeddings", f"SELECT COUNT(*) FROM conversation_embeddings WHERE creator_id = '{cid}'"),
                ("nurturing_followups", f"SELECT COUNT(*) FROM nurturing_followups WHERE creator_id = '{cid}'"),
            ]

            for name, query in tables:
                try:
                    result = session.execute(text(query)).scalar()
                    counts[name] = result
                except Exception:
                    counts[name] = -1

            for name, query in optional_tables:
                try:
                    result = session.execute(text(query)).scalar()
                    counts[name] = result
                except Exception:
                    counts[name] = 0  # Table may not exist

            # Latest IG post date
            try:
                latest_post = session.execute(
                    text(f"SELECT MAX(posted_at) FROM instagram_posts WHERE creator_id = '{cid}'")
                ).scalar()
                counts["latest_ig_post"] = latest_post.isoformat() if latest_post else None
            except Exception:
                counts["latest_ig_post"] = None

            return {
                "creator_id": creator_id,
                "creator_name": creator_name,
                "counts": counts,
                "safe_tables": ["instagram_posts", "content_chunks", "products"],
                "protected_tables": ["leads", "messages", "follower_memories", "conversation_embeddings"],
            }
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingestion status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingestion/refresh-ig-posts/{creator_id}")
async def refresh_ig_posts(creator_id: str, max_posts: int = 50, clean_before: bool = False):
    """
    Re-scrape Instagram posts for a creator via Graph API.

    Uses the creator's stored OAuth token.
    Default: clean_before=false (append new posts without deleting old ones).
    """
    try:
        from sqlalchemy import or_

        from api.database import get_db_session
        from api.models import Creator

        # Look up creator and IG credentials
        with get_db_session() as db:
            creator = (
                db.query(Creator)
                .filter(or_(
                    Creator.name == creator_id,
                    Creator.id == creator_id if len(creator_id) > 20 else False,
                ))
                .first()
            )
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")
            if not creator.instagram_token:
                raise HTTPException(status_code=400, detail="Creator has no Instagram token")

            access_token = creator.instagram_token
            instagram_business_id = creator.instagram_page_id
            # Try to determine username from page_id or name
            ig_username = creator.name

        from ingestion.v2.instagram_ingestion import ingest_instagram_v2

        result = await ingest_instagram_v2(
            creator_id=creator_id,
            instagram_username=ig_username,
            max_posts=max_posts,
            clean_before=clean_before,
            access_token=access_token,
            instagram_business_id=instagram_business_id,
        )

        return RefreshResult(
            success=result.success,
            operation="refresh-ig-posts",
            details={
                "posts_scraped": result.posts_scraped,
                "posts_passed_sanity": result.posts_passed_sanity,
                "posts_rejected": result.posts_rejected,
                "posts_saved_db": result.posts_saved_db,
                "rag_chunks_created": result.rag_chunks_created,
                "errors": result.errors[:5],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IG posts refresh failed for {creator_id}: {e}")
        return RefreshResult(success=False, operation="refresh-ig-posts", error=str(e))


@router.post("/ingestion/refresh-content/{creator_id}")
async def refresh_content(creator_id: str, url: Optional[str] = None, max_pages: int = 10):
    """
    Re-scrape creator website, detect products, create RAG chunks.

    Uses clean_before=true to replace old website content (not IG posts).
    If url is not provided, tries to use creator's stored website URL.
    """
    try:
        from sqlalchemy import or_

        from api.database import get_db_session
        from api.models import Creator

        website_url = url
        if not website_url:
            with get_db_session() as db:
                creator = (
                    db.query(Creator)
                    .filter(or_(
                        Creator.name == creator_id,
                        Creator.id == creator_id if len(creator_id) > 20 else False,
                    ))
                    .first()
                )
                if not creator:
                    raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

                # Try to find website URL from knowledge_about or other fields
                knowledge = creator.knowledge_about or {}
                website_url = knowledge.get("website") or knowledge.get("url")
                if not website_url:
                    raise HTTPException(
                        status_code=400,
                        detail="No website URL found. Pass ?url=https://... to specify one.",
                    )

        from api.database import SessionLocal
        from ingestion.v2 import IngestionV2Pipeline

        db_session = SessionLocal()
        try:
            pipeline = IngestionV2Pipeline(db_session=db_session, max_pages=max_pages)
            result = await pipeline.run(
                creator_id=creator_id,
                website_url=website_url,
                clean_before=True,
                re_verify=True,
            )

            return RefreshResult(
                success=result.success,
                operation="refresh-content",
                details={
                    "website_url": website_url,
                    "pages_scraped": result.pages_scraped,
                    "products_detected": result.products_detected,
                    "products_verified": result.products_verified,
                    "products_saved": result.products_saved,
                    "rag_docs_saved": result.rag_docs_saved,
                    "errors": result.errors[:5],
                },
            )
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Content refresh failed for {creator_id}: {e}")
        return RefreshResult(success=False, operation="refresh-content", error=str(e))


@router.post("/ingestion/full-refresh/{creator_id}")
async def full_refresh(
    creator_id: str,
    url: Optional[str] = None,
    max_ig_posts: int = 50,
    max_web_pages: int = 10,
    skip_ig: bool = False,
    skip_website: bool = False,
):
    """
    Full re-ingestion: IG posts + website content in sequence.

    SAFE: Never touches messages, leads, follower_memories, conversation_states.

    Args:
        creator_id: Creator name or UUID
        url: Website URL (optional, auto-detected from DB)
        max_ig_posts: Max IG posts to scrape (default 50)
        max_web_pages: Max website pages to scrape (default 10)
        skip_ig: Skip Instagram refresh
        skip_website: Skip website refresh
    """
    results = {
        "creator_id": creator_id,
        "operations": [],
        "overall_success": True,
    }

    # Step 1: Instagram posts refresh
    if not skip_ig:
        try:
            ig_result = await refresh_ig_posts(
                creator_id=creator_id,
                max_posts=max_ig_posts,
                clean_before=False,  # Append, don't delete
            )
            results["operations"].append({
                "operation": "refresh-ig-posts",
                "success": ig_result.success,
                "details": ig_result.details,
                "error": ig_result.error,
            })
            if not ig_result.success:
                results["overall_success"] = False
        except HTTPException as e:
            results["operations"].append({
                "operation": "refresh-ig-posts",
                "success": False,
                "error": e.detail,
            })
            results["overall_success"] = False
        except Exception as e:
            results["operations"].append({
                "operation": "refresh-ig-posts",
                "success": False,
                "error": str(e),
            })
            results["overall_success"] = False

    # Step 2: Website content refresh
    if not skip_website:
        try:
            content_result = await refresh_content(
                creator_id=creator_id,
                url=url,
                max_pages=max_web_pages,
            )
            results["operations"].append({
                "operation": "refresh-content",
                "success": content_result.success,
                "details": content_result.details,
                "error": content_result.error,
            })
            if not content_result.success:
                results["overall_success"] = False
        except HTTPException as e:
            results["operations"].append({
                "operation": "refresh-content",
                "success": False,
                "error": e.detail,
            })
            # Website might not have a URL — don't fail overall if IG succeeded
        except Exception as e:
            results["operations"].append({
                "operation": "refresh-content",
                "success": False,
                "error": str(e),
            })

    return results


@router.post("/content/refresh/{creator_id}")
async def trigger_content_refresh(creator_id: str):
    """
    Manually trigger content refresh for a creator.

    Re-scrapes recent Instagram posts via Graph API, chunks, embeds,
    and adds to pgvector. Appends only — never deletes existing content.

    SAFE: Never touches messages, leads, follower_memories, conversation_states.

    Returns:
        { success, new_posts, new_chunks, new_embeddings, errors }
    """
    try:
        from services.content_refresh import refresh_creator_content

        result = await refresh_creator_content(creator_id)

        return RefreshResult(
            success=result["success"],
            operation="content-refresh",
            details={
                "new_posts": result["new_posts"],
                "new_chunks": result["new_chunks"],
                "new_embeddings": result["new_embeddings"],
                "errors": result["errors"][:5],
            },
            error=result["errors"][0] if result["errors"] and not result["success"] else None,
        )

    except Exception as e:
        logger.error(f"Content refresh failed for {creator_id}: {e}")
        return RefreshResult(success=False, operation="content-refresh", error=str(e))


@router.get("/content/refresh/status")
async def get_content_refresh_status():
    """
    Get content refresh scheduler configuration and status.
    """
    import os

    return {
        "enabled": os.getenv("CONTENT_REFRESH_ENABLED", "true").lower() == "true",
        "interval_seconds": int(os.getenv("CONTENT_REFRESH_INTERVAL_SECONDS", "86400")),
        "interval_hours": int(os.getenv("CONTENT_REFRESH_INTERVAL_SECONDS", "86400")) // 3600,
        "max_posts_per_creator": int(os.getenv("CONTENT_REFRESH_MAX_POSTS", "20")),
        "initial_delay_seconds": int(os.getenv("CONTENT_REFRESH_INITIAL_DELAY", "120")),
    }
