"""Error response helpers to prevent information leakage."""

import logging

logger = logging.getLogger(__name__)


def safe_error_detail(error: Exception, context: str = "") -> str:
    """Return a safe error message for HTTP responses.

    Logs the full error internally but returns a generic message to clients.
    """
    logger.error("Error in %s: %s", context or "request", error, exc_info=True)
    return f"An error occurred{f' during {context}' if context else ''}. Please try again."
