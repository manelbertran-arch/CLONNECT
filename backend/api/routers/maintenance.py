"""
Maintenance endpoints for admin tasks like refreshing profile pictures.
"""

import asyncio
import logging

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
            query = query.filter(or_(Lead.profile_pic_url.is_(None), Lead.profile_pic_url == ""))

        leads = query.order_by(Lead.last_contact_at.desc()).offset(offset).limit(limit).all()

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
                            "fields": "id,username,name,profile_pic",
                            "access_token": creator.instagram_token,
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        profile_pic = data.get("profile_pic")

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
    """
    from services.lead_scoring import batch_recalculate_scores

    session = SessionLocal()
    try:
        result = batch_recalculate_scores(session, creator_name)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return result
    finally:
        session.close()


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
        raise HTTPException(status_code=500, detail=str(e))
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
        raise HTTPException(status_code=500, detail=str(e))
