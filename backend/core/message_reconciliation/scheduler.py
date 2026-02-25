"""
Scheduler functions for message reconciliation.

Functions for running reconciliation on startup and periodically.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import core.message_reconciliation.core as _core_module
from core.message_reconciliation.core import (
    RECONCILIATION_LOOKBACK_HOURS,
    run_reconciliation_cycle,
)

logger = logging.getLogger("clonnect-reconciliation")


async def run_startup_reconciliation():
    """
    Run reconciliation on server startup.
    Recovers messages from the last 24 hours.
    """
    logger.info(
        f"[Reconciliation] Starting startup reconciliation (last {RECONCILIATION_LOOKBACK_HOURS}h)"
    )

    try:
        result = await run_reconciliation_cycle(lookback_hours=RECONCILIATION_LOOKBACK_HOURS)

        _core_module._last_reconciliation = datetime.now(timezone.utc).isoformat()
        _core_module._reconciliation_count += 1

        if result["total_inserted"] > 0:
            logger.info(
                f"[Reconciliation] Startup complete: recovered {result['total_inserted']} messages"
            )
        else:
            logger.info("[Reconciliation] Startup complete: no missing messages found")

        return result

    except Exception as e:
        logger.error(f"[Reconciliation] Startup reconciliation failed: {e}")
        return {"error": str(e)}


async def run_periodic_reconciliation():
    """
    Run periodic reconciliation (called by scheduler).
    Checks for messages from the last hour.
    """
    try:
        result = await run_reconciliation_cycle(lookback_hours=1)

        _core_module._last_reconciliation = datetime.now(timezone.utc).isoformat()
        _core_module._reconciliation_count += 1

        return result

    except Exception as e:
        logger.error(f"[Reconciliation] Periodic reconciliation failed: {e}")
        return {"error": str(e)}
