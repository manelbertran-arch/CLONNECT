"""
Maintenance endpoints for admin tasks like refreshing profile pictures.
"""

import asyncio
import logging
import os
import uuid as uuid_lib

import httpx
from api.database import SessionLocal
from api.models import Creator, Lead
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/profile-picture-stats/{creator_name}")
async def profile_picture_stats(creator_name: str):
    """Get statistics on how many leads have/don't have profile pictures."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        result = session.execute(
            text(
                """
            SELECT
                COUNT(*) FILTER (WHERE profile_pic_url IS NOT NULL AND profile_pic_url != '') as with_photo,
                COUNT(*) FILTER (WHERE profile_pic_url IS NULL OR profile_pic_url = '') as without_photo,
                COUNT(*) as total
            FROM leads
            WHERE creator_id = :creator_id
        """
            ),
            {"creator_id": str(creator.id)},
        )

        row = result.fetchone()

        return {
            "creator": creator_name,
            "with_photo": row[0],
            "without_photo": row[1],
            "total": row[2],
            "percentage_with_photo": round(row[0] / row[2] * 100, 1) if row[2] > 0 else 0,
        }
    finally:
        session.close()


@router.post("/refresh-profile-pictures/{creator_name}")
async def refresh_profile_pictures(
    creator_name: str,
    limit: int = Query(default=50, description="Maximum leads to process"),
    offset: int = Query(default=0, description="Offset for pagination"),
    force: bool = Query(default=False, description="Refresh even if already has photo"),
):
    """
    Refresh profile pictures for leads without photos.
    Calls Instagram API for each lead.
    """
    session = SessionLocal()
    try:
        # 1. Get creator
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        if not creator.instagram_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        # 2. Get leads without photo (or all if force=True)
        query = session.query(Lead).filter(Lead.creator_id == creator.id)

        if not force:
            # Include NULL/empty AND expired CDN URLs
            from services.profile_pic_refresh import is_pic_expiring_soon
            all_leads = query.filter(Lead.platform == "instagram").order_by(Lead.last_contact_at.desc()).all()
            leads = [
                l for l in all_leads
                if not l.profile_pic_url or l.profile_pic_url == "" or is_pic_expiring_soon(l.profile_pic_url)
            ][offset:offset + limit]
        else:
            leads = query.filter(Lead.platform == "instagram").order_by(Lead.last_contact_at.desc()).offset(offset).limit(limit).all()

        if not leads:
            return {"message": "No leads to update", "updated": 0, "failed": 0}

        # 3. Refresh photos
        updated = 0
        failed = 0
        errors = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for lead in leads:
                try:
                    # Get the platform_user_id (Instagram ID)
                    ig_user_id = lead.platform_user_id
                    if ig_user_id and ig_user_id.startswith("ig_"):
                        ig_user_id = ig_user_id[3:]  # Remove ig_ prefix

                    if not ig_user_id:
                        failed += 1
                        errors.append(f"{lead.username}: No Instagram user ID")
                        continue

                    # Call Instagram API
                    response = await client.get(
                        f"https://graph.instagram.com/v21.0/{ig_user_id}",
                        params={
                            "fields": "id,username,name,profile_picture_url",
                            "access_token": creator.instagram_token,
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        profile_pic = data.get("profile_picture_url") or data.get("profile_pic")

                        if profile_pic:
                            lead.profile_pic_url = profile_pic
                            # Also update username if available
                            if data.get("username") and not lead.username:
                                lead.username = data.get("username")
                            session.commit()
                            updated += 1
                            logger.info(f"Updated profile pic for {lead.username}")
                        else:
                            failed += 1
                            errors.append(f"{lead.username}: No profile_pic in response")
                    else:
                        failed += 1
                        error_msg = f"{lead.username}: API error {response.status_code}"
                        try:
                            error_data = response.json()
                            if "error" in error_data:
                                error_msg += f" - {error_data['error'].get('message', '')}"
                        except Exception as e:
                            logger.warning("Suppressed error in error_data = response.json(): %s", e)
                        errors.append(error_msg)

                    # Rate limiting - wait 100ms between requests
                    await asyncio.sleep(0.1)

                except Exception as e:
                    failed += 1
                    errors.append(f"{lead.username}: {str(e)}")

        return {
            "message": f"Refreshed profile pictures for {creator_name}",
            "total_processed": len(leads),
            "updated": updated,
            "failed": failed,
            "errors": errors[:10],  # Only first 10 errors
        }

    finally:
        session.close()


@router.post("/run-profile-pic-refresh")
async def trigger_profile_pic_refresh():
    """
    Trigger the profile picture refresh job immediately (runs on server).
    This correctly uses the production Railway environment for API calls.
    """
    from services.profile_pic_refresh import refresh_profile_pics_job
    stats = await refresh_profile_pics_job()
    return {"message": "Profile pic refresh complete", "stats": stats}


@router.post("/refresh-profile-pictures-public/{creator_name}")
async def refresh_profile_pictures_public(
    creator_name: str,
    batch_size: int = Query(default=50, ge=1, le=100, description="Leads per batch"),
    delay: float = Query(default=2.0, ge=0.5, le=10.0, description="Seconds between API calls"),
):
    """
    Refresh profile pictures using Instagram's public API (no Graph API needed).
    Fetches pics by username, uploads to Cloudinary for permanent URLs.
    Runs on the server (Railway IP) to avoid local rate limiting.
    """
    import time as _time

    import requests as _requests

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Get leads needing refresh
        leads = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                Lead.platform_user_id.isnot(None),
                Lead.username.isnot(None),
                Lead.username != "",
                or_(
                    Lead.profile_pic_url.is_(None),
                    Lead.profile_pic_url == "",
                    ~Lead.profile_pic_url.like("%cloudinary%"),
                ),
            )
            .order_by(Lead.last_contact_at.desc().nullslast())
            .all()
        )

        total = len(leads)
        if total == 0:
            return {"message": "All leads already have Cloudinary pics", "total": 0}

        refreshed = 0
        failed = 0
        no_pic = 0
        rate_limited = False

        # Setup Cloudinary
        has_cloudinary = False
        cloudinary_svc = None
        try:
            from services.cloudinary_service import get_cloudinary_service
            cloudinary_svc = get_cloudinary_service()
            has_cloudinary = cloudinary_svc.is_configured
        except Exception:
            pass

        for i, lead in enumerate(leads):
            username = (lead.username or "").strip().lstrip("@")
            if not username:
                failed += 1
                continue

            try:
                resp = _requests.get(
                    f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                    headers={
                        "User-Agent": "Instagram 76.0.0.15.395 Android",
                        "x-ig-app-id": "936619743392459",
                    },
                    timeout=10,
                )

                if resp.status_code in (401, 429):
                    # Rate limited - pause and retry once
                    logger.warning(f"[PROFILE_PICS_PUBLIC] Rate limited at lead {i+1}/{total}, pausing 120s")
                    await asyncio.sleep(120)
                    resp = _requests.get(
                        f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                        headers={
                            "User-Agent": "Instagram 76.0.0.15.395 Android",
                            "x-ig-app-id": "936619743392459",
                        },
                        timeout=10,
                    )
                    if resp.status_code in (401, 429):
                        rate_limited = True
                        logger.error(f"[PROFILE_PICS_PUBLIC] Still rate limited, stopping at {i+1}/{total}")
                        break

                if resp.status_code == 200:
                    data = resp.json()
                    user = data.get("data", {}).get("user")
                    if user:
                        pic_url = user.get("profile_pic_url_hd") or user.get("profile_pic_url")
                        if pic_url:
                            final_url = pic_url
                            # Upload to Cloudinary
                            if has_cloudinary and cloudinary_svc:
                                try:
                                    cloud_result = cloudinary_svc.upload_from_url(
                                        url=pic_url,
                                        media_type="image",
                                        folder=f"clonnect/{creator.name}/profiles",
                                        public_id=f"profile_{lead.platform_user_id}",
                                    )
                                    if cloud_result.success and cloud_result.url:
                                        final_url = cloud_result.url
                                except Exception as cloud_err:
                                    logger.debug(f"[PROFILE_PICS_PUBLIC] Cloudinary error for @{username}: {cloud_err}")

                            lead.profile_pic_url = final_url
                            refreshed += 1
                        else:
                            no_pic += 1
                    else:
                        no_pic += 1  # Account may not exist
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                logger.debug(f"[PROFILE_PICS_PUBLIC] Error for @{username}: {e}")

            # Commit every batch
            if (i + 1) % batch_size == 0:
                session.commit()
                logger.info(f"[PROFILE_PICS_PUBLIC] Batch {(i+1)//batch_size}: {refreshed} ok, {failed} fail, {no_pic} no pic")

            await asyncio.sleep(delay)

        session.commit()

        return {
            "message": f"Profile pic refresh complete for {creator_name}",
            "total_leads": total,
            "refreshed": refreshed,
            "failed": failed,
            "no_pic_from_api": no_pic,
            "rate_limited": rate_limited,
            "cloudinary_enabled": has_cloudinary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROFILE_PICS_PUBLIC] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/leads-without-photo/{creator_name}")
async def list_leads_without_photo(creator_name: str, limit: int = 20):
    """List leads that don't have profile pictures."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        leads = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                or_(Lead.profile_pic_url.is_(None), Lead.profile_pic_url == ""),
            )
            .limit(limit)
            .all()
        )

        return {
            "creator": creator_name,
            "count": len(leads),
            "leads": [
                {
                    "username": lead.username,
                    "platform_user_id": lead.platform_user_id,
                    "status": lead.status,
                    "last_contact": (
                        lead.last_contact_at.isoformat() if lead.last_contact_at else None
                    ),
                }
                for lead in leads
            ],
        }
    finally:
        session.close()


