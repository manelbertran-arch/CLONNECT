#!/usr/bin/env python3
"""
Script para RESET NUCLEAR + RE-SYNC de un creator.
Borra todos los datos y re-sincroniza desde Instagram con los nuevos campos:
- profile_pic_url en Lead
- attachments en Message.msg_metadata

Uso:
    DATABASE_URL=postgresql://... python scripts/reset_and_resync.py stefano_bonanno
"""

import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta, timezone

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
CREATOR_ID = sys.argv[1] if len(sys.argv) > 1 else "stefano_bonanno"
API_BASE = "https://graph.facebook.com/v21.0"
MAX_AGE_DAYS = 365


async def reset_nuclear(session, creator):
    """Borra TODOS los datos del creator."""
    from api.models import Lead, Message, SyncQueue, SyncState, LeadActivity, LeadTask

    logger.info(f"\n{'='*60}")
    logger.info(f"RESET NUCLEAR: {CREATOR_ID}")
    logger.info(f"{'='*60}\n")

    # Get all leads for this creator
    leads = session.query(Lead).filter_by(creator_id=creator.id).all()
    lead_ids = [l.id for l in leads]

    if not lead_ids:
        logger.info("No leads to delete")
        return {"leads": 0, "messages": 0}

    # Delete messages
    msg_count = session.query(Message).filter(Message.lead_id.in_(lead_ids)).delete(synchronize_session=False)
    logger.info(f"Deleted {msg_count} messages")

    # Delete lead activities
    try:
        activity_count = session.query(LeadActivity).filter(LeadActivity.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        logger.info(f"Deleted {activity_count} lead activities")
    except Exception as e:
        logger.warning(f"Could not delete lead activities: {e}")

    # Delete lead tasks
    try:
        task_count = session.query(LeadTask).filter(LeadTask.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        logger.info(f"Deleted {task_count} lead tasks")
    except Exception as e:
        logger.warning(f"Could not delete lead tasks: {e}")

    # Delete leads
    lead_count = session.query(Lead).filter_by(creator_id=creator.id).delete(synchronize_session=False)
    logger.info(f"Deleted {lead_count} leads")

    # Delete sync queue
    queue_count = session.query(SyncQueue).filter_by(creator_id=CREATOR_ID).delete(synchronize_session=False)
    logger.info(f"Deleted {queue_count} sync queue jobs")

    # Reset sync state
    sync_state = session.query(SyncState).filter_by(creator_id=CREATOR_ID).first()
    if sync_state:
        sync_state.status = "idle"
        sync_state.conversations_total = 0
        sync_state.conversations_synced = 0
        sync_state.messages_saved = 0
        sync_state.error_count = 0
        sync_state.current_conversation = None
        sync_state.rate_limit_until = None
        sync_state.last_error = None
        logger.info("Reset sync state")

    session.commit()
    logger.info(f"\nRESET COMPLETE: {lead_count} leads, {msg_count} messages deleted\n")

    return {"leads": lead_count, "messages": msg_count}


async def resync_with_images(session, creator):
    """Re-sincroniza incluyendo profile_pic y attachments."""
    import httpx
    from api.models import Lead, Message

    access_token = creator.instagram_token
    ig_user_id = creator.instagram_user_id or creator.instagram_page_id

    if not access_token or not ig_user_id:
        logger.error("Creator missing instagram_token or instagram_user_id")
        return

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    logger.info(f"\n{'='*60}")
    logger.info(f"RE-SYNC WITH IMAGES: {CREATOR_ID}")
    logger.info(f"{'='*60}\n")

    stats = {
        "conversations": 0,
        "leads_created": 0,
        "leads_with_pic": 0,
        "messages_saved": 0,
        "messages_with_media": 0,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch ALL conversations
        logger.info("Fetching conversations...")
        conversations = []
        next_url = f"{API_BASE}/{ig_user_id}/conversations"
        params = {"platform": "instagram", "access_token": access_token, "limit": 50}

        page_num = 0
        while next_url and page_num < 20:  # Safety limit
            page_num += 1
            if page_num == 1:
                resp = await client.get(next_url, params=params)
            else:
                resp = await client.get(next_url)

            if resp.status_code != 200:
                logger.error(f"API error: {resp.json()}")
                break

            data = resp.json()
            batch = data.get("data", [])
            conversations.extend(batch)
            logger.info(f"  Page {page_num}: {len(batch)} conversations (total: {len(conversations)})")

            next_url = data.get("paging", {}).get("next")
            if not batch:
                break

        stats["conversations"] = len(conversations)
        logger.info(f"\nProcessing {len(conversations)} conversations...\n")

        # Process each conversation
        for i, conv in enumerate(conversations):
            conv_id = conv.get("id")
            if not conv_id:
                continue

            # 1. Get participants with profile_pic
            participant_profile_pics = {}
            try:
                conv_resp = await client.get(
                    f"{API_BASE}/{conv_id}",
                    params={"fields": "participants", "access_token": access_token}
                )
                if conv_resp.status_code == 200:
                    participants = conv_resp.json().get("participants", {}).get("data", [])
                    for p in participants:
                        if p.get("id") and p.get("profile_pic"):
                            participant_profile_pics[p["id"]] = p["profile_pic"]
                        if p.get("username") and p.get("profile_pic"):
                            participant_profile_pics[p["username"]] = p["profile_pic"]
            except Exception as e:
                logger.warning(f"Could not fetch participants: {e}")

            # 2. Get messages WITH attachments
            messages = []
            msg_next_url = f"{API_BASE}/{conv_id}/messages"
            msg_params = {
                "fields": "id,message,from,to,created_time,attachments",
                "access_token": access_token,
                "limit": 50
            }

            while msg_next_url:
                if len(messages) == 0:
                    msg_resp = await client.get(msg_next_url, params=msg_params)
                else:
                    msg_resp = await client.get(msg_next_url)

                if msg_resp.status_code != 200:
                    break

                msg_data = msg_resp.json()
                batch = msg_data.get("data", [])
                messages.extend(batch)
                msg_next_url = msg_data.get("paging", {}).get("next")
                if not batch:
                    break

            if not messages:
                continue

            # Find follower
            follower_id = None
            follower_username = None
            for msg in messages:
                from_data = msg.get("from", {})
                if from_data.get("id") and from_data.get("id") != ig_user_id:
                    follower_id = from_data.get("id")
                    follower_username = from_data.get("username", "")
                    break

            if not follower_id:
                continue

            # Check for recent messages
            has_recent = False
            for msg in messages:
                if msg.get("created_time"):
                    try:
                        msg_time = datetime.fromisoformat(msg["created_time"].replace("+0000", "+00:00"))
                        if msg_time >= cutoff_date:
                            has_recent = True
                            break
                    except:
                        has_recent = True
                        break

            if not has_recent:
                continue

            # Get profile pic for this follower
            profile_pic = participant_profile_pics.get(follower_id) or participant_profile_pics.get(follower_username)

            # Create Lead with profile_pic
            lead = Lead(
                creator_id=creator.id,
                platform="instagram",
                platform_user_id=follower_id,
                username=follower_username,
                profile_pic_url=profile_pic,
                status="active"
            )
            session.add(lead)
            session.commit()
            stats["leads_created"] += 1
            if profile_pic:
                stats["leads_with_pic"] += 1

            # Save messages with attachments
            for msg in messages:
                msg_id = msg.get("id")
                msg_text = msg.get("message", "")
                msg_time = msg.get("created_time")

                # Process attachments
                attachments_data = msg.get("attachments", {}).get("data", [])
                media_attachments = []
                for att in attachments_data:
                    attachment_info = {"id": att.get("id"), "mime_type": att.get("mime_type")}
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

                if not msg_text and not media_attachments:
                    continue

                # Parse timestamp
                created_at = None
                if msg_time:
                    try:
                        created_at = datetime.fromisoformat(msg_time.replace("+0000", "+00:00"))
                        if created_at < cutoff_date:
                            continue
                    except:
                        pass

                # Build msg_metadata
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

                msg_from = msg.get("from", {})
                is_from_creator = msg_from.get("id") == ig_user_id
                role = "assistant" if is_from_creator else "user"

                new_msg = Message(
                    lead_id=lead.id,
                    role=role,
                    content=msg_text or "[Media]",
                    status="sent",
                    platform_message_id=msg_id,
                    msg_metadata=msg_metadata
                )
                if created_at:
                    new_msg.created_at = created_at

                session.add(new_msg)
                stats["messages_saved"] += 1
                if msg_metadata:
                    stats["messages_with_media"] += 1

            session.commit()

            if (i + 1) % 10 == 0:
                logger.info(f"  Processed {i + 1}/{len(conversations)} conversations...")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SYNC COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Conversations: {stats['conversations']}")
    logger.info(f"Leads created: {stats['leads_created']} ({stats['leads_with_pic']} with profile pic)")
    logger.info(f"Messages saved: {stats['messages_saved']} ({stats['messages_with_media']} with media)")
    logger.info(f"{'='*60}\n")

    return stats


async def main():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from api.models import Creator

    # Check DATABASE_URL
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set!")
        logger.info("Usage: DATABASE_URL=postgresql://... python scripts/reset_and_resync.py [creator_id]")
        return

    # Setup DB
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=CREATOR_ID).first()
        if not creator:
            logger.error(f"Creator not found: {CREATOR_ID}")
            return

        logger.info(f"Found creator: {creator.name} (id: {creator.id})")

        # 1. Reset nuclear
        await reset_nuclear(session, creator)

        # 2. Re-sync with images
        await resync_with_images(session, creator)

    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
