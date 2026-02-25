"""
Copilot Service — backward-compatible re-export shim.

The implementation has been decomposed into:
  core/copilot/models.py      — PendingResponse, constants, is_non_text_message
  core/copilot/service.py     — CopilotService class + factory
  core/copilot/lifecycle.py   — create_pending_response, get_pending_responses
  core/copilot/actions.py     — approve, discard, auto_discard
  core/copilot/messaging.py   — platform sends + debounce regeneration

All original imports continue to work.
"""

# Re-export everything that was previously importable from this module
from core.copilot.models import (  # noqa: F401
    DEBOUNCE_SECONDS,
    PendingResponse,
    is_non_text_message,
)
from core.copilot.service import (  # noqa: F401
    CopilotService,
    get_copilot_service,
)

__all__ = [
    "DEBOUNCE_SECONDS",
    "PendingResponse",
    "is_non_text_message",
    "CopilotService",
    "get_copilot_service",
]
