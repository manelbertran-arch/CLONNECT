#!/usr/bin/env python3
"""
Instagram DM Sync - Creates COMPLETE leads from the start.

Usage: DATABASE_URL=postgresql://... python scripts/sync_instagram_dms.py

This script syncs Instagram DM conversations to the database, creating leads
with COMPLETE data from the beginning:
- username
- full_name (display name)
- profile_pic_url
- categorized status based on message history
- messages with link_previews generated inline

NO BACKFILLS NEEDED - everything is done in one pass.

Rate Limits:
- Instagram Graph API: 200 requests/hour per token
- This script uses 180/hour leaving 10% margin
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.instagram_rate_limiter import get_instagram_rate_limiter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Rate limiter global
rate_limiter = get_instagram_rate_limiter()

# Config
CREATOR_ID = os.environ.get("CREATOR_ID", "stefano_bonanno")
START_FROM_CONVERSATION = int(os.environ.get("START_FROM", "0"))
API_BASE = "https://graph.instagram.com/v21.0"
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", "365"))

# Optimizations
CONSECUTIVE_403_LIMIT = int(os.environ.get("CONSECUTIVE_403_LIMIT", "10"))
BLACKLIST_FILE = Path(__file__).parent / "data" / "ig_403_blacklist.json"

# URL pattern for link preview
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)


def load_blacklist() -> set:
    """Load conversation IDs that previously returned 403."""
    if BLACKLIST_FILE.exists():
        try:
            with open(BLACKLIST_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("conversation_ids", []))
        except Exception as e:
            logger.warning(f"Error loading blacklist: {e}")
    return set()


def save_blacklist(conv_ids: set):
    """Save conversation IDs that returned 403."""
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


def categorize_lead_by_history(oldest_message_date: Optional[datetime]) -> str:
    """
    Categorize lead based on conversation history age.

    - No history or < 7 days: "new"
    - 7-30 days: "returning"
    - > 30 days: "existing_customer"
    """
    if not oldest_message_date:
        return "new"

    now = datetime.now(timezone.utc)
    age_days = (now - oldest_message_date).days

    if age_days < 7:
        return "new"
    elif age_days < 30:
        return "returning"
    else:
        return "existing_customer"


async def extract_link_preview(url: str, client) -> Optional[Dict]:
    """Extract Open Graph metadata from a URL for link preview."""
    try:
        # Skip CDN URLs
        if "cdninstagram.com" in url or "fbcdn.net" in url:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)",
            "Accept": "text/html",
        }

        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=5.0)
        if resp.status_code != 200:
            return None

        html = resp.text
        preview = {"url": str(resp.url), "original_url": url}

        # Extract og:title
        title_match = re.search(
            r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        if title_match:
            preview["title"] = title_match.group(1).strip()[:200]

        # Extract og:image
        img_match = re.search(
            r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        if img_match:
            preview["image"] = img_match.group(1).strip()

        # Fallback to <title> tag
        if "title" not in preview:
            title_tag = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            if title_tag:
                preview["title"] = title_tag.group(1).strip()[:200]

        return preview if preview.get("title") or preview.get("image") else None

    except Exception:
        return None


async def sync_dms():
    """Main sync function - creates COMPLETE leads."""
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

        ACCESS_TOKEN = creator.instagram_token
        IG_USER_ID = creator.instagram_user_id or creator.instagram_page_id

        if not ACCESS_TOKEN:
            logger.error(f"Creator {CREATOR_ID} has no instagram_token in DB")
            return
        if not IG_USER_ID:
            logger.error(f"Creator {CREATOR_ID} has no instagram_user_id/page_id in DB")
            return

        logger.info(f"Creator: {creator.name} (id: {creator.id})")
        logger.info(f"IG_USER_ID: {IG_USER_ID}")

        # Stats
        stats = {
            "conversations_fetched": 0,
            "leads_created": 0,
            "leads_updated": 0,
            "leads_skipped": 0,
            "messages_saved": 0,
            "link_previews_generated": 0,
            "convs_blacklisted": 0,
            "convs_no_messages": 0,
        }

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
                        logger.warning("Rate limit hit (429). Waiting 60s...")
                        await asyncio.sleep(60)
                        return await rate_limited_request(url, params)
                    return resp
                except Exception as e:
                    logger.error(f"Request error: {e}")
                    rate_limiter.record_call(CREATOR_ID, url[:50], 500)
                    raise

            async def fetch_user_profile(user_id: str) -> Optional[Dict]:
                """Fetch user profile data (name, profile_pic)."""
                try:
                    resp = await rate_limited_request(
                        f"{API_BASE}/{user_id}",
                        params={
                            "fields": "id,username,name,profile_picture_url",
                            "access_token": ACCESS_TOKEN,
                        },
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    return None
                except Exception:
                    return None

            # Fetch all conversations with pagination
            logger.info("Fetching conversations...")
            conversations = []
            next_url = f"{API_BASE}/{IG_USER_ID}/conversations"
            params = {"platform": "instagram", "access_token": ACCESS_TOKEN, "limit": 50}

            page_num = 0
            while next_url:
                page_num += 1
                logger.info(f"  Page {page_num}...")

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
                logger.info(f"    Got {len(batch)} (total: {len(conversations)})")

                paging = data.get("paging", {})
                next_url = paging.get("next")

                if not batch:
                    break

            stats["conversations_fetched"] = len(conversations)
            logger.info(f"Found {len(conversations)} total conversations")

            if START_FROM_CONVERSATION > 0:
                logger.info(f"Skipping first {START_FROM_CONVERSATION} conversations")
                conversations = conversations[START_FROM_CONVERSATION:]

            # Process each conversation
            start_time = time.time()
            early_stopped = False

            for i, conv in enumerate(conversations):
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                # Skip blacklisted conversations
                if conv_id in blacklist:
                    stats["convs_blacklisted"] += 1
                    continue

                actual_index = i + START_FROM_CONVERSATION

                # Progress every 20 conversations
                if i > 0 and i % 20 == 0:
                    elapsed = time.time() - start_time
                    rate = i / (elapsed / 60) if elapsed > 0 else 0
                    remaining = len(conversations) - i
                    eta_min = remaining / rate if rate > 0 else 0
                    logger.info(f"\n{'='*50}")
                    logger.info(f"PROGRESS: {actual_index}/{stats['conversations_fetched']}")
                    logger.info(f"  Speed: {rate:.1f} conv/min | ETA: {eta_min:.0f} min")
                    logger.info(f"  Leads created: {stats['leads_created']}")
                    logger.info(f"{'='*50}\n")

                # Fetch messages for this conversation
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
                        new_403s.add(conv_id)
                        consecutive_403 += 1
                        logger.warning(
                            f"  Conv {actual_index}: 403 (consecutive: {consecutive_403})"
                        )

                        if consecutive_403 >= CONSECUTIVE_403_LIMIT:
                            logger.warning(f"EARLY STOP: {consecutive_403} consecutive 403s")
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

                if early_stopped:
                    break

                # RULE: Never create lead with 0 messages
                if not messages:
                    stats["convs_no_messages"] += 1
                    continue

                # Find the follower (other person in conversation)
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

                # Filter messages by date and count valid ones
                valid_messages = []
                oldest_date = None
                newest_date = None  # For last_contact_at

                for msg in messages:
                    msg_text = msg.get("message", "")
                    if not msg_text:
                        continue

                    msg_time_str = msg.get("created_time")
                    created_at = None

                    if msg_time_str:
                        try:
                            created_at = datetime.fromisoformat(
                                msg_time_str.replace("+0000", "+00:00")
                            )
                            if created_at < cutoff_date:
                                continue

                            # Track oldest for categorization
                            if oldest_date is None or created_at < oldest_date:
                                oldest_date = created_at

                            # Track newest for last_contact_at
                            if newest_date is None or created_at > newest_date:
                                newest_date = created_at
                        except Exception:
                            pass

                    valid_messages.append(
                        {
                            "id": msg.get("id"),
                            "message": msg_text,
                            "from": msg.get("from", {}),
                            "created_at": created_at,
                        }
                    )

                # RULE: Must have at least 1 valid message
                if not valid_messages:
                    stats["convs_no_messages"] += 1
                    continue

                # Check if lead already exists
                lead = (
                    session.query(Lead)
                    .filter_by(
                        creator_id=creator.id,
                        platform="instagram",
                        platform_user_id=follower_id,
                    )
                    .first()
                )

                if lead:
                    # Lead exists - check if we need to update profile data or timestamps
                    needs_update = False

                    # Update profile data if missing
                    if not lead.profile_pic_url or not lead.full_name:
                        profile = await fetch_user_profile(follower_id)
                        if profile:
                            if not lead.full_name and profile.get("name"):
                                lead.full_name = profile["name"]
                                needs_update = True
                            if not lead.profile_pic_url and profile.get("profile_picture_url"):
                                lead.profile_pic_url = profile["profile_picture_url"]
                                needs_update = True

                    # Update last_contact_at if we have newer messages
                    if newest_date:
                        if not lead.last_contact_at or newest_date > lead.last_contact_at:
                            lead.last_contact_at = newest_date
                            needs_update = True

                    # Update first_contact_at if we have older messages
                    if oldest_date:
                        if not lead.first_contact_at or oldest_date < lead.first_contact_at:
                            lead.first_contact_at = oldest_date
                            needs_update = True

                    if needs_update:
                        session.commit()
                        stats["leads_updated"] += 1
                        logger.info(f"  Updated @{follower_username}")
                    else:
                        stats["leads_skipped"] += 1

                else:
                    # CREATE COMPLETE LEAD
                    # 1. Fetch profile data
                    profile = await fetch_user_profile(follower_id)

                    full_name = ""
                    profile_pic_url = ""

                    if profile:
                        full_name = profile.get("name", "")
                        profile_pic_url = profile.get("profile_picture_url", "")
                        if profile.get("username"):
                            follower_username = profile["username"]

                    # 2. Categorize by history
                    status = categorize_lead_by_history(oldest_date)

                    # 3. Create lead with ALL data + correct timestamps
                    lead = Lead(
                        creator_id=creator.id,
                        platform="instagram",
                        platform_user_id=follower_id,
                        username=follower_username,
                        full_name=full_name,
                        profile_pic_url=profile_pic_url,
                        status=status,
                        purchase_intent=(
                            0.1
                            if status == "returning"
                            else (0.2 if status == "existing_customer" else 0.0)
                        ),
                        first_contact_at=oldest_date,  # Real first message date
                        last_contact_at=newest_date,  # Real last message date
                    )
                    session.add(lead)
                    session.commit()
                    stats["leads_created"] += 1

                    logger.info(
                        f"  Created @{follower_username} "
                        f"(name={full_name[:20] if full_name else 'N/A'}, "
                        f"pic={'Yes' if profile_pic_url else 'No'}, "
                        f"status={status}, "
                        f"last_msg={newest_date.strftime('%Y-%m-%d') if newest_date else 'N/A'})"
                    )

                # Save messages with link previews
                for msg_data in valid_messages:
                    msg_id = msg_data["id"]
                    msg_text = msg_data["message"]
                    msg_from = msg_data["from"]
                    created_at = msg_data["created_at"]

                    # Check if message exists
                    existing = session.query(Message).filter_by(platform_message_id=msg_id).first()

                    if existing:
                        continue

                    is_from_creator = msg_from.get("id") == IG_USER_ID
                    role = "assistant" if is_from_creator else "user"

                    # Generate link preview if message has URLs
                    msg_metadata = None
                    urls = URL_PATTERN.findall(msg_text)

                    if urls:
                        preview = await extract_link_preview(urls[0], client)
                        if preview:
                            msg_metadata = {"link_preview": preview}
                            stats["link_previews_generated"] += 1

                    new_msg = Message(
                        lead_id=lead.id,
                        role=role,
                        content=msg_text,
                        status="sent",
                        platform_message_id=msg_id,
                        approved_by="historical_sync",
                        msg_metadata=msg_metadata,
                    )

                    if created_at:
                        new_msg.created_at = created_at

                    session.add(new_msg)
                    stats["messages_saved"] += 1

                session.commit()

        # Save updated blacklist
        final_blacklist = blacklist.union(new_403s)
        if new_403s:
            save_blacklist(final_blacklist)

        # Summary
        logger.info("\n" + "=" * 50)
        logger.info("SYNC COMPLETE")
        logger.info("=" * 50)
        logger.info(f"Conversations fetched: {stats['conversations_fetched']}")
        logger.info(f"Conversations blacklisted: {stats['convs_blacklisted']}")
        logger.info(f"Conversations without messages: {stats['convs_no_messages']}")
        logger.info(f"Leads created: {stats['leads_created']}")
        logger.info(f"Leads updated: {stats['leads_updated']}")
        logger.info(f"Leads skipped: {stats['leads_skipped']}")
        logger.info(f"Messages saved: {stats['messages_saved']}")
        logger.info(f"Link previews generated: {stats['link_previews_generated']}")

        if early_stopped:
            logger.info("(Early stopped due to consecutive 403s)")

    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(sync_dms())
