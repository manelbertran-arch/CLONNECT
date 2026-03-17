"""
Import Iris's Instagram DM history from the Instagram Conversations API.

Fetches all conversations and messages, creates leads and messages in the DB.
Skips conversations/messages that already exist (deduplication by platform_message_id).

Usage:
    # Dry run (no DB writes)
    python3 scripts/import_iris_ig_history.py --dry-run

    # Real import
    python3 scripts/import_iris_ig_history.py

    # Limit to N conversations (for testing)
    python3 scripts/import_iris_ig_history.py --limit 10
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import psycopg2
import requests

# ─── Config ───────────────────────────────────────────────────────────────────
DB_URL = "postgresql://neondb_owner:npg_91lRcgDvZAIy@ep-raspy-truth-agjtq3o5-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"
IGAAT_TOKEN = "IGAAT0qmmGnyJBZAGFIVlRnQ3ZAYSHNyMm51VENSOFBqNVNzTUVUVGxCMk5QWlFzR29rU01ZAN0ZA6QnBzRWdwVmx6ZAzByQzY3Tm9iZAGIxcU8xOFB3OTl4OUVhOExDM3dCODBGcGZAiRkQ0QWdRQjhpWk40TWJB"
IRIS_CREATOR_ID = "8e9d1705-4772-40bd-83b1-c6821c5593bf"
IRIS_IG_USER_ID = "17841400999933058"  # iraais5

API_BASE = "https://graph.instagram.com/v21.0"
MESSAGES_PER_CONVERSATION = 500  # Max messages to fetch per conversation
REQUEST_DELAY = 0.15  # Seconds between API calls to avoid rate limits


def get_all_conversations(token: str, limit: int = 0) -> list:
    """Paginate through all conversations."""
    url = f"{API_BASE}/me/conversations?platform=instagram&limit=25&access_token={token}"
    conversations = []
    pages = 0

    while url and (limit == 0 or len(conversations) < limit):
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"  ERROR fetching conversations page {pages + 1}: {resp.status_code} {resp.text[:200]}")
            break

        data = resp.json()
        batch = data.get("data", [])
        conversations.extend(batch)
        pages += 1

        remaining = limit - len(conversations) if limit > 0 else None
        print(f"  Page {pages}: {len(batch)} conversations (total: {len(conversations)})")

        url = data.get("paging", {}).get("next")
        if url and remaining is not None and remaining <= 0:
            break

        time.sleep(REQUEST_DELAY)

    return conversations[:limit] if limit > 0 else conversations


def get_conversation_messages(conv_id: str, token: str) -> dict:
    """Fetch conversation participants and messages."""
    url = (
        f"{API_BASE}/{conv_id}"
        f"?fields=participants,messages{{id,created_time,from,to,message}}"
        f"&access_token={token}"
    )

    participants = []
    messages = []

    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"    ERROR fetching conversation {conv_id[:30]}...: {resp.status_code}")
        return {"participants": [], "messages": []}

    data = resp.json()
    participants = data.get("participants", {}).get("data", [])

    # First page of messages
    msg_data = data.get("messages", {})
    messages.extend(msg_data.get("data", []))

    # Paginate messages
    next_url = msg_data.get("paging", {}).get("next")
    msg_pages = 1
    while next_url and len(messages) < MESSAGES_PER_CONVERSATION:
        time.sleep(REQUEST_DELAY)
        resp2 = requests.get(next_url)
        if resp2.status_code != 200:
            break
        md = resp2.json()
        batch = md.get("data", [])
        if not batch:
            break
        messages.extend(batch)
        msg_pages += 1
        next_url = md.get("paging", {}).get("next")

    return {"participants": participants, "messages": messages}


def find_follower_participant(participants: list) -> dict:
    """Find the non-Iris participant in a conversation."""
    for p in participants:
        if str(p.get("id")) != IRIS_IG_USER_ID:
            return p
    return {}


def ensure_lead(cur, platform_user_id: str, username: str, dry_run: bool) -> str:
    """Get or create lead, return lead UUID."""
    cur.execute(
        "SELECT id FROM leads WHERE creator_id = %s AND platform_user_id = %s AND platform = 'instagram'",
        (IRIS_CREATOR_ID, platform_user_id),
    )
    row = cur.fetchone()
    if row:
        return str(row[0])

    if dry_run:
        return f"DRY-RUN-{platform_user_id}"

    cur.execute(
        """
        INSERT INTO leads (id, creator_id, platform, platform_user_id, username, status, source, first_contact_at, last_contact_at)
        VALUES (gen_random_uuid(), %s, 'instagram', %s, %s, 'nuevo', 'ig_import', now(), now())
        RETURNING id
        """,
        (IRIS_CREATOR_ID, platform_user_id, username or None),
    )
    return str(cur.fetchone()[0])


def insert_message(cur, lead_id: str, msg: dict, dry_run: bool) -> bool:
    """Insert a message if it doesn't already exist. Returns True if inserted."""
    mid = msg.get("id", "")

    # Dedup check
    cur.execute("SELECT 1 FROM messages WHERE platform_message_id = %s", (mid,))
    if cur.fetchone():
        return False

    if dry_run:
        return True

    from_id = msg.get("from", {}).get("id", "")
    role = "assistant" if str(from_id) == IRIS_IG_USER_ID else "user"
    content = msg.get("message") or "[Media/Attachment]"
    created_time = msg.get("created_time", "")

    # Parse ISO timestamp
    try:
        created_at = datetime.fromisoformat(created_time.replace("+0000", "+00:00"))
    except Exception:
        created_at = datetime.now(timezone.utc)

    cur.execute(
        """
        INSERT INTO messages (id, lead_id, role, content, status, platform_message_id, created_at)
        VALUES (gen_random_uuid(), %s, %s, %s, 'sent', %s, %s)
        """,
        (lead_id, role, content or None, mid, created_at),
    )
    return True