# =============================================================================
# DISMISSED LEADS MANAGEMENT (Blocklist)
# =============================================================================


@router.get("/dismissed-leads/{creator_name}")
async def list_dismissed_leads(creator_name: str, limit: int = 100):
    """List all dismissed (deleted) leads for a creator."""
    session = SessionLocal()
    try:
        from api.models import Creator, DismissedLead

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        dismissed = (
            session.query(DismissedLead)
            .filter_by(creator_id=creator.id)
            .order_by(DismissedLead.dismissed_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "creator": creator_name,
            "count": len(dismissed),
            "dismissed_leads": [
                {
                    "id": str(d.id),
                    "platform_user_id": d.platform_user_id,
                    "username": d.username,
                    "reason": d.reason,
                    "dismissed_at": d.dismissed_at.isoformat() if d.dismissed_at else None,
                }
                for d in dismissed
            ],
        }
    finally:
        session.close()


@router.get("/db-indexes")
async def check_db_indexes():
    """Check which performance indexes exist in the database."""
    session = SessionLocal()
    try:
        # Check for important indexes
        result = session.execute(
            text(
                """
            SELECT indexname, tablename
            FROM pg_indexes
            WHERE tablename IN ('leads', 'messages', 'creators')
            AND schemaname = 'public'
            ORDER BY tablename, indexname
        """
            )
        )
        indexes = [{"table": row[1], "index": row[0]} for row in result.fetchall()]

        # Check alembic version
        try:
            version_result = session.execute(text("SELECT version_num FROM alembic_version"))
            alembic_version = version_result.scalar()
        except Exception:
            alembic_version = "not found"

        # Check table sizes
        size_result = session.execute(
            text(
                """
            SELECT relname, n_live_tup
            FROM pg_stat_user_tables
            WHERE relname IN ('leads', 'messages', 'creators')
            ORDER BY relname
        """
            )
        )
        table_sizes = {row[0]: row[1] for row in size_result.fetchall()}

        return {
            "alembic_version": alembic_version,
            "indexes": indexes,
            "table_sizes": table_sizes,
            "expected_indexes": [
                "idx_leads_creator_id",
                "idx_messages_lead_id",
                "ix_messages_lead_id",
                "ix_messages_lead_id_created_at",
            ],
        }
    finally:
        session.close()


@router.post("/create-indexes")
async def create_performance_indexes():
    """Create missing performance indexes (idempotent)."""
    session = SessionLocal()
    try:
        indexes_to_create = [
            "CREATE INDEX IF NOT EXISTS idx_leads_creator_id ON leads(creator_id)",
            "CREATE INDEX IF NOT EXISTS idx_leads_creator_status ON leads(creator_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_messages_lead_id ON messages(lead_id)",
            "CREATE INDEX IF NOT EXISTS ix_messages_lead_id ON messages(lead_id)",
            "CREATE INDEX IF NOT EXISTS ix_messages_lead_id_created_at ON messages(lead_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_creators_name ON creators(name)",
        ]

        created = []
        for idx_sql in indexes_to_create:
            try:
                session.execute(text(idx_sql))
                session.commit()
                idx_name = idx_sql.split("IF NOT EXISTS ")[1].split(" ON")[0]
                created.append(idx_name)
            except Exception as e:
                logger.warning(f"Index creation issue: {e}")

        return {
            "status": "ok",
            "message": f"Created/verified {len(created)} indexes",
            "indexes": created,
        }
    finally:
        session.close()


@router.delete("/dismissed-leads/{creator_name}/{platform_user_id}")
async def restore_dismissed_lead(creator_name: str, platform_user_id: str):
    """
    Remove a lead from the dismissed blocklist.
    This allows the lead to be re-imported on next sync.
    """
    session = SessionLocal()
    try:
        from api.models import Creator, DismissedLead

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        dismissed = (
            session.query(DismissedLead)
            .filter_by(creator_id=creator.id, platform_user_id=platform_user_id)
            .first()
        )

        if not dismissed:
            raise HTTPException(status_code=404, detail="Lead not in blocklist")

        username = dismissed.username
        session.delete(dismissed)
        session.commit()

        logger.info(f"Restored {platform_user_id} ({username}) from blocklist for {creator_name}")

        return {
            "status": "ok",
            "message": f"Lead {platform_user_id} removed from blocklist. Will be re-imported on next sync.",
            "username": username,
        }
    finally:
        session.close()


@router.post("/recalculate-scores/{creator_name}")
async def recalculate_lead_scores(creator_name: str):
    """
    Recalculate lead scores for all leads of a creator using V3 algorithm.

    V3 pipeline: extract_signals -> classify_lead -> calculate_score.
    Returns distribution by status (6 categories).

    Uses paged batches (50 leads/batch) with short-lived sessions to avoid
    blocking the event loop or monopolizing the DB connection pool.
    """
    import asyncio
    from services.lead_scoring import batch_recalculate_scores_paged

    result = await asyncio.to_thread(batch_recalculate_scores_paged, creator_name)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/batch-embed-conversations/{creator_name}")
async def batch_embed_conversations(creator_name: str, batch_size: int = Query(50, ge=1, le=200)):
    """
    Generate conversation embeddings for all un-embedded messages of a creator.
    Uses OpenAI text-embedding-3-small (1536 dims).
    RUNTIME: Execute post-deploy, not in CI.
    """
    import json
    import time

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        creator_uuid = str(creator.id)

        # Find messages not yet embedded
        result = session.execute(
            text(
                """
                SELECT m.id, m.lead_id, m.role, m.content, m.created_at,
                       l.platform_user_id
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE l.creator_id = :creator_id
                AND m.content IS NOT NULL
                AND LENGTH(m.content) > 10
                AND m.id NOT IN (
                    SELECT CAST(message_id AS UUID)
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_str
                    AND message_id IS NOT NULL
                )
                ORDER BY m.created_at
                """
            ),
            {"creator_id": creator_uuid, "creator_str": creator_name},
        )
        messages = result.fetchall()
        total = len(messages)

        if total == 0:
            return {
                "creator_id": creator_name,
                "total_messages": 0,
                "embedded": 0,
                "message": "All messages already embedded",
            }

        # Process in batches
        from core.embeddings import generate_embeddings_batch

        embedded = 0
        errors = 0
        start_time = time.time()

        for i in range(0, total, batch_size):
            batch = messages[i : i + batch_size]
            texts = [row[3] for row in batch]  # content column

            embeddings = generate_embeddings_batch(texts)

            for j, emb in enumerate(embeddings):
                if emb is None:
                    errors += 1
                    continue
                msg = batch[j]
                try:
                    session.execute(
                        text(
                            """
                            INSERT INTO conversation_embeddings
                            (creator_id, follower_id, message_role, content, embedding, message_id)
                            VALUES (:creator_id, :follower_id, :role, :content,
                                    CAST(:embedding AS vector), :message_id)
                            ON CONFLICT DO NOTHING
                            """
                        ),
                        {
                            "creator_id": creator_name,
                            "follower_id": str(msg[5]),  # platform_user_id
                            "role": msg[2],  # role
                            "content": msg[3][:500],  # content preview
                            "embedding": json.dumps(emb),
                            "message_id": str(msg[0]),  # message id
                        },
                    )
                    embedded += 1
                except Exception as e:
                    logger.error(f"[A13] Embed insert error: {e}")
                    errors += 1

            session.commit()
            await asyncio.sleep(0.5)  # Rate limit between batches

        elapsed = time.time() - start_time
        logger.info(
            f"[A13] Batch embed for {creator_name}: {embedded}/{total} in {elapsed:.1f}s"
        )

        return {
            "creator_id": creator_name,
            "total_messages": total,
            "embedded": embedded,
            "errors": errors,
            "duration_seconds": round(elapsed, 1),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[A13] Batch embed error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


@router.post("/backfill-personality-docs/{creator_name}")
async def backfill_personality_docs(creator_name: str):
    """
    Read Doc D and Doc E from disk and persist to personality_docs table in DB.

    Use this once after deploying migration 033 to backfill existing creators.
    After this, all future extractions persist automatically.
    """
    import glob as _glob

    session = SessionLocal()
    try:
        from sqlalchemy import text

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        creator_id = str(creator.id)

        extractions_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "personality_extractions",
        )

        saved = []
        errors = []

        doc_map = {
            "doc_d": "doc_d_bot_configuration.md",
            "doc_e": "doc_e_copilot_rules.md",
        }

        for doc_type, filename in doc_map.items():
            # Search for the file under any subdirectory
            matches = _glob.glob(os.path.join(extractions_dir, "**", filename), recursive=True)
            if not matches:
                errors.append(f"{doc_type}: not found on disk")
                continue

            # Prefer exact creator_id or creator_name subdirectory
            chosen = None
            for m in matches:
                parts = m.split(os.sep)
                if creator_id in parts or creator_name in parts:
                    chosen = m
                    break
            if not chosen:
                chosen = matches[0]  # fall back to first found

            try:
                with open(chosen, "r", encoding="utf-8") as f:
                    content = f.read()

                session.execute(
                    text(
                        """
                        INSERT INTO personality_docs (id, creator_id, doc_type, content)
                        VALUES (CAST(:id AS uuid), :creator_id, :doc_type, :content)
                        ON CONFLICT (creator_id, doc_type)
                        DO UPDATE SET content = EXCLUDED.content,
                                      updated_at = now()
                        """
                    ),
                    {"id": str(uuid_lib.uuid4()), "creator_id": creator_id, "doc_type": doc_type, "content": content},
                )
                saved.append(f"{doc_type} ({len(content)} chars from {chosen})")
            except Exception as e:
                errors.append(f"{doc_type}: {e}")

        session.commit()
        logger.info(f"[BACKFILL] personality_docs for {creator_name}: saved={saved} errors={errors}")

        return {
            "status": "ok",
            "creator": creator_name,
            "creator_id": creator_id,
            "saved": saved,
            "errors": errors,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BACKFILL] personality_docs error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


@router.post("/reload-personality/{creator_name}")
async def reload_personality(creator_name: str):
    """
    Invalidate Doc D personality cache for a creator, forcing hot-reload on next DM.

    Clears: personality_loader cache, DM agent cache, creator_data cache.
    The next DM will re-parse doc_d_bot_configuration.md from disk.
    """
    try:
        from core.personality_loader import invalidate_cache as invalidate_personality
        from core.dm_agent_v2 import invalidate_dm_agent_cache
        from core.creator_data_loader import invalidate_creator_cache

        invalidate_personality(creator_name)
        invalidate_dm_agent_cache(creator_name)
        invalidate_creator_cache(creator_name)

        logger.info(f"[HOT-RELOAD] All caches invalidated for {creator_name}")
        return {
            "status": "ok",
            "message": f"Personality cache invalidated for {creator_name}",
            "caches_cleared": ["personality_loader", "dm_agent", "creator_data"],
        }
    except Exception as e:
        logger.error(f"[HOT-RELOAD] Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ECHO ENGINE ENDPOINTS
# =============================================================================


@router.post("/analyze-style/{creator_name}")
async def analyze_style(creator_name: str, force: bool = Query(default=False)):
    """
    Run Style Analyzer for a creator. Extracts quantitative + qualitative
    style metrics from historical DMs and persists to DB.

    - First run: analyzes all messages (requires ≥30 messages)
    - force=True: re-analyzes even if profile exists
    """
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        creator_db_id = str(creator.id)
    finally:
        session.close()

    try:
        from core.style_analyzer import analyze_and_persist
        profile = await analyze_and_persist(creator_name, creator_db_id, force=force)

        if not profile:
            return {
                "status": "skipped",
                "message": "Not enough messages (minimum 30) or profile already exists (use force=true)",
            }

        return {
            "status": "ok",
            "creator": creator_name,
            "confidence": profile.get("confidence", 0),
            "messages_analyzed": profile.get("total_messages_analyzed", 0),
            "version": profile.get("version", 1),
            "prompt_injection_length": len(profile.get("prompt_injection", "")),
            "quantitative_keys": list(profile.get("quantitative", {}).keys()),
            "qualitative_keys": list(profile.get("qualitative", {}).keys()),
        }
    except Exception as e:
        logger.error(f"[ECHO] Style analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/style-profile/{creator_name}")
async def get_style_profile(creator_name: str):
    """View the computed StyleProfile for a creator."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        from core.style_analyzer import load_profile_from_db
        profile = load_profile_from_db(str(creator.id))

        if not profile:
            return {"status": "not_found", "message": "No StyleProfile computed yet. Run POST /maintenance/analyze-style/ first."}

        return {
            "status": "ok",
            "creator": creator_name,
            "confidence": profile.get("confidence", 0),
            "messages_analyzed": profile.get("total_messages_analyzed", 0),
            "version": profile.get("version", 1),
            "quantitative": profile.get("quantitative", {}),
            "qualitative": profile.get("qualitative", {}),
            "prompt_injection": profile.get("prompt_injection", ""),
        }
    finally:
        session.close()


@router.get("/commitments/{creator_name}/{lead_platform_id}")
async def get_lead_commitments(creator_name: str, lead_platform_id: str):
    """View pending commitments for a specific lead."""
    try:
        from services.commitment_tracker import get_commitment_tracker
        tracker = get_commitment_tracker()
        text_output = tracker.get_pending_text(lead_platform_id)
        commitments = tracker.get_pending_for_lead(lead_platform_id, limit=10)

        return {
            "status": "ok",
            "creator": creator_name,
            "lead": lead_platform_id,
            "pending_count": len(commitments),
            "pending_text": text_output,
            "commitments": [
                {
                    "id": str(c.id),
                    "text": c.commitment_text,
                    "type": c.commitment_type,
                    "status": c.status,
                    "due_date": c.due_date.isoformat() if c.due_date else None,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in commitments
            ],
        }
    except Exception as e:
        logger.error(f"[ECHO] Commitments query failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/echo-status/{creator_name}")
async def echo_status(creator_name: str):
    """Check ECHO Engine module status for a creator."""
    import os

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        creator_db_id = str(creator.id)

        # Style Analyzer status
        style_status = {"enabled": os.getenv("ENABLE_STYLE_ANALYZER", "true").lower() == "true"}
        try:
            from core.style_analyzer import load_profile_from_db
            profile = load_profile_from_db(creator_db_id)
            style_status["profile_exists"] = profile is not None
            if profile:
                style_status["confidence"] = profile.get("confidence", 0)
                style_status["messages_analyzed"] = profile.get("total_messages_analyzed", 0)
        except Exception:
            style_status["profile_exists"] = False

        # Memory Engine status
        memory_status = {
            "enabled": os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true",
        }

        # Relationship Adapter status
        adapter_status = {
            "enabled": os.getenv("ENABLE_RELATIONSHIP_ADAPTER", "true").lower() == "true",
        }

        # Commitment Tracker status
        commitment_status = {
            "enabled": os.getenv("ENABLE_COMMITMENT_TRACKING", "true").lower() == "true",
        }

        # CloneScore status
        clone_score_status = {
            "enabled": os.getenv("ENABLE_CLONE_SCORE", "true").lower() == "true",
        }
        try:
            from api.models import CloneScoreEvaluation
            eval_count = (
                session.query(CloneScoreEvaluation)
                .filter_by(creator_id=creator_db_id)
                .count()
            )
            clone_score_status["evaluations_count"] = eval_count
        except Exception:
            clone_score_status["evaluations_count"] = 0

        return {
            "creator": creator_name,
            "modules": {
                "style_analyzer": style_status,
                "clone_score": clone_score_status,
                "memory_engine": memory_status,
                "relationship_adapter": adapter_status,
                "commitment_tracker": commitment_status,
            },
        }
    finally:
        session.close()


@router.post("/run-content-refresh")
async def trigger_content_refresh(creator_name: str = None):
    """Trigger content refresh manually. Optionally limit to a single creator."""
    from services.content_refresh import refresh_all_active_creators, refresh_creator_content

    if creator_name:
        result = await refresh_creator_content(creator_name)
        return {"message": f"Content refresh complete for {creator_name}", "result": result}
    else:
        summary = await refresh_all_active_creators()
        return {"message": "Content refresh complete for all active creators", "summary": summary}


@router.post("/turbo-onboarding/{creator_name}")
async def turbo_onboarding(
    creator_name: str,
    source: str = Query(default="existing", description="existing | whatsapp | instagram"),
    instance: str = Query(default=None, description="Evolution API instance (for whatsapp)"),
    phases: str = Query(default="1,2,3,4,5,6", description="Comma-separated phase numbers"),
):
    """
    Turbo onboarding: bootstrap ALL AI systems from conversation history.

    Processes existing or fetches new messages and feeds every learning system
    so a new creator has a fully functional bot in ~15 minutes.

    Phases: 1=Fetch, 2=Style, 3=Leads, 4=Memory, 5=Summaries+Pairs, 6=Calibration
    """
    from scripts.turbo_onboarding import TurboOnboarding

    phase_list = [int(p.strip()) for p in phases.split(",")]
    pipeline = TurboOnboarding(
        creator_name=creator_name,
        source=source,
        instance_name=instance,
        phases=phase_list,
    )
    result = await pipeline.run()
    return result


@router.post("/reconcile/{creator_name}")
async def reconcile_creator(
    creator_name: str,
    limit: int = Query(default=50, description="Max conversations per folder"),
    lookback_hours: int = Query(default=168, description="Hours to look back (default 7 days)"),
):
    """
    Trigger a full message reconciliation for a specific creator.

    Fetches conversations from all IG folders (inbox + other/message requests)
    with a higher limit than the periodic job.
    """
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        if not creator.instagram_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        ig_user_id = creator.instagram_user_id or creator.instagram_page_id
        if not ig_user_id:
            raise HTTPException(status_code=400, detail="Creator has no Instagram user ID")

        token = creator.instagram_token
    finally:
        session.close()

    from core.message_reconciliation.core import reconcile_messages_for_creator

    async def _run_reconciliation():
        try:
            result = await reconcile_messages_for_creator(
                creator_id=creator_name,
                access_token=token,
                ig_user_id=ig_user_id,
                lookback_hours=lookback_hours,
                max_conversations=limit,
            )
            logger.info(
                f"[Reconciliation] Manual reconcile for {creator_name} done: "
                f"{result.get('messages_inserted', 0)} inserted, "
                f"{result.get('conversations_checked', 0)} conversations checked"
            )
        except Exception as e:
            logger.error(f"[Reconciliation] Manual reconcile for {creator_name} failed: {e}")

    asyncio.create_task(_run_reconciliation())

    return {
        "status": "started",
        "creator": creator_name,
        "limit": limit,
        "lookback_hours": lookback_hours,
        "message": "Reconciliation running in background. Check logs for results.",
    }


# Instance name mapping (mirrors evolution_webhook.py)
_INSTANCE_MAP = {
    "iris_bertran": "iris-bertran",
    "stefano_bonanno": "stefano-fitpack",
}


@router.post("/refresh-profiles/{creator_name}")
async def refresh_profiles(
    creator_name: str,
    platform: str = Query(default="all", description="whatsapp, instagram, or all"),
    limit: int = Query(default=100, description="Max leads to process"),
):
    """
    Bulk refresh profile pictures and display names for leads missing them.

    Runs in background. Fetches from Evolution API (WA) and Instagram Graph API (IG).
    """
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        creator_id = creator.id
        ig_token = creator.instagram_token
        ig_user_id = creator.instagram_user_id or creator.instagram_page_id
    finally:
        session.close()

    wa_instance = _INSTANCE_MAP.get(creator_name)

    async def _refresh():
        updated_wa = 0
        updated_ig = 0
        errors = 0

        # --- WhatsApp profile refresh ---
        if platform in ("whatsapp", "all") and wa_instance:
            try:
                from services.evolution_api import fetch_profile_picture

                def _get_wa_leads_missing_pic():
                    s = SessionLocal()
                    try:
                        return [
                            (str(l.id), l.platform_user_id, l.full_name)
                            for l in s.query(Lead).filter(
                                Lead.creator_id == creator_id,
                                Lead.platform == "whatsapp",
                                or_(
                                    Lead.profile_pic_url.is_(None),
                                    Lead.profile_pic_url == "",
                                ),
                            ).limit(limit).all()
                        ]
                    finally:
                        s.close()

                wa_leads = await asyncio.to_thread(_get_wa_leads_missing_pic)
                logger.info(f"[ProfileRefresh] {creator_name} WA: {len(wa_leads)} leads missing pics")

                for lead_id, puid, full_name in wa_leads:
                    try:
                        number = puid.replace("wa_", "").lstrip("+").split("-")[0]
                        if not number.isdigit():
                            continue  # Skip non-numeric IDs
                        # Skip Facebook/IG numeric IDs misclassified as WA
                        # Real phone numbers: 7-15 digits, but FB IDs are 15+
                        # Also skip very short numbers (< 7 digits)
                        if len(number) < 7 or len(number) > 15:
                            continue
                        pic_url = await fetch_profile_picture(wa_instance, number)
                        if pic_url:
                            def _update_wa(lid=lead_id, url=pic_url):
                                s = SessionLocal()
                                try:
                                    lead = s.query(Lead).get(lid)
                                    if lead:
                                        lead.profile_pic_url = url
                                        s.commit()
                                        return True
                                    return False
                                finally:
                                    s.close()

                            if await asyncio.to_thread(_update_wa):
                                updated_wa += 1
                        await asyncio.sleep(0.5)  # Rate limit
                    except Exception:
                        # Evolution API errors are expected for some numbers
                        pass

                logger.info(f"[ProfileRefresh] {creator_name} WA: {updated_wa} pics updated")

            except Exception as e:
                logger.error(f"[ProfileRefresh] WA refresh failed: {e}")

        # --- Instagram profile refresh ---
        if platform in ("instagram", "all") and ig_token:
            try:
                from core.instagram_profile import fetch_instagram_profile_detailed

                def _get_ig_leads_missing():
                    s = SessionLocal()
                    try:
                        return [
                            (str(l.id), l.platform_user_id, l.username)
                            for l in s.query(Lead).filter(
                                Lead.creator_id == creator_id,
                                Lead.platform == "instagram",
                                or_(
                                    Lead.profile_pic_url.is_(None),
                                    Lead.profile_pic_url == "",
                                    Lead.full_name.is_(None),
                                    Lead.username.is_(None),
                                ),
                            ).limit(limit).all()
                        ]
                    finally:
                        s.close()

                ig_leads = await asyncio.to_thread(_get_ig_leads_missing)
                logger.info(f"[ProfileRefresh] {creator_name} IG: {len(ig_leads)} leads missing info")

                for lead_id, puid, username in ig_leads:
                    try:
                        uid = puid.replace("ig_", "") if puid else ""
                        if not uid:
                            continue
                        result = await fetch_instagram_profile_detailed(
                            user_id=uid,
                            access_token=ig_token,
                        )
                        profile = result.profile if result.success else None
                        if profile:
                            def _update_ig(lid=lead_id, p=profile):
                                s = SessionLocal()
                                try:
                                    lead = s.query(Lead).get(lid)
                                    if lead:
                                        if p.get("username") and not lead.username:
                                            lead.username = p["username"]
                                        if p.get("name") and not lead.full_name:
                                            lead.full_name = p["name"]
                                        if p.get("profile_pic") and not lead.profile_pic_url:
                                            lead.profile_pic_url = p["profile_pic"]
                                        s.commit()
                                        return True
                                    return False
                                finally:
                                    s.close()

                            if await asyncio.to_thread(_update_ig):
                                updated_ig += 1
                        await asyncio.sleep(0.5)  # Rate limit
                    except Exception:
                        # IG API errors (consent required, etc.) are expected
                        pass

                logger.info(f"[ProfileRefresh] {creator_name} IG: {updated_ig} profiles updated")

            except Exception as e:
                logger.error(f"[ProfileRefresh] IG refresh failed: {e}")

        logger.info(
            f"[ProfileRefresh] {creator_name} DONE: WA={updated_wa}, IG={updated_ig}, errors={errors}"
        )

    asyncio.create_task(_refresh())

    return {
        "status": "started",
        "creator": creator_name,
        "platform": platform,
        "limit": limit,
        "wa_instance": wa_instance,
        "has_ig_token": bool(ig_token),
        "message": "Profile refresh running in background. Check logs for results.",
    }


@router.post("/sync-wa-contacts/{creator_name}")
async def sync_wa_contacts(
    creator_name: str,
    limit: int = Query(default=1000, description="Max leads to update"),
):
    """
    Bulk sync WA profile pics and names from Evolution API contacts cache.
    Uses findContacts endpoint (no per-contact API calls needed).
    """
    import aiohttp

    wa_instance = _INSTANCE_MAP.get(creator_name)
    if not wa_instance:
        raise HTTPException(status_code=400, detail=f"No WA instance for {creator_name}")

    evo_url = os.getenv("EVOLUTION_API_URL", "https://evolution-api-production-d840.up.railway.app")
    evo_key = os.getenv("EVOLUTION_API_KEY", "clonnect-evo-2026-prod")

    # Fetch all contacts from Evolution
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(
            f"{evo_url}/chat/findContacts/{wa_instance}",
            json={},
            headers={"apikey": evo_key, "Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail=f"Evolution API error: {resp.status}")
            contacts = await resp.json()

    # Build lookup: number -> {pic, name}
    contact_map = {}
    for c in contacts:
        jid = c.get("remoteJid", "")
        if not jid or c.get("isGroup"):
            continue
        number = jid.split("@")[0]
        pic_url = c.get("profilePicUrl") or ""
        push_name = c.get("pushName") or ""
        if pic_url or push_name:
            contact_map[number] = {"pic": pic_url, "name": push_name}

    # Update DB leads
    def _sync():
        s = SessionLocal()
        try:
            creator = s.query(Creator).filter_by(name=creator_name).first()
            if not creator:
                return {"error": "Creator not found"}

            leads = (
                s.query(Lead)
                .filter(Lead.creator_id == creator.id, Lead.platform == "whatsapp")
                .limit(limit)
                .all()
            )

            updated_pics = 0
            updated_names = 0
            matched = 0

            for lead in leads:
                puid = lead.platform_user_id or ""
                number = puid.replace("wa_", "").lstrip("+")
                contact = contact_map.get(number)
                if not contact:
                    continue
                matched += 1
                changed = False

                if (not lead.profile_pic_url) and contact["pic"]:
                    lead.profile_pic_url = contact["pic"]
                    updated_pics += 1
                    changed = True

                if (not lead.full_name) and contact["name"]:
                    name = contact["name"].strip()
                    if not name.replace("+", "").replace(" ", "").isdigit():
                        lead.full_name = name
                        updated_names += 1
                        changed = True

            s.commit()
            return {
                "total_leads": len(leads),
                "evolution_contacts": len(contact_map),
                "matched": matched,
                "updated_pics": updated_pics,
                "updated_names": updated_names,
            }
        finally:
            s.close()

    result = await asyncio.to_thread(_sync)
    return {"creator": creator_name, "instance": wa_instance, **result}


@router.post("/sync-ig-public/{creator_name}")
async def sync_ig_public_profiles(
    creator_name: str,
    limit: int = Query(default=100, description="Max leads to process"),
    delay: float = Query(default=2.5, ge=1.0, le=10.0, description="Seconds between requests"),
):
    """
    Fetch IG profile pics via public Instagram API (no Graph API consent needed).
    Runs in background on server. Works for leads that have a username.
    """
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        creator_id_str = str(creator.id)
    finally:
        session.close()

    async def _bg_sync():
        import aiohttp

        updated_pics = 0
        updated_names = 0
        rate_limited = False

        def _get_leads():
            s = SessionLocal()
            try:
                return [
                    (str(l.id), l.username, l.full_name, l.profile_pic_url)
                    for l in s.query(Lead).filter(
                        Lead.creator_id == creator_id_str,
                        Lead.platform == "instagram",
                        Lead.username.isnot(None),
                        Lead.username != "",
                        or_(
                            Lead.profile_pic_url.is_(None),
                            Lead.profile_pic_url == "",
                        ),
                    ).order_by(Lead.last_contact_at.desc().nullslast()).limit(limit).all()
                ]
            finally:
                s.close()

        leads = await asyncio.to_thread(_get_leads)
        logger.info(f"[IGPublicSync] {creator_name}: {len(leads)} leads need pics")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            for i, (lead_id, username, full_name, pic_url) in enumerate(leads):
                if rate_limited:
                    break

                try:
                    async with http.get(
                        f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                        headers={
                            "User-Agent": "Instagram 76.0.0.15.395 Android",
                            "x-ig-app-id": "936619743392459",
                        },
                    ) as resp:
                        if resp.status in (401, 429):
                            logger.warning(f"[IGPublicSync] Rate limited at {i+1}/{len(leads)}")
                            rate_limited = True
                            break

                        if resp.status == 200:
                            data = await resp.json()
                            user = data.get("data", {}).get("user", {})
                            if user:
                                new_pic = user.get("profile_pic_url_hd") or user.get("profile_pic_url", "")
                                new_name = user.get("full_name", "")

                                updates = {}
                                if new_pic and not pic_url:
                                    updates["pic"] = new_pic
                                if new_name and not full_name:
                                    updates["name"] = new_name

                                if updates:
                                    def _update(lid=lead_id, u=updates):
                                        s = SessionLocal()
                                        try:
                                            lead = s.query(Lead).get(lid)
                                            if lead:
                                                if "pic" in u:
                                                    lead.profile_pic_url = u["pic"]
                                                if "name" in u:
                                                    lead.full_name = u["name"]
                                                s.commit()
                                                return True
                                            return False
                                        finally:
                                            s.close()

                                    if await asyncio.to_thread(_update):
                                        if "pic" in updates:
                                            updated_pics += 1
                                        if "name" in updates:
                                            updated_names += 1

                except Exception:
                    pass

                await asyncio.sleep(delay)

        logger.info(
            f"[IGPublicSync] {creator_name} DONE: {updated_pics} pics, {updated_names} names"
            f" (processed {min(i+1, len(leads))}/{len(leads)}, rate_limited={rate_limited})"
        )

    asyncio.create_task(_bg_sync())

    return {
        "status": "started",
        "creator": creator_name,
        "limit": limit,
        "delay_seconds": delay,
        "message": "IG public profile sync running in background.",
    }
