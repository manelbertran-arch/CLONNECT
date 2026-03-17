"""
Recovery script for lost DMs from unmatched_webhooks.
Uses psycopg2 + httpx only (no SQLAlchemy) so it runs via `railway run python3`.

Run: railway run python3 scripts/recover_unmatched_dms.py
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("recover_dms")

CREATOR_NAME = "iris_bertran"
LOOKBACK_HOURS = 72

# All known iris IDs — must not create leads for these
IRIS_KNOWN_IDS = {
    "34327644223517531",   # ASID from IGAAT /me endpoint
    "17841400999933058",   # IGSID in conversation participants
    "17841400506734756",   # legacy webhook entry.id
}

API_BASE = "https://graph.instagram.com/v21.0"


async def fetch_conversations(token: str, ig_user_id: str, limit: int = 50):
    """Fetch conversations + messages from Instagram API."""
    conversations = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch conversation list
        resp = await client.get(
            f"{API_BASE}/{ig_user_id}/conversations",
            params={"fields": "id,participants", "access_token": token, "limit": limit},
        )
        if resp.status_code != 200:
            logger.error(f"Conversations API error: {resp.status_code} {resp.text[:200]}")
            return []

        conv_list = resp.json().get("data", [])
        logger.info(f"Fetched {len(conv_list)} conversation IDs")

        for conv in conv_list:
            conv_id = conv.get("id")
            if not conv_id:
                continue
            try:
                msg_resp = await client.get(
                    f"{API_BASE}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time,attachments,story,share",
                        "access_token": token,
                        "limit": 50,
                    },
                )
                if msg_resp.status_code == 200:
                    conv["messages"] = {"data": msg_resp.json().get("data", [])}
                else:
                    conv["messages"] = {"data": []}
                conversations.append(conv)
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Error fetching messages for {conv_id}: {e}")
                conv["messages"] = {"data": []}
                conversations.append(conv)

    return conversations


def extract_media_content(msg: dict) -> tuple[str, dict]:
    """Returns (content_text, metadata_extras)."""
    story = msg.get("story")
    share = msg.get("share")
    attachments = (msg.get("attachments") or {}).get("data", [])
    text = msg.get("message", "")

    meta = {}
    if story:
        link = story.get("link") or story.get("url")
        meta = {"type": "story_mention"}
        if link:
            meta["url"] = link
        return text or "Mentioned you in their story", meta
    if share:
        link = share.get("link") or share.get("url")
        meta = {"type": "shared_reel" if link and "reel" in link.lower() else "share"}
        if link:
            meta["url"] = link
        return text or ("Shared a reel" if meta["type"] == "shared_reel" else "Shared a post"), meta
    if attachments:
        att = attachments[0]
        att_type = (att.get("type") or "").lower()
        type_map = {
            "image": ("Sent a photo", "image"),
            "video": ("Sent a video", "video"),
            "audio": ("Sent a voice message", "audio"),
            "sticker": ("Sent a sticker", "sticker"),
        }
        label, mtype = type_map.get(att_type, ("Sent an attachment", "unknown"))
        meta = {"type": mtype}
        url = (att.get("payload") or {}).get("url") or att.get("url")
        if url:
            meta["url"] = url
        return text or label, meta
    return text or "[Media/Attachment]", meta


async def run():
    DATABASE_URL = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Get creator info
    cur.execute(
        "SELECT id, instagram_token, instagram_user_id FROM creators WHERE name = %s",
        (CREATOR_NAME,),
    )
    creator = cur.fetchone()
    if not creator or not creator["instagram_token"]:
        logger.error(f"Creator {CREATOR_NAME} not found or has no token")
        return

    creator_uuid = creator["id"]
    token = creator["instagram_token"]
    ig_user_id = creator["instagram_user_id"]  # 34327644223517531
    logger.info(f"Creator UUID={creator_uuid}, ig_user_id={ig_user_id}")

    # 2. Get unmatched webhooks
    cur.execute(
        "SELECT id, received_at, instagram_ids FROM unmatched_webhooks WHERE resolved = false ORDER BY received_at ASC"
    )
    unmatched = cur.fetchall()
    logger.info(f"Unmatched webhooks to resolve: {len(unmatched)}")

    sender_ids = set()
    unmatched_record_ids = []
    for row in unmatched:
        unmatched_record_ids.append(row["id"])
        for ig_id in (row["instagram_ids"] or []):
            if ig_id not in IRIS_KNOWN_IDS:
                sender_ids.add(ig_id)
    logger.info(f"Unique sender IDs: {sender_ids}")

    # 3. Get existing message IDs (last 72h)
    since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    cur.execute(
        """
        SELECT m.platform_message_id
        FROM messages m
        JOIN leads l ON l.id = m.lead_id
        WHERE l.creator_id = %s
          AND m.platform_message_id IS NOT NULL
          AND m.created_at >= %s
        """,
        (creator_uuid, since),
    )
    existing_msg_ids = {r["platform_message_id"] for r in cur.fetchall()}
    logger.info(f"Existing messages in DB (last {LOOKBACK_HOURS}h): {len(existing_msg_ids)}")

    # 4. Fetch conversations from Instagram
    conversations = await fetch_conversations(token, ig_user_id, limit=50)
    logger.info(f"Total conversations from API: {len(conversations)}")

    total_inserted = 0
    total_convs = 0

    for conv in conversations:
        conv_id = conv.get("id", "")
        participants = conv.get("participants", {}).get("data", [])
        messages_data = conv.get("messages", {}).get("data", [])

        # Identify follower
        follower_id = None
        for p in participants:
            pid = p.get("id", "")
            if pid and pid not in IRIS_KNOWN_IDS:
                follower_id = pid
                break
        if not follower_id:
            continue

        # Only process if in sender_ids (skip if none found in unmatched)
        if sender_ids and follower_id not in sender_ids:
            continue

        total_convs += 1
        logger.info(f"--- Conversation with {follower_id} ({len(messages_data)} messages) ---")

        # Find or create lead
        cur.execute(
            """
            SELECT id FROM leads
            WHERE creator_id = %s AND platform_user_id = ANY(%s)
            LIMIT 1
            """,
            (creator_uuid, [f"ig_{follower_id}", follower_id]),
        )
        lead_row = cur.fetchone()

        if not lead_row:
            # Only create lead if there's at least one message FROM follower
            has_user_msg = any(
                m.get("from", {}).get("id") == follower_id and m.get("id")
                for m in messages_data
            )
            if not has_user_msg:
                logger.info(f"  Skipping {follower_id}: no user messages")
                continue

            lead_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO leads (id, creator_id, platform, platform_user_id, status, context, created_at)
                VALUES (%s, %s, 'instagram', %s, 'nuevo', %s, NOW())
                """,
                (lead_id, creator_uuid, follower_id, psycopg2.extras.Json({"source": "dm_recovery"})),
            )
            conn.commit()
            logger.info(f"  Created new lead {lead_id} for {follower_id}")
        else:
            lead_id = str(lead_row["id"])

        # Insert missing messages
        conv_inserted = 0
        for msg in messages_data:
            msg_id = msg.get("id", "")
            if not msg_id or msg_id in existing_msg_ids:
                continue

            # Double-check DB
            cur.execute("SELECT 1 FROM messages WHERE platform_message_id = %s LIMIT 1", (msg_id,))
            if cur.fetchone():
                existing_msg_ids.add(msg_id)
                continue

            msg_from_id = msg.get("from", {}).get("id", "")
            role = "user" if msg_from_id == follower_id else "assistant"

            created_time_str = msg.get("created_time", "")
            created_at = None
            if created_time_str:
                try:
                    created_at = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
                except Exception:
                    created_at = datetime.now(timezone.utc)

            content, media_meta = extract_media_content(msg)
            metadata = {
                "source": "dm_recovery",
                "conversation_id": conv_id,
                "original_from_id": msg_from_id,
                **media_meta,
            }

            try:
                new_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO messages
                        (id, lead_id, role, content, platform_message_id, status, msg_metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'sent', %s, %s)
                    """,
                    (
                        new_id,
                        lead_id,
                        role,
                        content,
                        msg_id,
                        psycopg2.extras.Json(metadata),
                        created_at,
                    ),
                )
                # Update lead last_contact_at
                if role == "user" and created_at:
                    cur.execute(
                        """
                        UPDATE leads SET last_contact_at = %s
                        WHERE id = %s AND (last_contact_at IS NULL OR last_contact_at < %s)
                        """,
                        (created_at, lead_id, created_at),
                    )
                conn.commit()
                existing_msg_ids.add(msg_id)
                conv_inserted += 1
                total_inserted += 1
                logger.info(f"  [{role}] {content[:70]!r} ({created_at})")
            except Exception as e:
                conn.rollback()
                logger.error(f"  Insert failed for {msg_id}: {e}")

        logger.info(f"  Inserted {conv_inserted} messages for {follower_id}")

    # 5. Mark all unmatched webhooks as resolved
    if unmatched_record_ids:
        cur.execute(
            """
            UPDATE unmatched_webhooks
            SET resolved = true,
                resolved_to_creator_id = %s,
                resolved_at = NOW(),
                notes = 'Recovered via recover_unmatched_dms.py'
            WHERE id = ANY(%s)
            """,
            (creator_uuid, unmatched_record_ids),
        )
        conn.commit()
        logger.info(f"Marked {len(unmatched_record_ids)} unmatched_webhooks as resolved")

    conn.close()
    logger.info("=" * 60)
    logger.info("RECOVERY COMPLETE")
    logger.info(f"  Conversations with matched senders: {total_convs}")
    logger.info(f"  Messages inserted: {total_inserted}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())
