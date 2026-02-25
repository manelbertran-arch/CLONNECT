"""Copilot service sub-modules extracted from copilot_service.py."""
from core.copilot.models import DEBOUNCE_SECONDS, PendingResponse, is_non_text_message
from core.copilot.service import CopilotService, get_copilot_service

__all__ = [
    "DEBOUNCE_SECONDS",
    "PendingResponse",
    "is_non_text_message",
    "CopilotService",
    "get_copilot_service",
]
