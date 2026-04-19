"""
ARC5 Phase 3 — Request context middleware for automatic metric label injection.

Provides:
  - ContextVars for creator_id, lead_id, request_id
  - set_context() / get_context() / clear_context() helpers
  - CreatorContextMiddleware: FastAPI middleware that extracts creator_id and
    lead_id from the request and sets them in ContextVars for the duration of
    each request, so emit_metric() can auto-inject them as labels.

Design: docs/sprint5_planning/ARC5_observability.md §2.3.2
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ContextVars — one per meaningful dimension
# ─────────────────────────────────────────────────────────────────────────────

_current_creator_id: ContextVar[Optional[str]] = ContextVar("creator_id", default=None)
_current_lead_id: ContextVar[Optional[str]] = ContextVar("lead_id", default=None)
_current_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────

def set_context(
    creator_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """Set current request context. Call at the start of a request or DM turn."""
    _current_creator_id.set(creator_id)
    _current_lead_id.set(lead_id)
    _current_request_id.set(request_id or str(uuid.uuid4()))


def get_context() -> dict:
    """Return current context dict. Safe to call anywhere (returns Nones if unset)."""
    return {
        "creator_id": _current_creator_id.get(),
        "lead_id": _current_lead_id.get(),
        "request_id": _current_request_id.get(),
    }


def clear_context() -> None:
    """Reset all ContextVars to None. Call in finally blocks after request processing."""
    _current_creator_id.set(None)
    _current_lead_id.set(None)
    _current_request_id.set(None)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI / ASGI middleware
# ─────────────────────────────────────────────────────────────────────────────

class CreatorContextMiddleware:
    """ASGI middleware that extracts creator_id and lead_id from each request.

    Extraction order for creator_id:
      1. Header X-Creator-ID
      2. Path segment matching /creators/{creator_id}/ pattern
      3. None (emit_metric will skip auto-injection for that label)

    Extraction order for lead_id:
      1. Header X-Lead-ID
      2. None

    A unique request_id (UUID4) is generated if not present in X-Request-ID.
    Context is always cleared in the finally block — no leakage between requests.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        creator_id: Optional[str] = None
        lead_id: Optional[str] = None
        request_id: Optional[str] = None

        try:
            # Extract from headers
            headers: dict = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            creator_id = headers.get("x-creator-id")
            lead_id = headers.get("x-lead-id")
            request_id = headers.get("x-request-id")

            # Fallback: extract creator_id from URL path
            if not creator_id:
                path: str = scope.get("path", "")
                creator_id = _extract_creator_from_path(path)

            set_context(
                creator_id=creator_id,
                lead_id=lead_id,
                request_id=request_id,
            )

            await self.app(scope, receive, send)
        except Exception:
            raise
        finally:
            clear_context()


def _extract_creator_from_path(path: str) -> Optional[str]:
    """Extract creator_id from paths like /api/creators/{creator_id}/... or /dm/{creator_id}/..."""
    parts = [p for p in path.split("/") if p]
    for i, part in enumerate(parts):
        if part in ("creators", "dm", "clone", "webhook") and i + 1 < len(parts):
            candidate = parts[i + 1]
            # Reject UUIDs and common non-creator segments
            if candidate and not _looks_like_uuid(candidate) and candidate not in (
                "health", "metrics", "docs", "openapi.json", "redoc"
            ):
                return candidate
    return None


def _looks_like_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False
