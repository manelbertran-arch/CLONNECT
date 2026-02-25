"""
Standard API response helpers for consistent output.

Usage:
    from api.utils.responses import ok, error_response

    return ok(data=lead_data)
    return ok(data=leads, count=len(leads))
    return ok(message="Lead deleted")

Migration plan: Apply to all routers incrementally.
Priority: leads → messages → products → knowledge → rest
Each router should be migrated in a separate commit.
"""
from typing import Any, Optional


def ok(data: Any = None, count: int = None, message: str = None) -> dict:
    """Standard success response."""
    resp = {"status": "ok"}
    if data is not None:
        resp["data"] = data
    if count is not None:
        resp["count"] = count
    if message is not None:
        resp["message"] = message
    return resp


def error_response(message: str) -> dict:
    """Standard error response (for non-exception returns, not HTTPException)."""
    return {"status": "error", "error": message}
