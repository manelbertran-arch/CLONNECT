"""
SSE (Server-Sent Events) router for real-time frontend notifications.

When Instagram webhooks deliver new messages, the backend notifies
connected frontends via SSE so conversations update instantly.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

# Registry of active SSE connections per creator
_active_connections: Dict[str, list[asyncio.Queue]] = {}

# Max queued events before a connection is considered hung (client not consuming)
_SSE_QUEUE_MAXSIZE = 100
# Max SSE connections per creator (prevents runaway frontend reconnects)
_SSE_MAX_CONNECTIONS_PER_CREATOR = 10


async def notify_creator(creator_id: str, event_type: str, data: Dict[str, Any]) -> int:
    """
    Send an SSE event to all connected clients for a creator.

    Args:
        creator_id: The creator to notify
        event_type: Event type (new_message, new_conversation, message_approved)
        data: Event payload

    Returns:
        Number of clients notified
    """
    queues = _active_connections.get(creator_id, [])
    if not queues:
        return 0

    payload = json.dumps({"type": event_type, "data": data})
    notified = 0
    for queue in queues:
        try:
            queue.put_nowait(payload)
            notified += 1
        except asyncio.QueueFull:
            logger.warning("[SSE] Queue full for creator %s, dropping event", creator_id)

    if notified:
        logger.info("[SSE] Notified %d client(s) for %s: %s", notified, creator_id, event_type)

    return notified


def _verify_token_for_creator(token: str, creator_id: str) -> bool:
    """Verify JWT token and check access to creator_id."""
    try:
        from api.auth import decode_token, get_user_creators, is_admin_key, validate_api_key
        from api.database import SessionLocal
        from api.models import User

        # Try as JWT
        payload = decode_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                session = SessionLocal()
                try:
                    user = (
                        session.query(User)
                        .filter(User.id == user_id, User.is_active == True)
                        .first()
                    )
                    if user:
                        creators = get_user_creators(session, str(user.id))
                        creator_names = [c["name"] for c in creators]
                        return creator_id in creator_names
                finally:
                    session.close()

        # Try as API key
        if is_admin_key(token):
            return True
        key_creator_id = validate_api_key(token)
        if key_creator_id and key_creator_id == creator_id:
            return True

    except Exception as e:
        logger.debug("[SSE] Token verification failed: %s", e)

    return False


@router.get("/{creator_id}")
async def event_stream(
    creator_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    """SSE endpoint for real-time updates. Frontend connects via EventSource.

    Since EventSource doesn't support custom headers, auth token is passed
    as a query parameter.
    """
    # Verify auth
    if not token or not _verify_token_for_creator(token, creator_id):
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    queue: asyncio.Queue = asyncio.Queue(maxsize=_SSE_QUEUE_MAXSIZE)

    if creator_id not in _active_connections:
        _active_connections[creator_id] = []

    # Evict oldest hung connections if at limit (full queue = client not consuming)
    conns = _active_connections[creator_id]
    if len(conns) >= _SSE_MAX_CONNECTIONS_PER_CREATOR:
        # Find and remove the oldest full queue (hung client)
        full_queues = [q for q in conns if q.full()]
        if full_queues:
            conns.remove(full_queues[0])
            logger.warning("[SSE] Evicted hung connection for %s (queue full)", creator_id)
        else:
            # All queues active but at limit — evict oldest (index 0)
            conns.pop(0)
            logger.warning("[SSE] Evicted oldest connection for %s (at max %d)", creator_id, _SSE_MAX_CONNECTIONS_PER_CREATOR)

    _active_connections[creator_id].append(queue)

    logger.info(
        "[SSE] Client connected for %s (total: %d)",
        creator_id,
        len(_active_connections[creator_id]),
    )

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping to prevent connection timeout
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            # Safe removal — guard against race condition where key was already deleted
            conns = _active_connections.get(creator_id)
            if conns is not None:
                try:
                    conns.remove(queue)
                except ValueError:
                    pass  # Already removed by eviction
                if not conns:
                    _active_connections.pop(creator_id, None)
            logger.info("[SSE] Client disconnected for %s", creator_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
