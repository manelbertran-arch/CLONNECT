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
IG_USER_ID = "17841407135263418"
API_BASE = "https://graph.instagram.com/v21.0"
MAX_CONVERSATIONS = 50
MAX_MESSAGES_PER_CONV = 50


async def sync_dms():
    import httpx
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

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
            # Get conversations
            logger.info("Fetching conversations...")
            conv_resp = await client.get(
                f"{API_BASE}/{IG_USER_ID}/conversations",
                params={"access_token": ACCESS_TOKEN, "limit": MAX_CONVERSATIONS}
            )

            if conv_resp.status_code != 200:
                logger.error(f"Conversations API error: {conv_resp.json()}")
                return

            conversations = conv_resp.json().get("data", [])
            conversations_fetched = len(conversations)
            logger.info(f"Found {conversations_fetched} conversations")

            # Process each conversation
            for i, conv in enumerate(conversations):
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                # Get messages
                msg_resp = await client.get(
                    f"{API_BASE}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": ACCESS_TOKEN,
                        "limit": MAX_MESSAGES_PER_CONV
                    }
                )

                if msg_resp.status_code != 200:
                    logger.warning(f"  Conv {i+1}: Error getting messages")
                    continue

                messages = msg_resp.json().get("data", [])
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
                        status="active"
                    )
                    session.add(lead)
                    session.commit()
                    leads_created += 1
                    logger.info(f"  Created lead: @{follower_username}")

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

                    # Check if exists
                    existing = session.query(Message).filter_by(
                        platform_message_id=msg_id
                    ).first()

                    if existing:
                        continue

                    # Determine role
                    is_from_creator = msg_from.get("id") == IG_USER_ID
                    role = "assistant" if is_from_creator else "user"

                    # Parse timestamp
                    created_at = None
                    if msg_time:
                        try:
                            created_at = datetime.fromisoformat(msg_time.replace("+0000", "+00:00"))
                        except:
                            pass

                    new_msg = Message(
                        lead_id=lead.id,
                        role=role,
                        content=msg_text,
                        status="sent",
                        platform_message_id=msg_id,
                        approved_by="historical_sync"
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
