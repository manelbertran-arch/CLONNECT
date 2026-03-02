"""
Token Refresh Service - Auto-renueva tokens de Instagram antes de expirar

Tipos de tokens Meta:
- Short-lived: 1-2 horas, no se puede refrescar
- Long-lived: 60 días, se puede refrescar indefinidamente

Flujo:
1. Usuario autentica -> recibe short-lived token
2. exchange_for_long_lived_token() -> convierte a long-lived (60 días)
3. Cron diario -> check_and_refresh_if_needed() -> extiende 60 días más
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)

# Meta App credentials
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")


async def exchange_for_long_lived_token(short_lived_token: str) -> Optional[Dict[str, Any]]:
    """
    Convierte token short-lived (1-2h) a long-lived (60 días).

    Meta API: GET /access_token?grant_type=ig_exchange_token

    Args:
        short_lived_token: Token de corta duración obtenido del OAuth flow

    Returns:
        Dict con token, expires_in y expires_at, o None si falla
    """
    import aiohttp

    if not META_APP_SECRET:
        logger.error("META_APP_SECRET not configured")
        return None

    url = "https://graph.instagram.com/access_token"
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": META_APP_SECRET,
        "access_token": short_lived_token
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if "error" in data:
                    logger.error(f"Error exchanging token: {data['error']}")
                    return None

                expires_in = data.get("expires_in", 5184000)  # ~60 días default

                return {
                    "token": data["access_token"],
                    "expires_in": expires_in,
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                }
    except Exception as e:
        logger.error(f"Exception exchanging token: {e}")
        return None


async def refresh_long_lived_token(current_token: str) -> Optional[Dict[str, Any]]:
    """
    Refresca un token long-lived ANTES de que expire.

    IMPORTANTE: Solo funciona si el token tiene más de 24h de vida restante.
    No funciona con tokens ya expirados.

    Token types:
    - IGAAT...: Instagram Graph API token (use graph.instagram.com)
    - EAA...: Page Access Token (use graph.facebook.com, or skip - doesn't expire often)

    Args:
        current_token: Token long-lived actual (no expirado)

    Returns:
        Dict con nuevo token y fechas, o None si falla
    """
    import aiohttp

    # CRITICAL FIX: Page Access Tokens (EAA) should NOT be refreshed with Instagram API
    # The Instagram refresh endpoint converts them to Instagram tokens (IGAAT),
    # which breaks messaging functionality.
    if current_token.startswith("EAA"):
        logger.info("Token is a Page Access Token (EAA), using Facebook refresh endpoint")
        # Page tokens are long-lived and rarely need refresh
        # If they do, use Facebook endpoint
        url = "https://graph.facebook.com/v21.0/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "fb_exchange_token": current_token
        }

        if not META_APP_ID or not META_APP_SECRET:
            logger.warning("Cannot refresh Page token: META_APP_ID/SECRET not configured")
            # Return current token as still valid (Page tokens last a long time)
            return {
                "token": current_token,
                "expires_in": 5184000,
                "expires_at": datetime.now(timezone.utc) + timedelta(days=60)
            }
    else:
        # Instagram token (IGAAT) - use Instagram refresh endpoint
        url = "https://graph.instagram.com/refresh_access_token"
        params = {
            "grant_type": "ig_refresh_token",
            "access_token": current_token
        }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if "error" in data:
                    logger.error(f"Error refreshing token: {data['error']}")
                    return None

                expires_in = data.get("expires_in", 5184000)

                return {
                    "token": data["access_token"],
                    "expires_in": expires_in,
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                }
    except Exception as e:
        logger.error(f"Exception refreshing token: {e}")
        return None


async def check_and_refresh_if_needed(
    creator_id: str,
    db_session,
    refresh_threshold_days: int = 30
) -> Dict[str, Any]:
    """
    Verifica si el token está por expirar y lo refresca automáticamente.

    Llamar esto:
    - En un cron job diario
    - Antes de operaciones críticas de Instagram

    Args:
        creator_id: ID o nombre del creator
        db_session: Sesión de SQLAlchemy
        refresh_threshold_days: Días antes de expiración para refrescar (default: 7)

    Returns:
        Dict con status y detalles
    """
    from sqlalchemy import text

    result = {
        "creator_id": creator_id,
        "action": "none",
        "success": False,
        "message": ""
    }

    try:
        # Obtener token y fecha de expiración
        query_result = db_session.execute(
            text("""
                SELECT id, name, instagram_token, instagram_token_expires_at
                FROM creators
                WHERE id::text = :cid OR name = :cid
            """),
            {"cid": creator_id}
        ).fetchone()

        if not query_result:
            result["message"] = f"Creator {creator_id} not found"
            return result

        creator_uuid, creator_name, token, expires_at = query_result

        if not token:
            result["message"] = f"No Instagram token for {creator_name}"
            return result

        # Si no hay fecha de expiración, asumir que necesita refresh
        if not expires_at:
            logger.info(f"No expiry date for {creator_name}, assuming needs refresh")
            expires_at = datetime.now(timezone.utc) - timedelta(days=1)  # Forzar refresh

        # Calcular días hasta expiración
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        days_until_expiry = (expires_at - now).days

        result["expires_at"] = expires_at.isoformat()
        result["days_until_expiry"] = days_until_expiry

        # Verificar si necesita refresh
        if days_until_expiry >= refresh_threshold_days:
            result["action"] = "skip"
            result["success"] = True
            result["message"] = f"Token still valid ({days_until_expiry} days remaining)"
            return result

        # Token por expirar o expirado, intentar refresh
        logger.info(f"Token for {creator_name} expires in {days_until_expiry} days, refreshing...")
        result["action"] = "refresh"

        new_token_data = await refresh_long_lived_token(token)

        if not new_token_data:
            result["message"] = "Failed to refresh token (may be expired)"
            return result

        # Actualizar en DB
        db_session.execute(
            text("""
                UPDATE creators
                SET instagram_token = :token,
                    instagram_token_expires_at = :expires_at
                WHERE id = :cid
            """),
            {
                "token": new_token_data["token"],
                "expires_at": new_token_data["expires_at"],
                "cid": str(creator_uuid)
            }
        )
        db_session.commit()

        result["success"] = True
        result["message"] = f"Token refreshed, new expiry: {new_token_data['expires_at']}"
        result["new_expires_at"] = new_token_data["expires_at"].isoformat()

        logger.info(f"Token refreshed for {creator_name}, expires: {new_token_data['expires_at']}")

    except Exception as e:
        logger.error(f"Error checking/refreshing token for {creator_id}: {e}")
        result["message"] = str(e)
        db_session.rollback()

    return result


async def refresh_all_creator_tokens(db_session) -> Dict[str, Any]:
    """
    Revisa todos los creators con token de Instagram y refresca los que expiran pronto.

    Diseñado para ser llamado por un cron job diario.
    Sends Telegram alerts for tokens that are expiring and couldn't be renewed.

    Args:
        db_session: Sesión de SQLAlchemy

    Returns:
        Dict con estadísticas del proceso
    """
    from sqlalchemy import text
    from core.alerts import get_alert_manager, AlertLevel

    alert_manager = get_alert_manager()

    stats = {
        "total_creators": 0,
        "checked": 0,
        "refreshed": 0,
        "skipped": 0,
        "failed": 0,
        "alerts_sent": 0,
        "details": []
    }

    try:
        # Obtener todos los creators con token de Instagram
        result = db_session.execute(
            text("""
                SELECT id, name
                FROM creators
                WHERE instagram_token IS NOT NULL
            """)
        ).fetchall()

        stats["total_creators"] = len(result)

        for creator in result:
            creator_id, creator_name = creator

            try:
                # Retry token refresh up to 3 times with exponential backoff
                check_result = None
                for attempt in range(3):
                    check_result = await check_and_refresh_if_needed(str(creator_id), db_session)
                    if check_result.get("success") or check_result.get("action") == "skip":
                        break
                    if attempt < 2:  # Don't sleep after last attempt
                        import asyncio as _aio
                        wait = 60 * (2 ** attempt)  # 60s, 120s
                        logger.warning(f"[TOKEN-REFRESH] Retry {attempt+1}/3 for {creator_name} in {wait}s")
                        await _aio.sleep(wait)
                stats["checked"] += 1

                days_remaining = check_result.get("days_until_expiry")

                if check_result["action"] == "refresh":
                    if check_result["success"]:
                        stats["refreshed"] += 1
                        logger.info(f"Token refreshed for {creator_name}")
                    else:
                        stats["failed"] += 1
                        # Send alert based on urgency
                        if days_remaining is not None and days_remaining < 5:
                            await alert_manager.send_telegram_alert(
                                message=f"Token expires in {days_remaining} days and refresh FAILED.\nManual intervention required immediately.",
                                level=AlertLevel.CRITICAL,
                                title="OAuth Token CRITICAL",
                                creator_id=str(creator_id),
                                metadata={"creator_name": creator_name, "days_remaining": days_remaining},
                            )
                            stats["alerts_sent"] += 1
                        elif days_remaining is not None and days_remaining < 15:
                            await alert_manager.send_telegram_alert(
                                message=f"Token expires in {days_remaining} days and auto-refresh failed.\nPlease re-authenticate via OAuth.",
                                level=AlertLevel.ERROR,
                                title="OAuth Token Expiring",
                                creator_id=str(creator_id),
                                metadata={"creator_name": creator_name, "days_remaining": days_remaining},
                            )
                            stats["alerts_sent"] += 1
                        else:
                            await alert_manager.send_telegram_alert(
                                message=f"Token auto-refresh failed ({days_remaining} days remaining).\nWill retry in 6h.",
                                level=AlertLevel.WARNING,
                                title="OAuth Token Refresh Failed",
                                creator_id=str(creator_id),
                                metadata={"creator_name": creator_name, "days_remaining": days_remaining},
                            )
                            stats["alerts_sent"] += 1
                elif check_result["action"] == "skip":
                    stats["skipped"] += 1

                stats["details"].append({
                    "creator": creator_name,
                    "result": check_result
                })

            except Exception as e:
                logger.error(f"Error processing {creator_name}: {e}")
                stats["failed"] += 1
                stats["details"].append({
                    "creator": creator_name,
                    "error": str(e)
                })

    except Exception as e:
        logger.error(f"Error in refresh_all_creator_tokens: {e}")
        stats["error"] = str(e)

    # Summary log
    logger.info(
        f"[TOKEN-REFRESH] Done: {stats['checked']} checked, "
        f"{stats['refreshed']} refreshed, {stats['skipped']} skipped, "
        f"{stats['failed']} failed, {stats['alerts_sent']} alerts sent"
    )

    return stats


def check_and_refresh_sync(creator_id: str) -> Dict[str, Any]:
    """
    Versión síncrona de check_and_refresh_if_needed.
    Para uso en contextos no-async.
    """
    import asyncio
    from api.services.db_service import get_session

    session = get_session()
    if not session:
        return {"success": False, "message": "No database connection"}

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(check_and_refresh_if_needed(creator_id, session))
        loop.close()
        return result
    finally:
        session.close()
