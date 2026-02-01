#!/usr/bin/env python3
"""
Script para sincronizar mensajes históricos de Instagram DM a la base de datos.
Uso: DATABASE_URL=postgresql://... python scripts/sync_instagram_dms.py

Requisitos:
- DATABASE_URL configurado (PostgreSQL/Neon)
- Creator 'stefano_bonanno' debe existir en la DB con instagram_token configurado

Rate Limits (Enero 2026):
- Instagram Graph API: 200 requests/hora por token
- Este script usa 190/hora dejando 5% margen de seguridad

Optimizaciones (Feb 2026):
- Blacklist de 403: guarda conv_ids que dan 403 para no reintentar
- Early stop: para después de N errores 403 consecutivos
- Sync incremental: detecta leads existentes y hace skip
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.instagram_rate_limiter import get_instagram_rate_limiter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Rate limiter global
rate_limiter = get_instagram_rate_limiter()

# Config
CREATOR_ID = "stefano_bonanno"
START_FROM_CONVERSATION = int(os.environ.get("START_FROM", "0"))
ACCESS_TOKEN = "IGAAT4utuSH75BZAGE0SFNwU0lfc2oxQ2hhZADNoQkJxR0hrNGc5ZAzZAScjd0dHNHYmJyQXBTODViQlFpOUdlSDlQSHE5Y2c1WjJ3MUluX2xLazdZAWUlHcC1xOE81R2tHRXJZARnM2U2xlYkk0Vk9tblRsSTBfS3VVQm1sLWllSElkUQZDZD"
IG_USER_ID = "17841407135263418"
API_BASE = "https://graph.facebook.com/v21.0"
MAX_AGE_DAYS = 365

# ============================================
# OPTIMIZACIONES (Feb 2026)
# ============================================
CONSECUTIVE_403_LIMIT = int(os.environ.get("CONSECUTIVE_403_LIMIT", "10"))
BLACKLIST_FILE = Path(__file__).parent / "data" / "ig_403_blacklist.json"


def load_blacklist() -> set:
    """Carga IDs de conversaciones que dieron 403 previamente"""
    if BLACKLIST_FILE.exists():
        try:
            with open(BLACKLIST_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("conversation_ids", []))
        except Exception as e:
            logger.warning(f"Error loading blacklist: {e}")
    return set()


def save_blacklist(conv_ids: set):
    """Guarda IDs de conversaciones que dieron 403"""
    BLACKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(BLACKLIST_FILE, "w") as f:
            json.dump(
                {
                    "conversation_ids": list(conv_ids),
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "count": len(conv_ids),
                },
                f,
                indent=2,
            )
        logger.info(f"Blacklist saved: {len(conv_ids)} conv_ids")
    except Exception as e:
        logger.error(f"Error saving blacklist: {e}")


async def sync_dms():
    from datetime import datetime, timedelta, timezone

    import httpx
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Export it and run again.")
        return

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    from api.models import Creator, Lead, Message

    try:
        creator = session.query(Creator).filter_by(name=CREATOR_ID).first()
        if not creator:
            logger.error(f"Creator not found: {CREATOR_ID}")
            return

        logger.info(f"Found creator: {creator.name} (id: {creator.id})")

        conversations_fetched = 0
        messages_saved = 0
        leads_created = 0
        leads_skipped = 0
        convs_blacklisted = 0
        insights = []

        # Cargar blacklist de 403s previos
        blacklist = load_blacklist()
        new_403s = set()
        consecutive_403 = 0

        if blacklist:
            logger.info(f"Loaded blacklist: {len(blacklist)} conv_ids to skip")

        async with httpx.AsyncClient(timeout=30.0) as client:

            async def rate_limited_request(url, params=None):
                await rate_limiter.wait_if_needed(CREATOR_ID)
                try:
                    if params:
                        resp = await client.get(url, params=params)
                    else:
                        resp = await client.get(url)
                    rate_limiter.record_call(CREATOR_ID, url[:50], resp.status_code)

                    if resp.status_code == 429:
                        logger.warning("Rate limit hit (429). Esperando 60s...")
                        await asyncio.sleep(60)
                        return await rate_limited_request(url, params)
                    return resp
                except Exception as e:
                    logger.error(f"Request error: {e}")
                    rate_limiter.record_call(CREATOR_ID, url[:50], 500)
                    raise

            # Get ALL conversations with pagination
            logger.info("Fetching conversations (with pagination)...")
            conversations = []
            next_url = f"{API_BASE}/{IG_USER_ID}/conversations"
            params = {"platform": "instagram", "access_token": ACCESS_TOKEN, "limit": 50}

            page_num = 0
            while next_url:
                page_num += 1
                logger.info(f"  Fetching page {page_num}...")

                if page_num == 1:
                    conv_resp = await rate_limited_request(next_url, params)
                else:
                    conv_resp = await rate_limited_request(next_url)

                if conv_resp.status_code != 200:
                    logger.error(f"Conversations API error: {conv_resp.json()}")
                    break

                data = conv_resp.json()
                batch = data.get("data", [])
                conversations.extend(batch)
                logger.info(f"    Got {len(batch)} conversations (total: {len(conversations)})")

                paging = data.get("paging", {})
                next_url = paging.get("next")

                if not batch:
                    break

            conversations_fetched = len(conversations)
            logger.info(f"Found {conversations_fetched} total conversations")

            if START_FROM_CONVERSATION > 0:
                logger.info(
                    f"Skipping first {START_FROM_CONVERSATION} conversations (already processed)"
                )
                conversations = conversations[START_FROM_CONVERSATION:]
                logger.info(f"Processing {len(conversations)} remaining conversations")

            # Process each conversation
            start_time = time.time()
            early_stopped = False

            for i, conv in enumerate(conversations):
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                # OPTIMIZACIÓN 1: Skip si está en blacklist
                if conv_id in blacklist:
                    convs_blacklisted += 1
                    if convs_blacklisted <= 5 or convs_blacklisted % 50 == 0:
                        logger.info(f"  SKIP conv {i}: blacklisted (403 previo)")
                    continue

                actual_index = i + START_FROM_CONVERSATION
                logger.info(f"Processing conversation {actual_index}/{conversations_fetched}...")

                # Progreso cada 20 conversaciones
                if i > 0 and i % 20 == 0:
                    elapsed = time.time() - start_time
                    rate = i / (elapsed / 60) if elapsed > 0 else 0
                    remaining = len(conversations) - i
                    eta_min = remaining / rate if rate > 0 else 0
                    stats = rate_limiter.get_stats(CREATOR_ID)
                    logger.info(f"\n{'='*50}")
                    logger.info(f"PROGRESO: {actual_index}/{conversations_fetched} conversaciones")
                    logger.info(f"  Velocidad: {rate:.1f} conv/min | ETA: {eta_min:.0f} min")
                    logger.info(f"  Rate limit: {stats['calls_last_hour']}/190 calls esta hora")
                    logger.info(f"{'='*50}\n")

                # Get ALL messages with pagination
                messages = []
                msg_next_url = f"{API_BASE}/{conv_id}/messages"
                msg_params = {
                    "fields": "id,message,from,to,created_time",
                    "access_token": ACCESS_TOKEN,
                    "limit": 50,
                }

                while msg_next_url:
                    if len(messages) == 0:
                        msg_resp = await rate_limited_request(msg_next_url, msg_params)
                    else:
                        msg_resp = await rate_limited_request(msg_next_url)

                    if msg_resp.status_code == 403:
                        # OPTIMIZACIÓN 2: Añadir a blacklist y contar para early stop
                        new_403s.add(conv_id)
                        consecutive_403 += 1
                        logger.warning(
                            f"  Conv {actual_index}: 403 Forbidden (consecutive: {consecutive_403})"
                        )

                        # OPTIMIZACIÓN 3: Early stop si muchos 403 consecutivos
                        if consecutive_403 >= CONSECUTIVE_403_LIMIT:
                            logger.warning(f"\n{'!'*50}")
                            logger.warning(f"EARLY STOP: {consecutive_403} consecutive 403 errors")
                            logger.warning("Probably reached end of accessible conversations")
                            logger.warning(f"{'!'*50}\n")
                            early_stopped = True
                        break
                    elif msg_resp.status_code != 200:
                        logger.warning(f"  Conv {actual_index}: HTTP {msg_resp.status_code}")
                        break
                    else:
                        consecutive_403 = 0

                    msg_data = msg_resp.json()
                    batch = msg_data.get("data", [])
                    messages.extend(batch)

                    msg_paging = msg_data.get("paging", {})
                    msg_next_url = msg_paging.get("next")

                    if not batch:
                        break

                # Early stop check
                if early_stopped:
                    break

                if not messages:
                    continue

                # Find follower (the other person)
                follower_id = None
                follower_username = None

                for msg in messages:
                    from_data = msg.get("from", {})
                    if from_data.get("id") and from_data.get("id") != IG_USER_ID:
                        follower_id = from_data.get("id")
                        follower_username = from_data.get("username", "")
                        break

                if not follower_id:
                    for msg in messages:
                        to_data = msg.get("to", {}).get("data", [])
                        for r in to_data:
                            if r.get("id") != IG_USER_ID:
                                follower_id = r.get("id")
                                follower_username = r.get("username", "")
                                break
                        if follower_id:
                            break

                if not follower_id:
                    continue

                # Verificar si hay mensajes dentro del período
                has_recent_messages = False
                for msg in messages:
                    if msg.get("created_time"):
                        try:
                            msg_time = datetime.fromisoformat(
                                msg["created_time"].replace("+0000", "+00:00")
                            )
                            if msg_time >= cutoff_date:
                                has_recent_messages = True
                                break
                        except Exception:
                            has_recent_messages = True
                            break

                if not has_recent_messages:
                    logger.info(
                        f"  Skipping @{follower_username}: no messages in last {MAX_AGE_DAYS} days"
                    )
                    continue

                # Create or get Lead
                lead = (
                    session.query(Lead)
                    .filter_by(
                        creator_id=creator.id, platform="instagram", platform_user_id=follower_id
                    )
                    .first()
                )

                if not lead:
                    lead = Lead(
                        creator_id=creator.id,
                        platform="instagram",
                        platform_user_id=follower_id,
                        username=follower_username,
                        status="active",
                    )
                    session.add(lead)
                    session.commit()
                    leads_created += 1
                    logger.info(f"  Created lead: @{follower_username}")
                else:
                    leads_skipped += 1
                    if leads_skipped <= 3 or leads_skipped % 20 == 0:
                        logger.info(f"  SKIP @{follower_username}: already exists")

                # Save messages
                conv_messages_saved = 0
                conv_topics = []
                conv_questions = []

                for msg in messages:
                    msg_id = msg.get("id")
                    msg_text = msg.get("message", "")
                    msg_from = msg.get("from", {})
                    msg_time = msg.get("created_time")

                    if not msg_text:
                        continue

                    existing = session.query(Message).filter_by(platform_message_id=msg_id).first()

                    if existing:
                        continue

                    is_from_creator = msg_from.get("id") == IG_USER_ID
                    role = "assistant" if is_from_creator else "user"

                    created_at = None
                    if msg_time:
                        try:
                            created_at = datetime.fromisoformat(msg_time.replace("+0000", "+00:00"))
                            if created_at < cutoff_date:
                                continue
                        except Exception:
                            pass

                    new_msg = Message(
                        lead_id=lead.id,
                        role=role,
                        content=msg_text,
                        status="sent",
                        platform_message_id=msg_id,
                        approved_by="historical_sync",
                    )
                    if created_at:
                        new_msg.created_at = created_at

                    session.add(new_msg)
                    conv_messages_saved += 1
                    messages_saved += 1

                    if role == "user":
                        if "?" in msg_text:
                            conv_questions.append(msg_text.strip()[:100])
                        lower_text = msg_text.lower()
                        if any(w in lower_text for w in ["precio", "cuesta", "vale", "pagar"]):
                            conv_topics.append("precio")
                        if any(w in lower_text for w in ["info", "información", "detalles"]):
                            conv_topics.append("información")
                        if any(w in lower_text for w in ["comprar", "quiero", "interesa"]):
                            conv_topics.append("intención_compra")
                        if any(w in lower_text for w in ["challenge", "reto", "programa"]):
                            conv_topics.append("productos")

                session.commit()

                if conv_messages_saved > 0:
                    intent_score = 0.0
                    if "intención_compra" in conv_topics:
                        intent_score += 0.4
                    if "precio" in conv_topics:
                        intent_score += 0.3
                    if "información" in conv_topics:
                        intent_score += 0.2
                    if conv_questions:
                        intent_score += 0.1

                    insights.append(
                        {
                            "follower": follower_username or "unknown",
                            "messages": len(messages),
                            "topics": list(set(conv_topics)),
                            "intent_score": min(intent_score, 1.0),
                            "questions": conv_questions[:3],
                        }
                    )

                    logger.info(
                        f"  @{follower_username}: {conv_messages_saved} msgs saved, intent={intent_score:.1f}"
                    )

        # Guardar blacklist actualizada
        final_blacklist = blacklist.union(new_403s)
        if new_403s:
            save_blacklist(final_blacklist)

        # Summary
        logger.info("\n" + "=" * 50)
        logger.info("SYNC COMPLETE")
        logger.info("=" * 50)
        logger.info(f"Conversations fetched: {conversations_fetched}")
        logger.info(f"Conversations blacklisted (skipped): {convs_blacklisted}")
        logger.info(f"New 403 errors: {len(new_403s)}")
        logger.info(f"Total blacklist size: {len(final_blacklist)}")
        logger.info(f"Messages saved: {messages_saved}")
        logger.info(f"Leads created: {leads_created}")
        logger.info(f"Leads skipped (existing): {leads_skipped}")
        if early_stopped:
            logger.info("(Early stopped due to consecutive 403s)")

        if insights:
            logger.info("\nTOP INSIGHTS (by intent):")
            for insight in sorted(insights, key=lambda x: x["intent_score"], reverse=True)[:10]:
                logger.info(
                    f"  @{insight['follower']}: intent={insight['intent_score']:.1f}, topics={insight['topics']}"
                )
                if insight["questions"]:
                    logger.info(f"    Questions: {insight['questions'][0][:60]}...")

    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(sync_dms())
