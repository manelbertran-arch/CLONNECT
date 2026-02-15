"""Instagram DM history sync endpoints."""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# =============================================================================
# INSTAGRAM DM HISTORY SYNC
# =============================================================================


class InstagramDMSyncRequest(BaseModel):
    """Request for syncing Instagram DM history"""

    creator_id: str
    max_conversations: int = 50
    max_messages_per_conversation: int = 50
    analyze_insights: bool = True
    run_background: bool = False  # Run as background task


# In-memory status for background sync jobs
dm_sync_status: Dict[str, Dict] = {}


class ConversationInsight(BaseModel):
    """Insights from a conversation"""

    follower_id: str
    follower_username: str
    total_messages: int
    topics: List[str]
    purchase_intent_score: float
    common_questions: List[str]


class InstagramDMSyncResponse(BaseModel):
    """Response from Instagram DM sync"""

    success: bool
    creator_id: str
    conversations_fetched: int = 0
    messages_saved: int = 0
    leads_created: int = 0
    insights: Optional[List[ConversationInsight]] = None
    errors: List[str] = []


@router.post("/sync-instagram-dms", response_model=InstagramDMSyncResponse)
async def sync_instagram_dms(request: InstagramDMSyncRequest):
    """
    Sincroniza mensajes historicos de Instagram DM usando Graph API.

    Implementa:
    - Rate limiting con backoff exponencial
    - Throttling entre llamadas (max 20/min)
    - Procesamiento en batches
    - Retry automatico en rate limits
    """
    import asyncio
    from datetime import datetime, timezone

    import httpx
    from core.instagram_rate_limiter import (
        InstagramRateLimiter,
        InstagramRateLimitError,
        RateLimitConfig,
    )

    errors = []
    conversations_fetched = 0
    messages_saved = 0
    leads_created = 0
    insights = []
    rate_limit_hits = 0

    # Configurar rate limiter
    config = RateLimitConfig(
        max_retries=5,
        base_delay=30.0,
        calls_per_minute=15,  # Conservador para evitar limits
        batch_size=5,
        batch_delay=10.0,
    )
    limiter = InstagramRateLimiter(config)

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            raise HTTPException(status_code=500, detail="Database not configured")

        session = SessionLocal()
        try:
            # Get creator and token
            creator = session.query(Creator).filter_by(name=request.creator_id).first()
            if not creator:
                raise HTTPException(
                    status_code=404, detail=f"Creator not found: {request.creator_id}"
                )

            if not creator.instagram_token:
                raise HTTPException(status_code=400, detail="Instagram token not configured")

            ig_user_id = creator.instagram_user_id or creator.instagram_page_id
            page_id = creator.instagram_page_id
            if not ig_user_id:
                raise HTTPException(status_code=400, detail="Instagram user ID not configured")

            access_token = creator.instagram_token

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

            logger.info(f"[DMSync] Starting sync for {request.creator_id} using {api_used} API")

            async with httpx.AsyncClient(timeout=60.0) as client:

                # Helper para hacer llamadas con rate limiting
                async def fetch_with_retry(url: str, params: dict, max_retries: int = 5) -> dict:
                    nonlocal rate_limit_hits

                    for attempt in range(max_retries):
                        await limiter.throttle()

                        response = await client.get(url, params=params)
                        data = response.json()

                        # Verificar rate limit
                        error = data.get("error", {})
                        if error.get("code") in [4, 17] or error.get("error_subcode") == 1349210:
                            rate_limit_hits += 1
                            if attempt == max_retries - 1:
                                raise InstagramRateLimitError(error.get("message", "Rate limit"))

                            delay = limiter.calculate_backoff(attempt)
                            logger.warning(
                                f"[DMSync] Rate limit hit, waiting {delay:.0f}s (attempt {attempt + 1})"
                            )
                            await asyncio.sleep(delay)
                            continue

                        if response.status_code != 200:
                            return {"error": data.get("error", {}), "data": []}

                        return data

                    return {"error": {"message": "Max retries exceeded"}, "data": []}

                # 1. Fetch conversations (1 llamada)
                conv_url = f"{api_base}/{conv_id_for_api}/conversations"
                conv_params = {
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": min(request.max_conversations, 50),
                }
                conv_data = await fetch_with_retry(conv_url, conv_params)

                if "error" in conv_data and conv_data["error"]:
                    error_msg = conv_data["error"].get("message", "Unknown error")
                    errors.append(f"Conversations API error: {error_msg}")
                    logger.error(f"[DMSync] Conversations error: {conv_data['error']}")
                    return InstagramDMSyncResponse(
                        success=False, creator_id=request.creator_id, errors=errors
                    )

                conversations = conv_data.get("data", [])
                conversations_fetched = len(conversations)
                logger.info(f"[DMSync] Found {conversations_fetched} conversations")

                # 2. Process conversations in batches
                batch_size = config.batch_size
                total_batches = (len(conversations) + batch_size - 1) // batch_size

                for batch_idx in range(total_batches):
                    batch_start = batch_idx * batch_size
                    batch_end = min(batch_start + batch_size, len(conversations))
                    batch = conversations[batch_start:batch_end]

                    logger.info(
                        f"[DMSync] Processing batch {batch_idx + 1}/{total_batches} ({len(batch)} conversations)"
                    )

                    for conv in batch:
                        conv_id = conv.get("id")
                        if not conv_id:
                            continue

                        try:
                            # Fetch messages for this conversation
                            msg_url = f"{api_base}/{conv_id}/messages"
                            msg_data = await fetch_with_retry(
                                msg_url,
                                {
                                    "fields": "id,message,from,to,created_time",
                                    "access_token": access_token,
                                    "limit": min(request.max_messages_per_conversation, 50),
                                },
                            )

                            if "error" in msg_data and msg_data["error"]:
                                logger.warning(
                                    f"[DMSync] Messages error for conv {conv_id}: {msg_data['error']}"
                                )
                                continue

                            messages = msg_data.get("data", [])
                            if not messages:
                                continue

                            # Find the follower
                            follower_id = None
                            follower_username = None

                            for msg in messages:
                                from_data = msg.get("from", {})
                                from_id = from_data.get("id")
                                from_username = from_data.get("username", "")

                                if from_id and from_id != ig_user_id:
                                    follower_id = from_id
                                    follower_username = from_username
                                    break

                            if not follower_id:
                                for msg in messages:
                                    to_data = msg.get("to", {}).get("data", [])
                                    for recipient in to_data:
                                        if recipient.get("id") != ig_user_id:
                                            follower_id = recipient.get("id")
                                            follower_username = recipient.get("username", "")
                                            break
                                    if follower_id:
                                        break

                            if not follower_id:
                                continue

                            # Create or get Lead - check both with and without ig_ prefix
                            lead = (
                                session.query(Lead)
                                .filter(
                                    Lead.creator_id == creator.id,
                                    Lead.platform == "instagram",
                                    Lead.platform_user_id.in_([follower_id, f"ig_{follower_id}"]),
                                )
                                .first()
                            )

                            if not lead:
                                lead = Lead(
                                    creator_id=creator.id,
                                    platform="instagram",
                                    platform_user_id=follower_id,
                                    username=follower_username,
                                    status="active",
                                )
                                session.add(lead)
                                session.commit()
                                leads_created += 1

                            # Save messages
                            conv_messages_saved = 0
                            conv_topics = []
                            conv_questions = []

                            for msg in messages:
                                msg_id = msg.get("id")
                                msg_text = msg.get("message", "")
                                msg_from = msg.get("from", {})
                                msg_time = msg.get("created_time")

                                if not msg_text:
                                    continue

                                existing = (
                                    session.query(Message)
                                    .filter_by(platform_message_id=msg_id)
                                    .first()
                                )

                                if existing:
                                    continue

                                is_from_creator = msg_from.get("id") == ig_user_id
                                role = "assistant" if is_from_creator else "user"

                                created_at = None
                                if msg_time:
                                    try:
                                        created_at = datetime.fromisoformat(
                                            msg_time.replace("+0000", "+00:00")
                                        )
                                    except ValueError as e:
                                        logger.debug("Ignored ValueError in created_at = datetime.fromisoformat(: %s", e)

                                new_msg = Message(
                                    lead_id=lead.id,
                                    role=role,
                                    content=msg_text,
                                    status="sent",
                                    platform_message_id=msg_id,
                                    approved_by="historical_sync",
                                )
                                if created_at:
                                    new_msg.created_at = created_at

                                session.add(new_msg)
                                conv_messages_saved += 1
                                messages_saved += 1

                                if role == "user":
                                    if "?" in msg_text:
                                        conv_questions.append(msg_text.strip())
                                    lower_text = msg_text.lower()
                                    if any(
                                        w in lower_text
                                        for w in ["precio", "cuesta", "vale", "pagar"]
                                    ):
                                        conv_topics.append("precio")
                                    if any(
                                        w in lower_text for w in ["info", "información", "detalles"]
                                    ):
                                        conv_topics.append("información")
                                    if any(
                                        w in lower_text for w in ["comprar", "quiero", "interesa"]
                                    ):
                                        conv_topics.append("intención_compra")

                            # Calculate intent score
                            intent_score = 0.0
                            if "intención_compra" in conv_topics:
                                intent_score += 0.4
                            if "precio" in conv_topics:
                                intent_score += 0.3
                            if "información" in conv_topics:
                                intent_score += 0.2
                            if conv_questions:
                                intent_score += 0.1
                            intent_score = min(intent_score, 1.0)

                            # Recalculate multi-factor score after messages are synced
                            try:
                                from services.lead_scoring import recalculate_lead_score
                                recalculate_lead_score(session, str(lead.id))
                            except Exception as se:
                                logger.warning(f"[DMSync] Scoring failed: {se}")
                                lead.purchase_intent = intent_score
                                lead.score = max(0, min(100, int(intent_score * 100)))
                                # Use Spanish status values (consistent with frontend)
                                if intent_score >= 0.6:
                                    lead.status = "caliente"
                                elif intent_score >= 0.35:
                                    lead.status = "interesado"
                                else:
                                    lead.status = "nuevo"

                            session.commit()

                            if conv_messages_saved > 0:
                                logger.info(
                                    f"[DMSync] Saved {conv_messages_saved} msgs for {follower_username}"
                                )

                                if request.analyze_insights:
                                    insights.append(
                                        ConversationInsight(
                                            follower_id=follower_id,
                                            follower_username=follower_username or "unknown",
                                            total_messages=len(messages),
                                            topics=list(set(conv_topics)),
                                            purchase_intent_score=intent_score,
                                            common_questions=conv_questions[:5],
                                        )
                                    )

                        except InstagramRateLimitError as e:
                            logger.error(
                                f"[DMSync] Rate limit exceeded for conv {conv_id}: {e.message}"
                            )
                            errors.append(f"Rate limit: {e.message}")
                            # Guardar progreso parcial
                            session.commit()
                            break
                        except Exception as e:
                            logger.warning(f"[DMSync] Error processing conv {conv_id}: {e}")
                            continue

                    # Pausa entre batches
                    if batch_idx < total_batches - 1:
                        logger.info(f"[DMSync] Batch complete, waiting {config.batch_delay}s")
                        await asyncio.sleep(config.batch_delay)

        finally:
            session.close()

        logger.info(
            f"[DMSync] Complete: {conversations_fetched} convs, {messages_saved} msgs, {leads_created} leads, {rate_limit_hits} rate limits"
        )

        return InstagramDMSyncResponse(
            success=True,
            creator_id=request.creator_id,
            conversations_fetched=conversations_fetched,
            messages_saved=messages_saved,
            leads_created=leads_created,
            insights=insights if insights else None,
            errors=errors if errors else [],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DMSync] Error: {e}")
        import traceback

        traceback.print_exc()
        errors.append(str(e))
        return InstagramDMSyncResponse(
            success=False,
            creator_id=request.creator_id,
            conversations_fetched=conversations_fetched,
            messages_saved=messages_saved,
            leads_created=leads_created,
            errors=errors,
        )