def update_lead_timestamps(cur, lead_id: str):
    """Update lead first/last contact based on its messages."""
    cur.execute(
        """
        UPDATE leads SET
            first_contact_at = (SELECT min(created_at) FROM messages WHERE lead_id = %s),
            last_contact_at = (SELECT max(created_at) FROM messages WHERE lead_id = %s)
        WHERE id = %s
        """,
        (lead_id, lead_id, lead_id),
    )


def main():
    parser = argparse.ArgumentParser(description="Import Iris IG DM history")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of conversations (0=all)")
    args = parser.parse_args()

    print(f"=== Iris IG History Import {'(DRY RUN)' if args.dry_run else '(LIVE)'} ===")
    print(f"Limit: {args.limit or 'all'}")
    print()

    # 1. Fetch all conversations
    print("[1/3] Fetching conversations from Instagram API...")
    conversations = get_all_conversations(IGAAT_TOKEN, limit=args.limit)
    print(f"  Total conversations: {len(conversations)}\n")

    if not conversations:
        print("No conversations found. Exiting.")
        return

    # 2. Connect to DB
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    stats = {
        "conversations_processed": 0,
        "leads_created": 0,
        "leads_existing": 0,
        "messages_inserted": 0,
        "messages_skipped": 0,
        "conversations_skipped": 0,
        "errors": 0,
    }

    try:
        # 3. Process each conversation
        print(f"[2/3] Processing {len(conversations)} conversations...")
        for i, conv in enumerate(conversations):
            conv_id = conv["id"]
            try:
                time.sleep(REQUEST_DELAY)
                conv_data = get_conversation_messages(conv_id, IGAAT_TOKEN)

                participants = conv_data["participants"]
                messages = conv_data["messages"]

                follower = find_follower_participant(participants)
                if not follower:
                    print(f"  [{i+1}/{len(conversations)}] SKIP — no follower participant found")
                    stats["conversations_skipped"] += 1
                    continue

                follower_id = str(follower["id"])
                follower_username = follower.get("username", "")

                # Check if lead exists
                cur.execute(
                    "SELECT id FROM leads WHERE creator_id = %s AND platform_user_id = %s AND platform = 'instagram'",
                    (IRIS_CREATOR_ID, follower_id),
                )
                lead_existed = cur.fetchone() is not None

                lead_id = ensure_lead(cur, follower_id, follower_username, args.dry_run)

                if lead_existed:
                    stats["leads_existing"] += 1
                else:
                    stats["leads_created"] += 1

                # Insert messages (oldest first)
                inserted = 0
                skipped = 0
                for msg in reversed(messages):
                    if insert_message(cur, lead_id, msg, args.dry_run):
                        inserted += 1
                    else:
                        skipped += 1

                stats["messages_inserted"] += inserted
                stats["messages_skipped"] += skipped
                stats["conversations_processed"] += 1

                # Update lead timestamps
                if not args.dry_run and inserted > 0:
                    update_lead_timestamps(cur, lead_id)

                # Commit after each conversation
                if not args.dry_run:
                    conn.commit()

                status = "EXISTS" if lead_existed else "NEW"
                if inserted > 0 or (i + 1) % 100 == 0:
                    print(
                        f"  [{i+1}/{len(conversations)}] @{follower_username or follower_id} "
                        f"[{status}] — {inserted} new msgs, {skipped} dupes",
                        flush=True,
                    )

            except Exception as e:
                err_msg = str(e).split("\n")[0][:120]
                print(f"  [{i+1}/{len(conversations)}] ERROR: {err_msg}")
                stats["errors"] += 1
                if not args.dry_run:
                    conn.rollback()
                continue

        # 4. Summary
        print(f"\n[3/3] Import complete!")
        print(f"  Conversations processed: {stats['conversations_processed']}")
        print(f"  Conversations skipped:   {stats['conversations_skipped']}")
        print(f"  Leads created:           {stats['leads_created']}")
        print(f"  Leads existing:          {stats['leads_existing']}")
        print(f"  Messages inserted:       {stats['messages_inserted']}")
        print(f"  Messages skipped (dupe): {stats['messages_skipped']}")
        print(f"  Errors:                  {stats['errors']}")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
