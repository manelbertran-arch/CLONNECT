"""
Import Instagram DM history from the Instagram Conversations API (generic).

Fetches all conversations and messages, creates leads and messages in the DB.
Skips conversations/messages that already exist (deduplication by platform_message_id).

Usage:
    # Iris — dry run
    python3 scripts/import_ig_history.py iris_bertran --dry-run

    # Iris — real import
    python3 scripts/import_ig_history.py iris_bertran

    # Stefano — limit 10
    python3 scripts/import_ig_history.py stefano_bonanno --limit 10

    # Custom cutoff (only messages after this date)
    python3 scripts/import_ig_history.py iris_bertran --since 2025-09-01
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import psycopg2
import requests

# ─── Config ───────────────────────────────────────────────────────────────────
DB_URL = "postgresql://neondb_owner:npg_91lRcgDvZAIy@ep-raspy-truth-agjtq3o5-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"
API_BASE = "https://graph.instagram.com/v21.0"
MESSAGES_PER_CONVERSATION = 500
REQUEST_DELAY = 0.15


def load_creator_config(creator_name: str) -> dict:
    """Load creator config from DB."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, instagram_token, instagram_user_id FROM creators WHERE name = %s",
        (creator_name,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        print(f"ERROR: Creator '{creator_name}' not found in DB")
        sys.exit(1)

    if not row[1]:
        print(f"ERROR: Creator '{creator_name}' has no instagram_token")
        sys.exit(1)

    return {
        "creator_id": str(row[0]),
        "token": row[1],
        "ig_user_id": str(row[2]) if row[2] else None,
    }


def resolve_ig_user_id(token: str) -> str:
    """Get the IG user ID that appears in conversation participants."""
    # First, get /me to find username
    resp = requests.get(f"{API_BASE}/me?fields=id,username&access_token={token}", timeout=15)
    if resp.status_code != 200:
        return None
    me = resp.json()
    me_id = me.get("id")

    # The conversations API may use a different ID format (IGBL vs IGAAT)
    # Fetch first conversation to check which ID appears for us
    resp2 = requests.get(
        f"{API_BASE}/me/conversations?platform=instagram&limit=1&access_token={token}", timeout=15
    )
    if resp2.status_code != 200 or not resp2.json().get("data"):
        return me_id

    conv_id = resp2.json()["data"][0]["id"]
    resp3 = requests.get(
        f"{API_BASE}/{conv_id}?fields=participants&access_token={token}", timeout=15
    )
    if resp3.status_code != 200:
        return me_id

    username = me.get("username", "")
    for p in resp3.json().get("participants", {}).get("data", []):
        if p.get("username") == username:
            return str(p["id"])

    return me_id


def get_all_conversations(token: str, limit: int = 0) -> list:
    """Paginate through all conversations."""
    url = f"{API_BASE}/me/conversations?platform=instagram&limit=25&access_token={token}"
    conversations = []
    pages = 0

    while url and (limit == 0 or len(conversations) < limit):
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  ERROR fetching conversations page {pages + 1}: {resp.status_code} {resp.text[:200]}")
            break

        data = resp.json()
        batch = data.get("data", [])
        conversations.extend(batch)
        pages += 1

        print(f"  Page {pages}: {len(batch)} conversations (total: {len(conversations)})")

        url = data.get("paging", {}).get("next")
        if limit > 0 and len(conversations) >= limit:
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

    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        print(f"    ERROR fetching conversation {conv_id[:30]}...: {resp.status_code}")
        return {"participants": [], "messages": []}

    data = resp.json()
    participants = data.get("participants", {}).get("data", [])

    msg_data = data.get("messages", {})
    messages = list(msg_data.get("data", []))

    next_url = msg_data.get("paging", {}).get("next")
    while next_url and len(messages) < MESSAGES_PER_CONVERSATION:
        time.sleep(REQUEST_DELAY)
        resp2 = requests.get(next_url, timeout=30)
        if resp2.status_code != 200:
            break
        md = resp2.json()
        batch = md.get("data", [])
        if not batch:
            break
        messages.extend(batch)
        next_url = md.get("paging", {}).get("next")

    return {"participants": participants, "messages": messages}


def find_follower_participant(participants: list, my_ig_id: str) -> dict:
    """Find the non-creator participant in a conversation."""
    for p in participants:
        if str(p.get("id")) != my_ig_id:
            return p
    return {}


def ensure_lead(cur, creator_uuid: str, platform_user_id: str, username: str, dry_run: bool) -> str:
    """Get or create lead, return lead UUID."""
    cur.execute(
        "SELECT id FROM leads WHERE creator_id = %s AND platform_user_id = %s AND platform = 'instagram'",
        (creator_uuid, platform_user_id),
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
        (creator_uuid, platform_user_id, username or None),
    )
    return str(cur.fetchone()[0])


def insert_message(cur, lead_id: str, msg: dict, my_ig_id: str, since_dt, dry_run: bool) -> str:
    """Insert a message if it doesn't already exist. Returns 'inserted', 'skipped', or 'old'."""
    mid = msg.get("id", "")
    created_time = msg.get("created_time", "")

    # Parse timestamp
    try:
        created_at = datetime.fromisoformat(created_time.replace("+0000", "+00:00"))
    except Exception:
        created_at = datetime.now(timezone.utc)

    # Skip messages older than cutoff
    if since_dt and created_at < since_dt:
        return "old"

    # Dedup check
    cur.execute("SELECT 1 FROM messages WHERE platform_message_id = %s", (mid,))
    if cur.fetchone():
        return "skipped"

    if dry_run:
        return "inserted"

    from_id = msg.get("from", {}).get("id", "")
    role = "assistant" if str(from_id) == my_ig_id else "user"
    content = msg.get("message") or "[Media/Attachment]"

    cur.execute(
        """
        INSERT INTO messages (id, lead_id, role, content, status, platform_message_id, created_at)
        VALUES (gen_random_uuid(), %s, %s, %s, 'sent', %s, %s)
        """,
        (lead_id, role, content, mid, created_at),
    )
    return "inserted"


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
    parser = argparse.ArgumentParser(description="Import IG DM history for any creator")
    parser.add_argument("creator", help="Creator name (e.g. iris_bertran, stefano_bonanno)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of conversations (0=all)")
    parser.add_argument("--since", type=str, default=None, help="Only import messages after this date (YYYY-MM-DD)")
    args = parser.parse_args()

    since_dt = None
    if args.since:
        since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Load creator config from DB
    print(f"Loading config for '{args.creator}'...")
    config = load_creator_config(args.creator)
    creator_uuid = config["creator_id"]
    token = config["token"]

    # Resolve the IG user ID as it appears in conversation participants
    print("Resolving IG user ID from API...")
    my_ig_id = resolve_ig_user_id(token)
    if not my_ig_id:
        print("ERROR: Could not resolve IG user ID from token")
        sys.exit(1)
    print(f"  IG user ID in conversations: {my_ig_id}")

    mode = "(DRY RUN)" if args.dry_run else "(LIVE)"
    print(f"\n=== IG History Import for {args.creator} {mode} ===")
    print(f"  Creator UUID: {creator_uuid}")
    print(f"  Limit: {args.limit or 'all'}")
    print(f"  Since: {args.since or 'all time'}")
    print()

    # 1. Fetch all conversations
    print("[1/3] Fetching conversations from Instagram API...")
    conversations = get_all_conversations(token, limit=args.limit)
    print(f"  Total conversations: {len(conversations)}\n")

    if not conversations:
        print("No conversations found. Exiting.")
        return

    stats = {
        "conversations_processed": 0,
        "leads_created": 0,
        "leads_existing": 0,
        "messages_inserted": 0,
        "messages_skipped": 0,
        "messages_old": 0,
        "conversations_skipped": 0,
        "errors": 0,
    }

    print(f"[2/3] Processing {len(conversations)} conversations...")
    for i, conv in enumerate(conversations):
        conv_id = conv["id"]
        try:
            time.sleep(REQUEST_DELAY)
            conv_data = get_conversation_messages(conv_id, token)

            participants = conv_data["participants"]
            messages = conv_data["messages"]

            follower = find_follower_participant(participants, my_ig_id)
            if not follower:
                if (i + 1) % 500 == 0:
                    print(f"  [{i+1}/{len(conversations)}] SKIP — no follower participant found")
                stats["conversations_skipped"] += 1
                continue

            follower_id = str(follower["id"])
            follower_username = follower.get("username", "")

            # Open fresh DB connection per conversation (Neon pooler drops idle)
            conn = psycopg2.connect(DB_URL)
            conn.autocommit = False
            cur = conn.cursor()

            try:
                # Check if lead exists
                cur.execute(
                    "SELECT id FROM leads WHERE creator_id = %s AND platform_user_id = %s AND platform = 'instagram'",
                    (creator_uuid, follower_id),
                )
                lead_existed = cur.fetchone() is not None

                lead_id = ensure_lead(cur, creator_uuid, follower_id, follower_username, args.dry_run)

                if lead_existed:
                    stats["leads_existing"] += 1
                else:
                    stats["leads_created"] += 1

                # Insert messages (oldest first)
                inserted = 0
                skipped = 0
                old = 0
                for msg in reversed(messages):
                    result = insert_message(cur, lead_id, msg, my_ig_id, since_dt, args.dry_run)
                    if result == "inserted":
                        inserted += 1
                    elif result == "skipped":
                        skipped += 1
                    else:
                        old += 1

                stats["messages_inserted"] += inserted
                stats["messages_skipped"] += skipped
                stats["messages_old"] += old
                stats["conversations_processed"] += 1

                if not args.dry_run and inserted > 0:
                    update_lead_timestamps(cur, lead_id)

                if not args.dry_run:
                    conn.commit()

                status = "EXISTS" if lead_existed else "NEW"
                if inserted > 0 or (i + 1) % 200 == 0:
                    print(
                        f"  [{i+1}/{len(conversations)}] @{follower_username or follower_id} "
                        f"[{status}] — {inserted} new, {skipped} dupes, {old} old",
                        flush=True,
                    )

            except Exception as db_err:
                err_msg = str(db_err).split("\n")[0][:120]
                print(f"  [{i+1}/{len(conversations)}] DB ERROR: {err_msg}")
                stats["errors"] += 1
                try:
                    conn.rollback()
                except Exception:
                    pass
            finally:
                try:
                    cur.close()
                    conn.close()
                except Exception:
                    pass

        except Exception as e:
            err_msg = str(e).split("\n")[0][:120]
            print(f"  [{i+1}/{len(conversations)}] ERROR: {err_msg}")
            stats["errors"] += 1
            continue

    # Summary
    print(f"\n[3/3] Import complete!")
    print(f"  Conversations processed: {stats['conversations_processed']}")
    print(f"  Conversations skipped:   {stats['conversations_skipped']}")
    print(f"  Leads created:           {stats['leads_created']}")
    print(f"  Leads existing:          {stats['leads_existing']}")
    print(f"  Messages inserted:       {stats['messages_inserted']}")
    print(f"  Messages skipped (dupe): {stats['messages_skipped']}")
    print(f"  Messages too old:        {stats['messages_old']}")
    print(f"  Errors:                  {stats['errors']}")


if __name__ == "__main__":
    main()
