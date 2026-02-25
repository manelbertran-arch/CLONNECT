"""One-off fixes for leads, emojis, Instagram IDs, and unique constraints."""
import logging

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/fix-lead-timestamps/{creator_id}")
async def fix_lead_timestamps(creator_id: str, admin: str = Depends(require_admin)):
    """
    Corrige las fechas de last_contact_at basandose en los mensajes guardados.

    El problema: last_contact_at se estaba guardando con el timestamp del ultimo
    mensaje de la conversacion (incluyendo mensajes del bot), pero para FANTASMA
    necesitamos el ultimo mensaje del USUARIO.

    Esta funcion:
    1. Lee todos los mensajes de cada lead
    2. Calcula first_contact y last_contact correctamente
    3. last_contact = ultimo mensaje role=user
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                creator = (
                    session.query(Creator)
                    .filter(text("id::text = :cid"))
                    .params(cid=creator_id)
                    .first()
                )

            if not creator:
                return {"status": "error", "error": f"Creator not found: {creator_id}"}

            leads = session.query(Lead).filter_by(creator_id=creator.id).all()

            stats = {
                "total_leads": len(leads),
                "leads_updated": 0,
                "leads_no_messages": 0,
                "leads_no_user_messages": 0,
                "details": [],
            }

            # TODO: N+1 query - batch this. Should pre-fetch all messages grouped by lead_id
            # in a single query (like the pattern in recategorize_leads below) instead of
            # querying per-lead. Low priority since this is an admin maintenance endpoint.
            for lead in leads:
                messages = (
                    session.query(Message)
                    .filter_by(lead_id=lead.id)
                    .order_by(Message.created_at)
                    .all()
                )
                old_first = lead.first_contact_at
                old_last = lead.last_contact_at

                if not messages:
                    # Para leads SIN mensajes: last_contact = first_contact
                    # Esto permite detectarlos correctamente como fantasma
                    if lead.first_contact_at and lead.last_contact_at != lead.first_contact_at:
                        lead.last_contact_at = lead.first_contact_at
                        stats["leads_no_messages"] += 1
                        stats["leads_updated"] += 1
                        stats["details"].append(
                            {
                                "username": lead.username,
                                "old_first": str(old_first) if old_first else None,
                                "new_first": (
                                    str(lead.first_contact_at) if lead.first_contact_at else None
                                ),
                                "old_last": str(old_last) if old_last else None,
                                "new_last": (
                                    str(lead.last_contact_at) if lead.last_contact_at else None
                                ),
                                "total_messages": 0,
                                "user_messages": 0,
                                "fix_type": "no_messages_use_first_contact",
                            }
                        )
                    else:
                        stats["leads_no_messages"] += 1
                    continue

                # Separar mensajes de usuario vs bot
                user_messages = [m for m in messages if m.role == "user"]
                all_timestamps = [m.created_at for m in messages if m.created_at]
                user_timestamps = [m.created_at for m in user_messages if m.created_at]

                # first_contact = primer mensaje de cualquiera
                if all_timestamps:
                    lead.first_contact_at = min(all_timestamps)

                # last_contact = ultimo mensaje del USUARIO
                if user_timestamps:
                    lead.last_contact_at = max(user_timestamps)
                    stats["leads_updated"] += 1

                    stats["details"].append(
                        {
                            "username": lead.username,
                            "old_first": str(old_first) if old_first else None,
                            "new_first": (
                                str(lead.first_contact_at) if lead.first_contact_at else None
                            ),
                            "old_last": str(old_last) if old_last else None,
                            "new_last": str(lead.last_contact_at) if lead.last_contact_at else None,
                            "total_messages": len(messages),
                            "user_messages": len(user_messages),
                        }
                    )
                else:
                    # Mensajes pero ninguno del usuario: usar first_contact
                    if lead.first_contact_at:
                        lead.last_contact_at = lead.first_contact_at
                        stats["leads_updated"] += 1
                    stats["leads_no_user_messages"] += 1

            session.commit()
            logger.info(f"[FixTimestamps] Updated {stats['leads_updated']} leads for {creator_id}")

            return {"status": "success", "creator_id": creator_id, **stats}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Fix timestamps failed for {creator_id}: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.api_route("/fix-reaction-emojis", methods=["GET", "POST"])
async def fix_reaction_emojis(admin: str = Depends(require_admin)):
    """
    Fix reaction emojis missing the variation selector.

    The problem: Hearts stored as "\u2764" (U+2764) render as white/black text.
    The fix: Add variation selector to make "\u2764\ufe0f" (U+2764 U+FE0F) render as red emoji.
    """
    try:
        from api.database import SessionLocal
        from api.models import Message

        session = SessionLocal()
        try:
            # Find messages with reaction type or emoji in metadata
            messages = session.query(Message).filter(Message.msg_metadata.isnot(None)).all()

            fixed_count = 0
            for msg in messages:
                if msg.msg_metadata and isinstance(msg.msg_metadata, dict):
                    emoji = msg.msg_metadata.get("emoji")
                    # Check if it's the heart without variation selector
                    if emoji == "\u2764" or emoji == "\u2764":
                        msg.msg_metadata = {**msg.msg_metadata, "emoji": "\u2764\ufe0f"}
                        fixed_count += 1

            session.commit()
            return {
                "status": "ok",
                "messages_checked": len(messages),
                "messages_fixed": fixed_count,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error fixing reaction emojis: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/apply-unique-constraint")
async def apply_unique_constraint(admin: str = Depends(require_admin)):
    """
    Apply UniqueConstraint to leads table to prevent duplicates.
    Steps:
    1. Find and merge duplicates (keep one with most messages)
    2. Add the UniqueConstraint
    """
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    results = {"duplicates_merged": [], "constraint_applied": False, "errors": []}

    try:
        # 1. Find all duplicates
        duplicates = session.execute(
            text(
                """
                SELECT platform_user_id, creator_id,
                       array_agg(id::text ORDER BY (SELECT COUNT(*) FROM messages m WHERE m.lead_id = leads.id) DESC) as ids
                FROM leads
                GROUP BY platform_user_id, creator_id
                HAVING COUNT(*) > 1
            """
            )
        ).fetchall()

        for dup in duplicates:
            platform_user_id, creator_id, ids = dup
            # Keep the first one (has most messages), delete the rest
            keep_id = ids[0]
            delete_ids = ids[1:]

            for del_id in delete_ids:
                # Move any messages to the kept lead
                session.execute(
                    text("UPDATE messages SET lead_id = :keep_id WHERE lead_id = :del_id"),
                    {"keep_id": keep_id, "del_id": del_id},
                )
                # Delete the duplicate lead
                session.execute(text("DELETE FROM leads WHERE id = :del_id"), {"del_id": del_id})
                results["duplicates_merged"].append(
                    {
                        "platform_user_id": platform_user_id,
                        "deleted_id": del_id[:8],
                        "kept_id": keep_id[:8],
                    }
                )

        session.commit()

        # 2. Check if constraint already exists
        existing = session.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'leads'::regclass
                AND conname = 'uq_lead_creator_platform'
            """
            )
        ).fetchone()

        if existing:
            results["constraint_applied"] = "already_exists"
        else:
            # 3. Apply the constraint
            try:
                session.execute(
                    text(
                        """
                        ALTER TABLE leads
                        ADD CONSTRAINT uq_lead_creator_platform
                        UNIQUE (creator_id, platform_user_id)
                    """
                    )
                )
                session.commit()
                results["constraint_applied"] = True
            except Exception as e:
                results["errors"].append(f"Constraint error: {str(e)}")
                session.rollback()

        # 4. Verify constraint exists now
        constraints = session.execute(
            text(
                """
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'leads'::regclass
            """
            )
        ).fetchall()
        results["current_constraints"] = [{"name": c[0], "def": c[1]} for c in constraints]

        return {"status": "ok", "results": results}

    except Exception as e:
        logger.error(f"Error applying constraint: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        session.close()


@router.post("/fix-instagram-page-id/{creator_id}")
async def fix_instagram_page_id(creator_id: str, admin: str = Depends(require_admin)):
    """
    Fetch and save the Facebook Page ID for a creator.

    This is needed because Meta webhooks send the page_id (Facebook Page ID),
    not the ig_user_id (Instagram User ID). Without the page_id stored,
    webhooks cannot be routed to the correct creator.
    """
    import requests
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        if not creator.instagram_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        token = creator.instagram_token
        token_prefix = token[:15] if token else "NONE"
        token_length = len(token) if token else 0
        is_page_token = token.startswith("EAA") if token else False
        is_igaat_token = token.startswith("IGAAT") if token else False

        logger.info(
            f"[FixPageID] Token: {token_prefix}... (len={token_length}), is_page={is_page_token}, is_igaat={is_igaat_token}"
        )

        page_id = None
        page_name = None
        pages = []

        # Return token debug info in all responses
        token_debug = {
            "token_prefix": token_prefix,
            "token_length": token_length,
            "is_page_token": is_page_token,
            "is_igaat_token": is_igaat_token,
        }

        if is_igaat_token:
            # IGAAT token = Instagram Graph API Token
            # Use graph.instagram.com/me to get Instagram user info
            url = "https://graph.instagram.com/me"
            params = {"access_token": token, "fields": "id,username"}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                return {
                    "status": "error",
                    "error": f"Instagram API error: {response.status_code}",
                    "detail": response.text[:500],
                    "token_debug": token_debug,
                    "hint": "IGAAT tokens work with graph.instagram.com, not graph.facebook.com",
                }

            data = response.json()
            ig_user_id = data.get("id")
            ig_username = data.get("username")

            # For IGAAT tokens, the ig_user_id is what Meta sends as recipient
            # Update DB: set ig_user_id AND add Facebook page ID to additional_ids
            old_page_id = creator.instagram_page_id
            old_user_id = creator.instagram_user_id

            creator.instagram_user_id = ig_user_id
            # Keep page_id as ig_user_id for primary routing match
            if not creator.instagram_page_id or creator.instagram_page_id != ig_user_id:
                creator.instagram_page_id = ig_user_id

            # Add the Facebook Page ID (from env var) to additional_ids
            # so webhooks with the FB page ID also route correctly
            import os
            fb_page_id = os.getenv("FACEBOOK_PAGE_ID", "") or os.getenv("INSTAGRAM_PAGE_ID", "")
            additional_ids = creator.instagram_additional_ids or []
            added_ids = []
            for extra_id in [fb_page_id, old_page_id]:
                if extra_id and extra_id != ig_user_id and extra_id not in additional_ids:
                    additional_ids.append(extra_id)
                    added_ids.append(extra_id)
            if added_ids:
                creator.instagram_additional_ids = additional_ids

            session.commit()

            # Clear routing cache
            from core.webhook_routing import clear_routing_cache
            clear_routing_cache()

            return {
                "status": "ok",
                "message": "IGAAT token - updated Instagram routing IDs",
                "instagram_user_id": ig_user_id,
                "instagram_username": ig_username,
                "old_page_id": old_page_id,
                "old_user_id": old_user_id,
                "new_page_id": creator.instagram_page_id,
                "new_user_id": ig_user_id,
                "additional_ids_added": added_ids,
                "all_additional_ids": additional_ids,
                "token_debug": token_debug,
            }

        elif is_page_token:
            # EAA token = Page Access Token
            # Use /me to get the page info directly
            url = "https://graph.facebook.com/v18.0/me"
            params = {"access_token": token, "fields": "id,name"}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                return {
                    "status": "error",
                    "error": f"Meta API error: {response.status_code}",
                    "detail": response.text[:500],
                    "token_debug": token_debug,
                }

            data = response.json()
            page_id = data.get("id")
            page_name = data.get("name")

        else:
            # IGAAT token = User/Instagram token
            # Use /me/accounts to get pages
            url = "https://graph.facebook.com/v18.0/me/accounts"
            params = {"access_token": token}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                return {
                    "status": "error",
                    "error": f"Meta API error: {response.status_code}",
                    "detail": response.text[:500],
                    "token_debug": token_debug,
                }

            data = response.json()
            pages = data.get("data", [])

            if not pages:
                return {
                    "status": "error",
                    "error": "No Facebook pages found for this token",
                    "hint": "Make sure the token has pages_read_engagement permission",
                    "token_debug": token_debug,
                }

            # Use the first page
            page = pages[0]
            page_id = page.get("id")
            page_name = page.get("name")

        # Save to database
        old_page_id = creator.instagram_page_id
        creator.instagram_page_id = page_id
        session.commit()

        # Clear the lookup cache
        from api.routers.instagram import _creator_by_page_id_cache

        _creator_by_page_id_cache.clear()

        return {
            "status": "ok",
            "creator_id": creator_id,
            "old_page_id": old_page_id,
            "new_page_id": page_id,
            "page_name": page_name,
            "all_pages": [{"id": p.get("id"), "name": p.get("name")} for p in pages],
            "cache_cleared": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fixing Instagram page_id: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


@router.post("/add-instagram-id/{creator_id}/{instagram_id}")
async def add_instagram_id(creator_id: str, instagram_id: str, admin: str = Depends(require_admin)):
    """Add an Instagram ID to a creator's additional_ids for webhook routing."""
    from core.webhook_routing import add_instagram_id_to_creator, clear_routing_cache

    success = add_instagram_id_to_creator(creator_id, instagram_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

    clear_routing_cache()
    return {"status": "ok", "creator_id": creator_id, "added_id": instagram_id}


@router.post("/fix-lead-duplicates")
async def fix_lead_duplicates(admin: str = Depends(require_admin)):
    """
    Fix all duplicate leads and add unique constraint.
    1. Find all duplicates (same creator_id + platform_user_id)
    2. Merge messages to the one with most messages
    3. Delete duplicates
    4. Add unique constraint
    """
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    results = {
        "duplicates_found": 0,
        "leads_deleted": 0,
        "messages_moved": 0,
        "constraint_added": False,
        "details": [],
    }

    try:
        # Step 1: Find all duplicates across ALL creators
        duplicates = session.execute(
            text(
                """
                SELECT creator_id, platform_user_id, COUNT(*) as cnt
                FROM leads
                GROUP BY creator_id, platform_user_id
                HAVING COUNT(*) > 1
            """
            )
        ).fetchall()

        results["duplicates_found"] = len(duplicates)

        # Step 2: For each duplicate, keep the one with most messages
        for dup in duplicates:
            creator_id, platform_user_id, cnt = dup

            # Get all leads with this creator_id + platform_user_id, ordered by message count
            leads = session.execute(
                text(
                    """
                    SELECT l.id, l.username,
                           (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
                    FROM leads l
                    WHERE l.creator_id = :cid AND l.platform_user_id = :puid
                    ORDER BY msg_count DESC
                """
                ),
                {"cid": str(creator_id), "puid": platform_user_id},
            ).fetchall()

            if len(leads) <= 1:
                continue

            # Keep the first one (most messages), delete the rest
            keep_id = leads[0][0]
            keep_username = leads[0][1]
            _keep_msg_count = leads[0][2]

            for lead in leads[1:]:
                delete_id = lead[0]
                delete_msg_count = lead[2]

                # Move messages from duplicate to keeper
                if delete_msg_count > 0:
                    session.execute(
                        text("UPDATE messages SET lead_id = :keep WHERE lead_id = :delete"),
                        {"keep": str(keep_id), "delete": str(delete_id)},
                    )
                    results["messages_moved"] += delete_msg_count

                # Delete the duplicate lead
                session.execute(
                    text("DELETE FROM leads WHERE id = :id"),
                    {"id": str(delete_id)},
                )
                results["leads_deleted"] += 1

            results["details"].append(
                {
                    "platform_user_id": platform_user_id,
                    "kept_username": keep_username,
                    "duplicates_removed": len(leads) - 1,
                }
            )

        session.commit()

        # Step 3: Try to add unique constraint
        try:
            session.execute(
                text(
                    """
                    ALTER TABLE leads
                    ADD CONSTRAINT uq_lead_creator_platform
                    UNIQUE (creator_id, platform_user_id)
                """
                )
            )
            session.commit()
            results["constraint_added"] = True
        except Exception as ce:
            session.rollback()
            if "already exists" in str(ce).lower():
                results["constraint_added"] = "already_exists"
            else:
                results["constraint_error"] = str(ce)

        # Step 4: Count remaining leads
        total = session.execute(text("SELECT COUNT(*) FROM leads")).scalar()
        results["total_leads_after"] = total

        return {"status": "ok", "results": results}

    except Exception as e:
        session.rollback()
        logger.error(f"Error fixing duplicates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        session.close()
