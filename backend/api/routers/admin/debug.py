"""
Debug and diagnostic endpoints.

Provides tools for debugging Instagram API, message sync, and lead issues:
- Raw message inspection from Instagram API
- Sync logic simulation
- Orphaned message detection
- Full diagnostic queries
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/debug/memory")
async def debug_memory(admin: str = Depends(require_admin)):
    """
    Memory usage diagnostic endpoint.
    Shows RSS, cache sizes, and top objects by size.
    """
    import gc
    import os
    import resource
    import sys

    result = {}

    # 1. Process memory (RSS)
    try:
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        result["rss_mb"] = round(rusage.ru_maxrss / (1024 * 1024), 1)  # macOS: bytes
    except Exception:
        result["rss_mb"] = "unavailable"

    # Try /proc/self/status for Linux (Railway)
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    result["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
                    break
    except FileNotFoundError:
        pass

    # 2. Cache sizes
    caches = {}
    try:
        from core.embeddings import _embedding_cache
        caches["embedding_cache"] = _embedding_cache.stats()
    except Exception as e:
        caches["embedding_cache"] = str(e)

    try:
        from core.rag.semantic import _rag_cache
        caches["rag_cache"] = _rag_cache.stats()
    except Exception as e:
        caches["rag_cache"] = str(e)

    try:
        from core.dm.agent import _dm_agent_cache
        caches["dm_agent_cache"] = _dm_agent_cache.stats()
    except Exception as e:
        caches["dm_agent_cache"] = str(e)

    try:
        from core.creator_data_loader import _creator_data_cache
        caches["creator_data_cache"] = _creator_data_cache.stats()
    except Exception as e:
        caches["creator_data_cache"] = str(e)

    try:
        from core.citation_service import _index_cache
        caches["index_cache"] = _index_cache.stats()
    except Exception as e:
        caches["index_cache"] = str(e)

    try:
        from core.data.tone_profile_repo import get_tone_cache_stats
        caches["tone_cache"] = get_tone_cache_stats()
    except Exception as e:
        caches["tone_cache"] = str(e)

    try:
        from core.personality_loader import _cache as personality_cache
        caches["personality_cache"] = personality_cache.stats()
    except Exception as e:
        caches["personality_cache"] = str(e)

    try:
        from services.knowledge_base import _kb_cache
        caches["kb_cache"] = _kb_cache.stats()
    except Exception as e:
        caches["kb_cache"] = str(e)

    try:
        from core.semantic_memory_pgvector import _memory_cache
        caches["semantic_memory_pgvector"] = {"size": len(_memory_cache)}
    except Exception as e:
        caches["semantic_memory_pgvector"] = str(e)

    try:
        from core.cache import get_response_cache, get_search_cache
        rc = get_response_cache()
        sc = get_search_cache()
        caches["response_cache"] = rc.stats()
        caches["search_cache"] = sc.stats()
    except Exception as e:
        caches["lru_caches"] = str(e)

    result["caches"] = caches

    # 3. ML models loaded
    ml_models = {}
    try:
        from core.rag.reranker import _reranker
        ml_models["cross_encoder"] = "loaded" if _reranker is not None else "not_loaded"
    except Exception:
        ml_models["cross_encoder"] = "import_failed"

    if "sentence_transformers" in sys.modules:
        ml_models["sentence_transformers_imported"] = True
    if "torch" in sys.modules:
        ml_models["torch_imported"] = True

    result["ml_models"] = ml_models

    # 4. GC stats
    gc_stats = gc.get_stats()
    result["gc"] = {
        f"gen{i}": {"collections": s["collections"], "collected": s["collected"], "uncollectable": s["uncollectable"]}
        for i, s in enumerate(gc_stats)
    }

    # 5. Top object types by count
    gc.collect()
    type_counts = {}
    for obj in gc.get_objects():
        t = type(obj).__name__
        type_counts[t] = type_counts.get(t, 0) + 1
    result["top_types"] = dict(sorted(type_counts.items(), key=lambda x: -x[1])[:15])

    return result


@router.get("/debug-raw-messages/{creator_id}/{username}")
async def debug_raw_messages(creator_id: str, username: str, admin: str = Depends(require_admin)):
    """
    DEBUG: Get raw Instagram API response for messages to see what fields are actually returned.
    This helps debug why media rendering isn't working.
    """
    import httpx
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        access_token = creator.instagram_token
        ig_user_id = creator.instagram_user_id
        ig_page_id = creator.instagram_page_id

        if not access_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        # Dual API strategy
        if ig_page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = ig_page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id
            conv_extra_params = {}

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get conversations
            conv_resp = await client.get(
                f"{api_base}/{conv_id_for_api}/conversations",
                params={
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": 20,
                    "fields": "id,updated_time",
                },
            )

            if conv_resp.status_code != 200:
                return {
                    "error": f"Conversations API error: {conv_resp.status_code}",
                    "response": conv_resp.text,
                }

            conversations = conv_resp.json().get("data", [])

            # Find conversation with target username
            target_conv_id = None
            for conv in conversations:
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                msg_resp = await client.get(
                    f"{api_base}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 3,
                    },
                )
                if msg_resp.status_code == 200:
                    for msg in msg_resp.json().get("data", []):
                        if msg.get("from", {}).get("username") == username:
                            target_conv_id = conv_id
                            break
                        for recipient in msg.get("to", {}).get("data", []):
                            if recipient.get("username") == username:
                                target_conv_id = conv_id
                                break
                if target_conv_id:
                    break

            if not target_conv_id:
                return {"error": f"Conversation with {username} not found"}

            # Get messages with ALL possible fields
            msg_resp = await client.get(
                f"{api_base}/{target_conv_id}/messages",
                params={
                    "fields": "id,message,from,to,created_time,attachments,story,shares,reactions,sticker,is_unsupported",
                    "access_token": access_token,
                    "limit": 20,
                },
            )

            raw_messages = (
                msg_resp.json() if msg_resp.status_code == 200 else {"error": msg_resp.text}
            )

            # Analyze what fields are present in each message
            field_analysis = []
            for msg in raw_messages.get("data", []):
                analysis = {
                    "id": msg.get("id", "")[:20] + "...",
                    "has_message_text": bool(msg.get("message")),
                    "message_preview": (
                        (msg.get("message", "")[:50] + "...") if msg.get("message") else None
                    ),
                    "has_attachments": bool(msg.get("attachments")),
                    "has_story": bool(msg.get("story")),
                    "has_shares": bool(msg.get("shares")),
                    "has_reactions": bool(msg.get("reactions")),
                    "has_sticker": bool(msg.get("sticker")),
                    "is_unsupported": msg.get("is_unsupported"),
                    "all_keys": list(msg.keys()),
                }
                if msg.get("attachments"):
                    analysis["attachments_data"] = msg.get("attachments")
                if msg.get("story"):
                    analysis["story_data"] = msg.get("story")
                if msg.get("shares"):
                    analysis["shares_data"] = msg.get("shares")
                field_analysis.append(analysis)

            return {
                "conversation_id": target_conv_id,
                "username": username,
                "total_messages": len(raw_messages.get("data", [])),
                "field_analysis": field_analysis,
                "raw_messages": raw_messages.get("data", [])[:5],  # First 5 raw messages
            }

    finally:
        session.close()


@router.get("/debug-instagram-api/{creator_id}")
async def debug_instagram_api(creator_id: str, admin: str = Depends(require_admin)):
    """
    Debug: Ver qué retorna la API de Instagram para conversaciones y mensajes.
    Uses centralized get_instagram_credentials() for consistent token lookup.
    """
    import httpx
    from api.services import db_service

    try:
        # Use centralized function for Instagram credentials
        creds = db_service.get_instagram_credentials(creator_id)
        if not creds["success"]:
            return {"error": creds["error"]}

        ig_user_id = creds["user_id"] or creds["page_id"]
        page_id = creds["page_id"]
        access_token = creds["token"]

        # FIX: Check token type FIRST to determine API
        is_igaat_token = access_token.startswith("IGAAT")
        is_page_token = access_token.startswith("EAA")

        if is_igaat_token:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id or page_id
            conv_extra_params = {}
            api_used = "Instagram"
        elif is_page_token and page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = page_id
            conv_extra_params = {"platform": "instagram"}
            api_used = "Facebook"
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id or page_id
            conv_extra_params = {}
            api_used = "Instagram"

        results = {
            "ig_user_id": ig_user_id,
            "page_id": page_id,
            "api_used": api_used,
            "conversations": [],
            "sample_messages": [],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get conversations
            conv_url = f"{api_base}/{conv_id_for_api}/conversations"
            conv_resp = await client.get(
                conv_url, params={**conv_extra_params, "access_token": access_token, "limit": 5}
            )

            if conv_resp.status_code != 200:
                results["conversations_error"] = conv_resp.json()
                return results

            conv_data = conv_resp.json()
            conversations = conv_data.get("data", [])
            results["conversations_count"] = len(conversations)

            # Try to get messages for first 3 conversations
            for i, conv in enumerate(conversations[:3]):
                conv_id = conv.get("id")
                conv_info = {"conv_id": conv_id, "conv_data": conv}

                # Get messages
                msg_url = f"{api_base}/{conv_id}/messages"
                msg_resp = await client.get(
                    msg_url,
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 3,
                    },
                )

                if msg_resp.status_code != 200:
                    conv_info["messages_error"] = msg_resp.json()
                else:
                    msg_data = msg_resp.json()
                    conv_info["messages"] = msg_data.get("data", [])
                    conv_info["messages_count"] = len(conv_info["messages"])

                results["sample_messages"].append(conv_info)

        return results

    except Exception as e:
        return {"error": str(e)}


@router.get("/debug-sync-logic/{creator_id}")
async def debug_sync_logic(creator_id: str, admin: str = Depends(require_admin)):
    """
    Debug: Simular exactamente lo que hace sync_worker para identificar
    por qué los mensajes no se guardan.
    """
    import httpx
    from api.services import db_service

    try:
        creds = db_service.get_instagram_credentials(creator_id)
        if not creds["success"]:
            return {"error": creds["error"]}

        ig_user_id = creds["user_id"] or creds["page_id"]
        ig_page_id = creds["page_id"]
        creator_ids = {ig_user_id, ig_page_id} - {None}
        access_token = creds["token"]

        # FIX: Check token type FIRST to determine API
        is_igaat_token = access_token.startswith("IGAAT")
        is_page_token = access_token.startswith("EAA")

        if is_igaat_token:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id or ig_page_id
            conv_extra_params = {}
        elif is_page_token and ig_page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = ig_page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id or ig_page_id
            conv_extra_params = {}

        results = {
            "creator_ids": list(creator_ids),
            "api_base": api_base,
            "conversations_analysis": [],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get conversations
            conv_resp = await client.get(
                f"{api_base}/{conv_id_for_api}/conversations",
                params={**conv_extra_params, "access_token": access_token, "limit": 3},
            )

            if conv_resp.status_code != 200:
                return {"error": f"Conversations API error: {conv_resp.json()}"}

            conversations = conv_resp.json().get("data", [])

            for conv in conversations[:3]:
                conv_id = conv.get("id")
                conv_analysis = {
                    "conv_id": conv_id,
                    "messages_raw": [],
                    "follower_detection": {},
                    "messages_would_save": [],
                }

                # Get messages
                msg_resp = await client.get(
                    f"{api_base}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 10,
                    },
                )

                if msg_resp.status_code != 200:
                    conv_analysis["messages_error"] = msg_resp.json()
                    results["conversations_analysis"].append(conv_analysis)
                    continue

                messages = msg_resp.json().get("data", [])
                conv_analysis["total_messages"] = len(messages)

                # Simular lógica de identificación de follower
                follower_id = None
                follower_username = None

                for msg in messages:
                    from_data = msg.get("from", {})
                    from_id = from_data.get("id")
                    from_username = from_data.get("username", "unknown")
                    msg_text = msg.get("message", "")

                    conv_analysis["messages_raw"].append(
                        {
                            "id": msg.get("id"),
                            "from_id": from_id,
                            "from_username": from_username,
                            "is_creator": from_id in creator_ids if from_id else "no_from_id",
                            "has_text": bool(msg_text),
                            "text_preview": msg_text[:50] if msg_text else "(empty)",
                        }
                    )

                    # Lógica de sync_worker para encontrar follower
                    if from_id and from_id not in creator_ids and not follower_id:
                        follower_id = from_id
                        follower_username = from_username

                conv_analysis["follower_detection"] = {
                    "found": bool(follower_id),
                    "follower_id": follower_id,
                    "follower_username": follower_username,
                    "reason": (
                        "Found non-creator sender"
                        if follower_id
                        else "All senders are in creator_ids or no from.id"
                    ),
                }

                # Simular qué mensajes se guardarían
                for msg in messages:
                    msg_id = msg.get("id")
                    msg_text = msg.get("message", "")
                    from_id = msg.get("from", {}).get("id")

                    would_save = bool(msg_text) and bool(msg_id)
                    role = "assistant" if from_id in creator_ids else "user"

                    conv_analysis["messages_would_save"].append(
                        {
                            "id": msg_id,
                            "would_save": would_save,
                            "skip_reason": (
                                None if would_save else ("no_text" if not msg_text else "no_id")
                            ),
                            "role": role,
                        }
                    )

                results["conversations_analysis"].append(conv_analysis)

        return results

    except Exception as e:
        import traceback

        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/debug-orphaned-messages/{creator_id}")
async def debug_orphaned_messages(creator_id: str, admin: str = Depends(require_admin)):
    """
    Diagnóstico: Buscar mensajes huérfanos o duplicados que impiden el sync.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator '{creator_id}' not found"}

            # 1. Contar mensajes totales en la BD
            total_messages = session.query(Message).count()

            # 2. Leads actuales del creator
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [str(l.id) for l in leads]
            lead_count = len(leads)

            # 3. Mensajes vinculados a leads de este creator
            if lead_ids:
                creator_messages = (
                    session.query(Message)
                    .filter(Message.lead_id.in_([l.id for l in leads]))
                    .count()
                )
            else:
                creator_messages = 0

            # 4. Mensajes con platform_message_id de Instagram (posibles duplicados)
            ig_messages = (
                session.query(Message)
                .filter(
                    Message.platform_message_id.like(
                        "aWdf%"
                    )  # Instagram message IDs start with aWdf
                )
                .all()
            )

            # Analizar a qué leads pertenecen
            orphaned = []
            for msg in ig_messages[:20]:  # Limitar para no sobrecargar
                lead = session.query(Lead).filter_by(id=msg.lead_id).first()
                orphaned.append(
                    {
                        "msg_id": str(msg.id)[:8],
                        "platform_msg_id": msg.platform_message_id[:30] + "...",
                        "lead_id": str(msg.lead_id)[:8] if msg.lead_id else None,
                        "lead_exists": lead is not None,
                        "lead_creator": lead.creator_id == creator.id if lead else False,
                        "content_preview": msg.content[:30] if msg.content else "(empty)",
                    }
                )

            return {
                "creator_id": creator_id,
                "creator_uuid": str(creator.id),
                "total_messages_in_db": total_messages,
                "leads_for_creator": lead_count,
                "messages_for_creator": creator_messages,
                "instagram_messages_sample": orphaned,
                "diagnosis": (
                    "Messages exist but not linked to current creator's leads"
                    if len(ig_messages) > 0 and creator_messages == 0
                    else "OK" if creator_messages > 0 else "No messages found"
                ),
            }

        finally:
            session.close()

    except Exception as e:
        import traceback

        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/full-diagnostic/{creator_id}")
