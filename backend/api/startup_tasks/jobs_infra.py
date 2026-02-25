"""
Infrastructure scheduled jobs — keep-alive, Evolution API health check,
pending expiry, token expiry, message retry.
"""

import logging
import os

logger = logging.getLogger(__name__)


# --- Keep-alive (every 60s) ---
async def keep_alive_job():
    import time

    from api.database import SessionLocal

    _t_start = time.time()

    if SessionLocal:
        try:
            from sqlalchemy import text

            session = SessionLocal()
            session.execute(text("SELECT 1"))
            session.close()
        except Exception as e:
            logger.warning(f"[KEEP-ALIVE] DB ping failed: {e}")

    _t_end = time.time()
    logger.debug(f"[KEEP-ALIVE] Ping OK in {_t_end - _t_start:.3f}s")


# --- Evolution API health check (every 5min) ---
# Track state changes per instance to avoid spamming alerts
_evolution_last_state = {}  # instance -> "ok" | "error"


async def evolution_health_check_job():
    enable = os.getenv("ENABLE_EVOLUTION_HEALTH_CHECK", "true").lower() == "true"
    if not enable:
        logger.debug("[EVOLUTION_HEALTH] Disabled via env var, skipping")
        return
    from api.routers.messaging_webhooks import (
        EVOLUTION_INSTANCE_MAP,
    )
    from services.evolution_api import (
        EVOLUTION_API_URL,
        get_instance_status,
    )

    if not EVOLUTION_API_URL:
        return

    for instance, creator_id in EVOLUTION_INSTANCE_MAP.items():
        try:
            status = await get_instance_status(instance)
            state = (
                status.get("instance", {}).get("state", "unknown")
            )

            if state == "open":
                if _evolution_last_state.get(instance) == "error":
                    logger.info(
                        f"[EVOLUTION_HEALTH] {instance} reconnected"
                    )
                _evolution_last_state[instance] = "ok"
            else:
                logger.warning(
                    f"[EVOLUTION_HEALTH] {instance} state={state}"
                )
                if _evolution_last_state.get(instance) != "error":
                    _evolution_last_state[instance] = "error"
                    try:
                        from core.alerts import get_alert_manager

                        mgr = get_alert_manager()
                        await mgr.critical(
                            title="Evolution API Disconnected",
                            message=(
                                f"Instance {instance} state={state}. "
                                f"WhatsApp messages may be lost."
                            ),
                            creator_id=creator_id,
                            metadata={
                                "instance": instance,
                                "state": state,
                            },
                        )
                    except Exception as alert_err:
                        logger.error(
                            f"[EVOLUTION_HEALTH] Alert failed: {alert_err}"
                        )

        except Exception as inst_err:
            err_str = str(inst_err)
            is_401 = "401" in err_str or "Unauthorized" in err_str
            logger.error(
                f"[EVOLUTION_HEALTH] {instance} check failed: {inst_err}"
            )
            if _evolution_last_state.get(instance) != "error":
                _evolution_last_state[instance] = "error"
                try:
                    from core.alerts import get_alert_manager

                    mgr = get_alert_manager()
                    await mgr.critical(
                        title=(
                            "Evolution API 401 Unauthorized"
                            if is_401
                            else "Evolution API Error"
                        ),
                        message=(
                            f"Instance {instance}: {err_str[:200]}. "
                            f"Check EVOLUTION_API_KEY."
                        ),
                        creator_id=creator_id,
                        metadata={
                            "instance": instance,
                            "error": err_str[:200],
                            "is_401": is_401,
                        },
                    )
                except Exception as alert_err:
                    logger.error(
                        f"[EVOLUTION_HEALTH] Alert failed: {alert_err}"
                    )


# --- Auto-expire stale pending_approval messages (every 1h) ---
async def pending_expiry_job():
    enable = os.getenv("ENABLE_PENDING_EXPIRY", "true").lower() == "true"
    if not enable:
        logger.debug("[A15] Pending expiry disabled via env var, skipping")
        return
    from api.database import SessionLocal as _SL16
    from sqlalchemy import text

    session = _SL16()
    try:
        result = session.execute(
            text(
                """
                UPDATE messages
                SET status = 'expired',
                    msg_metadata = COALESCE(msg_metadata, '{}'::jsonb)
                        || '{"expired_reason": "auto_24h"}'::jsonb
                WHERE status = 'pending_approval'
                AND created_at < NOW() - INTERVAL '24 hours'
                """
            )
        )
        count = result.rowcount
        session.commit()
        if count > 0:
            logger.info(
                f"[A15] Auto-expired {count} stale pending_approval messages (>24h)"
            )
    finally:
        session.close()


# --- Instagram token expiry warning (daily) ---
async def token_expiry_check_job():
    enable = os.getenv("ENABLE_TOKEN_EXPIRY_CHECK", "true").lower() == "true"
    if not enable:
        logger.debug("[B11] Token expiry check disabled via env var, skipping")
        return
    from datetime import datetime, timedelta, timezone

    from api.database import SessionLocal as _SL17
    from api.models import Creator

    session = _SL17()
    try:
        creators = (
            session.query(Creator)
            .filter(
                Creator.instagram_token.isnot(None),
                Creator.instagram_token_expires_at.isnot(None),
                Creator.bot_active.is_(True),
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for c in creators:
            expires = c.instagram_token_expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            days_left = (expires - now).days
            if days_left <= 0:
                from core.alerts import get_alert_manager

                mgr = get_alert_manager()
                await mgr.critical(
                    title=f"Token IG EXPIRADO: {c.name}",
                    message=f"El token de Instagram de {c.name} ha expirado. Bot detenido.",
                    source="token_expiry_check",
                )
            elif days_left <= 3:
                from core.alerts import get_alert_manager

                mgr = get_alert_manager()
                await mgr.critical(
                    title=f"URGENTE: Token IG de {c.name} expira en {days_left} dias",
                    message=f"El token de Instagram de {c.name} expira en {days_left} dias. Renovar ASAP.",
                    source="token_expiry_check",
                )
            elif days_left <= 14:
                from core.alerts import get_alert_manager

                mgr = get_alert_manager()
                await mgr.warning(
                    title=f"Token IG de {c.name} expira en {days_left} dias",
                    message=f"Token de Instagram de {c.name} expira el {expires.strftime('%Y-%m-%d')}. Planificar renovacion.",
                    source="token_expiry_check",
                )
                logger.info(
                    f"[B11] Token expiry warning: {c.name} expires in {days_left} days"
                )
    finally:
        session.close()


# --- Message retry worker (every 60s) ---
async def message_retry_job():
    from services.message_retry_service import process_retry_queue
    await process_retry_queue()


def register_infra_jobs(scheduler):
    """Register all infrastructure scheduled jobs with the task scheduler."""
    scheduler.register("keep_alive", keep_alive_job, interval_seconds=60, initial_delay_seconds=3)
    scheduler.register("evolution_health_check", evolution_health_check_job, interval_seconds=300, initial_delay_seconds=420)
    scheduler.register("pending_expiry", pending_expiry_job, interval_seconds=3600, initial_delay_seconds=450)
    scheduler.register("token_expiry_check", token_expiry_check_job, interval_seconds=86400, initial_delay_seconds=480)
    scheduler.register("message_retry", message_retry_job, interval_seconds=60, initial_delay_seconds=60)
