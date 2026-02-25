"""
Debug and utility endpoints for Ingestion V2 API.

Endpoints:
- GET /debug/scraper-test — Step-by-step scraper diagnostic
- POST /full-refresh/{creator_id} — Full content refresh for a creator
- GET /data-status/{creator_id} — Data status for a creator
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request Models
# =============================================================================


class FullRefreshRequest(BaseModel):
    """Request for full content refresh."""

    creator_id: str
    instagram_username: str = ""
    website_url: str = ""
    max_ig_posts: int = 30
    clean_ig_before: bool = False  # Append by default


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/debug/scraper-test")
async def debug_scraper_test(url: str = "https://www.stefanobonanno.com"):
    """
    Diagnóstico paso a paso del scraper.

    Testea cada componente individualmente para identificar
    dónde falla exactamente.
    """
    import os
    import time

    results = {
        "url": url,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [],
        "config": {},
        "final_status": "unknown",
    }

    # Step 0: Config check
    results["config"] = {
        "SCRAPER_VERIFY_SSL_env": os.getenv("SCRAPER_VERIFY_SSL", "NOT_SET"),
        "SCRAPER_RESPECT_ROBOTS_env": os.getenv("SCRAPER_RESPECT_ROBOTS", "NOT_SET"),
        "PLAYWRIGHT_ENABLED_env": os.getenv("SCRAPER_USE_PLAYWRIGHT", "NOT_SET"),
    }

    # Step 1: Import check
    step1 = {"step": 1, "name": "imports", "status": "pending", "details": {}}
    try:
        from ingestion.deterministic_scraper import (
            RESPECT_ROBOTS_TXT,
            VERIFY_SSL,
            DeterministicScraper,
            get_robots_checker,
            scraper_circuit_breaker,
        )

        step1["status"] = "ok"
        step1["details"] = {
            "VERIFY_SSL_actual": VERIFY_SSL,
            "RESPECT_ROBOTS_TXT_actual": RESPECT_ROBOTS_TXT,
            "circuit_breaker_state": scraper_circuit_breaker.current_state,
            "circuit_breaker_fail_count": scraper_circuit_breaker.fail_counter,
        }
    except Exception as e:
        step1["status"] = "error"
        step1["details"] = {"error": str(e)}
    results["steps"].append(step1)

    if step1["status"] == "error":
        results["final_status"] = "import_error"
        return results

    # Step 2: Robots.txt check
    step2 = {"step": 2, "name": "robots_txt", "status": "pending", "details": {}}
    try:
        robots_checker = get_robots_checker()
        is_allowed = robots_checker.is_allowed(url)
        step2["status"] = "ok" if is_allowed else "blocked"
        step2["details"] = {
            "is_allowed": is_allowed,
            "respect_robots_enabled": RESPECT_ROBOTS_TXT,
        }
    except Exception as e:
        step2["status"] = "error"
        step2["details"] = {"error": str(e)}
    results["steps"].append(step2)

    if step2["status"] == "blocked":
        results["final_status"] = "blocked_by_robots_txt"
        return results

    # Step 3: Direct HTTP fetch (bypass circuit breaker)
    step3 = {"step": 3, "name": "http_fetch", "status": "pending", "details": {}}
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            verify=VERIFY_SSL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)"},
        ) as client:
            start = time.time()
            response = await client.get(url)
            duration = time.time() - start

            step3["status"] = "ok" if response.status_code == 200 else "http_error"
            step3["details"] = {
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "unknown"),
                "content_length": len(response.text),
                "final_url": str(response.url),
                "duration_seconds": round(duration, 3),
                "ssl_verify_used": VERIFY_SSL,
            }
    except httpx.ConnectError as e:
        step3["status"] = "connection_error"
        step3["details"] = {"error": str(e), "hint": "Check SSL settings or network"}
    except Exception as e:
        step3["status"] = "error"
        step3["details"] = {"error": str(e), "error_type": type(e).__name__}
    results["steps"].append(step3)

    if step3["status"] != "ok":
        results["final_status"] = f"http_failed_{step3['status']}"
        return results

    # Step 4: Full scrape attempt
    step4 = {"step": 4, "name": "full_scrape", "status": "pending", "details": {}}
    try:
        scraper = DeterministicScraper(max_pages=1)
        start = time.time()
        page = await scraper.scrape_page(url)
        duration = time.time() - start

        if page:
            step4["status"] = "ok"
            step4["details"] = {
                "title": page.title[:100] if page.title else None,
                "content_length": len(page.main_content),
                "has_content": page.has_content,
                "sections_count": len(page.sections),
                "links_count": len(page.links),
                "duration_seconds": round(duration, 3),
            }
        else:
            step4["status"] = "no_content"
            step4["details"] = {"page": None, "duration_seconds": round(duration, 3)}
    except Exception as e:
        step4["status"] = "error"
        step4["details"] = {"error": str(e), "error_type": type(e).__name__}
    results["steps"].append(step4)

    # Step 5: Playwright check
    step5 = {"step": 5, "name": "playwright", "status": "pending", "details": {}}
    try:
        from ingestion.playwright_scraper import get_playwright_scraper, is_playwright_available

        available = is_playwright_available()
        step5["details"]["is_available"] = available

        if available:
            pw_scraper = get_playwright_scraper()
            start = time.time()
            pw_page = await pw_scraper.scrape_page(url)
            duration = time.time() - start

            if pw_page:
                step5["status"] = "ok"
                step5["details"]["content_length"] = len(pw_page.main_content)
                step5["details"]["has_content"] = pw_page.has_content
                step5["details"]["duration_seconds"] = round(duration, 3)
            else:
                step5["status"] = "no_content"
                step5["details"]["duration_seconds"] = round(duration, 3)
        else:
            step5["status"] = "not_available"
    except ImportError as e:
        step5["status"] = "not_installed"
        step5["details"] = {"error": str(e)}
    except Exception as e:
        step5["status"] = "error"
        step5["details"] = {"error": str(e), "error_type": type(e).__name__}
    results["steps"].append(step5)

    # Final status
    if step4["status"] == "ok":
        results["final_status"] = "success_deterministic"
    elif step5["status"] == "ok":
        results["final_status"] = "success_playwright"
    else:
        results["final_status"] = "failed"

    return results


@router.post("/full-refresh/{creator_id}")
async def full_refresh(creator_id: str, request: FullRefreshRequest = None):
    """
    Full content refresh for a creator.

    Runs Instagram ingestion + website ingestion + RAG re-hydration.
    SAFE: Never touches messages, leads, follower_memories, conversation_states.
    IDEMPOTENT: Can be run multiple times without duplicating data (upsert logic).

    If instagram_username or website_url are not provided, tries to look them up.
    """
    if request is None:
        request = FullRefreshRequest(creator_id=creator_id)

    results = {
        "creator_id": creator_id,
        "instagram": None,
        "website": None,
        "rag_rehydrated": False,
        "errors": [],
    }

    # Look up creator data from DB
    ig_username = request.instagram_username
    website_url = request.website_url
    access_token = None
    instagram_business_id = None

    try:
        from api.database import get_db_session
        from api.models import Creator
        from sqlalchemy import or_

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
            if creator:
                if creator.instagram_token:
                    access_token = creator.instagram_token
                    instagram_business_id = creator.instagram_page_id
    except Exception as e:
        logger.warning(f"Could not lookup creator data: {e}")

    # Step 1: Instagram ingestion
    if ig_username:
        try:
            from ingestion.v2.instagram_ingestion import ingest_instagram_v2

            ig_result = await ingest_instagram_v2(
                creator_id=creator_id,
                instagram_username=ig_username,
                max_posts=request.max_ig_posts,
                clean_before=request.clean_ig_before,
                access_token=access_token,
                instagram_business_id=instagram_business_id,
            )
            results["instagram"] = {
                "success": ig_result.success,
                "posts_scraped": ig_result.posts_scraped,
                "posts_saved_db": ig_result.posts_saved_db,
                "rag_chunks_created": ig_result.rag_chunks_created,
            }
            logger.info(
                f"[FULL-REFRESH] IG done for {creator_id}: "
                f"{ig_result.posts_saved_db} posts saved"
            )
        except Exception as e:
            logger.error(f"[FULL-REFRESH] IG failed for {creator_id}: {e}")
            results["errors"].append(f"instagram: {e}")
            results["instagram"] = {"success": False, "error": str(e)}

    # Step 2: Website ingestion
    if website_url:
        try:
            from ingestion.v2 import IngestionV2Pipeline

            db_session = None
            try:
                from api.database import SessionLocal

                db_session = SessionLocal()
            except Exception as e:
                logger.warning("Suppressed error in from api.database import SessionLocal: %s", e)

            pipeline = IngestionV2Pipeline(db_session=db_session, max_pages=10)
            web_result = await pipeline.run(
                creator_id=creator_id,
                website_url=website_url,
                clean_before=True,
                re_verify=True,
            )
            results["website"] = {
                "success": web_result.success,
                "pages_scraped": web_result.pages_scraped,
                "products_verified": web_result.products_verified,
                "products_saved": web_result.products_saved,
                "rag_docs_saved": web_result.rag_docs_saved,
            }
            logger.info(
                f"[FULL-REFRESH] Website done for {creator_id}: "
                f"{web_result.products_saved} products, {web_result.rag_docs_saved} docs"
            )

            if db_session:
                db_session.close()
        except Exception as e:
            logger.error(f"[FULL-REFRESH] Website failed for {creator_id}: {e}")
            results["errors"].append(f"website: {e}")
            results["website"] = {"success": False, "error": str(e)}

    # Step 3: Re-hydrate RAG from DB
    try:
        from core.rag import get_simple_rag

        rag = get_simple_rag()
        loaded = rag.load_from_db()
        results["rag_rehydrated"] = True
        results["rag_documents"] = loaded
        logger.info(f"[FULL-REFRESH] RAG re-hydrated with {loaded} documents")
    except Exception as e:
        logger.warning(f"[FULL-REFRESH] RAG re-hydration failed: {e}")
        results["errors"].append(f"rag: {e}")

    return results


@router.get("/data-status/{creator_id}")
async def get_data_status(creator_id: str):
    """
    Get current data status for a creator.

    Returns counts of all content tables (safe SELECT COUNT queries only).
    Useful to verify data before/after re-ingestion.

    NEVER touches: messages, leads, follower_memories, conversation_states.
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Resolve creator UUID
            creator_row = session.execute(
                text("""
                    SELECT id, name FROM creators
                    WHERE id::text = :cid OR name = :cid
                """),
                {"cid": creator_id},
            ).fetchone()

            if not creator_row:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            creator_uuid, creator_name = creator_row

            # Count content tables (safe read-only queries)
            counts = {}
            queries = {
                "instagram_posts": "SELECT COUNT(*) FROM instagram_posts WHERE creator_id = :cid",
                "content_chunks": "SELECT COUNT(*) FROM content_chunks WHERE creator_id = :cid",
                "products": "SELECT COUNT(*) FROM products WHERE creator_id = :uuid",
                "leads": "SELECT COUNT(*) FROM leads WHERE creator_id = :uuid",
                "messages": "SELECT COUNT(*) FROM messages m JOIN leads l ON m.lead_id = l.id WHERE l.creator_id = :uuid",
                "conversation_embeddings": "SELECT COUNT(*) FROM conversation_embeddings WHERE creator_id = :cid",
                "follower_memories": "SELECT COUNT(*) FROM follower_memories WHERE creator_id = :cid",
            }

            for table, query in queries.items():
                try:
                    param = {"cid": creator_id} if ":cid" in query else {"uuid": str(creator_uuid)}
                    result = session.execute(text(query), param).scalar()
                    counts[table] = result
                except Exception as e:
                    session.rollback()
                    counts[table] = f"error: {e}"

            return {
                "creator_id": creator_id,
                "creator_name": creator_name,
                "counts": counts,
                "safe_to_refresh": [
                    "instagram_posts",
                    "content_chunks",
                    "products",
                ],
                "never_touched": [
                    "leads",
                    "messages",
                    "conversation_embeddings",
                    "follower_memories",
                ],
            }
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data status error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