async def full_diagnostic(creator_id: str, username: str = None, search: str = None, admin: str = Depends(require_admin)):
    """
    Run comprehensive diagnostic queries for debugging.

    Args:
        creator_id: Creator name
        username: Exact username to get messages for
        search: Search term to find leads by username or full_name (partial match)
    """
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        from api.models import Creator

        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        creator_uuid = str(creator.id)
        results = {}

        # Creator info (including bot_active status)
        results["creator_info"] = {
            "id": str(creator.id)[:8],
            "name": creator.name,
            "bot_active": creator.bot_active,
            "instagram_page_id": creator.instagram_page_id,
            "instagram_user_id": creator.instagram_user_id,
            "has_instagram_token": bool(creator.instagram_token),
        }

        # 0. Search for leads by name (if search parameter provided)
        if search:
            result = session.execute(
                text(
                    """
                    SELECT l.username, l.platform_user_id, l.full_name, l.status,
                           l.last_contact_at::text, l.updated_at::text,
                           (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
                    FROM leads l
                    WHERE l.creator_id = :cid
                    AND (l.username ILIKE :search OR l.full_name ILIKE :search)
                    ORDER BY l.last_contact_at DESC NULLS LAST
                """
                ),
                {"cid": creator_uuid, "search": f"%{search}%"},
            )
            rows = result.fetchall()
            results["search_results"] = [
                {
                    "username": r[0],
                    "platform_user_id": r[1],
                    "full_name": r[2],
                    "status": r[3],
                    "last_contact_at": r[4][:19] if r[4] else None,
                    "updated_at": r[5][:19] if r[5] else None,
                    "msg_count": r[6],
                }
                for r in rows
            ]

        # 1. Media/Metadatos for specific user
        if username:
            result = session.execute(
                text(
                    """
                    SELECT m.id::text, LEFT(m.content, 80) as content,
                           m.msg_metadata, m.role, m.created_at::text
                    FROM messages m
                    JOIN leads l ON m.lead_id = l.id
                    WHERE l.username = :username AND l.creator_id = :cid
                    ORDER BY m.created_at DESC LIMIT 10
                """
                ),
                {"username": username, "cid": creator_uuid},
            )
            rows = result.fetchall()
            results["messages_for_user"] = [
                {
                    "id": r[0][:8] + "...",
                    "content": r[1],
                    "metadata": r[2],
                    "role": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]

        # 2. Leads with Sergio in name
        result = session.execute(
            text(
                """
                SELECT l.username, l.platform_user_id, l.full_name,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count,
                       l.id::text
                FROM leads l
                WHERE l.creator_id = :cid
                AND (l.username ILIKE '%sergio%' OR l.full_name ILIKE '%sergio%')
            """
            ),
            {"cid": creator_uuid},
        )
        rows = result.fetchall()
        results["sergio_leads"] = [
            {
                "username": r[0],
                "platform_user_id": r[1],
                "full_name": r[2],
                "msg_count": r[3],
                "id": r[4][:8],
            }
            for r in rows
        ]

        # 3. Leads without profile (username NULL or ig_%)
        result = session.execute(
            text(
                """
                SELECT l.platform_user_id, l.username, l.full_name,
                       CASE WHEN l.profile_pic_url IS NOT NULL THEN true ELSE false END as has_pic,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
                FROM leads l
                WHERE l.creator_id = :cid
                AND (l.username IS NULL OR l.username LIKE 'ig_%' OR l.username = '')
                LIMIT 20
            """
            ),
            {"cid": creator_uuid},
        )
        rows = result.fetchall()
        results["leads_without_profile"] = [
            {
                "platform_user_id": r[0],
                "username": r[1],
                "full_name": r[2],
                "has_pic": r[3],
                "msg_count": r[4],
            }
            for r in rows
        ]

        # 4. Order/sorting - top 10 by last_contact_at
        result = session.execute(
            text(
                """
                SELECT l.username, l.updated_at::text, l.last_contact_at::text,
                       l.first_contact_at::text,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
                FROM leads l
                WHERE l.creator_id = :cid
                ORDER BY l.last_contact_at DESC NULLS LAST
                LIMIT 10
            """
            ),
            {"cid": creator_uuid},
        )
        rows = result.fetchall()
        results["top_10_by_last_contact"] = [
            {
                "username": r[0],
                "updated_at": r[1][:19] if r[1] else None,
                "last_contact_at": r[2][:19] if r[2] else None,
                "first_contact_at": r[3][:19] if r[3] else None,
                "msg_count": r[4],
            }
            for r in rows
        ]

        # 5. Search for Sebastien/Roger
        result = session.execute(
            text(
                """
                SELECT l.username, l.platform_user_id, l.full_name, l.status,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count,
                       l.last_contact_at::text
                FROM leads l
                WHERE l.username ILIKE '%bastien%' OR l.username ILIKE '%roger%'
                   OR l.full_name ILIKE '%bastien%' OR l.full_name ILIKE '%roger%'
                   OR l.username ILIKE '%sebastien%'
            """
            ),
        )
        rows = result.fetchall()
        results["sebastien_roger_search"] = [
            {
                "username": r[0],
                "platform_user_id": r[1],
                "full_name": r[2],
                "status": r[3],
                "msg_count": r[4],
                "last_contact": r[5][:19] if r[5] else None,
            }
            for r in rows
        ]

        # Summary stats
        total_leads = session.execute(
            text("SELECT COUNT(*) FROM leads WHERE creator_id = :cid"),
            {"cid": creator_uuid},
        ).scalar()

        leads_with_messages = session.execute(
            text(
                """
                SELECT COUNT(*) FROM leads l
                WHERE l.creator_id = :cid
                AND EXISTS (SELECT 1 FROM messages m WHERE m.lead_id = l.id)
            """
            ),
            {"cid": creator_uuid},
        ).scalar()

        # 6. Check constraints on leads table
        result = session.execute(
            text(
                """
                SELECT conname, contype, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'leads'::regclass
            """
            )
        )
        rows = result.fetchall()
        results["table_constraints"] = [
            {"name": r[0], "type": r[1], "definition": r[2]} for r in rows
        ]

        # 7. Find duplicates by platform_user_id
        result = session.execute(
            text(
                """
                SELECT platform_user_id, COUNT(*) as cnt,
                       array_agg(username) as usernames,
                       array_agg(id::text) as ids
                FROM leads
                WHERE creator_id = :cid
                GROUP BY platform_user_id
                HAVING COUNT(*) > 1
            """
            ),
            {"cid": creator_uuid},
        )
        rows = result.fetchall()
        results["duplicates_by_platform_id"] = [
            {"platform_user_id": r[0], "count": r[1], "usernames": r[2], "ids": r[3]} for r in rows
        ]

        # 8. Leads updated in last 30 minutes (leads table has updated_at, not created_at)
        result = session.execute(
            text(
                """
                SELECT l.username, l.platform_user_id, l.updated_at::text,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
                FROM leads l
                WHERE l.creator_id = :cid
                AND l.updated_at > NOW() - INTERVAL '30 minutes'
                ORDER BY l.updated_at DESC
            """
            ),
            {"cid": creator_uuid},
        )
        rows = result.fetchall()
        results["leads_updated_last_30min"] = [
            {
                "username": r[0],
                "platform_user_id": r[1],
                "updated_at": r[2][:19] if r[2] else None,
                "msg_count": r[3],
            }
            for r in rows
        ]

        # 9. Leads with 0 messages
        result = session.execute(
            text(
                """
                SELECT l.username, l.platform_user_id, l.updated_at::text
                FROM leads l
                WHERE l.creator_id = :cid
                AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.lead_id = l.id)
                ORDER BY l.updated_at DESC
                LIMIT 10
            """
            ),
            {"cid": creator_uuid},
        )
        rows = result.fetchall()
        results["leads_with_zero_messages"] = [
            {"username": r[0], "platform_user_id": r[1], "updated_at": r[2][:19] if r[2] else None}
            for r in rows
        ]

        results["summary"] = {
            "total_leads": total_leads,
            "leads_with_messages": leads_with_messages,
            "leads_without_profile_count": len(results["leads_without_profile"]),
            "duplicates_count": len(results["duplicates_by_platform_id"]),
            "zero_message_leads_count": len(results["leads_with_zero_messages"]),
        }

        return {"status": "ok", "creator_id": creator_id, "results": results}

    except Exception as e:
        logger.error(f"Error in diagnostic: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        session.close()