# =============================================================================
# BACKGROUND DM SYNC
# =============================================================================


async def _background_dm_sync(
    creator_id: str, max_conversations: int, max_messages_per_conversation: int, job_id: str
):
    """
    Background task for DM sync.
    Updates dm_sync_status with progress.
    """
    import asyncio
    from datetime import datetime, timezone

    import httpx
    from core.instagram_rate_limiter import (
        InstagramRateLimiter,
        InstagramRateLimitError,
        RateLimitConfig,
    )

    # Initialize status
    dm_sync_status[job_id] = {
        "status": "running",
        "creator_id": creator_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "conversations_fetched": 0,
        "messages_saved": 0,
        "leads_created": 0,
        "current_batch": 0,
        "total_batches": 0,
        "errors": [],
        "completed_at": None,
    }

    errors = []
    conversations_fetched = 0
    messages_saved = 0
    leads_created = 0

    config = RateLimitConfig(
        max_retries=5, base_delay=30.0, calls_per_minute=15, batch_size=5, batch_delay=10.0
    )
    limiter = InstagramRateLimiter(config)

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            dm_sync_status[job_id]["status"] = "failed"
            dm_sync_status[job_id]["errors"].append("Database not configured")
            return

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator or not creator.instagram_token:
                dm_sync_status[job_id]["status"] = "failed"
                dm_sync_status[job_id]["errors"].append("Creator or token not found")
                return

            ig_user_id = creator.instagram_user_id or creator.instagram_page_id
            page_id = creator.instagram_page_id
            access_token = creator.instagram_token

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

            logger.info(f"[BGSync] Starting background sync for {creator_id} using {api_used} API")

            async with httpx.AsyncClient(timeout=60.0) as client:

                async def fetch_with_retry(url: str, params: dict, max_retries: int = 5) -> dict:
                    for attempt in range(max_retries):
                        await limiter.throttle()
                        response = await client.get(url, params=params)
                        data = response.json()
                        error = data.get("error", {})
                        if error.get("code") in [4, 17] or error.get("error_subcode") == 1349210:
                            if attempt == max_retries - 1:
                                raise InstagramRateLimitError(error.get("message", "Rate limit"))
                            delay = limiter.calculate_backoff(attempt)
                            logger.warning(f"[BGSync] Rate limit, waiting {delay:.0f}s")
                            await asyncio.sleep(delay)
                            continue
                        if response.status_code != 200:
                            return {"error": data.get("error", {}), "data": []}
                        return data
                    return {"error": {"message": "Max retries"}, "data": []}

                # Fetch conversations
                conv_url = f"{api_base}/{conv_id_for_api}/conversations"
                conv_params = {
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": min(max_conversations, 50),
                }
                conv_data = await fetch_with_retry(conv_url, conv_params)

                if "error" in conv_data and conv_data["error"]:
                    dm_sync_status[job_id]["status"] = "failed"
                    dm_sync_status[job_id]["errors"].append(
                        f"API error: {conv_data['error'].get('message')}"
                    )
                    return

                conversations = conv_data.get("data", [])
                conversations_fetched = len(conversations)
                dm_sync_status[job_id]["conversations_fetched"] = conversations_fetched

                batch_size = config.batch_size
                total_batches = (len(conversations) + batch_size - 1) // batch_size
                dm_sync_status[job_id]["total_batches"] = total_batches

                for batch_idx in range(total_batches):
                    dm_sync_status[job_id]["current_batch"] = batch_idx + 1
                    batch_start = batch_idx * batch_size
                    batch_end = min(batch_start + batch_size, len(conversations))
                    batch = conversations[batch_start:batch_end]

                    logger.info(f"[BGSync] Batch {batch_idx + 1}/{total_batches}")

                    for conv in batch:
                        conv_id = conv.get("id")
                        if not conv_id:
                            continue

                        try:
                            msg_url = f"{api_base}/{conv_id}/messages"
                            msg_data = await fetch_with_retry(
                                msg_url,
                                {
                                    "fields": "id,message,from,to,created_time",
                                    "access_token": access_token,
                                    "limit": min(max_messages_per_conversation, 50),
                                },
                            )

                            if "error" in msg_data and msg_data["error"]:
                                continue

                            messages = msg_data.get("data", [])
                            if not messages:
                                continue

                            # Find follower
                            follower_id = None
                            follower_username = None
                            for msg in messages:
                                from_data = msg.get("from", {})
                                from_id = from_data.get("id")
                                if from_id and from_id != ig_user_id:
                                    follower_id = from_id
                                    follower_username = from_data.get("username", "")
                                    break
                            if not follower_id:
                                for msg in messages:
                                    to_data = msg.get("to", {}).get("data", [])
                                    for recipient in to_data:
                                        if recipient.get("id") != ig_user_id:
                                            follower_id = recipient.get("id")
                                            follower_username = recipient.get("username", "")
                                            break
                                    if follower_id:
                                        break
                            if not follower_id:
                                continue

                            # Get or create lead - check both with and without ig_ prefix
                            lead = (
                                session.query(Lead)
                                .filter(
                                    Lead.creator_id == creator.id,
                                    Lead.platform == "instagram",
                                    Lead.platform_user_id.in_([follower_id, f"ig_{follower_id}"]),
                                )
                                .first()
                            )

                            if not lead:
                                lead = Lead(
                                    creator_id=creator.id,
                                    platform="instagram",
                                    platform_user_id=follower_id,
                                    username=follower_username,
                                    status="active",
                                )
                                session.add(lead)
                                session.commit()
                                leads_created += 1
                                dm_sync_status[job_id]["leads_created"] = leads_created

                            # Save messages
                            for msg in messages:
                                msg_id = msg.get("id")
                                msg_content = msg.get("message", "")
                                from_data = msg.get("from", {})
                                from_id = from_data.get("id")
                                role = "user" if from_id == follower_id else "assistant"

                                existing = (
                                    session.query(Message)
                                    .filter_by(lead_id=lead.id, platform_message_id=msg_id)
                                    .first()
                                )

                                if not existing and msg_content:
                                    new_msg = Message(
                                        lead_id=lead.id,
                                        role=role,
                                        content=msg_content,
                                        platform_message_id=msg_id,
                                    )
                                    if msg.get("created_time"):
                                        try:
                                            new_msg.created_at = datetime.fromisoformat(
                                                msg["created_time"].replace("Z", "+00:00")
                                            )
                                        except ValueError as e:
                                            logger.debug("Ignored ValueError in new_msg.created_at = datetime.fromisoformat(: %s", e)
                                    session.add(new_msg)
                                    messages_saved += 1
                                    dm_sync_status[job_id]["messages_saved"] = messages_saved

                            session.commit()

                        except InstagramRateLimitError as e:
                            logger.error(f"[BGSync] Rate limit: {e.message}")
                            errors.append(f"Rate limit: {e.message}")
                            session.commit()
                            break
                        except Exception as e:
                            logger.warning(f"[BGSync] Error: {e}")
                            continue

                    # Pause between batches
                    if batch_idx < total_batches - 1:
                        await asyncio.sleep(config.batch_delay)

        finally:
            session.close()

        dm_sync_status[job_id]["status"] = "completed"
        dm_sync_status[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
        dm_sync_status[job_id]["errors"] = errors
        logger.info(f"[BGSync] Complete: {conversations_fetched} convs, {messages_saved} msgs")

    except Exception as e:
        logger.error(f"[BGSync] Error: {e}")
        dm_sync_status[job_id]["status"] = "failed"
        dm_sync_status[job_id]["errors"].append(str(e))
        dm_sync_status[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()


@router.post("/sync-instagram-dms-background")
async def sync_instagram_dms_background(
    request: InstagramDMSyncRequest, background_tasks: BackgroundTasks
):
    """
    Start a background DM sync job.
    Returns immediately with a job_id to check status.
    """
    import uuid
    from datetime import datetime, timezone

    job_id = f"dmsync_{request.creator_id}_{uuid.uuid4().hex[:8]}"

    background_tasks.add_task(
        _background_dm_sync,
        request.creator_id,
        request.max_conversations,
        request.max_messages_per_conversation,
        job_id,
    )

    return {
        "status": "started",
        "job_id": job_id,
        "creator_id": request.creator_id,
        "check_status_url": f"/onboarding/sync-instagram-dms-status/{job_id}",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/sync-instagram-dms-status/{job_id}")
async def get_dm_sync_status(job_id: str):
    """
    Check the status of a background DM sync job.
    """
    if job_id not in dm_sync_status:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return dm_sync_status[job_id]


@router.get("/sync-instagram-dms-jobs/{creator_id}")
async def list_dm_sync_jobs(creator_id: str):
    """
    List all DM sync jobs for a creator.
    """
    jobs = []
    for job_id, status in dm_sync_status.items():
        if status.get("creator_id") == creator_id:
            jobs.append({"job_id": job_id, **status})

    return {"creator_id": creator_id, "jobs": jobs}
