"""Security event alerting — QW3.

Dispatched fire-and-forget from `core/dm/phases/detection.py` on:
  * prompt_injection_attempt match (always WARNING)
  * sensitive_content detection (WARNING below escalation, CRITICAL at/above)

Design:
  * Fail-silent: any exception (DB down, cache glitch, hash failure) is
    logged at debug and swallowed. Alerting NEVER crashes the pipeline.
  * Rate-limited: in-process `TTLCache` keyed by
    `(creator_id, sender_id, event_type)` with a 60s window and a
    10k-entry LRU cap. Every 100th suppressed event is still recorded
    as an INFO `rate_limit_summary` row so bursts stay visible.
  * GDPR: raw content NEVER persists. We store only SHA256 hex digest
    (64 chars) and the original character length.
  * Async DB write: `asyncio.to_thread(_sync_write)` using
    `get_db_session()` (same pattern as `core/dm/phases/context.py:163`).

Public API:
  alert_security_event(creator_id, sender_id, event_type, content,
                       severity, metadata=None) -> awaitable[None]
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from typing import Any, Dict, Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"
_VALID_SEVERITIES = {SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL}

EVENT_PROMPT_INJECTION = "prompt_injection"
EVENT_SENSITIVE_CONTENT = "sensitive_content"
EVENT_RATE_LIMIT_SUMMARY = "rate_limit_summary"

# Per-(creator, sender, event_type) rate window.
# Cache TTL of 300s defines the effective de-duplication window: the first
# event emits, subsequent events in the same key within 300s are suppressed.
# 10_000 LRU entries give headroom for many concurrent senders.
_RATE_LIMIT_CACHE: TTLCache = TTLCache(maxsize=10_000, ttl=300)

# Mutex for the compound read-modify-write inside _should_emit. _sync_write
# runs inside asyncio.to_thread, so concurrent tasks really do race the cache.
_RATE_LIMIT_LOCK = threading.Lock()

# Emit a summary row every N suppressed events for the same key.
_SUMMARY_EVERY = 100

# Orphan-task prevention: keep references alive until done.
_pending_tasks: set[asyncio.Task] = set()

# Defensive: creator_id column is String(100). Truncate before persist to
# avoid DataError if a malformed agent ever supplies a longer slug.
_CREATOR_ID_MAX = 100
_SENDER_ID_MAX = 100


def _hash_content(content: Optional[str]) -> tuple[Optional[str], int]:
    """Return (sha256_hex, char_length) or (None, 0) if content is empty."""
    if not content:
        return None, 0
    try:
        return hashlib.sha256(content.encode("utf-8")).hexdigest(), len(content)
    except Exception:  # e.g. weird encoding edge case
        logger.debug("security alerting: hash failed", exc_info=True)
        return None, len(content)


def _should_emit(key: tuple) -> tuple[bool, int]:
    """Rate-limit check. Returns (emit_now, suppressed_count_if_summary).

    * If key is unseen, mark and emit (True, 0).
    * If key is known, increment suppressed counter.
      - emit a summary row on every _SUMMARY_EVERY-th suppressed event.
      - otherwise suppress.

    Atomic under concurrent fire-and-forget dispatches: the compound
    read-modify-write is guarded by _RATE_LIMIT_LOCK.
    """
    try:
        with _RATE_LIMIT_LOCK:
            state = _RATE_LIMIT_CACHE.get(key)
            if state is None:
                _RATE_LIMIT_CACHE[key] = {"count": 0}
                return True, 0
            state["count"] += 1
            count = state["count"]
        # Every Nth suppressed event becomes an INFO summary
        if count % _SUMMARY_EVERY == 0:
            return True, count
        return False, count
    except Exception:
        logger.debug("security alerting: rate-limit lookup failed", exc_info=True)
        # On cache failure, default to emit — an extra row beats a missed alert.
        return True, 0


def _sync_write(row: Dict[str, Any]) -> None:
    """Synchronous DB insert for SecurityEvent. Safe to call inside to_thread."""
    # Import here to avoid loading SQLAlchemy metadata at module import time.
    from api.database import get_db_session
    from api.models.security import SecurityEvent

    with get_db_session() as session:
        event = SecurityEvent(**row)
        session.add(event)
        session.commit()


async def alert_security_event(
    creator_id: str,
    sender_id: Optional[str],
    event_type: str,
    content: Optional[str],
    severity: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a security event. Fail-silent: exceptions are swallowed.

    Args:
        creator_id: slug (e.g. "iris_bertran"), never UUID.
        sender_id:  Instagram platform_user_id (raw numeric, no "ig_" prefix)
                    or None for creator-wide events.
        event_type: one of EVENT_PROMPT_INJECTION / EVENT_SENSITIVE_CONTENT /
                    EVENT_RATE_LIMIT_SUMMARY.
        content:    the triggering user message (hashed + discarded).
        severity:   SEVERITY_INFO | SEVERITY_WARNING | SEVERITY_CRITICAL.
        metadata:   optional JSONB-safe dict (pattern, category, …).

    Returns: None. Always. Even on failure.
    """
    try:
        if severity not in _VALID_SEVERITIES:
            logger.debug("security alerting: invalid severity %r — coercing to WARNING", severity)
            severity = SEVERITY_WARNING

        # Defensive truncation: DB columns are String(100).
        creator_id_safe = (creator_id or "")[:_CREATOR_ID_MAX]
        sender_id_safe = sender_id[:_SENDER_ID_MAX] if sender_id else None

        rate_key = (creator_id_safe, sender_id_safe, event_type)
        emit, suppressed_count = _should_emit(rate_key)
        if not emit:
            return

        content_hash, message_length = _hash_content(content)
        row_metadata = dict(metadata or {})

        # If this emission is a summary row, relabel type + severity + annotate count.
        if suppressed_count and suppressed_count % _SUMMARY_EVERY == 0:
            row_metadata["suppressed_count"] = suppressed_count
            row_metadata["original_event_type"] = event_type
            event_type = EVENT_RATE_LIMIT_SUMMARY
            severity = SEVERITY_INFO

        row = {
            "creator_id": creator_id_safe,
            "sender_id": sender_id_safe,
            "event_type": event_type,
            "severity": severity,
            "content_hash": content_hash,
            "message_length": message_length,
            "event_metadata": row_metadata,
        }

        try:
            await asyncio.to_thread(_sync_write, row)
        except Exception:
            logger.debug("security alerting: DB write failed", exc_info=True)

    except Exception:
        # Belt-and-braces: never propagate an exception out of this dispatcher.
        logger.debug("security alerting: unexpected failure", exc_info=True)


def dispatch_fire_and_forget(
    creator_id: str,
    sender_id: Optional[str],
    event_type: str,
    content: Optional[str],
    severity: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Create a background task for alert_security_event.

    Uses a module-level `_pending_tasks` set + `add_done_callback` so that
    the event loop keeps a strong reference until the task finishes
    (prevents "Task was destroyed but it is pending" warnings).

    Must be called from inside a running event loop. If no loop is running
    we swallow the error rather than raising — alerting is best-effort.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("security alerting: no running loop, skipping dispatch")
        return

    try:
        task = loop.create_task(
            alert_security_event(
                creator_id=creator_id,
                sender_id=sender_id,
                event_type=event_type,
                content=content,
                severity=severity,
                metadata=metadata,
            )
        )
        _pending_tasks.add(task)
        task.add_done_callback(_pending_tasks.discard)
    except Exception:
        logger.debug("security alerting: dispatch failed", exc_info=True)


# ---------------------------------------------------------------------------
# Test helpers — intentionally module-private, used by unit tests only.
# ---------------------------------------------------------------------------

def _reset_rate_limit_cache_for_tests() -> None:
    """Clear the in-process rate-limit cache. Test-only."""
    _RATE_LIMIT_CACHE.clear()
