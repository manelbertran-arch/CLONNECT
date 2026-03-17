#!/usr/bin/env python3
"""
Bulk sync Instagram profile photos and names from multiple sources:
1. Conversations API participants (username mapping)
2. Graph API /{user_id} (limited by consent)
3. Public Instagram API /web_profile_info (works for public profiles)

Usage:
    python3 scripts/bulk_sync_ig_profiles.py iris_bertran [--limit 500]
    python3 scripts/bulk_sync_ig_profiles.py --all
"""
import os
import sys
import json
import time
import requests

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Iris IGAAT token
TOKENS = {}


def get_token(creator_name: str) -> str:
    """Get IG token from DB."""
    if creator_name in TOKENS:
        return TOKENS[creator_name]
    import sqlalchemy
    from sqlalchemy import text
    engine = sqlalchemy.create_engine(DATABASE_URL)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT instagram_token, instagram_user_id FROM creators WHERE name = :name"),
            {"name": creator_name}
        ).fetchone()
        if row and row[0]:
            TOKENS[creator_name] = row[0]
            return row[0]
    return ""


def fetch_ig_conversations_usernames(access_token: str, limit: int = 500) -> dict:
    """
    Fetch conversations and extract participant username→user_id mapping.
    Returns: {user_id: username}
    """
    if access_token.startswith("EAA"):
        api_base = "https://graph.facebook.com/v21.0"
    else:
        api_base = "https://graph.instagram.com/v21.0"

    url = f"{api_base}/me/conversations"
    params = {
        "fields": "id,participants",
        "access_token": access_token,
        "limit": 50,
    }

    mapping = {}  # user_id -> username
    page = 0
    max_pages = limit // 50 + 1

    while url and page < max_pages:
        try:
            if page == 0:
                resp = requests.get(url, params=params, timeout=30)
            else:
                resp = requests.get(url, timeout=30)

            if resp.status_code != 200:
                print(f"  API error at page {page}: {resp.status_code} - {resp.text[:200]}")
                break

            data = resp.json()
            convs = data.get("data", [])
            if not convs:
                break

            for conv in convs:
                for p in conv.get("participants", {}).get("data", []):
                    uid = p.get("id", "")
                    uname = p.get("username", "")
                    if uid and uname:
                        mapping[uid] = uname

            url = data.get("paging", {}).get("next")
            page += 1
            time.sleep(0.2)

        except Exception as e:
            print(f"  Error at page {page}: {e}")
            break

    return mapping


