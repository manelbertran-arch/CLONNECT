"""
Autolearning Analyzer — RE-EXPORT SHIM.

Real-time rule extraction removed (System B is batch-only now).
This file kept for backward compatibility of imports.
"""

import logging

logger = logging.getLogger(__name__)

# Re-export utilities used elsewhere
from services.persona_compiler import (  # noqa: F401
    _parse_llm_response,
    sanitize_rule_text,
    detect_language,
)

_NON_TEXT_PREFIXES = ("[🎤 Audio]", "[🏷️ Sticker]", "[📷", "[🎥", "[📎")


def _is_non_text_response(text: str) -> bool:
    """Check if a response is audio, sticker, or media."""
    if not text:
        return True
    return any(text.startswith(prefix) for prefix in _NON_TEXT_PREFIXES)


async def analyze_creator_action(**kwargs):
    """No-op: real-time rule extraction removed. B is batch-only now."""
    logger.debug("[AUTOLEARN] analyze_creator_action is a no-op (batch-only mode)")
    return None


__all__ = [
    "analyze_creator_action",
    "_is_non_text_response",
]
