#!/usr/bin/env python3
"""
Script para sincronizar mensajes históricos de Instagram DM a la base de datos.
Uso: DATABASE_URL=postgresql://... python scripts/sync_instagram_dms.py

Requisitos:
- DATABASE_URL configurado (PostgreSQL/Neon)
- Creator 'stefano_bonanno' debe existir en la DB con instagram_token configurado
"""

import asyncio
import os
import sys
import logging

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
CREATOR_ID = "stefano_bonanno"
ACCESS_TOKEN = "IGAAT4utuSH75BZAGE0SFNwU0lfc2oxQ2hhZADNoQkJxR0hrNGc5ZAzZAScjd0dHNHYmJyQXBTODViQlFpOUdlSDlQSHE5Y2c1WjJ3MUluX2xLazdZAWUlHcC1xOE81R2tHRXJZARnM2U2xlYkk0Vk9tblRsSTBfS3VVQm1sLWllSElkUQZDZD"
IG_USER_ID = "17841407135263418"  # This is the page_id (used for conversations)
# IMPORTANTE: Usar graph.facebook.com para conversations/messages
API_BASE = "https://graph.facebook.com/v21.0"
# Sin límite de cantidad - solo filtro por tiempo (12 meses)
MAX_AGE_DAYS = 365


async def sync_dms():
    import httpx
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Fecha límite: solo mensajes de los últimos 12 meses
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    # Check DATABASE_URL
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Export it and run again.")
        logger.info("Example: DATABASE_URL=postgresql://user:pass@host:5432/db python scripts/sync_instagram_dms.py")
        return

    # Setup DB
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Import models
    from api.models import Creator, Lead, Message

    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=CREATOR_ID).first()
        if not creator:
            logger.error(f"Creator not found: {CREATOR_ID}")
            return

        logger.info(f"Found creator: {creator.name} (id: {creator.id})")

        conversations_fetched = 0
        messages_saved = 0
        leads_created = 0
        insights = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get ALL conversations with pagination
            logger.info("Fetching conversations (with pagination)...")
            conversations = []
            next_url = f"{API_BASE}/{IG_USER_ID}/conversations"
            params = {"platform": "instagram", "access_token": ACCESS_TOKEN, "limit": 50}

            page_num = 0
            while next_url:  # Sin límite de cantidad - cargar TODAS
                page_num += 1
                logger.info(f"  Fetching page {page_num}...")

                if page_num == 1:
                    conv_resp = await client.get(next_url, params=params)
                else:
                    # next_url already includes params
                    conv_resp = await client.get(next_url)

                if conv_resp.status_code != 200:
                    logger.error(f"Conversations API error: {conv_resp.json()}")
                    break

                data = conv_resp.json()
                batch = data.get("data", [])
                conversations.extend(batch)
                logger.info(f"    Got {len(batch)} conversations (total: {len(conversations)})")

                # Check for next page
                paging = data.get("paging", {})
                next_url = paging.get("next")

                if not batch:
                    break

            conversations_fetched = len(conversations)
            logger.info(f"Found {conversations_fetched} total conversations")

            # Process each conversation
            for i, conv in enumerate(conversations):
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                # First, get conversation details to get participant profile_pic
                participant_profile_pics = {}
                try:
                    conv_detail_resp = await client.get(
                        f"{API_BASE}/{conv_id}",
                        params={"fields": "participants", "access_token": ACCESS_TOKEN}
                    )
                    if conv_detail_resp.status_code == 200:
                        conv_data = conv_detail_resp.json()
                        participants = conv_data.get("participants", {}).get("data", [])
                        for p in participants:
                            if p.get("id") and p.get("profile_pic"):
                                participant_profile_pics[p["id"]] = p["profile_pic"]
                            if p.get("username") and p.get("profile_pic"):
                                participant_profile_pics[p["username"]] = p["profile_pic"]
                except Exception as e:
                    logger.warning(f"Could not fetch participant profile pics: {e}")

                # Get ALL messages with pagination (including attachments)
                messages = []
                msg_next_url = f"{API_BASE}/{conv_id}/messages"
                msg_params = {
                    "fields": "id,message,from,to,created_time,attachments",
                    "access_token": ACCESS_TOKEN,
                    "limit": 50
                }

                while msg_next_url:  # Sin límite - cargar TODOS los mensajes
                    if len(messages) == 0:
                        msg_resp = await client.get(msg_next_url, params=msg_params)
                    else:
                        msg_resp = await client.get(msg_next_url)

                    if msg_resp.status_code != 200:
                        break

                    msg_data = msg_resp.json()
                    batch = msg_data.get("data", [])
                    messages.extend(batch)

                    msg_paging = msg_data.get("paging", {})
                    msg_next_url = msg_paging.get("next")

                    if not batch:
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

                # =====================================================
                # PRIMERO: Verificar si hay mensajes dentro del período
                # Solo crear Lead si hay mensajes válidos (últimos 365 días)
                # =====================================================
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
                        except:
                            # Si no puede parsear, asumimos que es reciente
                            has_recent_messages = True
                            break

                if not has_recent_messages:
                    logger.info(f"  Skipping @{follower_username}: no messages in last {MAX_AGE_DAYS} days")
                    continue  # Skip esta conversación - no crear lead

                # Get profile pic URL for this follower
                follower_profile_pic = (
                    participant_profile_pics.get(follower_id) or
                    participant_profile_pics.get(follower_username)
                )

                # Create or get Lead
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform="instagram",
                    platform_user_id=follower_id
                ).first()

                if not lead:
                    lead = Lead(
                        creator_id=creator.id,
                        platform="instagram",
                        platform_user_id=follower_id,
                        username=follower_username,
                        profile_pic_url=follower_profile_pic,  # Save profile picture
                        status="active"
                    )
                    session.add(lead)
                    session.commit()
                    leads_created += 1
                    logger.info(f"  Created lead: @{follower_username} (pic: {'yes' if follower_profile_pic else 'no'})")
                else:
                    # Update profile pic if we have it and lead doesn't
                    if follower_profile_pic and not lead.profile_pic_url:
                        lead.profile_pic_url = follower_profile_pic
                        session.commit()

                # Save messages
                conv_messages_saved = 0
                conv_topics = []
                conv_questions = []

                for msg in messages:
                    msg_id = msg.get("id")
                    msg_text = msg.get("message", "")
                    msg_from = msg.get("from", {})
                    msg_time = msg.get("created_time")

                    # Process attachments (images, videos, etc.)
                    attachments_data = msg.get("attachments", {}).get("data", [])
                    media_attachments = []
                    for att in attachments_data:
                        attachment_info = {
                            "id": att.get("id"),
                            "mime_type": att.get("mime_type"),
                        }
                        if "image_data" in att:
                            attachment_info["type"] = "image"
                            attachment_info["url"] = att["image_data"].get("url")
                            attachment_info["preview_url"] = att["image_data"].get("preview_url")
                        elif "video_data" in att:
                            attachment_info["type"] = "video"
                            attachment_info["url"] = att["video_data"].get("url")
                            attachment_info["preview_url"] = att["video_data"].get("preview_url")
                        elif att.get("file_url"):
                            attachment_info["type"] = "file"
                            attachment_info["url"] = att.get("file_url")
                        if attachment_info.get("url"):
                            media_attachments.append(attachment_info)

                    # Skip if no text AND no attachments
                    if not msg_text and not media_attachments:
                        continue

                    # Check if exists
                    existing = session.query(Message).filter_by(
                        platform_message_id=msg_id
                    ).first()

                    if existing:
                        # Update existing message with attachments if we have them
                        if media_attachments and not existing.msg_metadata:
                            primary = media_attachments[0]
                            existing.msg_metadata = {
                                "type": primary.get("type", "image"),
                                "url": primary.get("url"),
                                "preview_url": primary.get("preview_url"),
                            }
                        continue

                    # Determine role
                    is_from_creator = msg_from.get("id") == IG_USER_ID
                    role = "assistant" if is_from_creator else "user"

                    # Parse timestamp
                    created_at = None
                    if msg_time:
                        try:
                            created_at = datetime.fromisoformat(msg_time.replace("+0000", "+00:00"))
                            # Filtrar mensajes muy antiguos
                            if created_at < cutoff_date:
                                continue  # Skip - mensaje fuera del período
                        except:
                            pass

                    # Build msg_metadata for attachments
                    msg_metadata = None
                    if media_attachments:
                        primary = media_attachments[0]
                        msg_metadata = {
                            "type": primary.get("type", "image"),
                            "url": primary.get("url"),
                            "preview_url": primary.get("preview_url"),
                        }
                        if len(media_attachments) > 1:
                            msg_metadata["attachments"] = media_attachments

                    new_msg = Message(
                        lead_id=lead.id,
                        role=role,
                        content=msg_text or "[Media]",
                        status="sent",
                        platform_message_id=msg_id,
                        approved_by="historical_sync",
                        msg_metadata=msg_metadata
                    )
                    if created_at:
                        new_msg.created_at = created_at

                    session.add(new_msg)
                    conv_messages_saved += 1
                    messages_saved += 1

                    # Collect insights
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
                    # Calculate purchase intent
                    intent_score = 0.0
                    if "intención_compra" in conv_topics:
                        intent_score += 0.4
                    if "precio" in conv_topics:
                        intent_score += 0.3
                    if "información" in conv_topics:
                        intent_score += 0.2
                    if conv_questions:
                        intent_score += 0.1

                    insights.append({
                        "follower": follower_username or "unknown",
                        "messages": len(messages),
                        "topics": list(set(conv_topics)),
                        "intent_score": min(intent_score, 1.0),
                        "questions": conv_questions[:3]
                    })

                    logger.info(f"  @{follower_username}: {conv_messages_saved} msgs saved, intent={intent_score:.1f}")

        # Summary
        logger.info("\n" + "="*50)
        logger.info("SYNC COMPLETE")
        logger.info("="*50)
        logger.info(f"Conversations: {conversations_fetched}")
        logger.info(f"Messages saved: {messages_saved}")
        logger.info(f"Leads created: {leads_created}")

        if insights:
            logger.info("\nINSIGHTS:")
            for insight in sorted(insights, key=lambda x: x["intent_score"], reverse=True)[:10]:
                logger.info(f"  @{insight['follower']}: intent={insight['intent_score']:.1f}, topics={insight['topics']}")
                if insight['questions']:
                    logger.info(f"    Questions: {insight['questions'][0][:60]}...")

    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(sync_dms())