def fetch_public_ig_profile(username: str) -> dict:
    """Fetch profile from public Instagram API."""
    try:
        resp = requests.get(
            f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers={
                "User-Agent": "Instagram 76.0.0.15.395 Android",
                "x-ig-app-id": "936619743392459",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            user = resp.json().get("data", {}).get("user", {})
            if user:
                return {
                    "username": user.get("username", ""),
                    "full_name": user.get("full_name", ""),
                    "profile_pic": user.get("profile_pic_url_hd") or user.get("profile_pic_url", ""),
                }
        elif resp.status_code in (401, 429):
            return {"rate_limited": True}
    except Exception:
        pass
    return {}


def sync_ig_profiles(creator_name: str, limit: int = 500):
    """Sync IG profiles using multiple methods."""
    import sqlalchemy
    from sqlalchemy import text

    token = get_token(creator_name)
    if not token:
        print(f"  No IG token for {creator_name}, skipping Graph API methods")

    print(f"\n{'='*60}")
    print(f"Syncing IG profiles for {creator_name}")
    print(f"{'='*60}")

    engine = sqlalchemy.create_engine(DATABASE_URL)

    # Step 1: Get conversations API username mapping
    username_map = {}
    if token:
        print("\n[1] Fetching username mapping from Conversations API...")
        username_map = fetch_ig_conversations_usernames(token, limit=limit)
        print(f"  Found {len(username_map)} username mappings")

    # Step 2: Get leads missing data
    with engine.connect() as conn:
        creator_row = conn.execute(
            text("SELECT id FROM creators WHERE name = :name"),
            {"name": creator_name}
        ).fetchone()
        if not creator_row:
            print(f"ERROR: Creator {creator_name} not found")
            return
        creator_id = str(creator_row[0])

        leads = conn.execute(
            text("""
                SELECT id, platform_user_id, username, full_name, profile_pic_url
                FROM leads
                WHERE creator_id = :cid AND platform = 'instagram'
                ORDER BY last_contact_at DESC NULLS LAST
            """),
            {"cid": creator_id}
        ).fetchall()

        print(f"\n  Total IG leads: {len(leads)}")
        missing_pic = sum(1 for l in leads if not l[4])
        missing_name = sum(1 for l in leads if not l[3])
        missing_username = sum(1 for l in leads if not l[2])
        print(f"  Missing pic: {missing_pic}")
        print(f"  Missing name: {missing_name}")
        print(f"  Missing username: {missing_username}")

        # Step 3: Update usernames from conversations API
        updated_usernames = 0
        if username_map:
            print("\n[2] Updating usernames from Conversations API...")
            for lead_id, puid, username, full_name, pic_url in leads:
                if username:
                    continue
                uid = (puid or "").replace("ig_", "")
                if uid in username_map:
                    conn.execute(
                        text("UPDATE leads SET username = :uname WHERE id = :lid"),
                        {"uname": username_map[uid], "lid": str(lead_id)}
                    )
                    updated_usernames += 1
            conn.commit()
            print(f"  Updated {updated_usernames} usernames")

        # Step 4: Fetch profiles via public IG API for leads with username but no pic
        # Re-fetch leads with updated usernames
        leads = conn.execute(
            text("""
                SELECT id, platform_user_id, username, full_name, profile_pic_url
                FROM leads
                WHERE creator_id = :cid AND platform = 'instagram'
                  AND username IS NOT NULL AND username != ''
                  AND (
                    profile_pic_url IS NULL OR profile_pic_url = ''
                    OR full_name IS NULL OR full_name = ''
                  )
                ORDER BY last_contact_at DESC NULLS LAST
                LIMIT :lim
            """),
            {"cid": creator_id, "lim": limit}
        ).fetchall()

        print(f"\n[3] Fetching profiles via public IG API for {len(leads)} leads...")
        updated_pics = 0
        updated_names = 0
        rate_limited = False

        for i, (lead_id, puid, username, full_name, pic_url) in enumerate(leads):
            if rate_limited:
                break

            result = fetch_public_ig_profile(username)
            if result.get("rate_limited"):
                print(f"  Rate limited at {i+1}/{len(leads)}, stopping public API")
                rate_limited = True
                break

            updates = {}
            if result.get("profile_pic") and (not pic_url or pic_url == ""):
                updates["profile_pic_url"] = result["profile_pic"]
            if result.get("full_name") and (not full_name or full_name == ""):
                updates["full_name"] = result["full_name"]

            if updates:
                set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
                updates["lid"] = str(lead_id)
                try:
                    conn.execute(
                        text(f"UPDATE leads SET {set_clauses} WHERE id = :lid"),
                        updates
                    )
                    conn.commit()
                    if "profile_pic_url" in updates:
                        updated_pics += 1
                    if "full_name" in updates:
                        updated_names += 1
                except Exception as e:
                    conn.rollback()
                    if "deadlock" in str(e).lower():
                        time.sleep(1)
                    # Skip this lead

            # Rate limit: 1 request per 2 seconds for public API
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i+1}/{len(leads)} (pics: +{updated_pics}, names: +{updated_names})")
            time.sleep(2.0)

        print(f"\n  Results:")
        print(f"    Usernames updated (from conversations): {updated_usernames}")
        print(f"    Pics updated (from public API): {updated_pics}")
        print(f"    Names updated (from public API): {updated_names}")
        if rate_limited:
            print(f"    NOTE: Rate limited — re-run later for more")


def main():
    limit = 500
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    if "--all" in sys.argv or len(sys.argv) < 2:
        creators = ["iris_bertran", "stefano_bonanno"]
    else:
        creators = [sys.argv[1]]

    for creator in creators:
        sync_ig_profiles(creator, limit=limit)

    # Print final stats
    import sqlalchemy
    from sqlalchemy import text
    engine = sqlalchemy.create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT c.name, l.platform,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE l.profile_pic_url IS NOT NULL AND l.profile_pic_url != '') as has_pic,
                COUNT(*) FILTER (WHERE l.full_name IS NOT NULL AND l.full_name != '') as has_name,
                COUNT(*) FILTER (WHERE l.username IS NOT NULL AND l.username != '') as has_username
            FROM leads l JOIN creators c ON l.creator_id = c.id
            WHERE l.platform = 'instagram'
            GROUP BY c.name, l.platform
            ORDER BY c.name
        """))
        print(f"\n{'='*60}")
        print("Final IG profile stats:")
        print(f"{'='*60}")
        for row in result:
            name, platform, total, has_pic, has_name, has_uname = row
            print(f"  {name}: {total} total, {has_pic} pics ({100*has_pic//total}%), {has_name} names ({100*has_name//total}%), {has_uname} usernames")


if __name__ == "__main__":
    main()
