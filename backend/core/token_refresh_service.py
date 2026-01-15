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
from datetime import datetime, timedelta
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
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if "error" in data:
                    logger.error(f"Error exchanging token: {data['error']}")
                    return None

                expires_in = data.get("expires_in", 5184000)  # ~60 días default

                return {
                    "token": data["access_token"],
                    "expires_in": expires_in,
                    "expires_at": datetime.utcnow() + timedelta(seconds=expires_in)
                }
    except Exception as e:
        logger.error(f"Exception exchanging token: {e}")
        return None


async def refresh_long_lived_token(current_token: str) -> Optional[Dict[str, Any]]:
    """
    Refresca un token long-lived ANTES de que expire.

    IMPORTANTE: Solo funciona si el token tiene más de 24h de vida restante.
    No funciona con tokens ya expirados.

    Meta API: GET /refresh_access_token?grant_type=ig_refresh_token

    Args:
        current_token: Token long-lived actual (no expirado)

    Returns:
        Dict con nuevo token y fechas, o None si falla
    """
    import aiohttp

    url = "https://graph.instagram.com/refresh_access_token"
    params = {
        "grant_type": "ig_refresh_token",
        "access_token": current_token
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if "error" in data:
                    logger.error(f"Error refreshing token: {data['error']}")
                    return None

                expires_in = data.get("expires_in", 5184000)

                return {
                    "token": data["access_token"],
                    "expires_in": expires_in,
                    "expires_at": datetime.utcnow() + timedelta(seconds=expires_in)
                }
    except Exception as e:
        logger.error(f"Exception refreshing token: {e}")
        return None


async def check_and_refresh_if_needed(
    creator_id: str,
    db_session,
    refresh_threshold_days: int = 7
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
            expires_at = datetime.utcnow() - timedelta(days=1)  # Forzar refresh

        # Calcular días hasta expiración
        now = datetime.utcnow()
        if expires_at.tzinfo:
            expires_at = expires_at.replace(tzinfo=None)

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

    Args:
        db_session: Sesión de SQLAlchemy

    Returns:
        Dict con estadísticas del proceso
    """
    from sqlalchemy import text

    stats = {
        "total_creators": 0,
        "checked": 0,
        "refreshed": 0,
        "skipped": 0,
        "failed": 0,
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
                check_result = await check_and_refresh_if_needed(str(creator_id), db_session)
                stats["checked"] += 1

                if check_result["action"] == "refresh":
                    if check_result["success"]:
                        stats["refreshed"] += 1
                    else:
                        stats["failed"] += 1
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
