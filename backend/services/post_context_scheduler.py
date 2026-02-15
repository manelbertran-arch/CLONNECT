"""PostContext Auto-refresh Scheduler.

Handles automatic refresh of expired post contexts.
Can be triggered by cron job or background task.

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import logging
from typing import Any, Dict

from services.post_context_repository import get_expired_contexts
from services.post_context_service import PostContextService

logger = logging.getLogger(__name__)


async def refresh_expired_contexts() -> Dict[str, Any]:
    """Refresh all expired post contexts.

    Fetches all contexts past their expiration time and
    triggers a refresh for each one.

    Returns:
        Dict with refresh statistics:
        - refreshed: Number successfully refreshed
        - errors: Number of errors encountered
    """
    result = {
        "refreshed": 0,
        "errors": 0,
    }

    try:
        expired = get_expired_contexts()

        if not expired:
            logger.info("No expired contexts to refresh")
            return result

        logger.info(f"Found {len(expired)} expired contexts to refresh")

        service = PostContextService()

        for ctx in expired:
            creator_id = ctx.get("creator_id")
            if not creator_id:
                logger.warning("Expired context missing creator_id, skipping")
                result["errors"] += 1
                continue

            try:
                await service.force_refresh(creator_id)
                result["refreshed"] += 1
                logger.debug(f"Refreshed context for {creator_id}")

            except Exception as e:
                logger.error(f"Error refreshing context for {creator_id}: {e}")
                result["errors"] += 1

    except Exception as e:
        logger.error(f"Error in refresh_expired_contexts: {e}")

    logger.info(
        f"Refresh complete: {result['refreshed']} refreshed, "
        f"{result['errors']} errors"
    )

    return result


async def schedule_refresh_job() -> None:
    """Entry point for scheduled job.

    Can be called by APScheduler, Celery, or cron.
    """
    logger.info("Starting scheduled post context refresh")
    result = await refresh_expired_contexts()
    logger.info(f"Scheduled refresh completed: {result}")
