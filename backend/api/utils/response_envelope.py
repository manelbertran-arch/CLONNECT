"""
Standard API response envelope utilities.

Provides ok() and err() helpers for consistent API response formatting.
"""
from typing import Any, Optional


def ok(data: Any = None, message: str = "success") -> dict:
    """Return a success response envelope."""
    response = {"success": True, "message": message}
    if data is not None:
        response["data"] = data
    return response


def err(message: str = "error", code: str = None, status_code: int = 400) -> dict:
    """Return an error response envelope."""
    response = {"success": False, "error": message}
    if code:
        response["code"] = code
    return response
